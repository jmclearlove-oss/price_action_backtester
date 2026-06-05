from __future__ import annotations

"""Replay indicator/strategy overlay registry.

这个文件是网页端复盘系统的指标入口。默认会把当前仓库已有的价格行为
策略特征转成前端可绘制的 line / marker。你可以在
``pa_backtester/user_replay_indicators.py`` 中添加自己的指标，避免修改核心文件。
"""

from dataclasses import dataclass, asdict
from typing import Any, Literal

import pandas as pd

from .config import AppConfig, load_config
from .strategy import generate_signals


IndicatorKind = Literal['line', 'band']
MarkerShape = Literal['arrowUp', 'arrowDown', 'circle', 'square']


@dataclass(frozen=True)
class IndicatorSpec:
    """前端线段/区域指标描述。"""

    id: str
    label: str
    kind: IndicatorKind = 'line'
    price_scale: str = 'right'
    color: str = '#dcae45'
    line_width: int = 1
    default_visible: bool = True
    group: str = 'Built-in'


@dataclass(frozen=True)
class SignalMarkerSpec:
    """前端策略信号标记描述。"""

    id: str
    label: str
    column: str
    position: Literal['aboveBar', 'belowBar']
    shape: MarkerShape
    color: str
    text: str
    default_visible: bool = True
    group: str = 'Strategy'


def load_replay_config(path: str = 'config.yaml') -> AppConfig:
    """加载复盘指标配置，失败时使用默认配置。"""

    try:
        return load_config(path)
    except Exception:
        return AppConfig()


def build_replay_features(raw: pd.DataFrame, cfg: AppConfig | None = None) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    """返回带指标/策略列的 DataFrame，以及前端可绘制的指标和标记配置。

    默认指标：
    - EMA 快慢线；
    - 最近区间高低点；
    - 价格行为策略 long_signal / short_signal 标记；
    - 成交量异动标记。

    自定义扩展：
    新建 ``pa_backtester/user_replay_indicators.py``，实现：

    ```python
    def add_custom_replay_indicators(df):
        df = df.copy()
        df['sma_200'] = df['close'].rolling(200).mean()
        specs = [{
            'id': 'sma_200',
            'label': 'SMA 200',
            'kind': 'line',
            'color': '#f59e0b',
            'line_width': 1,
            'default_visible': True,
            'group': 'Custom',
        }]
        markers = []
        return df, specs, markers
    ```
    """

    cfg = cfg or load_replay_config()
    try:
        features = generate_signals(raw, cfg)
    except Exception:
        # 如果用户的配置或高周期共振计算失败，至少保证基础K线可以回放。
        features = raw.copy()

    specs: list[IndicatorSpec] = [
        IndicatorSpec(id='ema_fast', label=f'EMA {cfg.strategy.ema_fast}', color='#22c55e', line_width=2, group='Trend'),
        IndicatorSpec(id='ema_slow', label=f'EMA {cfg.strategy.ema_slow}', color='#f59e0b', line_width=2, group='Trend'),
        IndicatorSpec(id='range_high', label=f'Range High {cfg.strategy.breakout_lookback}', color='#ef4444', line_width=1, default_visible=False, group='Price Action'),
        IndicatorSpec(id='range_low', label=f'Range Low {cfg.strategy.breakout_lookback}', color='#3b82f6', line_width=1, default_visible=False, group='Price Action'),
        IndicatorSpec(id='last_swing_high', label='Last Swing High', color='#fb7185', line_width=1, default_visible=False, group='Price Action'),
        IndicatorSpec(id='last_swing_low', label='Last Swing Low', color='#60a5fa', line_width=1, default_visible=False, group='Price Action'),
    ]

    marker_specs: list[SignalMarkerSpec] = [
        SignalMarkerSpec(
            id='long_signal',
            label='策略做多信号',
            column='long_signal',
            position='belowBar',
            shape='arrowUp',
            color='#20b486',
            text='LONG',
            group='Strategy',
        ),
        SignalMarkerSpec(
            id='short_signal',
            label='策略做空信号',
            column='short_signal',
            position='aboveBar',
            shape='arrowDown',
            color='#ef5b5b',
            text='SHORT',
            group='Strategy',
        ),
        SignalMarkerSpec(
            id='volume_spike',
            label='成交量异动',
            column='volume_spike',
            position='belowBar',
            shape='circle',
            color='#dcae45',
            text='VOL',
            default_visible=False,
            group='Volume',
        ),
    ]

    custom_specs: list[dict[str, Any]] = []
    custom_markers: list[dict[str, Any]] = []
    try:
        from .user_replay_indicators import add_custom_replay_indicators  # type: ignore
    except Exception:
        add_custom_replay_indicators = None

    if add_custom_replay_indicators is not None:
        result = add_custom_replay_indicators(features.copy())
        if isinstance(result, tuple):
            if len(result) == 3:
                features, custom_specs, custom_markers = result
            elif len(result) == 2:
                features, custom_specs = result
                custom_markers = []
            else:
                raise ValueError('add_custom_replay_indicators must return (df, specs) or (df, specs, markers)')
        else:
            features = result

    return features, [asdict(s) for s in specs] + custom_specs, [asdict(s) for s in marker_specs] + custom_markers
