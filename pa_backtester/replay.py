from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4
import csv
import json
import math
import re
from collections import defaultdict

import pandas as pd

from .data import load_csv
from .replay_indicators import build_replay_features


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
    indicators: dict[str, float] = field(default_factory=dict)
    signals: dict[str, bool] = field(default_factory=dict)


@dataclass
class ReplayTrade:
    id: str
    side: TradeSide
    entry_time: str
    entry_price: float
    qty: float
    entry_fee: float = 0.0
    exit_time: str | None = None
    exit_price: float | None = None
    exit_fee: float = 0.0
    gross_pnl: float | None = None
    net_pnl: float | None = None
    pnl: float | None = None
    return_pct: float | None = None
    status: Literal['open', 'closed'] = 'open'
    note: str = ''


@dataclass
class ReplaySession:
    id: str
    symbol: str
    timeframe: str
    start_time: str
    current_time: str | None
    initial_cash: float = 10000.0
    cash: float = 10000.0
    fee_rate: float = 0.0006
    slippage_rate: float = 0.0002
    position: ReplayTrade | None = None
    trades: list[ReplayTrade] = field(default_factory=list)


class CandleStore:
    """CSV K线数据仓库。

    默认读取 sample_data/sample_ohlcv.csv，同时会扫描 data/*.csv、
    sample_data/*.csv，以及 binance_data/<symbol>/<timeframe>/*.csv。
    Binance 月度文件会按同一 symbol/timeframe 合并成一个数据集，并在
    catalog 中暴露缺失月份信息。
    """

    indicator_value_columns = {
        'ema_fast',
        'ema_slow',
        'range_high',
        'range_low',
        'last_swing_high',
        'last_swing_low',
        'atr',
        'vol_ma',
    }
    signal_columns = {
        'long_signal',
        'short_signal',
        'volume_spike',
        'breakout_up',
        'breakout_down',
        'false_break_up',
        'false_break_down',
    }

    def __init__(self, csv_path: str | Path = 'sample_data/sample_ohlcv.csv'):
        self.default_csv_path = Path(csv_path)
        self.datasets = self._discover_datasets()
        self.dataset_id = self._first_dataset_id()
        self.source = self.datasets[self.dataset_id]['source']
        self.df = self._load_dataset(self.dataset_id)
        self.indicator_specs: list[dict[str, Any]] = []
        self.signal_marker_specs: list[dict[str, Any]] = []
        self.df = self._with_features(self.df)

    def catalog(self) -> dict:
        active = self.datasets[self.dataset_id]
        return {
            'active_dataset': self.dataset_id,
            'datasets': list(self.datasets.values()),
            'symbols': sorted({d['symbol'] for d in self.datasets.values()}),
            'timeframes': sorted({d['timeframe'] for d in self.datasets.values()}),
            'rows': int(len(self.df)),
            'start_time': self.df.index.min().isoformat(),
            'end_time': self.df.index.max().isoformat(),
            'source': str(active['source']),
            'missing_months': active.get('missing_months', []),
            'indicator_specs': self.indicator_specs,
            'signal_marker_specs': self.signal_marker_specs,
        }

    def select_dataset(self, symbol: str | None = None, timeframe: str | None = None, dataset_id: str | None = None) -> None:
        target = dataset_id
        if target is None:
            normalized_symbol = self._normalize_symbol(symbol or '')
            normalized_timeframe = timeframe or ''
            for key, item in self.datasets.items():
                if self._normalize_symbol(item['symbol']) == normalized_symbol and item['timeframe'] == normalized_timeframe:
                    target = key
                    break
        if target is None or target not in self.datasets:
            available = ', '.join(f"{d['symbol']} {d['timeframe']}" for d in self.datasets.values())
            raise ValueError(f'Dataset not found for {symbol} {timeframe}. Available: {available}')
        if target != self.dataset_id:
            self.dataset_id = target
            self.source = self.datasets[target]['source']
            self.df = self._with_features(self._load_dataset(target))

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

    def _discover_datasets(self) -> dict[str, dict[str, Any]]:
        candidates: list[Path] = []
        for folder in (Path('sample_data'), Path('data')):
            if folder.exists():
                candidates.extend(sorted(folder.glob('*.csv')))
        if self.default_csv_path.exists() and self.default_csv_path not in candidates:
            candidates.insert(0, self.default_csv_path)

        datasets: dict[str, dict[str, Any]] = {}
        for path in candidates:
            try:
                df = load_csv(path)
            except Exception:
                continue
            if df.empty:
                continue
            symbol, timeframe = self._infer_symbol_timeframe(path)
            dataset_id = f'{self._safe_id(symbol)}_{self._safe_id(timeframe)}_{len(datasets) + 1}'
            datasets[dataset_id] = {
                'id': dataset_id,
                'symbol': symbol,
                'timeframe': timeframe,
                'rows': int(len(df)),
                'start_time': df.index.min().isoformat(),
                'end_time': df.index.max().isoformat(),
                'source': str(path),
                'source_type': 'csv',
                'months': [],
                'missing_months': [],
            }
        for item in self._discover_binance_datasets():
            dataset_id = f"{self._safe_id(item['symbol'])}_{self._safe_id(item['timeframe'])}_binance_{len(datasets) + 1}"
            datasets[dataset_id] = {'id': dataset_id, **item}
        if not datasets:
            raise FileNotFoundError('No OHLCV CSV found. Put CSV files in sample_data/, data/, or binance_data/.')
        return datasets

    def _first_dataset_id(self) -> str:
        for key, item in self.datasets.items():
            if Path(item['source']) == self.default_csv_path:
                return key
        return next(iter(self.datasets))

    def _load_dataset(self, dataset_id: str) -> pd.DataFrame:
        dataset = self.datasets[dataset_id]
        sources = dataset.get('sources')
        if sources:
            frames = [load_csv(path) for path in sources]
            return pd.concat(frames).sort_index().loc[lambda df: ~df.index.duplicated(keep='last')]
        return load_csv(dataset['source'])

    def _with_features(self, df: pd.DataFrame) -> pd.DataFrame:
        features, indicator_specs, signal_marker_specs = build_replay_features(df)
        self.indicator_specs = indicator_specs
        self.signal_marker_specs = signal_marker_specs
        for spec in indicator_specs:
            self.indicator_value_columns.add(spec['id'])
        for spec in signal_marker_specs:
            self.signal_columns.add(spec['column'])
        return features

    def _to_candles(self, df: pd.DataFrame) -> list[Candle]:
        candles: list[Candle] = []
        for ts, row in df.iterrows():
            indicators: dict[str, float] = {}
            for col in self.indicator_value_columns:
                if col in row.index:
                    value = row[col]
                    if _is_finite_number(value):
                        indicators[col] = float(value)

            signals: dict[str, bool] = {}
            for col in self.signal_columns:
                if col in row.index:
                    value = row[col]
                    if isinstance(value, (bool, int, float)) and bool(value) and not pd.isna(value):
                        signals[col] = True

            candles.append(Candle(
                timestamp=ts.isoformat(),
                time=int(ts.timestamp()),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
                indicators=indicators,
                signals=signals,
            ))
        return candles

    @staticmethod
    def _infer_symbol_timeframe(path: Path) -> tuple[str, str]:
        stem = path.stem
        monthly = CandleStore._parse_binance_month_file(path)
        if monthly is not None:
            return monthly[0], monthly[1]
        match = re.search(r'([A-Z0-9]+USDT|[A-Z0-9]+USD|[A-Z0-9]+BTC|[A-Z0-9]+ETH)[_-]([0-9]+[mhdwM])$', stem, re.IGNORECASE)
        if match:
            return match.group(1).upper(), match.group(2)
        if stem == 'sample_ohlcv':
            return 'BTCUSDT', '1h'
        parts = stem.split('_')
        if len(parts) >= 2:
            return parts[-2].upper(), parts[-1]
        return stem.upper(), '1h'

    def _discover_binance_datasets(self) -> list[dict[str, Any]]:
        root = Path('binance_data')
        if not root.exists():
            return []

        grouped: dict[tuple[str, str], list[tuple[Path, str]]] = defaultdict(list)
        for path in sorted(root.glob('*/*/*.csv')):
            parsed = self._parse_binance_month_file(path)
            if parsed is None:
                continue
            symbol, timeframe, month = parsed
            grouped[(symbol, timeframe)].append((path, month))

        datasets: list[dict[str, Any]] = []
        for (symbol, timeframe), files in sorted(grouped.items()):
            frames: list[pd.DataFrame] = []
            sources: list[str] = []
            months: list[str] = []
            for path, month in sorted(files, key=lambda item: item[1]):
                try:
                    df = load_csv(path)
                except Exception:
                    continue
                if df.empty:
                    continue
                frames.append(df)
                sources.append(str(path))
                months.append(month)
            if not frames:
                continue

            merged = pd.concat(frames).sort_index().loc[lambda df: ~df.index.duplicated(keep='last')]
            missing_months = self._missing_months(months)
            datasets.append({
                'symbol': symbol,
                'timeframe': timeframe,
                'rows': int(len(merged)),
                'start_time': merged.index.min().isoformat(),
                'end_time': merged.index.max().isoformat(),
                'source': f'binance_data/{symbol}/{timeframe}',
                'sources': sources,
                'source_type': 'binance_data',
                'file_count': len(sources),
                'months': months,
                'missing_months': missing_months,
            })
        return datasets

    @staticmethod
    def _parse_binance_month_file(path: Path) -> tuple[str, str, str] | None:
        match = re.match(
            r'(?P<symbol>[A-Z0-9]+)[_-](?P<timeframe>[0-9]+[mhdwM])[-_](?P<year>\d{4})[-_](?P<month>\d{2})$',
            path.stem,
            re.IGNORECASE,
        )
        if match is None:
            return None
        symbol = match.group('symbol').upper()
        timeframe = match.group('timeframe')
        month = f"{match.group('year')}-{match.group('month')}"
        return symbol, timeframe, month

    @staticmethod
    def _missing_months(months: list[str]) -> list[str]:
        if not months:
            return []
        periods = sorted({pd.Period(month, freq='M') for month in months})
        expected = pd.period_range(periods[0], periods[-1], freq='M')
        available = set(periods)
        return [str(month) for month in expected if month not in available]

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.replace('/', '').replace('-', '').replace('_', '').upper()

    @staticmethod
    def _safe_id(value: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_-]+', '', value.replace('/', '')).strip('_') or 'dataset'


class ReplayJournal:
    def __init__(self, root: str | Path = 'outputs/replay_sessions'):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, session: ReplaySession) -> None:
        folder = self.root / session.id
        folder.mkdir(parents=True, exist_ok=True)
        payload = asdict(session)
        (folder / 'session.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self.write_trades_csv(session, folder / 'trades.csv')

    def write_trades_csv(self, session: ReplaySession, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            'id', 'side', 'status', 'entry_time', 'exit_time', 'entry_price', 'exit_price',
            'qty', 'entry_fee', 'exit_fee', 'gross_pnl', 'net_pnl', 'pnl', 'return_pct', 'note',
        ]
        with path.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for trade in session.trades:
                row = asdict(trade)
                writer.writerow({key: row.get(key) for key in fields})
        return path

    def trades_csv_path(self, session_id: str) -> Path:
        return self.root / session_id / 'trades.csv'


class ReplayService:
    def __init__(self, store: CandleStore):
        self.store = store
        self.sessions: dict[str, ReplaySession] = {}
        self.journal = ReplayJournal()

    def create_session(
        self,
        symbol: str,
        timeframe: str,
        start_time: str,
        context_bars: int = 200,
        chunk_size: int = 500,
        initial_cash: float = 10000.0,
        fee_rate: float = 0.0006,
        slippage_rate: float = 0.0002,
        dataset_id: str | None = None,
    ) -> dict:
        self.store.select_dataset(symbol=symbol, timeframe=timeframe, dataset_id=dataset_id)
        context = self.store.context_before(start_time, context_bars)
        playback = self.store.chunk_from(start_time, chunk_size)
        cursor = playback[-1].timestamp if playback else start_time
        active = self.store.datasets[self.store.dataset_id]
        session = ReplaySession(
            id=f'rep_{uuid4().hex}',
            symbol=active['symbol'],
            timeframe=active['timeframe'],
            start_time=start_time,
            current_time=context[-1].timestamp if context else None,
            initial_cash=float(initial_cash),
            cash=float(initial_cash),
            fee_rate=float(fee_rate),
            slippage_rate=float(slippage_rate),
        )
        self.sessions[session.id] = session
        self.journal.save(session)
        return {
            'session_id': session.id,
            'symbol': active['symbol'],
            'timeframe': active['timeframe'],
            'dataset_id': self.store.dataset_id,
            'start_time': start_time,
            'cursor': cursor,
            'context': [asdict(c) for c in context],
            'playback': [asdict(c) for c in playback],
            'indicator_specs': self.store.indicator_specs,
            'signal_marker_specs': self.store.signal_marker_specs,
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
        note: str = '',
    ) -> dict:
        session = self._session(session_id)
        mark_price = float(price)
        qty = float(qty)
        if qty <= 0:
            raise ValueError('qty must be greater than 0.')

        if action in ('open_long', 'open_short'):
            if session.position is not None:
                raise ValueError('A position is already open. Close it before opening a new one.')
            side: TradeSide = 'long' if action == 'open_long' else 'short'
            entry_price = self._fill_price(side, 'entry', mark_price, session.slippage_rate)
            entry_fee = entry_price * qty * session.fee_rate
            trade = ReplayTrade(
                id=f'trd_{uuid4().hex}',
                side=side,
                entry_time=timestamp,
                entry_price=round(entry_price, 8),
                qty=qty,
                entry_fee=round(entry_fee, 8),
                note=note,
            )
            session.position = trade
            session.trades.append(trade)
        elif action == 'close':
            if session.position is None:
                raise ValueError('No open position to close.')
            trade = session.position
            exit_price = self._fill_price(trade.side, 'exit', mark_price, session.slippage_rate)
            exit_fee = exit_price * trade.qty * session.fee_rate
            gross = self._gross_pnl(trade.side, trade.entry_price, exit_price, trade.qty)
            net = gross - trade.entry_fee - exit_fee
            trade.exit_time = timestamp
            trade.exit_price = round(exit_price, 8)
            trade.exit_fee = round(exit_fee, 8)
            trade.gross_pnl = round(gross, 8)
            trade.net_pnl = round(net, 8)
            trade.pnl = trade.net_pnl
            notional = trade.entry_price * trade.qty
            trade.return_pct = round((net / notional) * 100, 4) if notional else 0.0
            trade.status = 'closed'
            session.cash = round(session.cash + net, 8)
            session.position = None
        else:
            raise ValueError(f'Unsupported order action: {action}')
        session.current_time = timestamp
        self.journal.save(session)
        return self.session_snapshot(session_id, mark_price=mark_price)

    def session_snapshot(self, session_id: str, mark_price: float | None = None) -> dict:
        session = self._session(session_id)
        realized = round(sum(t.net_pnl or 0.0 for t in session.trades if t.status == 'closed'), 8)
        unrealized = 0.0
        if session.position and mark_price is not None:
            gross = self._gross_pnl(session.position.side, session.position.entry_price, mark_price, session.position.qty)
            estimated_exit_fee = mark_price * session.position.qty * session.fee_rate
            unrealized = gross - session.position.entry_fee - estimated_exit_fee
        return {
            'id': session.id,
            'symbol': session.symbol,
            'timeframe': session.timeframe,
            'start_time': session.start_time,
            'current_time': session.current_time,
            'initial_cash': session.initial_cash,
            'cash': session.cash,
            'fee_rate': session.fee_rate,
            'slippage_rate': session.slippage_rate,
            'position': asdict(session.position) if session.position else None,
            'trades': [asdict(t) for t in session.trades],
            'realized_pnl': realized,
            'unrealized_pnl': round(unrealized, 8),
            'equity': round(session.cash + unrealized, 8),
        }

    def export_trades_csv(self, session_id: str) -> Path:
        session = self._session(session_id)
        path = self.journal.trades_csv_path(session_id)
        self.journal.write_trades_csv(session, path)
        return path

    def _session(self, session_id: str) -> ReplaySession:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise KeyError(f'Replay session not found: {session_id}') from exc

    @staticmethod
    def _fill_price(side: TradeSide, phase: Literal['entry', 'exit'], price: float, slippage_rate: float) -> float:
        if side == 'long':
            return price * (1 + slippage_rate) if phase == 'entry' else price * (1 - slippage_rate)
        return price * (1 - slippage_rate) if phase == 'entry' else price * (1 + slippage_rate)

    @staticmethod
    def _gross_pnl(side: TradeSide, entry: float, exit_price: float, qty: float) -> float:
        if side == 'long':
            return (exit_price - entry) * qty
        return (entry - exit_price) * qty


def _is_finite_number(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)
