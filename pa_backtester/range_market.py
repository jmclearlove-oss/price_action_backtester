from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RangeMarketSettings:
    enabled: bool = True
    timeframe: str = '15m'
    lookback: int = 32
    min_range_age_bars: int = 16
    min_range_width_pct: float = 0.003
    max_range_width_pct: float = 0.04
    atr_ma_period: int = 96
    atr_expand_multiplier: float = 1.15


@dataclass(frozen=True)
class MeanReversionSettings:
    enabled: bool = True
    zscore_window: int = 96
    zscore_entry_threshold: float = 1.5
    entry_zone_pct: float = 0.2
    exit_at_midline: bool = True


def _setting(config: Any, key: str, default: Any) -> Any:
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _bool_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    series = df[column]
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).ne(0)
    return series.astype(str).str.lower().isin({'true', '1', 'yes', 'y', 't'})


def _time_values(df: pd.DataFrame) -> pd.Series:
    if 'timestamp' in df.columns:
        return pd.to_datetime(df['timestamp'], errors='coerce')
    return pd.Series(df.index, index=df.index)


def add_range_market_features(df: pd.DataFrame, config: Any = None) -> pd.DataFrame:
    """Add no-lookahead range-market features using current and historical data.

    The range bounds come from already-confirmed ``last_swing_high`` and
    ``last_swing_low``. The validity flags use rolling or sequential state that
    only depends on bars up to the current row.
    """

    out = df.copy()
    lookback = max(int(_setting(config, 'lookback', RangeMarketSettings.lookback)), 1)
    min_age = max(int(_setting(config, 'min_range_age_bars', RangeMarketSettings.min_range_age_bars)), 1)
    min_width = float(_setting(config, 'min_range_width_pct', RangeMarketSettings.min_range_width_pct))
    max_width = float(_setting(config, 'max_range_width_pct', RangeMarketSettings.max_range_width_pct))
    atr_ma_period = max(int(_setting(config, 'atr_ma_period', RangeMarketSettings.atr_ma_period)), 1)
    atr_expand = float(_setting(config, 'atr_expand_multiplier', RangeMarketSettings.atr_expand_multiplier))

    close = pd.to_numeric(out.get('close'), errors='coerce')
    range_high = pd.to_numeric(out.get('last_swing_high'), errors='coerce')
    range_low = pd.to_numeric(out.get('last_swing_low'), errors='coerce')
    range_width = range_high - range_low
    range_mid = (range_high + range_low) / 2
    range_width_pct = range_width / close.replace(0, np.nan)
    atr = pd.to_numeric(out.get('atr'), errors='coerce')
    atr_ma = atr.rolling(atr_ma_period, min_periods=1).mean()

    bos = _bool_series(out, 'bos_up') | _bool_series(out, 'bos_down')
    recent_bos = bos.rolling(lookback, min_periods=1).max().fillna(False).astype(bool)
    inside_range = close.lt(range_high) & close.gt(range_low)
    atr_is_calm = atr.notna() & atr_ma.notna() & atr.le(atr_ma * atr_expand)
    width_ok = range_width_pct.ge(min_width) & range_width_pct.le(max_width)
    trend_is_range = out.get('trend_state', pd.Series('RANGE', index=out.index)).astype(str).eq('RANGE')

    base_range = (
        trend_is_range
        & ~recent_bos
        & inside_range.fillna(False)
        & width_ok.fillna(False)
        & atr_is_calm.fillna(False)
    )

    ages: list[int] = []
    valid_flags: list[bool] = []
    range_ids: list[int | None] = []
    start_times: list[Any] = []
    current_age = 0
    current_range_id = 0
    active_range_id: int | None = None
    active_start_time: Any = pd.NA
    times = _time_values(out)

    for idx, is_base in zip(out.index, base_range):
        if bool(is_base):
            current_age += 1
        else:
            current_age = 0

        is_valid = current_age >= min_age
        if is_valid:
            if active_range_id is None:
                current_range_id += 1
                active_range_id = current_range_id
                start_pos = max(0, len(ages) - min_age + 1)
                active_start_time = times.iloc[start_pos]
            range_ids.append(active_range_id)
            start_times.append(active_start_time)
        else:
            active_range_id = None
            active_start_time = pd.NA
            range_ids.append(None)
            start_times.append(pd.NA)

        ages.append(current_age)
        valid_flags.append(is_valid)

    out['range_high'] = range_high
    out['range_low'] = range_low
    out['range_mid'] = range_mid
    out['range_width'] = range_width
    out['range_width_pct'] = range_width_pct
    out['range_atr_ratio'] = range_width / atr.replace(0, np.nan)
    out['recent_bos'] = recent_bos
    out['inside_range'] = inside_range.fillna(False)
    out['atr_is_calm'] = atr_is_calm.fillna(False)
    out['is_range_market'] = pd.Series(valid_flags, index=out.index, dtype='bool')
    out['range_id'] = pd.Series(range_ids, index=out.index, dtype='Int64')
    out['range_start_time'] = pd.Series(start_times, index=out.index, dtype='object')
    out['range_age_bars'] = pd.Series(ages, index=out.index, dtype='int64')
    return out


def add_mean_reversion_features(df: pd.DataFrame, config: Any = None) -> pd.DataFrame:
    """Add no-lookahead mean-reversion entries and exits inside range boxes."""

    out = df.copy()
    zscore_window = max(int(_setting(config, 'zscore_window', MeanReversionSettings.zscore_window)), 2)
    z_threshold = float(_setting(config, 'zscore_entry_threshold', MeanReversionSettings.zscore_entry_threshold))
    entry_zone_pct = float(_setting(config, 'entry_zone_pct', MeanReversionSettings.entry_zone_pct))
    exit_at_midline = bool(_setting(config, 'exit_at_midline', MeanReversionSettings.exit_at_midline))

    close = pd.to_numeric(out['close'], errors='coerce')
    range_high = pd.to_numeric(out['range_high'], errors='coerce')
    range_low = pd.to_numeric(out['range_low'], errors='coerce')
    range_mid = pd.to_numeric(out['range_mid'], errors='coerce')
    range_width = pd.to_numeric(out['range_width'], errors='coerce')
    is_range = _bool_series(out, 'is_range_market')

    rolling_mean = close.rolling(zscore_window, min_periods=max(2, zscore_window // 4)).mean()
    rolling_std = close.rolling(zscore_window, min_periods=max(2, zscore_window // 4)).std(ddof=0)
    range_zscore = (close - rolling_mean) / rolling_std.replace(0, np.nan)

    lower_entry = range_low + entry_zone_pct * range_width
    upper_entry = range_high - entry_zone_pct * range_width
    near_low = is_range & close.le(lower_entry)
    near_high = is_range & close.ge(upper_entry)

    out['range_zscore'] = range_zscore
    out['distance_to_range_high_pct'] = (range_high - close) / close.replace(0, np.nan)
    out['distance_to_range_low_pct'] = (close - range_low) / close.replace(0, np.nan)
    out['near_range_high'] = near_high.fillna(False)
    out['near_range_low'] = near_low.fillna(False)
    out['mean_reversion_long'] = (near_low & range_zscore.le(-z_threshold)).fillna(False)
    out['mean_reversion_short'] = (near_high & range_zscore.ge(z_threshold)).fillna(False)

    exit_long_flags: list[bool] = []
    exit_short_flags: list[bool] = []
    active_long = False
    active_short = False
    bos_up = _bool_series(out, 'bos_up')
    bos_down = _bool_series(out, 'bos_down')

    for i in range(len(out)):
        long_entry = bool(out['mean_reversion_long'].iloc[i])
        short_entry = bool(out['mean_reversion_short'].iloc[i])
        active_long = active_long or long_entry
        active_short = active_short or short_entry

        mid_exit_long = exit_at_midline and bool(close.iloc[i] >= range_mid.iloc[i]) if pd.notna(range_mid.iloc[i]) else False
        mid_exit_short = exit_at_midline and bool(close.iloc[i] <= range_mid.iloc[i]) if pd.notna(range_mid.iloc[i]) else False
        exit_long = active_long and (mid_exit_long or not bool(is_range.iloc[i]) or bool(bos_down.iloc[i]))
        exit_short = active_short and (mid_exit_short or not bool(is_range.iloc[i]) or bool(bos_up.iloc[i]))

        exit_long_flags.append(exit_long)
        exit_short_flags.append(exit_short)
        if exit_long:
            active_long = False
        if exit_short:
            active_short = False

    out['mean_reversion_exit_long'] = pd.Series(exit_long_flags, index=out.index, dtype='bool')
    out['mean_reversion_exit_short'] = pd.Series(exit_short_flags, index=out.index, dtype='bool')
    return out
