from datetime import datetime, timedelta, timezone


def event(event_id, visitor_id, event_type, **kwargs):
    payload = {
        "event_id": event_id,
        "store_id": "ST1008",
        "camera_id": "CAM_1",
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": kwargs.pop("timestamp", datetime.now(timezone.utc).isoformat()),
        "zone_id": kwargs.pop("zone_id", None),
        "dwell_ms": kwargs.pop("dwell_ms", None),
        "is_staff": kwargs.pop("is_staff", False),
        "confidence": kwargs.pop("confidence", 0.9),
        "metadata": kwargs.pop("metadata", {}),
    }
    payload.update(kwargs)
    return payload


def ingest(client, payload):
    response = client.post("/events/ingest", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_entry_exit_metrics_and_duplicate_events(client):
    ingest(client, event("e1", "v1", "ENTRY"))
    ingest(client, event("e2", "v1", "ZONE_ENTER", zone_id="billing"))
    ingest(client, event("e3", "v1", "ZONE_DWELL", zone_id="billing", dwell_ms=30000))
    duplicate = ingest(client, event("e3", "v1", "ZONE_DWELL", zone_id="billing", dwell_ms=30000))
    assert duplicate["duplicate"] is True

    metrics = client.get("/stores/ST1008/metrics").json()
    assert metrics["unique_visitors"] == 1
    assert metrics["average_dwell_ms"] == 30000
    assert metrics["conversion_rate"] == 0


def test_staff_excluded_from_business_metrics(client):
    ingest(client, event("staff-1", "s1", "ENTRY", is_staff=True))
    ingest(client, event("staff-2", "s1", "ZONE_ENTER", zone_id="billing", is_staff=True))

    metrics = client.get("/stores/ST1008/metrics").json()
    assert metrics["unique_visitors"] == 0


def test_reentry_does_not_double_count(client):
    ingest(client, event("e1", "v1", "ENTRY"))
    ingest(client, event("e2", "v1", "EXIT"))
    ingest(client, event("e3", "v1", "REENTRY"))

    funnel = client.get("/stores/ST1008/funnel").json()
    assert funnel["entered"] == 1


def test_queue_abandonment(client):
    ingest(client, event("q1", "v1", "ENTRY"))
    ingest(client, event("q2", "v1", "BILLING_QUEUE_JOIN"))
    ingest(client, event("q3", "v1", "BILLING_QUEUE_ABANDON"))

    metrics = client.get("/stores/ST1008/metrics").json()
    assert metrics["queue_depth"] == 0
    assert metrics["abandonment_rate"] == 1.0


def test_zero_traffic_and_health(client):
    metrics = client.get("/stores/ST1008/metrics").json()
    assert metrics["unique_visitors"] == 0
    assert metrics["conversion_rate"] == 0
    health = client.get("/health").json()
    assert health["database"] == "ok"


def test_anomaly_queue_spike(client):
    for index in range(5):
        ingest(client, event(f"e{index}", f"v{index}", "ENTRY"))
        ingest(client, event(f"q{index}", f"v{index}", "BILLING_QUEUE_JOIN"))
    anomalies = client.get("/stores/ST1008/anomalies").json()
    assert any(item["anomaly_type"] == "QUEUE_SPIKE" for item in anomalies)


def test_zero_purchases_conversion_is_zero(client):
    for index in range(3):
        ingest(client, event(f"e{index}", f"v{index}", "ENTRY"))
    metrics = client.get("/stores/ST1008/metrics").json()
    assert metrics["converted_visitors"] == 0
    assert metrics["conversion_rate"] == 0
