import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Event, SessionRecord, Transaction, ZoneMetric
from app.schemas import EventIn, EventType

BILLING_ZONE_ID = "billing"
POS_WINDOW = timedelta(minutes=5)


def _json(data: dict) -> str:
    return json.dumps(data, default=str, sort_keys=True)


def ingest_event(db: Session, payload: EventIn) -> tuple[Event, bool]:
    existing = db.scalar(select(Event).where(Event.event_id == payload.event_id))
    if existing:
        return existing, True

    timestamp = _naive_utc(payload.timestamp)
    event = Event(
        event_id=payload.event_id,
        store_id=payload.store_id,
        camera_id=payload.camera_id,
        visitor_id=payload.visitor_id,
        event_type=payload.event_type.value,
        timestamp=timestamp,
        zone_id=payload.zone_id,
        dwell_ms=payload.dwell_ms,
        is_staff=payload.is_staff,
        confidence=payload.confidence,
        metadata_json=_json(payload.metadata),
    )
    db.add(event)
    try:
        _apply_session_updates(db, payload)
        _apply_zone_updates(db, payload)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Event).where(Event.event_id == payload.event_id))
        if existing:
            return existing, True
        raise
    return event, False


def _get_or_create_session(db: Session, event: EventIn) -> SessionRecord:
    session = db.scalar(
        select(SessionRecord).where(
            SessionRecord.store_id == event.store_id,
            SessionRecord.visitor_id == event.visitor_id,
        )
    )
    if session:
        return session
    timestamp = _naive_utc(event.timestamp)
    session = SessionRecord(
        store_id=event.store_id,
        visitor_id=event.visitor_id,
        first_seen=timestamp,
        last_seen=timestamp,
        is_staff=event.is_staff,
        entry_count=0,
    )
    db.add(session)
    db.flush()
    return session


def _apply_session_updates(db: Session, event: EventIn) -> None:
    session = _get_or_create_session(db, event)
    timestamp = _naive_utc(event.timestamp)
    session.last_seen = max(session.last_seen, timestamp)
    session.is_staff = session.is_staff or event.is_staff

    if event.event_type in {EventType.ENTRY, EventType.REENTRY}:
        session.entry_count += 1
        if event.event_type == EventType.ENTRY and session.first_seen > timestamp:
            session.first_seen = timestamp
        if event.event_type == EventType.REENTRY:
            session.exited_at = None
    elif event.event_type == EventType.EXIT:
        session.exited_at = timestamp
    elif event.event_type in {EventType.ZONE_ENTER, EventType.ZONE_DWELL, EventType.ZONE_EXIT}:
        session.visited_zone = True
        if event.zone_id == BILLING_ZONE_ID:
            session.visited_billing = True
            session.last_billing_at = timestamp
    elif event.event_type == EventType.BILLING_QUEUE_JOIN:
        session.visited_billing = True
        session.last_billing_at = timestamp
    elif event.event_type == EventType.BILLING_QUEUE_ABANDON:
        session.visited_billing = True


def _apply_zone_updates(db: Session, event: EventIn) -> None:
    if event.is_staff or not event.zone_id:
        return
    if event.event_type not in {EventType.ZONE_ENTER, EventType.ZONE_DWELL}:
        return

    timestamp = _naive_utc(event.timestamp)
    metric = db.scalar(
        select(ZoneMetric).where(
            ZoneMetric.store_id == event.store_id,
            ZoneMetric.zone_id == event.zone_id,
        )
    )
    if metric is None:
        metric = ZoneMetric(
            store_id=event.store_id,
            zone_id=event.zone_id,
            visits=0,
            dwell_ms=0,
            updated_at=timestamp,
        )
        db.add(metric)
    if event.event_type == EventType.ZONE_ENTER:
        metric.visits += 1
    metric.dwell_ms += event.dwell_ms or 0
    metric.updated_at = timestamp


def import_pos_csv(db: Session, path: str | Path) -> int:
    path = Path(path)
    if not path.exists():
        return 0

    grouped: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            invoice = row.get("invoice_number") or row.get("order_id")
            if not invoice:
                continue
            amount = _float(row.get("total_amount") or row.get("NMV") or row.get("GMV"))
            key = str(invoice)
            grouped.setdefault(key, {"rows": [], "amount": 0.0, "row": row})
            grouped[key]["rows"].append(row)
            grouped[key]["amount"] += amount

    inserted = 0
    for transaction_id, bundle in grouped.items():
        if db.scalar(select(Transaction).where(Transaction.transaction_id == transaction_id)):
            continue
        row = bundle["row"]
        timestamp = _parse_pos_timestamp(row.get("order_date"), row.get("order_time"))
        store_id = row.get("store_id") or "UNKNOWN"
        transaction = Transaction(
            transaction_id=transaction_id,
            store_id=store_id,
            timestamp=timestamp,
            amount=round(bundle["amount"], 2),
            raw_json=_json({"rows": len(bundle["rows"]), "sample": row}),
        )
        db.add(transaction)
        inserted += 1
    db.commit()
    correlate_transactions(db)
    return inserted


def correlate_transactions(db: Session, store_id: str | None = None) -> int:
    query = select(Transaction).where(Transaction.visitor_id.is_(None))
    if store_id:
        query = query.where(Transaction.store_id == store_id)
    transactions = db.scalars(query.order_by(Transaction.timestamp)).all()
    converted = 0
    for tx in transactions:
        tx_timestamp = _naive_utc(tx.timestamp)
        start = tx_timestamp - POS_WINDOW
        candidate = db.scalar(
            select(SessionRecord)
            .where(
                SessionRecord.store_id == tx.store_id,
                SessionRecord.is_staff.is_(False),
                SessionRecord.converted.is_(False),
                SessionRecord.last_billing_at.is_not(None),
                SessionRecord.last_billing_at >= start,
                SessionRecord.last_billing_at <= tx_timestamp,
            )
            .order_by(SessionRecord.last_billing_at.desc())
        )
        if candidate:
            candidate.converted = True
            candidate.transaction_id = tx.transaction_id
            tx.visitor_id = candidate.visitor_id
            converted += 1
    db.commit()
    return converted


def _parse_pos_timestamp(date_value: str | None, time_value: str | None) -> datetime:
    date_value = (date_value or "").strip()
    time_value = (time_value or "00:00:00").strip()
    for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(f"{date_value} {time_value}", fmt)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _float(value: str | None) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def append_events_jsonl(path: str | Path, events: Iterable[EventIn]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(event.model_dump_json() + "\n")


def last_event_timestamp(db: Session) -> datetime | None:
    return db.scalar(select(func.max(Event.timestamp)))


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
