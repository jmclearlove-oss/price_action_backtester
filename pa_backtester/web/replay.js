const state = {
  sessionId: null,
  cursor: null,
  visible: [],
  buffer: [],
  current: null,
  playing: false,
  timer: null,
};

const FIB_EXTENSION_RATIOS = [1.272, 1.414, 1.618, 2.0, 2.24, 2.618, 3.0, 3.618, 4.236, 5.0, 6.854, 13.09];
const FIB_BASE_RATIOS = [0, 1];
const FIB_SWING_LOOKBACK = 4;
const TRENDLINE_MIN_SCORE = 35;
const TRENDLINE_MAX_VISIBLE = 6;
const TRENDLINE_PIVOT_LIMIT = 18;

const el = {
  symbol: document.querySelector('#symbol'),
  timeframe: document.querySelector('#timeframe'),
  startTime: document.querySelector('#startTime'),
  speed: document.querySelector('#speed'),
  createSession: document.querySelector('#createSession'),
  playPause: document.querySelector('#playPause'),
  nextBar: document.querySelector('#nextBar'),
  longBtn: document.querySelector('#longBtn'),
  shortBtn: document.querySelector('#shortBtn'),
  closeBtn: document.querySelector('#closeBtn'),
  currentTime: document.querySelector('#currentTime'),
  currentPrice: document.querySelector('#currentPrice'),
  bufferCount: document.querySelector('#bufferCount'),
  realizedPnl: document.querySelector('#realizedPnl'),
  trades: document.querySelector('#trades'),
  fibEnabled: document.querySelector('#fibEnabled'),
  fibFillColor: document.querySelector('#fibFillColor'),
  fibFillOpacity: document.querySelector('#fibFillOpacity'),
  fibBorderColor: document.querySelector('#fibBorderColor'),
  fibLineColor: document.querySelector('#fibLineColor'),
  fibLineLength: document.querySelector('#fibLineLength'),
  fibLineWidth: document.querySelector('#fibLineWidth'),
  trendEnabled: document.querySelector('#trendEnabled'),
};

const chartEl = document.querySelector('#chart');
const fibOverlay = document.querySelector('#fibOverlay');
const fibCtx = fibOverlay.getContext('2d');

const chart = LightweightCharts.createChart(chartEl, {
  layout: { background: { color: '#0f141a' }, textColor: '#c8d2dc' },
  grid: { vertLines: { color: '#1d2730' }, horzLines: { color: '#1d2730' } },
  rightPriceScale: { borderColor: '#2a3540' },
  timeScale: { borderColor: '#2a3540', timeVisible: true, secondsVisible: false },
});

const candleSeries = chart.addCandlestickSeries({
  upColor: '#20b486',
  borderUpColor: '#20b486',
  wickUpColor: '#20b486',
  downColor: '#ef5b5b',
  borderDownColor: '#ef5b5b',
  wickDownColor: '#ef5b5b',
});

const volumeChart = LightweightCharts.createChart(document.querySelector('#volume'), {
  layout: { background: { color: '#0f141a' }, textColor: '#c8d2dc' },
  grid: { vertLines: { color: '#1d2730' }, horzLines: { color: '#1d2730' } },
  rightPriceScale: { borderColor: '#2a3540' },
  timeScale: { borderColor: '#2a3540', timeVisible: true, secondsVisible: false },
});

const volumeSeries = volumeChart.addHistogramSeries({
  color: '#365164',
  priceFormat: { type: 'volume' },
});

async function initCatalog() {
  const catalog = await request('/api/replay/catalog');
  const start = new Date(catalog.start_time);
  start.setUTCDate(start.getUTCDate() + 7);
  el.startTime.value = toDatetimeLocal(start);
}

async function createSession() {
  stop();
  const payload = {
    symbol: el.symbol.value,
    timeframe: el.timeframe.value,
    start_time: new Date(el.startTime.value).toISOString(),
    context_bars: 120,
    chunk_size: 300,
  };
  const data = await request('/api/replay/sessions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  state.sessionId = data.session_id;
  state.cursor = data.cursor;
  state.visible = data.context;
  state.buffer = data.playback;
  state.current = state.visible[state.visible.length - 1] || null;
  renderChart();
  updateInfo(data.session);
}

function renderChart() {
  candleSeries.setData(state.visible.map(toChartCandle));
  volumeSeries.setData(state.visible.map(toVolumeBar));
  chart.timeScale().fitContent();
  volumeChart.timeScale().fitContent();
  renderCurrent();
  drawOverlay();
}

async function nextBar() {
  if (!state.sessionId || state.buffer.length === 0) {
    await prefetch();
  }
  const candle = state.buffer.shift();
  if (!candle) {
    stop();
    return;
  }
  state.visible.push(candle);
  state.current = candle;
  state.cursor = candle.timestamp;
  candleSeries.update(toChartCandle(candle));
  volumeSeries.update(toVolumeBar(candle));
  renderCurrent();
  drawOverlay();
  if (state.buffer.length < 80) {
    prefetch();
  }
}

async function prefetch() {
  if (!state.sessionId || !state.cursor) {
    return;
  }
  const url = `/api/replay/sessions/${state.sessionId}/candles?cursor=${encodeURIComponent(state.cursor)}&limit=300`;
  const data = await request(url);
  if (data.candles.length > 0) {
    state.cursor = data.cursor;
    state.buffer.push(...data.candles);
  }
  renderCurrent();
  drawOverlay();
}

function togglePlay() {
  if (state.playing) {
    stop();
  } else {
    play();
  }
}

function play() {
  if (!state.sessionId) {
    return;
  }
  state.playing = true;
  el.playPause.textContent = 'Pause';
  clearInterval(state.timer);
  state.timer = setInterval(nextBar, Number(el.speed.value));
}

function stop() {
  state.playing = false;
  el.playPause.textContent = 'Play';
  clearInterval(state.timer);
  state.timer = null;
}

async function submitOrder(action) {
  if (!state.sessionId || !state.current) {
    return;
  }
  const snapshot = await request(`/api/replay/sessions/${state.sessionId}/orders`, {
    method: 'POST',
    body: JSON.stringify({
      action,
      price: state.current.close,
      timestamp: state.current.timestamp,
      qty: 1,
    }),
  });
  updateInfo(snapshot);
}

function updateInfo(session) {
  renderCurrent();
  if (session) {
    el.realizedPnl.textContent = formatNumber(session.realized_pnl);
    renderTrades(session.trades);
  }
}

function renderCurrent() {
  el.currentTime.textContent = state.current ? state.current.timestamp : '-';
  el.currentPrice.textContent = state.current ? formatNumber(state.current.close) : '-';
  el.bufferCount.textContent = String(state.buffer.length);
}

function drawOverlay() {
  const canvasSize = syncFibCanvasSize();
  fibCtx.clearRect(0, 0, canvasSize.width, canvasSize.height);
  drawFibBox(canvasSize);
  drawScoredTrendlines(canvasSize);
}

function drawFibBox(canvasSize) {
  if (!el.fibEnabled.checked || state.visible.length < FIB_SWING_LOOKBACK * 2 + 1) {
    return;
  }

  const swing = latestConfirmedSwingLeg(state.visible, FIB_SWING_LOOKBACK);
  if (!swing) {
    return;
  }

  const x1 = chart.timeScale().timeToCoordinate(swing.start.time);
  const x2 = chart.timeScale().timeToCoordinate(swing.end.time);
  const yHigh = candleSeries.priceToCoordinate(Math.max(swing.start.price, swing.end.price));
  const yLow = candleSeries.priceToCoordinate(Math.min(swing.start.price, swing.end.price));
  if ([x1, x2, yHigh, yLow].some((value) => value === null || Number.isNaN(value))) {
    return;
  }

  const left = Math.min(x1, x2);
  const right = Math.max(x1, x2);
  const top = Math.min(yHigh, yLow);
  const bottom = Math.max(yHigh, yLow);
  const fillOpacity = clamp(Number(el.fibFillOpacity.value), 0, 0.35);
  const borderColor = el.fibBorderColor.value;
  const lineColor = el.fibLineColor.value;
  const lineLengthBars = clamp(Number(el.fibLineLength.value), 2, 80);
  const lineWidth = clamp(Number(el.fibLineWidth.value), 1, 8);
  const barSpacing = Math.max(chart.timeScale().options().barSpacing || 6, 1);
  const shortLineLength = lineLengthBars * barSpacing;

  fibCtx.save();
  fibCtx.fillStyle = hexToRgba(el.fibFillColor.value, fillOpacity);
  fibCtx.strokeStyle = borderColor;
  fibCtx.lineWidth = 1;
  fibCtx.fillRect(left, top, Math.max(right - left, 1), Math.max(bottom - top, 1));
  fibCtx.strokeRect(left + 0.5, top + 0.5, Math.max(right - left, 1), Math.max(bottom - top, 1));

  fibCtx.strokeStyle = lineColor;
  fibCtx.lineWidth = lineWidth;
  fibCtx.setLineDash([]);
  fibCtx.lineCap = 'butt';
  for (const level of fibLevelsForSwing(swing)) {
    const y = candleSeries.priceToCoordinate(level.price);
    if (y === null || Number.isNaN(y) || y < -20 || y > canvasSize.height + 20) {
      continue;
    }
    const startX = Math.max(right - shortLineLength, left);
    const endX = right;
    fibCtx.beginPath();
    fibCtx.moveTo(startX, y);
    fibCtx.lineTo(endX, y);
    fibCtx.stroke();
  }
  fibCtx.restore();
}

function drawScoredTrendlines(canvasSize) {
  if (!el.trendEnabled.checked || state.visible.length < FIB_SWING_LOOKBACK * 2 + 1) {
    return;
  }

  const lines = buildScoredTrendlines(state.visible);
  for (const line of lines) {
    const start = state.visible[line.start_idx];
    const end = state.visible[state.visible.length - 1];
    const x1 = chart.timeScale().timeToCoordinate(start.time);
    const x2 = chart.timeScale().timeToCoordinate(end.time);
    const y1 = candleSeries.priceToCoordinate(line.slope * line.start_idx + line.intercept);
    const y2 = candleSeries.priceToCoordinate(line.slope * (state.visible.length - 1) + line.intercept);
    if ([x1, x2, y1, y2].some((value) => value === null || Number.isNaN(value))) {
      continue;
    }

    const alpha = 0.22 + (line.total_score / 100) * 0.58;
    const width = 1 + (line.total_score / 100) * 4;
    const color = line.side === 'support' ? `rgba(32, 180, 134, ${alpha})` : `rgba(239, 91, 91, ${alpha})`;
    fibCtx.save();
    fibCtx.strokeStyle = color;
    fibCtx.lineWidth = width;
    fibCtx.lineCap = 'round';
    fibCtx.beginPath();
    fibCtx.moveTo(x1, y1);
    fibCtx.lineTo(x2, y2);
    fibCtx.stroke();
    fibCtx.restore();
  }
}

function buildScoredTrendlines(candles) {
  const pivots = collectConfirmedPivots(candles, FIB_SWING_LOOKBACK);
  const lows = pivots.filter((pivot) => pivot.type === 'low').slice(-TRENDLINE_PIVOT_LIMIT);
  const highs = pivots.filter((pivot) => pivot.type === 'high').slice(-TRENDLINE_PIVOT_LIMIT);
  const supportLines = buildLinesFromPivots(candles, lows, 'support');
  const resistanceLines = buildLinesFromPivots(candles, highs, 'resistance');
  return [...supportLines, ...resistanceLines]
    .filter((line) => line.total_score >= TRENDLINE_MIN_SCORE && line.touch_count >= 2)
    .sort((a, b) => b.total_score - a.total_score)
    .slice(0, TRENDLINE_MAX_VISIBLE);
}

function buildLinesFromPivots(candles, pivots, side) {
  const lines = [];
  for (let i = 0; i < pivots.length - 1; i += 1) {
    for (let j = i + 1; j < pivots.length; j += 1) {
      const first = pivots[i];
      const second = pivots[j];
      if (second.index - first.index < 8) {
        continue;
      }
      const slope = (second.price - first.price) / (second.index - first.index);
      const intercept = first.price - slope * first.index;
      const line = {
        slope,
        intercept,
        start_idx: first.index,
        end_idx: second.index,
        side,
      };
      const score = scoreTrendline(candles, line);
      if (score) {
        lines.push({ ...line, ...score });
      }
    }
  }
  return lines;
}

function scoreTrendline(candles, line, thresholdPct = 0.0005) {
  const totalBars = candles.length;
  const lineLength = line.end_idx - line.start_idx;
  let touchCount = 0;
  const deviations = [];
  let lastTouchIdx = line.end_idx;

  for (let idx = line.start_idx; idx < totalBars; idx += 1) {
    const linePrice = line.slope * idx + line.intercept;
    if (!Number.isFinite(linePrice) || linePrice <= 0) {
      continue;
    }

    const candle = candles[idx];
    const testedPrice = line.side === 'support' ? candle.low : candle.high;
    const pctDiff = Math.abs(testedPrice - linePrice) / linePrice;
    if (line.side === 'support' && idx > line.end_idx && testedPrice < linePrice * (1 - thresholdPct * 2)) {
      break;
    }
    if (line.side === 'resistance' && idx > line.end_idx && testedPrice > linePrice * (1 + thresholdPct * 2)) {
      break;
    }
    if (pctDiff <= thresholdPct) {
      touchCount += 1;
      deviations.push(pctDiff);
      lastTouchIdx = idx;
    }
  }

  const sTouch = Math.min(Math.max(40 + (touchCount - 2) * 15, 0), 100);
  const sLength = Math.min((lineLength / 50) * 100, 100);
  const avgDev = deviations.length ? deviations.reduce((sum, value) => sum + value, 0) / deviations.length : thresholdPct;
  const sMse = Math.max(0, 100 * (1 - avgDev / thresholdPct));
  const barsAgo = totalBars - 1 - lastTouchIdx;
  const sRecency = Math.max(0, 100 * (1 - barsAgo / 100));
  const totalScore = sTouch * 0.5 + sLength * 0.2 + sMse * 0.2 + sRecency * 0.1;
  return {
    total_score: totalScore,
    touch_count: touchCount,
    line_length: lineLength,
    avg_deviation_pct: avgDev * 100,
    bars_ago: barsAgo,
  };
}

function collectConfirmedPivots(candles, lookback) {
  const pivots = [];
  for (let i = lookback; i < candles.length - lookback; i += 1) {
    const left = candles.slice(i - lookback, i);
    const right = candles.slice(i + 1, i + lookback + 1);
    const candle = candles[i];
    const isHigh = left.every((item) => candle.high > item.high) && right.every((item) => candle.high > item.high);
    const isLow = left.every((item) => candle.low < item.low) && right.every((item) => candle.low < item.low);
    if (isHigh) {
      pivots.push({ type: 'high', time: candle.time, price: candle.high, index: i, confirmedAt: i + lookback });
    }
    if (isLow) {
      pivots.push({ type: 'low', time: candle.time, price: candle.low, index: i, confirmedAt: i + lookback });
    }
  }
  return pivots.sort((a, b) => a.confirmedAt - b.confirmedAt || a.index - b.index);
}

function latestConfirmedSwingLeg(candles, lookback) {
  const pivots = collectConfirmedPivots(candles, lookback);
  const last = pivots[pivots.length - 1];
  if (!last) {
    return null;
  }
  for (let i = pivots.length - 2; i >= 0; i -= 1) {
    const previous = pivots[i];
    if (previous.type !== last.type && previous.index < last.index) {
      return { start: previous, end: last, direction: previous.type === 'low' ? 1 : -1 };
    }
  }
  return null;
}

function fibLevelsForSwing(swing) {
  const high = Math.max(swing.start.price, swing.end.price);
  const low = Math.min(swing.start.price, swing.end.price);
  const range = high - low;
  const ratios = [...FIB_BASE_RATIOS, ...FIB_EXTENSION_RATIOS];
  return ratios.map((ratio) => {
    const price = swing.direction === 1 ? low + range * ratio : high - range * ratio;
    return { ratio, price };
  });
}

function syncFibCanvasSize() {
  const rect = chartEl.getBoundingClientRect();
  const pixelRatio = window.devicePixelRatio || 1;
  const width = Math.max(Math.floor(rect.width * pixelRatio), 1);
  const height = Math.max(Math.floor(rect.height * pixelRatio), 1);
  if (fibOverlay.width !== width || fibOverlay.height !== height) {
    fibOverlay.width = width;
    fibOverlay.height = height;
    fibOverlay.style.width = `${rect.width}px`;
    fibOverlay.style.height = `${rect.height}px`;
  }
  fibCtx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  return { width: rect.width, height: rect.height };
}

function renderTrades(trades) {
  el.trades.innerHTML = '';
  for (const trade of trades.slice().reverse()) {
    const node = document.createElement('div');
    node.className = 'trade';
    node.textContent = `${trade.side} ${trade.status} entry ${formatNumber(trade.entry_price)} pnl ${trade.pnl ?? '-'}`;
    el.trades.appendChild(node);
  }
}

function toChartCandle(candle) {
  return {
    time: candle.time,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  };
}

function toVolumeBar(candle) {
  return {
    time: candle.time,
    value: candle.volume,
    color: candle.close >= candle.open ? 'rgba(32, 180, 134, 0.55)' : 'rgba(239, 91, 91, 0.55)',
  };
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function toDatetimeLocal(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return [
    date.getUTCFullYear(),
    '-',
    pad(date.getUTCMonth() + 1),
    '-',
    pad(date.getUTCDate()),
    'T',
    pad(date.getUTCHours()),
    ':',
    pad(date.getUTCMinutes()),
  ].join('');
}

function formatNumber(value) {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function hexToRgba(hex, alpha) {
  const clean = hex.replace('#', '');
  const value = Number.parseInt(clean, 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function clamp(value, min, max) {
  if (Number.isNaN(value)) {
    return min;
  }
  return Math.min(Math.max(value, min), max);
}

window.addEventListener('resize', () => {
  chart.resize(chartEl.clientWidth, chartEl.clientHeight);
  volumeChart.resize(document.querySelector('#volume').clientWidth, document.querySelector('#volume').clientHeight);
  drawOverlay();
});

chart.timeScale().subscribeVisibleTimeRangeChange(drawOverlay);

el.createSession.addEventListener('click', () => createSession().catch(alert));
el.playPause.addEventListener('click', togglePlay);
el.nextBar.addEventListener('click', () => nextBar().catch(alert));
el.speed.addEventListener('change', () => {
  if (state.playing) {
    play();
  }
});
el.longBtn.addEventListener('click', () => submitOrder('open_long').catch(alert));
el.shortBtn.addEventListener('click', () => submitOrder('open_short').catch(alert));
el.closeBtn.addEventListener('click', () => submitOrder('close').catch(alert));
[
  el.fibEnabled,
  el.fibFillColor,
  el.fibFillOpacity,
  el.fibBorderColor,
  el.fibLineColor,
  el.fibLineLength,
  el.fibLineWidth,
  el.trendEnabled,
].forEach((control) => control.addEventListener('input', drawOverlay));

initCatalog().catch(alert);
