from datetime import datetime, timedelta, timezone

import pytest

from app.database import SessionLocal
from app.models import ZoneMetric
from app.schemas import EventIn, EventType
from app.services.anomalies import detect_anomalies
from app.services.ingest import correlate_transactions, import_pos_csv, ingest_event
from app.services.metrics import get_funnel, get_heatmap, get_metrics


def make_event(event_id, visitor_id, event_type, **kwargs):
    return EventIn(
        event_id=event_id,
        store_id="ST1008",
        camera_id="CAM_1",
        visitor_id=visitor_id,
        event_type=EventType(event_type),
        timestamp=kwargs.pop("timestamp", datetime.now(timezone.utc)),
        zone_id=kwargs.pop("zone_id", None),
        dwell_ms=kwargs.pop("dwell_ms", None),
        is_staff=kwargs.pop("is_staff", False),
        confidence=kwargs.pop("confidence", 0.9),
        metadata=kwargs.pop("metadata", {}),
    )


def test_pos_import_and_conversion_correlation(tmp_path):
    csv_path = tmp_path / "pos.csv"
    csv_path.write_text(
        "order_id,invoice_number,order_date,order_time,store_id,total_amount\n"
        "1,INV1,10-04-2026,16:55:36,ST1008,100\n"
        "1,INV1,10-04-2026,16:55:36,ST1008,50\n",
        encoding="utf-8",
    )
    db = SessionLocal()
    try:
        timestamp = datetime(2026, 4, 10, 16, 52, 0, tzinfo=timezone.utc)
        ingest_event(db, make_event("entry", "v1", "ENTRY", timestamp=timestamp))
        ingest_event(db, make_event("billing", "v1", "ZONE_ENTER", zone_id="billing", timestamp=timestamp))
        inserted = import_pos_csv(db, csv_path)
        assert inserted == 1
        assert correlate_transactions(db, "ST1008") == 0
        metrics = get_metrics(db, "ST1008")
        assert metrics["converted_visitors"] == 1
        assert metrics["conversion_rate"] == 1.0
    finally:
        db.close()


def test_heatmap_and_funnel_are_session_based():
    db = SessionLocal()
    try:
        ingest_event(db, make_event("e1", "v1", "ENTRY"))
        ingest_event(db, make_event("z1", "v1", "ZONE_ENTER", zone_id="aisle_skin"))
        ingest_event(db, make_event("d1", "v1", "ZONE_DWELL", zone_id="aisle_skin", dwell_ms=10000))
        ingest_event(db, make_event("d2", "v1", "ZONE_DWELL", zone_id="aisle_skin", dwell_ms=20000))
        funnel = get_funnel(db, "ST1008")
        heatmap = get_heatmap(db, "ST1008")
        assert funnel["entered"] == 1
        assert funnel["zone_visit"] == 1
        assert heatmap["zones"][0]["average_dwell_ms"] == 30000
    finally:
        db.close()


def test_conversion_drop_and_dead_zone_anomalies():
    db = SessionLocal()
    try:
        for index in range(5):
            ingest_event(db, make_event(f"e{index}", f"v{index}", "ENTRY"))
        db.add(
            ZoneMetric(
                store_id="ST1008",
                zone_id="unused_zone",
                visits=0,
                dwell_ms=0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        anomalies = detect_anomalies(db, "ST1008")
        assert any(item.anomaly_type == "CONVERSION_DROP" for item in anomalies)
        assert any(item.anomaly_type == "DEAD_ZONE" for item in anomalies)
    finally:
        db.close()


def test_zone_id_required_for_zone_events():
    with pytest.raises(ValueError):
        make_event("bad", "v1", "ZONE_ENTER")
