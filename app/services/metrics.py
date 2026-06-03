from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, SessionRecord, ZoneMetric


def get_metrics(db: Session, store_id: str) -> dict:
    sessions = db.scalars(
        select(SessionRecord).where(
            SessionRecord.store_id == store_id,
            SessionRecord.is_staff.is_(False),
            SessionRecord.entry_count > 0,
        )
    ).all()
    unique_visitors = len(sessions)
    converted = sum(1 for session in sessions if session.converted)
    dwell_total = (
        db.scalar(
            select(func.coalesce(func.sum(Event.dwell_ms), 0)).where(
                Event.store_id == store_id,
                Event.is_staff.is_(False),
                Event.event_type == "ZONE_DWELL",
            )
        )
        or 0
    )
    dwell_count = (
        db.scalar(
            select(func.count(Event.id)).where(
                Event.store_id == store_id,
                Event.is_staff.is_(False),
                Event.event_type == "ZONE_DWELL",
            )
        )
        or 0
    )
    queue_depth = current_queue_depth(db, store_id)
    abandons = (
        db.scalar(
            select(func.count(Event.id)).where(
                Event.store_id == store_id,
                Event.is_staff.is_(False),
                Event.event_type == "BILLING_QUEUE_ABANDON",
            )
        )
        or 0
    )
    queue_joins = (
        db.scalar(
            select(func.count(Event.id)).where(
                Event.store_id == store_id,
                Event.is_staff.is_(False),
                Event.event_type == "BILLING_QUEUE_JOIN",
            )
        )
        or 0
    )
    return {
        "store_id": store_id,
        "unique_visitors": unique_visitors,
        "converted_visitors": converted,
        "conversion_rate": round(converted / unique_visitors, 4) if unique_visitors else 0.0,
        "average_dwell_ms": round(dwell_total / dwell_count, 2) if dwell_count else 0.0,
        "queue_depth": queue_depth,
        "abandonment_rate": round(abandons / queue_joins, 4) if queue_joins else 0.0,
    }


def current_queue_depth(db: Session, store_id: str) -> int:
    joins = (
        db.scalar(
            select(func.count(Event.id)).where(
                Event.store_id == store_id,
                Event.is_staff.is_(False),
                Event.event_type == "BILLING_QUEUE_JOIN",
            )
        )
        or 0
    )
    leaves = (
        db.scalar(
            select(func.count(Event.id)).where(
                Event.store_id == store_id,
                Event.is_staff.is_(False),
                Event.event_type.in_(["BILLING_QUEUE_ABANDON", "EXIT"]),
            )
        )
        or 0
    )
    return max(0, joins - leaves)


def get_funnel(db: Session, store_id: str) -> dict:
    sessions = db.scalars(
        select(SessionRecord).where(
            SessionRecord.store_id == store_id,
            SessionRecord.is_staff.is_(False),
            SessionRecord.entry_count > 0,
        )
    ).all()
    return {
        "store_id": store_id,
        "entered": len(sessions),
        "zone_visit": sum(1 for session in sessions if session.visited_zone),
        "billing": sum(1 for session in sessions if session.visited_billing),
        "purchase": sum(1 for session in sessions if session.converted),
    }


def get_heatmap(db: Session, store_id: str) -> dict:
    metrics = db.scalars(select(ZoneMetric).where(ZoneMetric.store_id == store_id)).all()
    return {
        "store_id": store_id,
        "zones": [
            {
                "zone_id": metric.zone_id,
                "visits": metric.visits,
                "dwell_ms": metric.dwell_ms,
                "average_dwell_ms": round(metric.dwell_ms / metric.visits, 2) if metric.visits else 0.0,
            }
            for metric in metrics
        ],
    }
