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
