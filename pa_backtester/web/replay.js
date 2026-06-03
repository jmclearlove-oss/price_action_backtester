const state = {
  sessionId: null,
  cursor: null,
  visible: [],
  buffer: [],
  current: null,
  playing: false,
  timer: null,
};

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
};

const chart = LightweightCharts.createChart(document.querySelector('#chart'), {
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

window.addEventListener('resize', () => {
  chart.resize(document.querySelector('#chart').clientWidth, document.querySelector('#chart').clientHeight);
  volumeChart.resize(document.querySelector('#volume').clientWidth, document.querySelector('#volume').clientHeight);
});

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

initCatalog().catch(alert);

