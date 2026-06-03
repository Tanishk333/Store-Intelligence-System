import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.logging_config import configure_logging, request_logging_middleware
from app.schemas import AnomalyOut, EventIn, EventOut, FunnelOut, HealthOut, HeatmapOut, MetricsOut
from app.services.anomalies import detect_anomalies
from app.services.ingest import import_pos_csv, ingest_event, last_event_timestamp
from app.services.metrics import get_funnel, get_heatmap, get_metrics

configure_logging()
app = FastAPI(title="Store Intelligence API", version="1.0.0")
app.middleware("http")(request_logging_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        for websocket in list(self.active):
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                self.disconnect(websocket)


manager = ConnectionManager()


@app.on_event("startup")
def startup() -> None:
    init_db()
    pos_path = os.getenv("POS_CSV_PATH", "Brigade_Bangalore_10_April_26 (1)bc6219c.csv")
    if os.path.exists(pos_path):
        from app.database import session_scope

        with session_scope() as db:
            import_pos_csv(db, pos_path)


@app.post("/events/ingest", response_model=EventOut)
async def ingest(payload: EventIn, db: Session = Depends(get_db)) -> EventOut:
    try:
        _, duplicate = ingest_event(db, payload)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    await manager.broadcast({"type": "event", "event": payload.model_dump(mode="json")})
    return EventOut(**payload.model_dump(), duplicate=duplicate)


@app.get("/stores/{id}/metrics", response_model=MetricsOut)
def metrics(id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return get_metrics(db, id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/stores/{id}/funnel", response_model=FunnelOut)
def funnel(id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return get_funnel(db, id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/stores/{id}/heatmap", response_model=HeatmapOut)
def heatmap(id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return get_heatmap(db, id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/stores/{id}/anomalies", response_model=list[AnomalyOut])
def anomalies(id: str, db: Session = Depends(get_db)) -> list:
    try:
        return detect_anomalies(db, id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("select 1"))
        last_seen = last_event_timestamp(db)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    stale_after = int(os.getenv("STALE_FEED_SECONDS", "300"))
    now = datetime.now(timezone.utc)
    last_seen_aware = last_seen.replace(tzinfo=timezone.utc) if last_seen and last_seen.tzinfo is None else last_seen
    stale = bool(last_seen_aware and now - last_seen_aware > timedelta(seconds=stale_after))
    return {
        "status": "ok" if not stale else "degraded",
        "database": "ok",
        "last_event_timestamp": last_seen,
        "stale_feed_warning": stale,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
