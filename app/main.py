from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.observability import configure_logging
from app.pipeline import AnalyticsPipeline, compare_payloads
from app.schemas import AskRequest, AskResponse, PinRequest, RefreshResponse
from app.storage import delete_pin, get_pin, init_db, list_pins, save_pin

configure_logging(settings.log_level)
init_db()
pipeline = AnalyticsPipeline()

app = FastAPI(title='Olist Sales Analytics Chatbot', version='1.0.0')

frontend_dist = Path('/app/frontend/dist')
if frontend_dist.exists():
    app.mount('/assets', StaticFiles(directory=frontend_dist / 'assets'), name='assets')


@app.get('/health')
async def health():
    return {'status': 'ok', 'agent_mode': settings.agent_mode, 'model': settings.openrouter_model}


@app.post('/api/ask', response_model=AskResponse)
async def ask(request: AskRequest):
    result = await pipeline.run(request.query)
    return result


@app.get('/api/pins')
async def pins():
    return list_pins()


@app.post('/api/pins')
async def pin(request: PinRequest):
    pin_id = hashlib.sha256(f"{request.query}:{os.urandom(8).hex()}".encode()).hexdigest()[:16]
    save_pin(pin_id, request.query, request.chart_payload)
    return {'id': pin_id}


@app.delete('/api/pins/{pin_id}')
async def unpin(pin_id: str):
    if not delete_pin(pin_id):
        raise HTTPException(status_code=404, detail='Pin not found')
    return {'deleted': True}


@app.post('/api/pins/{pin_id}/refresh', response_model=RefreshResponse)
async def refresh(pin_id: str):
    pin = get_pin(pin_id)
    if not pin:
        raise HTTPException(status_code=404, detail='Pin not found')
    new_payload = await pipeline.run(pin['query'])
    changed, score = compare_payloads(pin['chart_payload'], new_payload)
    save_pin(pin_id, pin['query'], new_payload)
    msg = 'Significant change detected since the pinned snapshot.' if changed else 'No significant change detected since the pinned snapshot.'
    return {
        'id': pin_id,
        'changed': changed,
        'change_score': round(score, 4),
        'message': msg,
        'payload': new_payload,
    }


@app.get('/')
async def index():
    index_file = frontend_dist / 'index.html'
    if index_file.exists():
        return FileResponse(index_file)
    return {'message': 'Frontend build missing'}
