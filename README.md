# Price Action Backtester：价格行为学交易分析与回测工程

这是一个可直接运行的 Python 工程，用于把价格行为学框架工程化：趋势、市场结构、K线形态、支撑阻力、突破/假突破、成交量确认、多周期共振、风控仓位、回测、交易明细 CSV 和图表报告。

> 说明：该项目用于研究和回测，不构成投资建议。实盘前必须做样本外测试、手续费/滑点校准和风控验证。

## 1. 功能清单

- OHLCV 数据来源：
  - 本地 CSV
  - ccxt 从交易所拉取，例如 Binance
- 价格行为分析模块：
  - EMA 趋势过滤
  - Swing High / Swing Low
  - HH / HL / LH / LL 市场结构偏向
  - 支撑阻力区间
  - 突破与假突破
  - 吞没形态
  - Pin Bar
  - 强势收盘 K 线
  - 成交量放大确认
- 多周期共振：
  - 默认主周期 `1h`
  - 高周期 `4h`、`1d`
  - 只有高周期不逆势时才允许开仓
- 回测模块：
  - 多空双向
  - ATR 止损
  - R 倍数止盈
  - 按账户权益百分比风险定仓
  - 手续费和滑点
  - 反向信号平仓
- 输出：
  - `outputs/trades.csv` 每笔交易明细
  - `outputs/equity_curve.csv` 资金曲线
  - `outputs/features_signals.csv` 全量因子与信号
  - `outputs/metrics.json` 回测指标
  - `outputs/price_signals.png` 价格与信号图，可关闭
  - `outputs/equity_curve.png` 资金曲线图，可关闭

## 2. 安装

```bash
cd price_action_backtester
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. 快速运行：使用示例数据

```bash
python generate_sample_data.py
python run_backtest.py backtest --config config.yaml --csv sample_data/sample_ohlcv.csv
```

运行后查看：

```bash
ls outputs
cat outputs/metrics.json
```

## 4. 使用交易所真实数据

编辑 `config.yaml`：

```yaml
symbol: BTC/USDT
exchange: binance
timeframe: 1h
higher_timeframes: [4h, 1d]
since: '2023-01-01T00:00:00Z'
limit: 1500
```

然后执行：

```bash
python run_backtest.py backtest --config config.yaml
```

如果你的环境无法访问 Binance，可以先导出 CSV 后用 `--csv` 运行。

## 4.1 下载 Binance 多周期数据

可以先把交易所 K线下载为 CSV，再用于回测或复盘：

```bash
python run_backtest.py download --config config.yaml --output-dir data
```

默认会下载配置里的主周期和高周期：

```text
timeframe: 1h
higher_timeframes: [4h, 1d]
```

也可以手动指定多个时间框架：

```bash
python run_backtest.py download \
  --config config.yaml \
  --symbol BTC/USDT \
  --timeframes 1m 5m 15m 1h 4h 1d \
  --limit 2000 \
  --output-dir data
```

生成文件示例：

```text
data/binance_BTCUSDT_1m.csv
data/binance_BTCUSDT_5m.csv
data/binance_BTCUSDT_1h.csv
```

下载完成后可以用 CSV 回测：

```bash
python run_backtest.py backtest --config config.yaml --csv data/binance_BTCUSDT_1h.csv
```

## 5. CSV 格式要求

CSV 必须包含这些列：

```text
timestamp,open,high,low,close,volume
```

`timestamp` 支持 ISO 时间，例如：

```text
2023-01-01 00:00:00+00:00,100,102,99,101,12345
```

## 6. 配置说明

核心配置在 `config.yaml`：

```yaml
initial_cash: 10000       # 初始资金
fee_rate: 0.0006          # 单边手续费
slippage_rate: 0.0002     # 滑点
risk_per_trade: 0.01      # 单笔风险占权益比例
atr_period: 14            # ATR 周期
atr_stop_multiplier: 1.8  # ATR 止损倍数
take_profit_r_multiple: 2.5
plot_enabled: true        # 是否生成图表
export_trades_csv: true   # 是否导出交易明细 CSV
```

策略配置：

```yaml
strategy:
  ema_fast: 20
  ema_slow: 50
  swing_lookback: 4
  breakout_lookback: 30
  volume_window: 20
  volume_spike_multiplier: 1.25
  min_body_ratio: 0.45
  pinbar_wick_ratio: 2.0
  require_structure_alignment: true
  fibonacci_extension_ratios: [1.272, 1.414, 1.618, 2.000, 2.240, 2.618, 3.000, 3.618, 4.236, 5.000, 6.854, 13.090]
```

市场结构识别配置：

```yaml
market_structure:
  enabled: true
  atr_period: 14
  atr_multiplier: 2.0
  min_bars_between_swings: 3
  trend_lookback: 4
```

## 7. 信号逻辑概览

### 做多条件

满足以下方向：

- 当前周期趋势不为空头；
- 市场结构不明显逆势；
- 高周期不逆势；
- 出现看涨价格行为：看涨吞没、看涨 Pin Bar、强势阳线、向上突破、向下假跌破；
- 同时满足成交量放大、接近支撑、或突破确认之一。

### 做空条件

满足以下方向：

- 当前周期趋势不为多头；
- 市场结构不明显逆势；
- 高周期不逆势；
- 出现看跌价格行为：看跌吞没、看跌 Pin Bar、强势阴线、向下突破、向上假突破；
- 同时满足成交量放大、接近阻力、或突破确认之一。

## 7.1 市场结构识别 v1

第一阶段市场结构模块位于 `pa_backtester/market_structure.py`，默认已接入回测和 Web 复盘。

### ATR 自适应 ZigZag 原理

模块不再使用固定 lookback 来确认结构 swing，而是用 ATR 自适应阈值过滤噪声：

- 上涨段中持续更新候选高点；
- 当价格从候选高点回撤超过 `ATR * atr_multiplier`，确认 Swing High；
- 下跌段中持续更新候选低点；
- 当价格从候选低点反弹超过 `ATR * atr_multiplier`，确认 Swing Low；
- 高点之间比较得到 `HH` / `LH`，低点之间比较得到 `HL` / `LL`；
- 最近结构中同时出现 `HH + HL` 判为 `UPTREND`，同时出现 `LL + LH` 判为 `DOWNTREND`，否则为 `RANGE`；
- 顺势突破最近结构高/低点标记为 BOS，逆势破坏当前趋势结构标记为 CHOCH。

### 输出字段

`outputs/features_signals.csv` 会包含这些市场结构字段：

```text
atr
swing_high
swing_low
swing_label
last_swing_high
last_swing_low
market_structure
trend_state
bos_up
bos_down
choch_up
choch_down
```

字段含义：

- `swing_high` / `swing_low`：当前 K 线是否确认了有效结构高点/低点；
- `swing_label`：`H` / `L` / `HH` / `HL` / `LH` / `LL`；
- `last_swing_high` / `last_swing_low`：最近确认结构高点/低点价格；
- `market_structure`：最近一次结构标签；
- `trend_state`：`UPTREND` / `DOWNTREND` / `RANGE`；
- `bos_up` / `bos_down`：收盘价突破最近结构高点/跌破最近结构低点；
- `choch_up` / `choch_down`：下跌趋势中向上破坏结构，或上涨趋势中向下破坏结构。

### 查看方式

回测后直接打开：

```bash
outputs/features_signals.csv
```

Web 复盘端会在左侧“指标 / 策略”面板中提供：

- `Last Swing High` / `Last Swing Low` 线；
- `HH` / `HL` / `LH` / `LL` 等结构 marker；
- `BOS` / `CHOCH` marker。

运行复盘：

```bash
uvicorn pa_backtester.replay_api:app --reload
```

然后访问：

```text
http://127.0.0.1:8000
```

注意：市场结构识别 v1 只是结构标签与事件识别模块，不直接代表买卖建议。策略是否使用这些字段，还需要结合趋势、形态、波动率、成交量、风控和样本外验证。

## 7.2 BOS / CHOCH Event Study

事件研究用于回答一个更具体的问题：当 `BOS`、`CHOCH` 或策略信号出现后，未来若干根 K 线的收益分布是否真的偏向有利方向。它不是回测撮合，也不考虑止损、止盈、滑点和仓位，只统计事件发生后的前瞻收益表现。

运行：

```bash
python scripts/event_study.py \
  --csv outputs/features_signals.csv \
  --horizons 5 10 20 50 \
  --output-dir outputs
```

默认会分析这些事件：

```text
bos_up
bos_down
choch_up
choch_down
long_signal
short_signal
```

输出文件：

```text
outputs/event_study.csv
outputs/event_study_summary.json
outputs/event_study.html
```

如果当前环境没有安装 Plotly，脚本会跳过 `event_study.html`，但仍会正常输出 CSV 和 JSON。

`event_study.csv` 字段含义：

- `event`：事件列名；
- `horizon`：向后观察的 K 线数量；
- `count`：该事件在该 horizon 下拥有有效未来价格的数据点数量；
- `mean_return`：未来收益均值，计算方式为 `close.shift(-horizon) / close - 1`；
- `median_return`：未来收益中位数；
- `win_rate`：方向胜率。`bos_up` / `choch_up` / `long_signal` 未来收益大于 0 记为 win；`bos_down` / `choch_down` / `short_signal` 未来收益小于 0 记为 win；
- `max_return`：事件后的最大未来收益；
- `min_return`：事件后的最小未来收益。

判断 BOS / CHOCH 是否有统计优势时，不要只看单个 horizon 的均值。更稳妥的做法是同时观察：

- `count` 是否足够，样本太少容易偶然；
- `mean_return` 和 `median_return` 是否方向一致；
- `win_rate` 是否持续高于随机水平；
- 多个 horizon 上是否有一致性；
- 上涨事件和下跌事件是否都有相对对称的表现；
- 换不同市场、周期和样本外数据后是否仍然成立。

注意：统计优势不等于可以直接实盘交易。真正的交易系统还需要入场规则、退出规则、手续费/滑点、风控、容量、回撤约束和样本外验证。

## 8. 适合继续扩展的方向

- 增加订单块 / FVG / 流动性扫单识别；
- 增加交易时段过滤，例如只交易欧美盘；
- 增加 walk-forward 优化；
- 增加参数网格搜索；
- 增加组合级别多币种回测；
- 增加实盘扫描模式和飞书/Telegram 推送。

## 9. K线复盘网站 MVP

本仓库新增了一个复盘网站 MVP 骨架，用于验证类似 TradingView Replay 的核心闭环：

- 选择交易对、周期和开始时间；
- 后端返回开始前的历史上下文 K线和开始后的播放缓存；
- 前端逐根追加 K线，支持播放、暂停、下一根和倍速；
- 支持市价做多、做空、平仓，并展示简单 PnL。

设计文档见：

```bash
docs/replay_platform_design.md
```

运行：

```bash
pip install -r requirements.txt
uvicorn pa_backtester.replay_api:app --reload
```

然后访问：

```text
http://127.0.0.1:8000
```

## 10. 项目结构

```text
price_action_backtester/
├── config.yaml
├── docs/
│   └── replay_platform_design.md
├── generate_sample_data.py
├── requirements.txt
├── run_backtest.py
├── README.md
└── pa_backtester/
    ├── __init__.py
    ├── backtest.py
    ├── cli.py
    ├── config.py
    ├── data.py
    ├── indicators.py
    ├── price_action.py
    ├── report.py
    ├── replay.py
    ├── replay_api.py
    └── strategy.py
```

---

## 11. Web K线回放终端 v0.2：TradingView-like 复盘版

我在原来的 MVP 上补齐了更接近实战复盘的网页端能力：

- 逐根 K 线回放：播放、暂停、下一根、倍速、分块预取；
- 手动交易：开多、开空、平仓；
- 交易记录：记录 entry / exit / qty / fee / gross pnl / net pnl / return_pct / note；
- 交易持久化：每个 replay session 会写入 `outputs/replay_sessions/<session_id>/session.json` 和 `trades.csv`；
- 前端交易标记：开仓和平仓会自动画在 K 线上；
- 持仓价格线：开仓后自动显示入场价水平线；
- 指标叠加：EMA、Range High/Low、Swing High/Low；
- 策略信号叠加：已有价格行为策略的 `long_signal` / `short_signal` 会画在前端；
- 自定义指标入口：编辑 `pa_backtester/user_replay_indicators.py` 即可把你的指标和策略画到网页端。

### 11.1 启动网页端复盘

```bash
pip install -r requirements.txt
uvicorn pa_backtester.replay_api:app --reload
```

浏览器打开：

```text
http://127.0.0.1:8000
```

### 11.2 导入更多 K线数据

把 CSV 放到：

```text
sample_data/
data/
```

CSV 需要包含：

```text
timestamp,open,high,low,close,volume
```

推荐命名：

```text
data/binance_BTCUSDT_1h.csv
data/binance_ETHUSDT_15m.csv
data/binance_SOLUSDT_5m.csv
```

网页会自动扫描这些 CSV，并在 Dataset 下拉框里显示。

### 11.3 手动交易记录

网页中点击：

```text
开多 / 开空 / 平仓
```

系统会按当前播放到的 K 线收盘价成交，并计入：

```text
fee_rate
slippage_rate
qty
```

每个 session 的交易文件在：

```text
outputs/replay_sessions/<session_id>/trades.csv
```

也可以在网页点击“导出CSV”。

### 11.4 添加你的指标

编辑：

```text
pa_backtester/user_replay_indicators.py
```

示例：

```python
import pandas as pd


def add_custom_replay_indicators(df: pd.DataFrame):
    out = df.copy()
    out['sma_200'] = out['close'].rolling(200).mean()

    indicator_specs = [
        {
            'id': 'sma_200',
            'label': 'SMA 200',
            'kind': 'line',
            'color': '#a78bfa',
            'line_width': 2,
            'default_visible': True,
            'group': 'Custom',
        }
    ]

    marker_specs = []
    return out, indicator_specs, marker_specs
```

`indicator_specs` 里的 `id` 必须等于 DataFrame 里的列名。刷新网页后会自动出现在左侧“指标 / 策略”面板。

### 11.5 添加你的策略信号

同样编辑：

```text
pa_backtester/user_replay_indicators.py
```

示例：

```python
out['my_long_signal'] = (out['close'] > out['sma_200']) & (out['close'].shift(1) <= out['sma_200'].shift(1))

marker_specs = [
    {
        'id': 'my_long_signal',
        'label': '我的做多信号',
        'column': 'my_long_signal',
        'position': 'belowBar',
        'shape': 'arrowUp',
        'color': '#20b486',
        'text': 'MY LONG',
        'default_visible': True,
        'group': 'Custom Strategy',
    }
]
```

刷新网页后，这些信号会像 TradingView 策略标记一样画在 K 线上。

### 11.6 当前版本边界

这个版本是本地单用户复盘终端，不是真实交易系统：

- 不连接交易所下单；
- 不做多用户权限；
- 不做数据库持久化，只写本地 JSON / CSV；
- 手动交易按当前 K 线 close 模拟成交；
- 指标默认画在主图价格轴，RSI / MACD 这类副图指标后续建议做独立 pane。
