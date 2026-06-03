from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def candle_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['body'] = (out['close'] - out['open']).abs()
    out['range'] = (out['high'] - out['low']).replace(0, np.nan)
    out['upper_wick'] = out['high'] - out[['open', 'close']].max(axis=1)
    out['lower_wick'] = out[['open', 'close']].min(axis=1) - out['low']
    out['body_ratio'] = out['body'] / out['range']
    out['is_bull'] = out['close'] > out['open']
    out['is_bear'] = out['close'] < out['open']
    return out


def add_base_indicators(df: pd.DataFrame, ema_fast: int, ema_slow: int, atr_period: int, volume_window: int) -> pd.DataFrame:
    out = candle_features(df)
    out['ema_fast'] = ema(out['close'], ema_fast)
    out['ema_slow'] = ema(out['close'], ema_slow)
    out['atr'] = atr(out, atr_period)
    out['vol_ma'] = out['volume'].rolling(volume_window).mean()
    return out
