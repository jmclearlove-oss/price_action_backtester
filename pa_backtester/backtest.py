from __future__ import annotations

from dataclasses import dataclass, asdict
import math
import pandas as pd


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    side: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    qty: float
    gross_pnl: float
    fees: float
    net_pnl: float
    r_multiple: float
    exit_reason: str
    equity_after: float


class Backtester:
    def __init__(self, cfg):
        self.cfg = cfg
        self.cash = float(cfg.initial_cash)
        self.equity_curve: list[dict] = []
        self.trades: list[Trade] = []

    def _size_position(self, entry: float, stop: float) -> float:
        risk_cash = self.cash * self.cfg.risk_per_trade
        risk_per_unit = abs(entry - stop)
        if risk_per_unit <= 0 or math.isnan(risk_per_unit):
            return 0.0
        return risk_cash / risk_per_unit

    @staticmethod
    def _valid_price(value) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    def run(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        position = None
        pending_signal = None
        for ts, row in df.iterrows():
            price = float(row['close'])
            self.equity_curve.append({'timestamp': ts, 'equity': self.cash})
            if pd.isna(row.get('atr')):
                continue

            if position is None and pending_signal is not None:
                atr = float(row['atr'])
                if pending_signal == 'long':
                    entry = float(row['open']) * (1 + self.cfg.slippage_rate)
                    atr_stop = entry - atr * self.cfg.atr_stop_multiplier
                    swing_stop = self._valid_price(row.get('last_swing_low'))
                    stop = min(swing_stop if swing_stop is not None else atr_stop, atr_stop)
                    target = entry + (entry - stop) * self.cfg.take_profit_r_multiple
                    qty = self._size_position(entry, stop)
                    if qty > 0:
                        position = {'side': 'long', 'entry_time': ts, 'entry': entry, 'stop': stop, 'target': target, 'qty': qty, 'risk_cash': self.cash * self.cfg.risk_per_trade}
                elif pending_signal == 'short':
                    entry = float(row['open']) * (1 - self.cfg.slippage_rate)
                    atr_stop = entry + atr * self.cfg.atr_stop_multiplier
                    swing_stop = self._valid_price(row.get('last_swing_high'))
                    stop = max(swing_stop if swing_stop is not None else atr_stop, atr_stop)
                    target = entry - (stop - entry) * self.cfg.take_profit_r_multiple
                    qty = self._size_position(entry, stop)
                    if qty > 0:
                        position = {'side': 'short', 'entry_time': ts, 'entry': entry, 'stop': stop, 'target': target, 'qty': qty, 'risk_cash': self.cash * self.cfg.risk_per_trade}
                pending_signal = None

            if position is not None:
                exit_price = None
                reason = ''
                if position['side'] == 'long':
                    if row['low'] <= position['stop']:
                        exit_price = position['stop'] * (1 - self.cfg.slippage_rate)
                        reason = 'stop_loss'
                    elif row['high'] >= position['target']:
                        exit_price = position['target'] * (1 - self.cfg.slippage_rate)
                        reason = 'take_profit'
                    elif bool(row.get('short_signal', False)):
                        exit_price = price * (1 - self.cfg.slippage_rate)
                        reason = 'opposite_signal'
                else:
                    if row['high'] >= position['stop']:
                        exit_price = position['stop'] * (1 + self.cfg.slippage_rate)
                        reason = 'stop_loss'
                    elif row['low'] <= position['target']:
                        exit_price = position['target'] * (1 + self.cfg.slippage_rate)
                        reason = 'take_profit'
                    elif bool(row.get('long_signal', False)):
                        exit_price = price * (1 + self.cfg.slippage_rate)
                        reason = 'opposite_signal'

                if exit_price is not None:
                    qty = position['qty']
                    if position['side'] == 'long':
                        gross = (exit_price - position['entry']) * qty
                    else:
                        gross = (position['entry'] - exit_price) * qty
                    fees = (position['entry'] * qty + exit_price * qty) * self.cfg.fee_rate
                    net = gross - fees
                    self.cash += net
                    r_mult = net / position['risk_cash'] if position['risk_cash'] else 0.0
                    self.trades.append(Trade(
                        entry_time=str(position['entry_time']), exit_time=str(ts), side=position['side'],
                        entry_price=position['entry'], exit_price=exit_price, stop_loss=position['stop'],
                        take_profit=position['target'], qty=qty, gross_pnl=gross, fees=fees,
                        net_pnl=net, r_multiple=r_mult, exit_reason=reason, equity_after=self.cash,
                    ))
                    position = None
                    self.equity_curve[-1]['equity'] = self.cash

            if position is None and pending_signal is None:
                if bool(row.get('long_signal', False)):
                    pending_signal = 'long'
                elif bool(row.get('short_signal', False)):
                    pending_signal = 'short'

        trades_df = pd.DataFrame([asdict(t) for t in self.trades])
        equity_df = pd.DataFrame(self.equity_curve).drop_duplicates('timestamp').set_index('timestamp')
        metrics = self.metrics(trades_df, equity_df)
        return trades_df, equity_df, metrics

    def metrics(self, trades: pd.DataFrame, equity: pd.DataFrame) -> dict:
        if trades.empty:
            return {'total_trades': 0, 'final_equity': self.cash, 'return_pct': (self.cash / self.cfg.initial_cash - 1) * 100}
        wins = trades[trades['net_pnl'] > 0]
        losses = trades[trades['net_pnl'] <= 0]
        peak = equity['equity'].cummax()
        dd = equity['equity'] / peak - 1
        profit_factor = wins['net_pnl'].sum() / abs(losses['net_pnl'].sum()) if not losses.empty and losses['net_pnl'].sum() != 0 else float('inf')
        return {
            'total_trades': int(len(trades)),
            'win_rate_pct': float(round(len(wins) / len(trades) * 100, 2)),
            'profit_factor': float(round(profit_factor, 3)) if profit_factor != float('inf') else 'inf',
            'avg_r': float(round(trades['r_multiple'].mean(), 3)),
            'max_drawdown_pct': float(round(dd.min() * 100, 2)),
            'final_equity': round(float(equity['equity'].iloc[-1]), 2),
            'return_pct': round((float(equity['equity'].iloc[-1]) / self.cfg.initial_cash - 1) * 100, 2),
            'total_net_pnl': round(float(trades['net_pnl'].sum()), 2),
        }
