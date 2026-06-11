from __future__ import annotations

import pandas as pd

from pa_backtester.range_market import add_mean_reversion_features, add_range_market_features


def make_range_df() -> pd.DataFrame:
    closes = [100, 101, 100.5, 99.5, 98.6, 98.2, 98.0, 98.4, 99.0, 100.0, 101.2, 101.8]
    index = pd.date_range('2024-01-01', periods=len(closes), freq='15min')
    return pd.DataFrame({
        'timestamp': index,
        'close': closes,
        'trend_state': ['RANGE'] * len(closes),
        'bos_up': [False] * len(closes),
        'bos_down': [False] * len(closes),
        'last_swing_high': [102.0] * len(closes),
        'last_swing_low': [98.0] * len(closes),
        'atr': [0.5] * len(closes),
    }, index=index)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    range_cfg = {
        'lookback': 3,
        'min_range_age_bars': 3,
        'min_range_width_pct': 0.001,
        'max_range_width_pct': 0.1,
        'atr_ma_period': 3,
        'atr_expand_multiplier': 1.2,
    }
    mr_cfg = {
        'zscore_window': 4,
        'zscore_entry_threshold': 0.5,
        'entry_zone_pct': 0.2,
        'exit_at_midline': True,
    }
    out = add_range_market_features(df, range_cfg)
    return add_mean_reversion_features(out, mr_cfg)


def test_range_market_and_mean_reversion_signals_are_generated() -> None:
    out = add_features(make_range_df())

    assert out['is_range_market'].any()
    assert out['mean_reversion_long'].any()
    assert out['mean_reversion_exit_long'].any()


def test_range_market_features_match_step_by_step_calculation() -> None:
    df = make_range_df()
    full = add_features(df)
    key_fields = [
        'is_range_market',
        'range_high',
        'range_low',
        'range_mid',
        'mean_reversion_long',
        'mean_reversion_short',
        'mean_reversion_exit_long',
        'mean_reversion_exit_short',
    ]

    for i in range(len(df)):
        step = add_features(df.iloc[:i + 1]).iloc[-1]
        for field in key_fields:
            assert full.iloc[i][field] == step[field]
