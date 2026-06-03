from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

np.random.seed(7)
rows = 1000
idx = pd.date_range('2023-01-01', periods=rows, freq='h', tz='UTC')
trend = np.linspace(0, 25, rows)
cycle = np.sin(np.arange(rows) / 35) * 8
noise = np.random.normal(0, 2.0, rows).cumsum() * 0.15
close = 100 + trend + cycle + noise
open_ = np.r_[close[0], close[:-1]] + np.random.normal(0, 0.35, rows)
high = np.maximum(open_, close) + np.random.uniform(0.2, 1.8, rows)
low = np.minimum(open_, close) - np.random.uniform(0.2, 1.8, rows)
volume = np.random.lognormal(mean=8, sigma=0.35, size=rows)

df = pd.DataFrame({
    'timestamp': idx,
    'open': open_,
    'high': high,
    'low': low,
    'close': close,
    'volume': volume,
})
Path('sample_data').mkdir(exist_ok=True)
df.to_csv('sample_data/sample_ohlcv.csv', index=False)
print('sample_data/sample_ohlcv.csv created')
