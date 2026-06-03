from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pandas as pd

from .data import load_csv


OrderAction = Literal['open_long', 'open_short', 'close']
TradeSide = Literal['long', 'short']


@dataclass
class Candle:
    timestamp: str
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class ReplayTrade:
    id: str
    side: TradeSide
    entry_time: str
    entry_price: float
    qty: float
    exit_time: str | None = None
    exit_price: float | None = None
    pnl: float | None = None
    status: Literal['open', 'closed'] = 'open'


@dataclass
class ReplaySession:
    id: str
    symbol: str
    timeframe: str
    start_time: str
    current_time: str | None
    position: ReplayTrade | None = None
    trades: list[ReplayTrade] = field(default_factory=list)


class CandleStore:
    def __init__(self, csv_path: str | Path = 'sample_data/sample_ohlcv.csv'):
        self.csv_path = Path(csv_path)
        self.df = load_csv(self.csv_path)

    def catalog(self) -> dict:
        return {
            'symbols': ['BTCUSDT'],
            'timeframes': ['1h'],
            'rows': int(len(self.df)),
            'start_time': self.df.index.min().isoformat(),
            'end_time': self.df.index.max().isoformat(),
            'source': str(self.csv_path),
        }

    def context_before(self, start_time: str, limit: int) -> list[Candle]:
        ts = pd.to_datetime(start_time, utc=True)
        data = self.df[self.df.index < ts].tail(max(limit, 0))
        return self._to_candles(data)

    def chunk_from(self, start_time: str, limit: int) -> list[Candle]:
        ts = pd.to_datetime(start_time, utc=True)
        data = self.df[self.df.index >= ts].head(max(limit, 0))
        return self._to_candles(data)

    def chunk_after(self, cursor: str, limit: int) -> list[Candle]:
        ts = pd.to_datetime(cursor, utc=True)
        data = self.df[self.df.index > ts].head(max(limit, 0))
        return self._to_candles(data)

    def _to_candles(self, df: pd.DataFrame) -> list[Candle]:
        candles: list[Candle] = []
        for ts, row in df.iterrows():
            candles.append(Candle(
                timestamp=ts.isoformat(),
                time=int(ts.timestamp()),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
            ))
        return candles


class ReplayService:
    def __init__(self, store: CandleStore):
        self.store = store
        self.sessions: dict[str, ReplaySession] = {}

    def create_session(
        self,
        symbol: str,
        timeframe: str,
        start_time: str,
        context_bars: int = 200,
        chunk_size: int = 500,
    ) -> dict:
        context = self.store.context_before(start_time, context_bars)
        playback = self.store.chunk_from(start_time, chunk_size)
        cursor = playback[-1].timestamp if playback else start_time
        session = ReplaySession(
            id=f'rep_{uuid4().hex}',
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            current_time=context[-1].timestamp if context else None,
        )
        self.sessions[session.id] = session
        return {
            'session_id': session.id,
            'symbol': symbol,
            'timeframe': timeframe,
            'start_time': start_time,
            'cursor': cursor,
            'context': [asdict(c) for c in context],
            'playback': [asdict(c) for c in playback],
            'session': self.session_snapshot(session.id),
        }

    def get_chunk(self, session_id: str, cursor: str, limit: int = 500) -> dict:
        session = self._session(session_id)
        candles = self.store.chunk_after(cursor, limit)
        next_cursor = candles[-1].timestamp if candles else cursor
        session.current_time = next_cursor
        return {
            'session_id': session_id,
            'cursor': next_cursor,
            'candles': [asdict(c) for c in candles],
        }

    def submit_order(
        self,
        session_id: str,
        action: OrderAction,
        price: float,
        timestamp: str,
        qty: float = 1.0,
    ) -> dict:
        session = self._session(session_id)
        if action in ('open_long', 'open_short'):
            if session.position is not None:
                raise ValueError('A position is already open. Close it before opening a new one.')
            side: TradeSide = 'long' if action == 'open_long' else 'short'
            trade = ReplayTrade(
                id=f'trd_{uuid4().hex}',
                side=side,
                entry_time=timestamp,
                entry_price=float(price),
                qty=float(qty),
            )
            session.position = trade
            session.trades.append(trade)
        elif action == 'close':
            if session.position is None:
                raise ValueError('No open position to close.')
            trade = session.position
            trade.exit_time = timestamp
            trade.exit_price = float(price)
            trade.pnl = self._pnl(trade.side, trade.entry_price, trade.exit_price, trade.qty)
            trade.status = 'closed'
            session.position = None
        else:
            raise ValueError(f'Unsupported order action: {action}')
        session.current_time = timestamp
        return self.session_snapshot(session_id)

    def session_snapshot(self, session_id: str) -> dict:
        session = self._session(session_id)
        return {
            'id': session.id,
            'symbol': session.symbol,
            'timeframe': session.timeframe,
            'start_time': session.start_time,
            'current_time': session.current_time,
            'position': asdict(session.position) if session.position else None,
            'trades': [asdict(t) for t in session.trades],
            'realized_pnl': round(sum(t.pnl or 0.0 for t in session.trades if t.status == 'closed'), 8),
        }

    def _session(self, session_id: str) -> ReplaySession:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise KeyError(f'Replay session not found: {session_id}') from exc

    @staticmethod
    def _pnl(side: TradeSide, entry: float, exit_price: float, qty: float) -> float:
        if side == 'long':
            return round((exit_price - entry) * qty, 8)
        return round((entry - exit_price) * qty, 8)

