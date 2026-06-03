from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Anomaly, ZoneMetric
from app.services.metrics import current_queue_depth, get_metrics


def detect_anomalies(db: Session, store_id: str) -> list[Anomaly]:
    for anomaly in db.scalars(select(Anomaly).where(Anomaly.store_id == store_id, Anomaly.active.is_(True))):
        anomaly.active = False

    metrics = get_metrics(db, store_id)
    found: list[Anomaly] = []

    if metrics["queue_depth"] >= 5:
        found.append(
            _new(
                store_id,
                "QUEUE_SPIKE",
                "high",
                f"Current queue depth is {metrics['queue_depth']}, above the operating threshold.",
                "Open an additional billing counter or assign staff to queue management.",
            )
        )

    if metrics["unique_visitors"] >= 5 and metrics["conversion_rate"] < 0.10:
        found.append(
            _new(
                store_id,
                "CONVERSION_DROP",
                "medium",
                "Conversion rate is below 10% with meaningful traffic.",
                "Review staffing, product availability, and checkout friction for the current period.",
            )
        )

    zones = db.scalars(select(ZoneMetric).where(ZoneMetric.store_id == store_id)).all()
    if metrics["unique_visitors"] > 0:
        for zone in zones:
            if zone.visits == 0:
                found.append(
                    _new(
                        store_id,
                        "DEAD_ZONE",
                        "low",
                        f"Zone {zone.zone_id} has no customer visits.",
                        "Check camera coverage, signage, and product placement for this zone.",
                    )
                )

    db.add_all(found)
    db.commit()
    return found


def _new(store_id: str, anomaly_type: str, severity: str, description: str, suggested_action: str) -> Anomaly:
    return Anomaly(
        store_id=store_id,
        anomaly_type=anomaly_type,
        severity=severity,
        description=description,
        suggested_action=suggested_action,
        detected_at=datetime.now(timezone.utc),
        active=True,
    )
