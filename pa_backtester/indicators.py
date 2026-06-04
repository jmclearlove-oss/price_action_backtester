from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


FIB_EXTENSION_RATIOS: tuple[float, ...] = (
    1.272,
    1.414,
    1.618,
    2.000,
    2.240,
    2.618,
    3.000,
    3.618,
    4.236,
    5.000,
    6.854,
    13.090,
)


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


def calculate_fibonacci_extensions(
    df: pd.DataFrame,
    pivot_high_col: str = 'pivot_high',
    pivot_low_col: str = 'pivot_low',
    prefix: str = 'fib_ext',
    ratios: tuple[float, ...] | list[float] = FIB_EXTENSION_RATIOS,
) -> pd.DataFrame:
    """基于最近一组 pivot swing 追加 12 个机构常用斐波那契扩展位。

    默认输出列覆盖完整 12 个扩展比例：1.272, 1.414, 1.618, 2.000, 2.240,
    2.618, 3.000, 3.618, 4.236, 5.000, 6.854, 13.090。

    计算逻辑：
    - 最近结构是 pivot low -> pivot high：视为上行 impulse，扩展目标为
      low + (high - low) * ratio，用于多头止盈和向上突破参考。
    - 最近结构是 pivot high -> pivot low：视为下行 impulse，扩展目标为
      high - (high - low) * ratio，用于空头止盈和向下突破参考。

    注意：本函数是否存在未来函数，取决于输入的 pivot_high / pivot_low 是否已经
    做了确认延迟。如果直接使用需要右侧 K 线确认的 pivot，请在确认完成后再暴露。
    """
    missing = [col for col in (pivot_high_col, pivot_low_col) if col not in df.columns]
    if missing:
        raise ValueError(f'Missing pivot columns: {missing}. Run calculate_adaptive_pivots first or provide pivot columns.')

    out = df
    high_pivots = out[pivot_high_col].astype(float)
    low_pivots = out[pivot_low_col].astype(float)
    row_no = pd.Series(np.arange(len(out), dtype=float), index=out.index)

    last_high = high_pivots.ffill()
    last_low = low_pivots.ffill()
    last_high_row = row_no.where(high_pivots.notna()).ffill()
    last_low_row = row_no.where(low_pivots.notna()).ffill()

    has_leg = last_high.notna() & last_low.notna()
    bullish_leg = has_leg & (last_low_row < last_high_row)
    bearish_leg = has_leg & (last_high_row < last_low_row)
    leg_range = (last_high - last_low).abs()

    out[f'{prefix}_direction'] = np.select(
        [bullish_leg.to_numpy(), bearish_leg.to_numpy()],
        [1, -1],
        default=0,
    )
    out[f'{prefix}_range'] = leg_range.where(has_leg)

    for ratio in ratios:
        label = f'{ratio:.3f}'.replace('.', '_')
        col = f'{prefix}_{label}'
        bullish_target = last_low + leg_range * ratio
        bearish_target = last_high - leg_range * ratio
        out[col] = np.select(
            [bullish_leg.to_numpy(), bearish_leg.to_numpy()],
            [bullish_target.to_numpy(), bearish_target.to_numpy()],
            default=np.nan,
        )

    return out


def score_trendline(
    df: pd.DataFrame,
    line_params: dict,
    threshold_pct: float = 0.0005,
    side: str = 'support',
) -> tuple[float, dict]:
    """对单条趋势线进行精细化评分。

    参数：
    - df: 至少包含 high / low 的 K 线 DataFrame。
    - line_params: {'slope': k, 'intercept': b, 'start_idx': x1, 'end_idx': x2}
    - threshold_pct: 触碰容差率，默认 0.05%。
    - side: 'support' 使用 low 评分，'resistance' 使用 high 评分。

    分数含义：
    - 触碰次数越多，趋势线越重要；
    - 跨度越长，越接近大级别结构；
    - 触碰偏差越小，线越精准；
    - 最近仍被触碰，时效性越强。
    """
    missing = [col for col in ('high', 'low') if col not in df.columns]
    if missing:
        raise ValueError(f'Missing columns: {missing}. Required columns: high, low')
    if side not in ('support', 'resistance'):
        raise ValueError("side must be 'support' or 'resistance'")

    k = float(line_params['slope'])
    b = float(line_params['intercept'])
    x1 = int(line_params['start_idx'])
    x2 = int(line_params['end_idx'])
    total_bars = len(df)
    if total_bars == 0 or x1 < 0 or x2 <= x1 or x1 >= total_bars:
        raise ValueError('Invalid line_params index range')

    line_length = x2 - x1
    touch_count = 0
    deviations: list[float] = []
    last_touch_idx = x2

    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)

    for idx in range(x1, total_bars):
        line_price = k * idx + b
        if line_price <= 0 or np.isnan(line_price):
            continue

        if side == 'support':
            price = low[idx]
            pct_diff = abs(price - line_price) / line_price
            if idx > x2 and price < line_price * (1 - threshold_pct * 2):
                break
        else:
            price = high[idx]
            pct_diff = abs(price - line_price) / line_price
            if idx > x2 and price > line_price * (1 + threshold_pct * 2):
                break

        if pct_diff <= threshold_pct:
            touch_count += 1
            deviations.append(float(pct_diff))
            last_touch_idx = idx

    s_touch = min(max(40 + (touch_count - 2) * 15, 0), 100)
    s_length = min((line_length / 50) * 100, 100)
    avg_dev = float(np.mean(deviations)) if deviations else threshold_pct
    s_mse = max(0, 100 * (1 - (avg_dev / threshold_pct)))
    bars_ago = total_bars - 1 - last_touch_idx
    s_recency = max(0, 100 * (1 - (bars_ago / 100)))
    total_score = (s_touch * 0.5) + (s_length * 0.2) + (s_mse * 0.2) + (s_recency * 0.1)

    report_data = {
        'total_score': round(total_score, 1),
        'side': side,
        'touch_count': touch_count,
        'line_length': line_length,
        'avg_deviation_pct': round(avg_dev * 100, 4),
        'bars_ago': bars_ago,
    }
    return total_score, report_data
