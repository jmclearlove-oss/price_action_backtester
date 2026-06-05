from __future__ import annotations

import time
from pathlib import Path
import pandas as pd


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if 'timestamp' not in df.columns and 'open_time' in df.columns:
        df = df.rename(columns={'open_time': 'timestamp'})

    expected = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f'Missing columns: {missing}. Required columns: {expected}')
    out = df[expected].copy()
    numeric_ts = pd.to_numeric(out['timestamp'], errors='coerce')
    if numeric_ts.notna().all():
        unit = 'ms' if numeric_ts.max() > 10_000_000_000 else 's'
        out['timestamp'] = pd.to_datetime(numeric_ts, unit=unit, utc=True)
    else:
        out['timestamp'] = pd.to_datetime(out['timestamp'], utc=True)
    out = out.sort_values('timestamp').drop_duplicates('timestamp')
    out = out.set_index('timestamp')
    for c in ['open', 'high', 'low', 'close', 'volume']:
        out[c] = pd.to_numeric(out[c], errors='coerce')
    return out.dropna()


def load_csv(path: str | Path) -> pd.DataFrame:
    return normalize_ohlcv(pd.read_csv(path))


def save_ohlcv_csv(df: pd.DataFrame, path: str | Path) -> None:
    out = df.reset_index()
    out.to_csv(path, index=False, encoding='utf-8-sig')


def fetch_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: str,
    since: str,
    limit: int = 1500,
    proxy: str | None = None,
) -> pd.DataFrame:
    import ccxt

    exchange_cls = getattr(ccxt, exchange_id)
    exchange_options = {'enableRateLimit': True}
    if proxy:
        exchange_options['proxies'] = {'http': proxy, 'https': proxy}
    exchange = exchange_cls(exchange_options)
    since_ms = exchange.parse8601(since)
    rows = []
    while len(rows) < limit:
        batch_limit = min(1000, limit - len(rows))
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=batch_limit)
        if not batch:
            break
        rows.extend(batch)
        since_ms = batch[-1][0] + 1
        time.sleep(exchange.rateLimit / 1000)
        if len(batch) < batch_limit:
            break
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    return normalize_ohlcv(df)


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    rule = timeframe.replace('m', 'min').replace('h', 'h').replace('d', 'D')
    out = df.resample(rule, label='right', closed='left').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()
    return out
