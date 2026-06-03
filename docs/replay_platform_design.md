# 加密货币 K 线复盘平台设计文档

## 1. 产品目标

建设一个面向交易员的历史行情复盘网站，核心能力是让用户选择交易对、周期和开始时间，然后像视频一样逐根播放历史 K 线，并在播放过程中进行模拟做多、做空、平仓和复盘记录。

第一阶段目标不是复制完整 TradingView，而是先跑通最小闭环：

```text
选择复盘参数 -> 加载历史上下文 -> 播放 K 线 -> 模拟交易 -> 查看复盘结果
```

## 2. 推荐技术栈

### 2.1 前端

推荐：

- Next.js / React
- TypeScript
- TradingView Lightweight Charts
- Zustand
- Tailwind CSS + shadcn/ui

理由：

- React/Next.js 独立开发效率高，生态成熟。
- Lightweight Charts 适合 K 线、成交量、价格线、标记点等交易图表场景。
- Zustand 足够管理播放状态、K线缓存、订单、持仓、笔记。

MVP 可以先使用静态 HTML + JavaScript 快速验证交互，后续再迁移到 Next.js。

### 2.2 后端

推荐：

- MVP：FastAPI + Python
- 异步任务：Celery / RQ
- 缓存：Redis
- 数据导入任务：独立 worker

理由：

- 当前工程已经是 Python，后端继续用 Python 可以复用现有数据处理、指标、回测模块。
- FastAPI 适合快速开发 JSON API。
- 后续可以把回测、复盘评分、数据导入、重采样放入后台 worker。

### 2.3 数据库

推荐分阶段：

| 阶段 | K线数据库 | 业务数据库 |
| --- | --- | --- |
| MVP | PostgreSQL / TimescaleDB | PostgreSQL |
| 数据量增长 | ClickHouse | PostgreSQL |
| 成熟阶段 | ClickHouse + Redis 热缓存 | PostgreSQL |

业务数据包括：

- 用户
- 复盘会话
- 模拟订单
- 持仓
- 笔记
- 复盘报告

K线数据包括：

- exchange
- symbol
- timeframe
- timestamp
- open
- high
- low
- close
- volume

## 3. 总体架构

MVP 架构：

```text
浏览器
  |
  | HTTP
  v
FastAPI
  |
  | CSV / TimescaleDB
  v
K线数据源
```

规模化架构：

```text
Next.js
  |
  v
FastAPI API Gateway
  |
  +--> PostgreSQL：用户、复盘、订单、笔记
  |
  +--> ClickHouse：海量 K线查询
  |
  +--> Redis：热门数据块、session 状态
  |
  +--> Worker：数据导入、重采样、缺口检查、复盘报告生成
```

## 4. 核心业务流程

### 4.1 创建复盘会话

用户选择：

- 交易所
- 交易对
- 周期
- 开始时间
- 历史上下文 K线数量
- 首次加载播放 K线数量

前端请求：

```http
POST /api/replay/sessions
```

示例：

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "start_time": "2023-01-10T00:00:00Z",
  "context_bars": 200,
  "chunk_size": 500
}
```

后端处理：

1. 校验交易对、周期、开始时间。
2. 查询开始时间之前的 `context_bars` 根 K线。
3. 查询开始时间之后的 `chunk_size` 根 K线。
4. 创建 replay session。
5. 返回 session id、上下文数据和播放缓存。

### 4.2 前端播放

前端维护：

- `visibleCandles`：已经显示在图表上的 K线
- `bufferCandles`：后续待播放 K线
- `currentCursor`：当前播放到的 K线时间
- `playStatus`：播放 / 暂停
- `speed`：播放速度
- `position`：当前模拟持仓
- `trades`：已完成交易

播放逻辑：

```text
点击播放
  |
  v
定时器启动
  |
  v
从 bufferCandles 取一根
  |
  v
chart.update(candle)
  |
  v
更新当前价格、浮盈浮亏、订单状态
  |
  v
buffer 剩余过少时预取下一块
```

### 4.3 分块预取

前端不应该每播放一根 K线就请求后端。合理方式是分块预取：

```http
GET /api/replay/sessions/{session_id}/candles?cursor=2023-01-20T00:00:00Z&limit=500
```

后端返回 cursor 之后的下一批 K线。

### 4.4 模拟交易

MVP 支持：

- 做多
- 做空
- 平仓
- 当前持仓
- 已完成交易
- 已实现盈亏

后续扩展：

- 限价单
- 止损单
- 止盈单
- 拖拽修改止损止盈
- 手续费、滑点、杠杆、保证金
- 后端复算交易结果

## 5. API 设计

### 5.1 健康检查

```http
GET /api/health
```

### 5.2 数据目录

```http
GET /api/replay/catalog
```

返回当前可用交易对、周期和数据起止时间。

### 5.3 创建会话

```http
POST /api/replay/sessions
```

返回：

```json
{
  "session_id": "rep_xxx",
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "cursor": "2023-01-20T00:00:00Z",
  "context": [],
  "playback": []
}
```

### 5.4 获取下一块 K线

```http
GET /api/replay/sessions/{session_id}/candles?cursor=...&limit=500
```

### 5.5 提交模拟交易动作

```http
POST /api/replay/sessions/{session_id}/orders
```

请求：

```json
{
  "action": "open_long",
  "price": 42100.5,
  "timestamp": "2024-01-01T12:00:00Z",
  "qty": 1
}
```

动作包括：

- `open_long`
- `open_short`
- `close`

## 6. 数据库表结构建议

### 6.1 candles

```sql
CREATE TABLE candles (
  exchange TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  open DOUBLE PRECISION NOT NULL,
  high DOUBLE PRECISION NOT NULL,
  low DOUBLE PRECISION NOT NULL,
  close DOUBLE PRECISION NOT NULL,
  volume DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (symbol, timeframe, timestamp)
);
```

TimescaleDB：

```sql
SELECT create_hypertable('candles', 'timestamp');
CREATE INDEX idx_candles_symbol_tf_time ON candles(symbol, timeframe, timestamp DESC);
```

ClickHouse：

```sql
CREATE TABLE candles (
  exchange LowCardinality(String),
  symbol LowCardinality(String),
  timeframe LowCardinality(String),
  timestamp DateTime64(3, 'UTC'),
  open Float64,
  high Float64,
  low Float64,
  close Float64,
  volume Float64
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (symbol, timeframe, timestamp);
```

### 6.2 replay_sessions

```sql
CREATE TABLE replay_sessions (
  id UUID PRIMARY KEY,
  user_id UUID,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  start_time TIMESTAMPTZ NOT NULL,
  current_time TIMESTAMPTZ,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.3 replay_trades

```sql
CREATE TABLE replay_trades (
  id UUID PRIMARY KEY,
  session_id UUID NOT NULL,
  side TEXT NOT NULL,
  entry_time TIMESTAMPTZ NOT NULL,
  exit_time TIMESTAMPTZ,
  entry_price DOUBLE PRECISION NOT NULL,
  exit_price DOUBLE PRECISION,
  qty DOUBLE PRECISION NOT NULL,
  pnl DOUBLE PRECISION,
  status TEXT NOT NULL
);
```

## 7. MVP 范围

第一阶段只做：

1. K线 CSV 导入或读取。
2. 复盘参数选择。
3. 图表展示历史上下文。
4. 播放 / 暂停 / 下一根 / 速度控制。
5. 分块预取。
6. 市价做多、做空、平仓。
7. 交易记录和简单 PnL。

第一阶段暂不做：

- 多用户权限系统
- AI 评分
- 复杂画线
- 多人同步复盘
- 真实交易所下单
- Tick 级撮合
- 排行榜

## 8. 当前代码落地方式

本仓库新增一个 MVP 版本：

```text
pa_backtester/replay.py      # 复盘数据切片、session、模拟订单
pa_backtester/replay_api.py  # FastAPI 接口和静态页面
pa_backtester/web/           # 单页前端
```

运行方式：

```bash
pip install -r requirements.txt
uvicorn pa_backtester.replay_api:app --reload
```

浏览器访问：

```text
http://127.0.0.1:8000
```

