from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


@dataclass
class StrategyConfig:
    ema_fast: int = 20
    ema_slow: int = 50
    swing_lookback: int = 4
    breakout_lookback: int = 30
    volume_window: int = 20
    volume_spike_multiplier: float = 1.25
    min_body_ratio: float = 0.45
    pinbar_wick_ratio: float = 2.0
    require_structure_alignment: bool = True


@dataclass
class AppConfig:
    symbol: str = 'BTC/USDT'
    exchange: str = 'binance'
    proxy: str | None = None
    timeframe: str = '1h'
    higher_timeframes: list[str] = field(default_factory=lambda: ['4h', '1d'])
    since: str = '2023-01-01T00:00:00Z'
    limit: int = 1500
    initial_cash: float = 10000.0
    fee_rate: float = 0.0006
    slippage_rate: float = 0.0002
    risk_per_trade: float = 0.01
    atr_period: int = 14
    atr_stop_multiplier: float = 1.8
    take_profit_r_multiple: float = 2.5
    min_rr: float = 1.5
    use_multitimeframe_confirmation: bool = True
    plot_enabled: bool = True
    export_trades_csv: bool = True
    output_dir: str = 'outputs'
    strategy: StrategyConfig = field(default_factory=StrategyConfig)


def _merge_dataclass(cls, data: dict[str, Any]):
    base = cls()
    for key, value in data.items():
        if hasattr(base, key):
            setattr(base, key, value)
    return base


def load_config(path: str | Path) -> AppConfig:
    with open(path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f) or {}
    strategy_raw = raw.pop('strategy', {}) or {}
    cfg = _merge_dataclass(AppConfig, raw)
    cfg.strategy = _merge_dataclass(StrategyConfig, strategy_raw)
    return cfg
