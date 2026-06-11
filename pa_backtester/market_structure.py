from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_OHLC_COLUMNS = ('high', 'low', 'close')
STRUCTURE_COLUMNS = [
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
]


def _missing_columns(df: pd.DataFrame, required: tuple[str, ...] = REQUIRED_OHLC_COLUMNS) -> list[str]:
    return [col for col in required if col not in df.columns]


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR as a simple moving average of True Range.

    The returned series preserves the input index. Empty data returns an empty
    float series. Missing OHLC columns raise a clear ValueError instead of a
    pandas KeyError.
    """

    missing = _missing_columns(df)
    if missing:
        raise ValueError(f'Missing columns for ATR calculation: {missing}')
    if df.empty:
        return pd.Series(dtype='float64', index=df.index, name='atr')

    period = max(int(period), 1)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(period).mean().rename('atr')


def _effective_atr(df: pd.DataFrame, atr_period: int) -> pd.Series:
    atr = calculate_atr(df, atr_period)
    high_low = (df['high'] - df['low']).abs()
    fallback = high_low.expanding(min_periods=1).mean()
    return atr.fillna(fallback).replace(0, np.nan).ffill().bfill().fillna(0.0)


def _empty_swings(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        columns=['type', 'price', 'candidate_index', 'candidate_pos', 'confirmation_pos'],
        index=pd.Index([], name=df.index.name),
    )


def detect_atr_zigzag_swings(
    df: pd.DataFrame,
    atr_period: int = 14,
    atr_multiplier: float = 2.0,
    min_bars_between_swings: int = 3,
) -> pd.DataFrame:
    """Detect confirmed structure swings with an ATR-adaptive ZigZag.

    During an upswing the highest high remains the candidate Swing High. A
    retracement larger than ``ATR * atr_multiplier`` confirms that candidate.
    During a downswing the same process is mirrored for candidate Swing Lows.

    Swing events are indexed by confirmation bar, while ``candidate_index`` and
    ``price`` point back to the candle that made the actual extreme.
    """

    missing = _missing_columns(df)
    if missing:
        raise ValueError(f'Missing columns for market structure detection: {missing}')
    if df.empty:
        return _empty_swings(df)

    min_gap = max(int(min_bars_between_swings), 1)
    multiplier = max(float(atr_multiplier), 0.0)
    atr_values = _effective_atr(df, atr_period).to_numpy(dtype=float)
    highs = df['high'].to_numpy(dtype=float)
    lows = df['low'].to_numpy(dtype=float)

    direction: str | None = None
    candidate_high = highs[0]
    candidate_high_pos = 0
    candidate_low = lows[0]
    candidate_low_pos = 0
    last_confirmation_pos = -min_gap
    records: list[dict[str, object]] = []

    def threshold_at(pos: int) -> float:
        threshold = atr_values[pos] * multiplier
        if not np.isfinite(threshold) or threshold <= 0:
            threshold = abs(highs[pos] - lows[pos]) * multiplier
        return float(threshold)

    def can_confirm(candidate_pos: int, confirmation_pos: int) -> bool:
        return (
            confirmation_pos - candidate_pos >= min_gap
            and confirmation_pos - last_confirmation_pos >= min_gap
        )

    def add_swing(kind: str, price: float, candidate_pos: int, confirmation_pos: int) -> None:
        records.append({
            'type': kind,
            'price': float(price),
            'candidate_index': df.index[candidate_pos],
            'candidate_pos': int(candidate_pos),
            'confirmation_pos': int(confirmation_pos),
        })

    for pos in range(1, len(df)):
        threshold = threshold_at(pos)

        if direction is None:
            if highs[pos] >= candidate_high:
                candidate_high = highs[pos]
                candidate_high_pos = pos
            if lows[pos] <= candidate_low:
                candidate_low = lows[pos]
                candidate_low_pos = pos

            if highs[pos] - candidate_low >= threshold and can_confirm(candidate_low_pos, pos):
                add_swing('L', candidate_low, candidate_low_pos, pos)
                last_confirmation_pos = pos
                direction = 'up'
                candidate_high = highs[pos]
                candidate_high_pos = pos
            elif candidate_high - lows[pos] >= threshold and can_confirm(candidate_high_pos, pos):
                add_swing('H', candidate_high, candidate_high_pos, pos)
                last_confirmation_pos = pos
                direction = 'down'
                candidate_low = lows[pos]
                candidate_low_pos = pos
            continue

        if direction == 'up':
            if highs[pos] >= candidate_high:
                candidate_high = highs[pos]
                candidate_high_pos = pos
            if candidate_high - lows[pos] >= threshold and can_confirm(candidate_high_pos, pos):
                add_swing('H', candidate_high, candidate_high_pos, pos)
                last_confirmation_pos = pos
                direction = 'down'
                candidate_low = lows[pos]
                candidate_low_pos = pos
        else:
            if lows[pos] <= candidate_low:
                candidate_low = lows[pos]
                candidate_low_pos = pos
            if highs[pos] - candidate_low >= threshold and can_confirm(candidate_low_pos, pos):
                add_swing('L', candidate_low, candidate_low_pos, pos)
                last_confirmation_pos = pos
                direction = 'up'
                candidate_high = highs[pos]
                candidate_high_pos = pos

    if not records:
        return _empty_swings(df)
    return pd.DataFrame.from_records(records, index=[df.index[r['confirmation_pos']] for r in records])


def label_market_structure(swings: pd.DataFrame) -> pd.DataFrame:
    """Label swings as H/L for first extremes, then HH/LH and HL/LL."""

    if swings.empty:
        out = swings.copy()
        out['label'] = pd.Series(dtype='object')
        return out

    out = swings.copy()
    labels: list[str] = []
    last_high: float | None = None
    last_low: float | None = None

    for _, swing in out.iterrows():
        price = float(swing['price'])
        if swing['type'] == 'H':
            if last_high is None:
                labels.append('H')
            else:
                labels.append('HH' if price > last_high else 'LH')
            last_high = price
        else:
            if last_low is None:
                labels.append('L')
            else:
                labels.append('HL' if price > last_low else 'LL')
            last_low = price

    out['label'] = labels
    return out


def detect_trend_state(labeled_swings: pd.DataFrame, lookback: int = 4) -> pd.Series:
    """Infer UPTREND, DOWNTREND, or RANGE from recent labeled swings."""

    if labeled_swings.empty:
        return pd.Series(dtype='object', index=labeled_swings.index, name='trend_state')

    lookback = max(int(lookback), 2)
    states: list[str] = []
    labels = labeled_swings['label'].astype(str).tolist()

    for pos in range(len(labels)):
        recent = labels[max(0, pos - lookback + 1):pos + 1]
        bull = 'HH' in recent and 'HL' in recent
        bear = 'LL' in recent and 'LH' in recent
        if bull and bear:
            latest_bull = max(i for i, label in enumerate(recent) if label in {'HH', 'HL'})
            latest_bear = max(i for i, label in enumerate(recent) if label in {'LL', 'LH'})
            states.append('UPTREND' if latest_bull > latest_bear else 'DOWNTREND')
        elif bull:
            states.append('UPTREND')
        elif bear:
            states.append('DOWNTREND')
        else:
            states.append('RANGE')

    return pd.Series(states, index=labeled_swings.index, name='trend_state')


def detect_bos_choch(
    df: pd.DataFrame,
    labeled_swings: pd.DataFrame,
    trend_state: pd.Series,
) -> pd.DataFrame:
    """Detect break of structure and change of character from close crosses."""

    out = pd.DataFrame(index=df.index)
    for col in ['bos_up', 'bos_down', 'choch_up', 'choch_down']:
        out[col] = False
    if df.empty or labeled_swings.empty:
        return out

    swing_high_price = pd.Series(np.nan, index=df.index, dtype='float64')
    swing_low_price = pd.Series(np.nan, index=df.index, dtype='float64')
    high_swings = labeled_swings[labeled_swings['type'] == 'H']
    low_swings = labeled_swings[labeled_swings['type'] == 'L']
    swing_high_price.loc[high_swings.index] = high_swings['price'].to_numpy(dtype=float)
    swing_low_price.loc[low_swings.index] = low_swings['price'].to_numpy(dtype=float)

    ref_high = swing_high_price.ffill().shift()
    ref_low = swing_low_price.ffill().shift()
    close = df['close']
    prev_close = close.shift()
    crossed_up = close.gt(ref_high) & prev_close.le(ref_high)
    crossed_down = close.lt(ref_low) & prev_close.ge(ref_low)

    state = trend_state.reindex(df.index).ffill().fillna('RANGE')
    previous_state = state.shift().fillna('RANGE')
    out['choch_up'] = crossed_up & previous_state.eq('DOWNTREND')
    out['choch_down'] = crossed_down & previous_state.eq('UPTREND')
    out['bos_up'] = crossed_up & ~out['choch_up']
    out['bos_down'] = crossed_down & ~out['choch_down']
    return out


def add_market_structure_features(
    df: pd.DataFrame,
    atr_period: int = 14,
    atr_multiplier: float = 2.0,
    min_bars_between_swings: int = 3,
    trend_lookback: int = 4,
) -> pd.DataFrame:
    """Append ATR ZigZag market-structure features to an OHLCV DataFrame."""

    missing = _missing_columns(df)
    if missing:
        raise ValueError(f'Missing columns for market structure features: {missing}')

    out = df.copy()
    out['atr'] = calculate_atr(out, atr_period)
    out['swing_high'] = False
    out['swing_low'] = False
    out['swing_label'] = pd.Series(pd.NA, index=out.index, dtype='object')
    out['swing_high_price'] = np.nan
    out['swing_low_price'] = np.nan
    if out.empty:
        out['last_swing_high'] = np.nan
        out['last_swing_low'] = np.nan
        out['market_structure'] = pd.Series(dtype='object', index=out.index)
        out['trend_state'] = pd.Series(dtype='object', index=out.index)
        for col in ['bos_up', 'bos_down', 'choch_up', 'choch_down']:
            out[col] = pd.Series(dtype='bool', index=out.index)
        for col in ['higher_high', 'lower_high', 'higher_low', 'lower_low']:
            out[col] = pd.Series(dtype='bool', index=out.index)
        out['structure_score'] = pd.Series(dtype='int64', index=out.index)
        out['structure_bias'] = pd.Series(dtype='int64', index=out.index)
        return out

    swings = detect_atr_zigzag_swings(out, atr_period, atr_multiplier, min_bars_between_swings)
    labeled_swings = label_market_structure(swings)
    trend_at_swings = detect_trend_state(labeled_swings, trend_lookback)

    if not labeled_swings.empty:
        high_swings = labeled_swings[labeled_swings['type'] == 'H']
        low_swings = labeled_swings[labeled_swings['type'] == 'L']
        out.loc[high_swings.index, 'swing_high'] = True
        out.loc[low_swings.index, 'swing_low'] = True
        out.loc[high_swings.index, 'swing_high_price'] = high_swings['price'].to_numpy(dtype=float)
        out.loc[low_swings.index, 'swing_low_price'] = low_swings['price'].to_numpy(dtype=float)
        out.loc[labeled_swings.index, 'swing_label'] = labeled_swings['label'].astype(str).to_numpy()

    if labeled_swings.empty:
        out['last_swing_high'] = np.nan
        out['last_swing_low'] = np.nan
        out['market_structure'] = 'RANGE'
        out['trend_state'] = 'RANGE'
    else:
        out['last_swing_high'] = out['swing_high_price'].ffill()
        out['last_swing_low'] = out['swing_low_price'].ffill()
        market_structure = out['swing_label'].ffill()
        out['market_structure'] = market_structure.mask(market_structure.isna(), 'RANGE')
        trend_series = trend_at_swings.reindex(out.index).ffill()
        out['trend_state'] = trend_series.mask(trend_series.isna(), 'RANGE')

    events = detect_bos_choch(out, labeled_swings, out['trend_state'])
    for col in ['bos_up', 'bos_down', 'choch_up', 'choch_down']:
        out[col] = events[col].fillna(False).astype(bool)

    out['higher_high'] = out['swing_label'].eq('HH')
    out['lower_high'] = out['swing_label'].eq('LH')
    out['higher_low'] = out['swing_label'].eq('HL')
    out['lower_low'] = out['swing_label'].eq('LL')
    out['structure_score'] = 0
    out.loc[out['higher_high'] | out['higher_low'], 'structure_score'] = 1
    out.loc[out['lower_high'] | out['lower_low'], 'structure_score'] = -1
    out['structure_bias'] = out['trend_state'].map({'UPTREND': 1, 'DOWNTREND': -1}).fillna(0).astype(int)
    return out
