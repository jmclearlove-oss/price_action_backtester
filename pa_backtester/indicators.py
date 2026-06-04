from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


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


def calculate_adaptive_pivots(df: pd.DataFrame) -> pd.DataFrame:
    """基于 ATR 波动率自适应窗口检测局部高低点。

    注意：该算法需要比较候选 K 线右侧的 N_dynamic 根 K 线，因此 pivot 只有在
    右侧确认窗口走完之后才真正可知。若用于实时交易或无未来函数回测，需要把
    pivot 信号延后 N_dynamic 根 K 线再使用。
    """
    required = ['open', 'high', 'low', 'close', 'volume']
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f'Missing columns: {missing}. Required columns: {required}')

    out = df
    n_min = 3
    n_max = 20

    try:
        import pandas_ta as ta
        atr_14 = ta.atr(
            high=out['high'],
            low=out['low'],
            close=out['close'],
            length=14,
        )
    except ImportError:
        # pandas-ta 在当前 Python 环境不可用时，使用同等 True Range rolling mean
        # 公式兜底，保证函数仍然可以运行；安装 pandas-ta 后会优先走上面的实现。
        atr_14 = atr(out, 14)
    atr_ma = atr_14.rolling(200).mean()

    # ATR / ATR_MA 衡量当前波动率相对“正常波动率”的放大或收缩程度：
    # - ratio > 1：当前波动更大，窗口随之变长，减少噪声 pivot；
    # - ratio < 1：当前波动更小，窗口随之变短，提高对细小结构的敏感度；
    # - ATR 或 ATR_MA 尚未形成时，用 ratio=1，使窗口回到基础长度 5。
    ratio = (atr_14 / atr_ma).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    dynamic_lengths = np.clip(np.rint(5 * ratio.to_numpy(dtype=float)), n_min, n_max).astype(int)

    high = out['high'].to_numpy(dtype=float)
    low = out['low'].to_numpy(dtype=float)
    pivot_high = np.full(len(out), np.nan, dtype=float)
    pivot_low = np.full(len(out), np.nan, dtype=float)

    # dynamic_lengths 每根 K 线可能不同。为了避免逐行 Python 循环，这里按窗口长度分组：
    # 对同一个 N，一次性构造长度为 2N+1 的滑动窗口，再批量比较中心点是否严格高于
    # 左右两侧 N 根 high，或严格低于左右两侧 N 根 low。
    for n in np.unique(dynamic_lengths):
        if len(out) < 2 * n + 1:
            continue

        centers = np.arange(n, len(out) - n)
        same_length = dynamic_lengths[centers] == n
        if not same_length.any():
            continue

        high_windows = sliding_window_view(high, 2 * n + 1)
        low_windows = sliding_window_view(low, 2 * n + 1)

        center_high = high_windows[:, n]
        left_high_max = high_windows[:, :n].max(axis=1)
        right_high_max = high_windows[:, n + 1:].max(axis=1)
        is_pivot_high = (center_high > left_high_max) & (center_high > right_high_max)

        center_low = low_windows[:, n]
        left_low_min = low_windows[:, :n].min(axis=1)
        right_low_min = low_windows[:, n + 1:].min(axis=1)
        is_pivot_low = (center_low < left_low_min) & (center_low < right_low_min)

        target_centers = centers[same_length]
        window_rows = target_centers - n
        high_hits = target_centers[is_pivot_high[window_rows]]
        low_hits = target_centers[is_pivot_low[window_rows]]
        pivot_high[high_hits] = high[high_hits]
        pivot_low[low_hits] = low[low_hits]

    out['pivot_high'] = pivot_high
    out['pivot_low'] = pivot_low
    return out
