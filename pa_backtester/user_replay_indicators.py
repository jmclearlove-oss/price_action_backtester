from __future__ import annotations

"""用户自定义复盘指标示例。

这个文件会被 ``pa_backtester.replay_indicators`` 自动加载。
你可以直接在这里加入自己的指标、策略信号，然后刷新网页。

函数必须返回：
    df, indicator_specs, marker_specs

- indicator_specs 用于画线；每个 spec 的 id 必须等于 df 中的列名。
- marker_specs 用于画策略信号；每个 spec 的 column 必须等于 df 中的布尔列名。
"""

import pandas as pd


def add_custom_replay_indicators(df: pd.DataFrame):
    out = df.copy()

    # 示例1：SMA 200 趋势线
    out['sma_200'] = out['close'].rolling(200).mean()

    # 示例2：Bollinger Bands
    out['bb_mid_20'] = out['close'].rolling(20).mean()
    bb_std = out['close'].rolling(20).std()
    out['bb_upper_20'] = out['bb_mid_20'] + 2 * bb_std
    out['bb_lower_20'] = out['bb_mid_20'] - 2 * bb_std

    # 示例3：自定义策略标记：收盘价上穿/下穿 SMA200
    prev_close = out['close'].shift(1)
    prev_sma = out['sma_200'].shift(1)
    out['custom_cross_up_sma_200'] = (prev_close <= prev_sma) & (out['close'] > out['sma_200'])
    out['custom_cross_down_sma_200'] = (prev_close >= prev_sma) & (out['close'] < out['sma_200'])

    indicator_specs = [
        {
            'id': 'sma_200',
            'label': 'SMA 200',
            'kind': 'line',
            'color': '#a78bfa',
            'line_width': 2,
            'default_visible': False,
            'group': 'Custom',
        },
        {
            'id': 'bb_mid_20',
            'label': 'BB Mid 20',
            'kind': 'line',
            'color': '#64748b',
            'line_width': 1,
            'default_visible': False,
            'group': 'Custom',
        },
        {
            'id': 'bb_upper_20',
            'label': 'BB Upper 20',
            'kind': 'line',
            'color': '#38bdf8',
            'line_width': 1,
            'default_visible': False,
            'group': 'Custom',
        },
        {
            'id': 'bb_lower_20',
            'label': 'BB Lower 20',
            'kind': 'line',
            'color': '#38bdf8',
            'line_width': 1,
            'default_visible': False,
            'group': 'Custom',
        },
    ]

    marker_specs = [
        {
            'id': 'custom_cross_up_sma_200',
            'label': '上穿 SMA200',
            'column': 'custom_cross_up_sma_200',
            'position': 'belowBar',
            'shape': 'arrowUp',
            'color': '#a78bfa',
            'text': 'SMA↑',
            'default_visible': False,
            'group': 'Custom Strategy',
        },
        {
            'id': 'custom_cross_down_sma_200',
            'label': '下穿 SMA200',
            'column': 'custom_cross_down_sma_200',
            'position': 'aboveBar',
            'shape': 'arrowDown',
            'color': '#a78bfa',
            'text': 'SMA↓',
            'default_visible': False,
            'group': 'Custom Strategy',
        },
    ]

    return out, indicator_specs, marker_specs
