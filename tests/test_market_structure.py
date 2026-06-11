from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pa_backtester.market_structure import add_market_structure_features, calculate_atr


def make_ohlcv(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range('2024-01-01', periods=len(closes), freq='h')
    return pd.DataFrame({
        'open': closes,
        'high': [close + 0.5 for close in closes],
        'low': [close - 0.5 for close in closes],
        'close': closes,
        'volume': [100] * len(closes),
    }, index=index)


def add_ms(df: pd.DataFrame) -> pd.DataFrame:
    return add_market_structure_features(
        df,
        atr_period=2,
        atr_multiplier=1.0,
        min_bars_between_swings=1,
        trend_lookback=4,
    )


def test_calculate_atr_uses_true_range_rolling_mean() -> None:
    df = pd.DataFrame({
        'high': [10.0, 12.0, 13.0],
        'low': [8.0, 9.0, 11.0],
        'close': [9.0, 11.0, 12.0],
    })

    atr = calculate_atr(df, period=2)

    assert np.isnan(atr.iloc[0])
    assert atr.iloc[1] == pytest.approx(2.5)
    assert atr.iloc[2] == pytest.approx(2.5)


def test_uptrend_sample_identifies_higher_highs_and_higher_lows() -> None:
    df = make_ohlcv([10, 11, 12, 13, 14, 13, 12, 13, 15, 16, 17, 16, 15, 16, 18, 19, 20])

    out = add_ms(df)

    labels = set(out['swing_label'].dropna())
    assert {'HH', 'HL'}.issubset(labels)
    assert 'UPTREND' in set(out['trend_state'])


def test_downtrend_sample_identifies_lower_highs_and_lower_lows() -> None:
    df = make_ohlcv([22, 21, 20, 19, 18, 19, 20, 19, 17, 16, 15, 16, 17, 16, 14, 13, 12])

    out = add_ms(df)

    labels = set(out['swing_label'].dropna())
    assert {'LH', 'LL'}.issubset(labels)
    assert 'DOWNTREND' in set(out['trend_state'])


def test_breaking_recent_swing_high_sets_bos_up() -> None:
    df = make_ohlcv([10, 11, 12, 13, 14, 13, 12, 13, 15, 16, 17])

    out = add_ms(df)

    assert out['bos_up'].any()


def test_breaking_recent_swing_low_in_uptrend_sets_choch_down() -> None:
    df = make_ohlcv([10, 11, 12, 13, 14, 13, 12, 13, 15, 16, 17, 16, 15, 16, 18, 19, 20, 19, 18, 17, 16, 15, 14])

    out = add_ms(df)

    assert out['choch_down'].any()


def test_empty_and_short_data_return_expected_columns() -> None:
    empty = make_ohlcv([])
    short = make_ohlcv([10])

    empty_out = add_ms(empty)
    short_out = add_ms(short)

    for out in [empty_out, short_out]:
        for col in [
            'atr',
            'swing_high',
            'swing_low',
            'swing_label',
            'last_swing_high',
            'last_swing_low',
            'market_structure',
            'trend_state',
            'bos_up',
            'bos_down',
            'choch_up',
            'choch_down',
        ]:
            assert col in out.columns


def test_missing_columns_raise_clear_value_error() -> None:
    df = pd.DataFrame({'close': [1.0, 2.0]})

    with pytest.raises(ValueError, match='Missing columns'):
        add_market_structure_features(df)
