from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .replay import CandleStore, ReplayService


WEB_DIR = Path(__file__).resolve().parent / 'web'

app = FastAPI(title='Price Action Replay Terminal', version='0.2.0')
store = CandleStore()
service = ReplayService(store)

app.mount('/static', StaticFiles(directory=WEB_DIR), name='static')


class CreateReplaySessionRequest(BaseModel):
    symbol: str = 'BTCUSDT'
    timeframe: str = '1h'
    start_time: str
    context_bars: int = Field(default=200, ge=0, le=5000)
    chunk_size: int = Field(default=500, ge=1, le=10000)
    initial_cash: float = Field(default=10000.0, gt=0)
    fee_rate: float = Field(default=0.0006, ge=0, le=0.05)
    slippage_rate: float = Field(default=0.0002, ge=0, le=0.05)
    dataset_id: str | None = None


class SubmitOrderRequest(BaseModel):
    action: Literal['open_long', 'open_short', 'close']
    price: float = Field(gt=0)
    timestamp: str
    qty: float = Field(default=1.0, gt=0)
    note: str = ''


@app.get('/')
def index():
    return FileResponse(WEB_DIR / 'replay.html')


@app.get('/api/health')
def health() -> dict:
    return {'status': 'ok'}


@app.get('/api/replay/catalog')
def catalog() -> dict:
    return store.catalog()


@app.post('/api/replay/sessions')
def create_session(payload: CreateReplaySessionRequest) -> dict:
    try:
        return service.create_session(
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            start_time=payload.start_time,
            context_bars=payload.context_bars,
            chunk_size=payload.chunk_size,
            initial_cash=payload.initial_cash,
            fee_rate=payload.fee_rate,
            slippage_rate=payload.slippage_rate,
            dataset_id=payload.dataset_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get('/api/replay/sessions/{session_id}')
def get_session(session_id: str) -> dict:
    try:
        return service.session_snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get('/api/replay/sessions/{session_id}/candles')
def get_candles(
    session_id: str,
    cursor: str = Query(...),
    limit: int = Query(default=500, ge=1, le=10000),
) -> dict:
    try:
        return service.get_chunk(session_id, cursor, limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/api/replay/sessions/{session_id}/orders')
def submit_order(session_id: str, payload: SubmitOrderRequest) -> dict:
    try:
        return service.submit_order(
            session_id=session_id,
            action=payload.action,
            price=payload.price,
            timestamp=payload.timestamp,
            qty=payload.qty,
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get('/api/replay/sessions/{session_id}/trades.csv')
def export_trades(session_id: str):
    try:
        path = service.export_trades_csv(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type='text/csv', filename=f'{session_id}_trades.csv')