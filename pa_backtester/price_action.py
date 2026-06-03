from __future__ import annotations

import numpy as np
import pandas as pd


def detect_swings(df: pd.DataFrame, lookback: int = 4) -> pd.DataFrame:
    out = df.copy()
    out['swing_high'] = False
    out['swing_low'] = False
    for i in range(lookback, len(out) - lookback):
        window = out.iloc[i - lookback:i + lookback + 1]
        idx = out.index[i]
        out.loc[idx, 'swing_high'] = out.loc[idx, 'high'] == window['high'].max()
        out.loc[idx, 'swing_low'] = out.loc[idx, 'low'] == window['low'].min()
    out['last_swing_high'] = out['high'].where(out['swing_high']).ffill()
    out['last_swing_low'] = out['low'].where(out['swing_low']).ffill()
    return out


def market_structure(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    swing_high_price = out['high'].where(out['swing_high'])
    swing_low_price = out['low'].where(out['swing_low'])
    prev_swing_high = swing_high_price.ffill().shift()
    prev_swing_low = swing_low_price.ffill().shift()
    out['higher_high'] = out['swing_high'] & (out['high'] > prev_swing_high)
    out['lower_high'] = out['swing_high'] & (out['high'] < prev_swing_high)
    out['higher_low'] = out['swing_low'] & (out['low'] > prev_swing_low)
    out['lower_low'] = out['swing_low'] & (out['low'] < prev_swing_low)
    out['structure_score'] = 0
    out.loc[out['higher_high'] | out['higher_low'], 'structure_score'] = 1
    out.loc[out['lower_high'] | out['lower_low'], 'structure_score'] = -1
    out['structure_bias'] = out['structure_score'].replace(0, np.nan).ffill().fillna(0)
    return out


def detect_candle_patterns(df: pd.DataFrame, min_body_ratio: float = 0.45, pinbar_wick_ratio: float = 2.0) -> pd.DataFrame:
    out = df.copy()
    prev_open = out['open'].shift()
    prev_close = out['close'].shift()
    out['bullish_engulfing'] = (out['is_bull'] & (prev_close < prev_open) & (out['close'] > prev_open) & (out['open'] < prev_close))
    out['bearish_engulfing'] = (out['is_bear'] & (prev_close > prev_open) & (out['open'] > prev_close) & (out['close'] < prev_open))
    out['bull_pinbar'] = (out['lower_wick'] >= pinbar_wick_ratio * out['body']) & (out['upper_wick'] <= out['body'])
    out['bear_pinbar'] = (out['upper_wick'] >= pinbar_wick_ratio * out['body']) & (out['lower_wick'] <= out['body'])
    out['strong_bull_close'] = out['is_bull'] & (out['body_ratio'] >= min_body_ratio) & (out['close'] > out['high'] - out['range'] * 0.25)
    out['strong_bear_close'] = out['is_bear'] & (out['body_ratio'] >= min_body_ratio) & (out['close'] < out['low'] + out['range'] * 0.25)
    return out


def support_resistance(df: pd.DataFrame, lookback: int = 30) -> pd.DataFrame:
    out = df.copy()
    out['range_high'] = out['high'].rolling(lookback).max().shift(1)
    out['range_low'] = out['low'].rolling(lookback).min().shift(1)
    out['breakout_up'] = out['close'] > out['range_high']
    out['breakout_down'] = out['close'] < out['range_low']
    out['false_break_up'] = (out['high'] > out['range_high']) & (out['close'] < out['range_high'])
    out['false_break_down'] = (out['low'] < out['range_low']) & (out['close'] > out['range_low'])
    return out


def trend_bias(df: pd.DataFrame) -> pd.Series:
    bias = np.where((df['close'] > df['ema_fast']) & (df['ema_fast'] > df['ema_slow']), 1,
                    np.where((df['close'] < df['ema_fast']) & (df['ema_fast'] < df['ema_slow']), -1, 0))
    return pd.Series(bias, index=df.index, name='trend_bias')
