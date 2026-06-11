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
    fibonacci_extension_ratios: list[float] = field(default_factory=lambda: [
        1.272, 1.414, 1.618, 2.000, 2.240, 2.618,
        3.000, 3.618, 4.236, 5.000, 6.854, 13.090,
    ])


@dataclass
class MarketStructureConfig:
    enabled: bool = True
    atr_period: int = 14
    atr_multiplier: float = 2.0
    min_bars_between_swings: int = 3
    trend_lookback: int = 4


@dataclass
class RangeMarketConfig:
    enabled: bool = True
    timeframe: str = '15m'
    lookback: int = 32
    min_range_age_bars: int = 16
    min_range_width_pct: float = 0.003
    max_range_width_pct: float = 0.04
    atr_ma_period: int = 96
    atr_expand_multiplier: float = 1.15


@dataclass
class MeanReversionConfig:
    enabled: bool = True
    zscore_window: int = 96
    zscore_entry_threshold: float = 1.5
    entry_zone_pct: float = 0.2
    exit_at_midline: bool = True


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
    market_structure: MarketStructureConfig = field(default_factory=MarketStructureConfig)
    range_market: RangeMarketConfig = field(default_factory=RangeMarketConfig)
    mean_reversion: MeanReversionConfig = field(default_factory=MeanReversionConfig)


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
    market_structure_raw = raw.pop('market_structure', {}) or {}
    range_market_raw = raw.pop('range_market', {}) or {}
    mean_reversion_raw = raw.pop('mean_reversion', {}) or {}
    cfg = _merge_dataclass(AppConfig, raw)
    cfg.strategy = _merge_dataclass(StrategyConfig, strategy_raw)
    cfg.market_structure = _merge_dataclass(MarketStructureConfig, market_structure_raw)
    cfg.range_market = _merge_dataclass(RangeMarketConfig, range_market_raw)
    cfg.mean_reversion = _merge_dataclass(MeanReversionConfig, mean_reversion_raw)
    return cfg
