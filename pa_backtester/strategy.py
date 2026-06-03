from __future__ import annotations

import pandas as pd

from .indicators import add_base_indicators
from .price_action import detect_swings, market_structure, detect_candle_patterns, support_resistance, trend_bias
from .data import resample_ohlcv


def prepare_features(df: pd.DataFrame, cfg) -> pd.DataFrame:
    s = cfg.strategy
    out = add_base_indicators(df, s.ema_fast, s.ema_slow, cfg.atr_period, s.volume_window)
    out = detect_swings(out, s.swing_lookback)
    out = market_structure(out)
    out = detect_candle_patterns(out, s.min_body_ratio, s.pinbar_wick_ratio)
    out = support_resistance(out, s.breakout_lookback)
    out['trend_bias'] = trend_bias(out)
    out['volume_spike'] = out['volume'] > out['vol_ma'] * s.volume_spike_multiplier
    out['near_support'] = (out['close'] - out['range_low']).abs() <= out['atr'] * 0.6
    out['near_resistance'] = (out['close'] - out['range_high']).abs() <= out['atr'] * 0.6
    return out


def higher_timeframe_bias(base_df: pd.DataFrame, timeframe: str, cfg) -> pd.Series:
    htf = resample_ohlcv(base_df, timeframe)
    feats = prepare_features(htf, cfg)
    bias = feats['trend_bias'].rename(f'htf_{timeframe}_bias')
    aligned = bias.reindex(base_df.index, method='ffill').fillna(0)
    return aligned


def generate_signals(df: pd.DataFrame, cfg) -> pd.DataFrame:
    out = prepare_features(df, cfg)
    if cfg.use_multitimeframe_confirmation:
        htf_cols = []
        for tf in cfg.higher_timeframes:
            col = f'htf_{tf}_bias'
            out[col] = higher_timeframe_bias(df, tf, cfg)
            htf_cols.append(col)
        out['mtf_long_ok'] = (out[htf_cols] >= 0).all(axis=1)
        out['mtf_short_ok'] = (out[htf_cols] <= 0).all(axis=1)
    else:
        out['mtf_long_ok'] = True
        out['mtf_short_ok'] = True

    long_pattern = out['bullish_engulfing'] | out['bull_pinbar'] | out['strong_bull_close'] | out['breakout_up'] | out['false_break_down']
    short_pattern = out['bearish_engulfing'] | out['bear_pinbar'] | out['strong_bear_close'] | out['breakout_down'] | out['false_break_up']

    if cfg.strategy.require_structure_alignment:
        long_structure = out['structure_bias'] >= 0
        short_structure = out['structure_bias'] <= 0
    else:
        long_structure = True
        short_structure = True

    out['long_signal'] = (
        (out['trend_bias'] >= 0) & long_structure & out['mtf_long_ok'] &
        long_pattern & (out['volume_spike'] | out['near_support'] | out['breakout_up'])
    )
    out['short_signal'] = (
        (out['trend_bias'] <= 0) & short_structure & out['mtf_short_ok'] &
        short_pattern & (out['volume_spike'] | out['near_resistance'] | out['breakout_down'])
    )
    return out
