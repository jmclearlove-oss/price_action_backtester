const state = {
  catalog: null,
  sessionId: null,
  cursor: null,
  visible: [],
  buffer: [],
  current: null,
  playing: false,
  timer: null,
  session: null,
  indicatorSpecs: [],
  signalMarkerSpecs: [],
  indicatorSeries: new Map(),
  indicatorVisibility: {},
  signalVisibility: {},
  entryPriceLine: null,
};

const FIB_EXTENSION_RATIOS = [1.272, 1.414, 1.618, 2.0, 2.24, 2.618, 3.0, 3.618, 4.236];
const FIB_BASE_RATIOS = [0, 1];
const FIB_SWING_LOOKBACK = 4;
const TRENDLINE_MIN_SCORE = 35;
const TRENDLINE_MAX_VISIBLE = 6;
const TRENDLINE_PIVOT_LIMIT = 18;

const el = {
  dataset: document.querySelector('#dataset'),
  symbol: document.querySelector('#symbol'),
  timeframe: document.querySelector('#timeframe'),
  startTime: document.querySelector('#startTime'),
  contextBars: document.querySelector('#contextBars'),
  chunkSize: document.querySelector('#chunkSize'),
  initialCash: document.querySelector('#initialCash'),
  qty: document.querySelector('#qty'),
  feeRate: document.querySelector('#feeRate'),
  slippageRate: document.querySelector('#slippageRate'),
  speed: document.querySelector('#speed'),
  createSession: document.querySelector('#createSession'),
  playPause: document.querySelector('#playPause'),
  nextBar: document.querySelector('#nextBar'),
  fitChart: document.querySelector('#fitChart'),
  longBtn: document.querySelector('#longBtn'),
  shortBtn: document.querySelector('#shortBtn'),
  closeBtn: document.querySelector('#closeBtn'),
  orderNote: document.querySelector('#orderNote'),
  currentTime: document.querySelector('#currentTime'),
  currentPrice: document.querySelector('#currentPrice'),
  bufferCount: document.querySelector('#bufferCount'),
  positionState: document.querySelector('#positionState'),
  realizedPnl: document.querySelector('#realizedPnl'),
  unrealizedPnl: document.querySelector('#unrealizedPnl'),
  equity: document.querySelector('#equity'),
  trades: document.querySelector('#trades'),
  exportTrades: document.querySelector('#exportTrades'),
  indicatorToggles: document.querySelector('#indicatorToggles'),
  signalToggles: document.querySelector('#signalToggles'),
  toggleAllIndicators: document.querySelector('#toggleAllIndicators'),
  fibEnabled: document.querySelector('#fibEnabled'),
  trendEnabled: document.querySelector('#trendEnabled'),
  chartTitle: document.querySelector('#chartTitle'),
};

const chartEl = document.querySelector('#chart');
const volumeEl = document.querySelector('#volume');
const fibOverlay = document.querySelector('#fibOverlay');
const fibCtx = fibOverlay.getContext('2d');

const chart = LightweightCharts.createChart(chartEl, {
  layout: { background: { color: '#0f141a' }, textColor: '#c8d2dc' },
  grid: { vertLines: { color: '#1d2730' }, horzLines: { color: '#1d2730' } },
  rightPriceScale: { borderColor: '#2a3540' },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
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

const volumeChart = LightweightCharts.createChart(volumeEl, {
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
  state.catalog = catalog;
  state.indicatorSpecs = catalog.indicator_specs || [];
  state.signalMarkerSpecs = catalog.signal_marker_specs || [];
  renderDatasetOptions(catalog.datasets || []);
  renderIndicatorControls();
  applyDatasetSelection();
}

function renderDatasetOptions(datasets) {
  el.dataset.innerHTML = '';
  for (const dataset of datasets) {
    const option = document.createElement('option');
    option.value = dataset.id;
    option.textContent = `${dataset.symbol} ${dataset.timeframe} · ${dataset.rows} bars`;
    option.dataset.symbol = dataset.symbol;
    option.dataset.timeframe = dataset.timeframe;
    option.dataset.start = dataset.start_time;
    option.dataset.end = dataset.end_time;
    el.dataset.appendChild(option);
  }
  if (state.catalog?.active_dataset) {
    el.dataset.value = state.catalog.active_dataset;
  }
}

function applyDatasetSelection() {
  const option = el.dataset.selectedOptions[0];
  if (!option) return;
  el.symbol.value = option.dataset.symbol || 'BTCUSDT';
  el.timeframe.value = option.dataset.timeframe || '1h';
  const start = new Date(option.dataset.start);
  const end = new Date(option.dataset.end);
  const suggested = new Date(start.getTime() + Math.min(7 * 24 * 60 * 60 * 1000, Math.max(0, (end - start) * 0.2)));
  el.startTime.value = toDatetimeLocalUTC(suggested);
  el.chartTitle.textContent = `${el.symbol.value} · ${el.timeframe.value}`;
}

function renderIndicatorControls() {
  el.indicatorToggles.innerHTML = '';
  el.signalToggles.innerHTML = '';

  for (const spec of state.indicatorSpecs) {
    if (state.indicatorVisibility[spec.id] === undefined) {
      state.indicatorVisibility[spec.id] = Boolean(spec.default_visible);
    }
    const node = createToggleRow({
      id: `ind-${spec.id}`,
      label: spec.label || spec.id,
      group: spec.group || 'Indicator',
      color: spec.color || '#dcae45',
      checked: state.indicatorVisibility[spec.id],
      onChange: (checked) => {
        state.indicatorVisibility[spec.id] = checked;
        refreshIndicatorSeries();
        updateMarkers();
      },
    });
    el.indicatorToggles.appendChild(node);
  }

  for (const spec of state.signalMarkerSpecs) {
    const id = spec.id || spec.column;
    if (state.signalVisibility[id] === undefined) {
      state.signalVisibility[id] = Boolean(spec.default_visible);
    }
    const node = createToggleRow({
      id: `sig-${id}`,
      label: spec.label || id,
      group: spec.group || 'Signal',
      color: spec.color || '#dcae45',
      checked: state.signalVisibility[id],
      onChange: (checked) => {
        state.signalVisibility[id] = checked;
        updateMarkers();
      },
    });
    el.signalToggles.appendChild(node);
  }
}

function createToggleRow({ id, label, group, color, checked, onChange }) {
  const row = document.createElement('label');
  row.className = 'toggle-row';
  row.htmlFor = id;

  const checkbox = document.createElement('input');
  checkbox.id = id;
  checkbox.type = 'checkbox';
  checkbox.checked = checked;
  checkbox.addEventListener('change', () => onChange(checkbox.checked));

  const text = document.createElement('span');
  text.textContent = label;

  const right = document.createElement('span');
  right.className = 'toggle-group';
  right.textContent = group;

  const dot = document.createElement('span');
  dot.className = 'toggle-color';
  dot.style.background = color;

  row.appendChild(checkbox);
  row.appendChild(text);
  row.appendChild(right);
  row.appendChild(dot);
  return row;
}

async function createSession() {
  stop();
  const payload = {
    dataset_id: el.dataset.value || null,
    symbol: el.symbol.value,
    timeframe: el.timeframe.value,
    start_time: datetimeLocalToIsoUTC(el.startTime.value),
    context_bars: Number(el.contextBars.value || 180),
    chunk_size: Number(el.chunkSize.value || 500),
    initial_cash: Number(el.initialCash.value || 10000),
    fee_rate: Number(el.feeRate.value || 0),
    slippage_rate: Number(el.slippageRate.value || 0),
  };
  const data = await request('/api/replay/sessions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  state.sessionId = data.session_id;
  state.cursor = data.cursor;
  state.visible = data.context || [];
  state.buffer = data.playback || [];
  state.current = state.visible[state.visible.length - 1] || null;
  state.session = data.session;
  state.indicatorSpecs = data.indicator_specs || state.indicatorSpecs;
  state.signalMarkerSpecs = data.signal_marker_specs || state.signalMarkerSpecs;
  renderIndicatorControls();
  initIndicatorSeries();
  renderChart();
  updateInfo(data.session);
  el.chartTitle.textContent = `${data.symbol} · ${data.timeframe} · ${data.session_id}`;
}

function initIndicatorSeries() {
  for (const series of state.indicatorSeries.values()) {
    try { chart.removeSeries(series); } catch (err) { console.warn(err); }
  }
  state.indicatorSeries.clear();
  for (const spec of state.indicatorSpecs) {
    const series = chart.addLineSeries({
      color: spec.color || '#dcae45',
      lineWidth: spec.line_width || 1,
      priceScaleId: spec.price_scale || 'right',
      lastValueVisible: true,
      priceLineVisible: false,
      title: spec.label || spec.id,
    });
    state.indicatorSeries.set(spec.id, series);
  }
}

function renderChart() {
  candleSeries.setData(state.visible.map(toChartCandle));
  volumeSeries.setData(state.visible.map(toVolumeBar));
  refreshIndicatorSeries();
  fitChart();
  renderCurrent();
  updateMarkers();
  drawOverlay();
}

function refreshIndicatorSeries() {
  for (const spec of state.indicatorSpecs) {
    const series = state.indicatorSeries.get(spec.id);
    if (!series) continue;
    if (!state.indicatorVisibility[spec.id]) {
      series.setData([]);
      continue;
    }
    series.setData(state.visible.map((candle) => toLinePoint(candle, spec.id)).filter(Boolean));
  }
}

function updateIndicatorSeriesForCandle(candle) {
  for (const spec of state.indicatorSpecs) {
    const series = state.indicatorSeries.get(spec.id);
    if (!series || !state.indicatorVisibility[spec.id]) continue;
    const point = toLinePoint(candle, spec.id);
    if (point) series.update(point);
  }
}

async function nextBar() {
  if (!state.sessionId) return;
  if (state.buffer.length === 0) {
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
  updateIndicatorSeriesForCandle(candle);
  renderCurrent();
  updateInfo(state.session);
  drawOverlay();
  if (state.buffer.length < 80) {
    prefetch().catch(console.warn);
  }
}

async function prefetch() {
  if (!state.sessionId || !state.cursor) return;
  const url = `/api/replay/sessions/${state.sessionId}/candles?cursor=${encodeURIComponent(state.cursor)}&limit=${Number(el.chunkSize.value || 500)}`;
  const data = await request(url);
  if (data.candles.length > 0) {
    state.cursor = data.cursor;
    state.buffer.push(...data.candles);
  }
  renderCurrent();
}

function togglePlay() {
  if (state.playing) stop(); else play();
}

function play() {
  if (!state.sessionId) return;
  state.playing = true;
  el.playPause.textContent = '暂停';
  clearInterval(state.timer);
  state.timer = setInterval(() => nextBar().catch((err) => { stop(); alert(err.message); }), Number(el.speed.value));
}

function stop() {
  state.playing = false;
  el.playPause.textContent = '播放';
  clearInterval(state.timer);
  state.timer = null;
}

async function submitOrder(action) {
  if (!state.sessionId || !state.current) return;
  const snapshot = await request(`/api/replay/sessions/${state.sessionId}/orders`, {
    method: 'POST',
    body: JSON.stringify({
      action,
      price: state.current.close,
      timestamp: state.current.timestamp,
      qty: Number(el.qty.value || 1),
      note: el.orderNote.value || '',
    }),
  });
  updateInfo(snapshot);
}

function updateInfo(session) {
  if (session) state.session = session;
  renderCurrent();
  updateAccountStats();
  renderTrades(state.session?.trades || []);
  updateMarkers();
  updatePositionLine();
}

function renderCurrent() {
  el.currentTime.textContent = state.current ? state.current.timestamp : '-';
  el.currentPrice.textContent = state.current ? formatNumber(state.current.close) : '-';
  el.bufferCount.textContent = String(state.buffer.length);
}

function updateAccountStats() {
  const session = state.session;
  if (!session) {
    el.positionState.textContent = '-';
    setPnlText(el.realizedPnl, 0);
    setPnlText(el.unrealizedPnl, 0);
    el.equity.textContent = '0';
    return;
  }

  let unrealized = Number(session.unrealized_pnl || 0);
  if (session.position && state.current) {
    unrealized = calculateUnrealized(session.position, state.current.close, session.fee_rate);
  }
  const equity = Number(session.cash || session.initial_cash || 0) + unrealized;
  const position = session.position;
  el.positionState.textContent = position ? `${position.side.toUpperCase()} ${position.qty} @ ${formatNumber(position.entry_price)}` : '-';
  setPnlText(el.realizedPnl, Number(session.realized_pnl || 0));
  setPnlText(el.unrealizedPnl, unrealized);
  setPnlText(el.equity, equity, false);
}

function calculateUnrealized(position, markPrice, feeRate) {
  const entry = Number(position.entry_price);
  const qty = Number(position.qty);
  const gross = position.side === 'long' ? (markPrice - entry) * qty : (entry - markPrice) * qty;
  const estimatedExitFee = markPrice * qty * Number(feeRate || 0);
  return gross - Number(position.entry_fee || 0) - estimatedExitFee;
}

function updatePositionLine() {
  if (state.entryPriceLine) {
    try { candleSeries.removePriceLine(state.entryPriceLine); } catch (err) { console.warn(err); }
    state.entryPriceLine = null;
  }
  const position = state.session?.position;
  if (!position) return;
  state.entryPriceLine = candleSeries.createPriceLine({
    price: Number(position.entry_price),
    color: position.side === 'long' ? '#20b486' : '#ef5b5b',
    lineWidth: 2,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true,
    title: `${position.side.toUpperCase()} ENTRY`,
  });
}

function updateMarkers() {
  const markers = [];
  for (const candle of state.visible) {
    for (const spec of state.signalMarkerSpecs) {
      const id = spec.id || spec.column;
      if (!state.signalVisibility[id]) continue;
      if (candle.signals && candle.signals[spec.column]) {
        markers.push({
          time: candle.time,
          position: spec.position || 'belowBar',
          shape: spec.shape || 'circle',
          color: spec.color || '#dcae45',
          text: spec.text || spec.label || id,
          size: 1,
        });
      }
    }
  }

  for (const trade of state.session?.trades || []) {
    markers.push({
      time: isoToUnix(trade.entry_time),
      position: trade.side === 'long' ? 'belowBar' : 'aboveBar',
      shape: trade.side === 'long' ? 'arrowUp' : 'arrowDown',
      color: trade.side === 'long' ? '#20b486' : '#ef5b5b',
      text: `${trade.side.toUpperCase()} ${formatNumber(trade.entry_price)}`,
      size: 2,
    });
    if (trade.status === 'closed' && trade.exit_time) {
      const pnl = Number(trade.net_pnl || trade.pnl || 0);
      markers.push({
        time: isoToUnix(trade.exit_time),
        position: pnl >= 0 ? 'aboveBar' : 'belowBar',
        shape: 'circle',
        color: pnl >= 0 ? '#20b486' : '#ef5b5b',
        text: `EXIT ${formatNumber(pnl)}`,
        size: 1,
      });
    }
  }

  markers.sort((a, b) => a.time - b.time);
  candleSeries.setMarkers(markers);
}

function drawOverlay() {
  const canvasSize = syncFibCanvasSize();
  fibCtx.clearRect(0, 0, canvasSize.width, canvasSize.height);
  drawFibBox(canvasSize);
  drawScoredTrendlines(canvasSize);
}

function drawFibBox(canvasSize) {
  if (!el.fibEnabled.checked || state.visible.length < FIB_SWING_LOOKBACK * 2 + 1) return;
  const swing = latestConfirmedSwingLeg(state.visible, FIB_SWING_LOOKBACK);
  if (!swing) return;

  const x1 = chart.timeScale().timeToCoordinate(swing.start.time);
  const x2 = chart.timeScale().timeToCoordinate(swing.end.time);
  const yHigh = candleSeries.priceToCoordinate(Math.max(swing.start.price, swing.end.price));
  const yLow = candleSeries.priceToCoordinate(Math.min(swing.start.price, swing.end.price));
  if ([x1, x2, yHigh, yLow].some((value) => value === null || Number.isNaN(value))) return;

  const left = Math.min(x1, x2);
  const right = Math.max(x1, x2);
  const top = Math.min(yHigh, yLow);
  const bottom = Math.max(yHigh, yLow);
  const barSpacing = Math.max(chart.timeScale().options().barSpacing || 6, 1);
  const shortLineLength = 8 * barSpacing;

  fibCtx.save();
  fibCtx.fillStyle = 'rgba(32, 180, 134, 0.08)';
  fibCtx.strokeStyle = '#dcae45';
  fibCtx.lineWidth = 1;
  fibCtx.fillRect(left, top, Math.max(right - left, 1), Math.max(bottom - top, 1));
  fibCtx.strokeRect(left + 0.5, top + 0.5, Math.max(right - left, 1), Math.max(bottom - top, 1));

  fibCtx.strokeStyle = '#dcae45';
  fibCtx.lineWidth = 2;
  for (const level of fibLevelsForSwing(swing)) {
    const y = candleSeries.priceToCoordinate(level.price);
    if (y === null || Number.isNaN(y) || y < -20 || y > canvasSize.height + 20) continue;
    fibCtx.beginPath();
    fibCtx.moveTo(Math.max(right - shortLineLength, left), y);
    fibCtx.lineTo(right, y);
    fibCtx.stroke();
  }
  fibCtx.restore();
}

function drawScoredTrendlines() {
  if (!el.trendEnabled.checked || state.visible.length < FIB_SWING_LOOKBACK * 2 + 1) return;
  const lines = buildScoredTrendlines(state.visible);
  for (const line of lines) {
    const start = state.visible[line.start_idx];
    const end = state.visible[state.visible.length - 1];
    const x1 = chart.timeScale().timeToCoordinate(start.time);
    const x2 = chart.timeScale().timeToCoordinate(end.time);
    const y1 = candleSeries.priceToCoordinate(line.slope * line.start_idx + line.intercept);
    const y2 = candleSeries.priceToCoordinate(line.slope * (state.visible.length - 1) + line.intercept);
    if ([x1, x2, y1, y2].some((value) => value === null || Number.isNaN(value))) continue;

    const alpha = 0.24 + (line.total_score / 100) * 0.55;
    const width = 1 + (line.total_score / 100) * 3;
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
  return [
    ...buildLinesFromPivots(candles, lows, 'support'),
    ...buildLinesFromPivots(candles, highs, 'resistance'),
  ]
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
      if (second.index - first.index < 8) continue;
      const slope = (second.price - first.price) / (second.index - first.index);
      const intercept = first.price - slope * first.index;
      const line = { slope, intercept, start_idx: first.index, end_idx: second.index, side };
      const score = scoreTrendline(candles, line);
      if (score) lines.push({ ...line, ...score });
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
    if (!Number.isFinite(linePrice) || linePrice <= 0) continue;
    const candle = candles[idx];
    const testedPrice = line.side === 'support' ? candle.low : candle.high;
    const pctDiff = Math.abs(testedPrice - linePrice) / linePrice;
    if (line.side === 'support' && idx > line.end_idx && testedPrice < linePrice * (1 - thresholdPct * 2)) break;
    if (line.side === 'resistance' && idx > line.end_idx && testedPrice > linePrice * (1 + thresholdPct * 2)) break;
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
  return { total_score: totalScore, touch_count: touchCount, line_length: lineLength, avg_deviation_pct: avgDev * 100, bars_ago: barsAgo };
}

function collectConfirmedPivots(candles, lookback) {
  const pivots = [];
  for (let i = lookback; i < candles.length - lookback; i += 1) {
    const left = candles.slice(i - lookback, i);
    const right = candles.slice(i + 1, i + lookback + 1);
    const candle = candles[i];
    const isHigh = left.every((item) => candle.high > item.high) && right.every((item) => candle.high > item.high);
    const isLow = left.every((item) => candle.low < item.low) && right.every((item) => candle.low < item.low);
    if (isHigh) pivots.push({ type: 'high', time: candle.time, price: candle.high, index: i, confirmedAt: i + lookback });
    if (isLow) pivots.push({ type: 'low', time: candle.time, price: candle.low, index: i, confirmedAt: i + lookback });
  }
  return pivots.sort((a, b) => a.confirmedAt - b.confirmedAt || a.index - b.index);
}

function latestConfirmedSwingLeg(candles, lookback) {
  const pivots = collectConfirmedPivots(candles, lookback);
  const last = pivots[pivots.length - 1];
  if (!last) return null;
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
  return [...FIB_BASE_RATIOS, ...FIB_EXTENSION_RATIOS].map((ratio) => ({
    ratio,
    price: swing.direction === 1 ? low + range * ratio : high - range * ratio,
  }));
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
  if (!trades.length) {
    const empty = document.createElement('div');
    empty.className = 'trade trade-meta';
    empty.textContent = '暂无交易。点击开多/开空开始记录。';
    el.trades.appendChild(empty);
    return;
  }
  for (const trade of trades.slice().reverse()) {
    const node = document.createElement('div');
    node.className = 'trade';
    const pnl = trade.net_pnl ?? trade.pnl;
    node.innerHTML = `
      <div class="trade-head">
        <span>${trade.side.toUpperCase()} · ${trade.status}</span>
        <span class="${Number(pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative'}">${pnl == null ? '-' : formatNumber(pnl)}</span>
      </div>
      <div class="trade-meta">Entry: ${trade.entry_time} @ ${formatNumber(trade.entry_price)} · Qty ${formatNumber(trade.qty)}</div>
      <div class="trade-meta">Exit: ${trade.exit_time || '-'} ${trade.exit_price ? `@ ${formatNumber(trade.exit_price)}` : ''}</div>
      ${trade.note ? `<div class="trade-meta">Note: ${escapeHtml(trade.note)}</div>` : ''}
    `;
    el.trades.appendChild(node);
  }
}

function toChartCandle(candle) {
  return { time: candle.time, open: candle.open, high: candle.high, low: candle.low, close: candle.close };
}

function toVolumeBar(candle) {
  return {
    time: candle.time,
    value: candle.volume,
    color: candle.close >= candle.open ? 'rgba(32, 180, 134, 0.55)' : 'rgba(239, 91, 91, 0.55)',
  };
}

function toLinePoint(candle, key) {
  const value = Number(candle.indicators?.[key]);
  if (!Number.isFinite(value)) return null;
  return { time: candle.time, value };
}

async function request(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json();
  return response.text();
}

function fitChart() {
  chart.timeScale().fitContent();
  volumeChart.timeScale().fitContent();
  drawOverlay();
}

function exportTrades() {
  if (!state.sessionId) return;
  window.location.href = `/api/replay/sessions/${state.sessionId}/trades.csv`;
}

function toDatetimeLocalUTC(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
}

function datetimeLocalToIsoUTC(value) {
  if (!value) return new Date().toISOString();
  const normalized = value.length === 16 ? `${value}:00Z` : `${value}Z`;
  return new Date(normalized).toISOString();
}

function isoToUnix(value) {
  return Math.floor(new Date(value).getTime() / 1000);
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return number.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function setPnlText(node, value, signed = true) {
  const number = Number(value || 0);
  node.textContent = signed && number > 0 ? `+${formatNumber(number)}` : formatNumber(number);
  node.classList.remove('pnl-positive', 'pnl-negative');
  if (number > 0) node.classList.add('pnl-positive');
  if (number < 0) node.classList.add('pnl-negative');
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function toggleAllIndicators() {
  const specs = state.indicatorSpecs;
  const shouldEnable = specs.some((spec) => !state.indicatorVisibility[spec.id]);
  for (const spec of specs) state.indicatorVisibility[spec.id] = shouldEnable;
  renderIndicatorControls();
  refreshIndicatorSeries();
}

window.addEventListener('resize', () => {
  chart.resize(chartEl.clientWidth, chartEl.clientHeight);
  volumeChart.resize(volumeEl.clientWidth, volumeEl.clientHeight);
  drawOverlay();
});

chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
  if (range) {
    try { volumeChart.timeScale().setVisibleRange(range); } catch (err) { console.warn(err); }
  }
  drawOverlay();
});

el.dataset.addEventListener('change', applyDatasetSelection);
el.createSession.addEventListener('click', () => createSession().catch((err) => alert(err.message)));
el.playPause.addEventListener('click', togglePlay);
el.nextBar.addEventListener('click', () => nextBar().catch((err) => alert(err.message)));
el.fitChart.addEventListener('click', fitChart);
el.speed.addEventListener('change', () => { if (state.playing) play(); });
el.longBtn.addEventListener('click', () => submitOrder('open_long').catch((err) => alert(err.message)));
el.shortBtn.addEventListener('click', () => submitOrder('open_short').catch((err) => alert(err.message)));
el.closeBtn.addEventListener('click', () => submitOrder('close').catch((err) => alert(err.message)));
el.exportTrades.addEventListener('click', exportTrades);
el.toggleAllIndicators.addEventListener('click', toggleAllIndicators);
el.fibEnabled.addEventListener('change', drawOverlay);
el.trendEnabled.addEventListener('change', drawOverlay);

initCatalog().catch((err) => alert(err.message));
