from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class EventIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=64)
    camera_id: str = Field(min_length=1, max_length=64)
    visitor_id: str = Field(min_length=1, max_length=128)
    event_type: EventType
    timestamp: datetime
    zone_id: str | None = None
    dwell_ms: int | None = Field(default=None, ge=0)
    is_staff: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("zone_id")
    @classmethod
    def zone_required_for_zone_events(cls, zone_id: str | None, info):
        event_type = info.data.get("event_type")
        if event_type in {
            EventType.ZONE_ENTER,
            EventType.ZONE_EXIT,
            EventType.ZONE_DWELL,
        } and not zone_id:
            raise ValueError("zone_id is required for zone events")
        return zone_id


class EventOut(EventIn):
    duplicate: bool = False


class MetricsOut(BaseModel):
    store_id: str
    unique_visitors: int
    converted_visitors: int
    conversion_rate: float
    average_dwell_ms: float
    queue_depth: int
    abandonment_rate: float


class FunnelOut(BaseModel):
    store_id: str
    entered: int
    zone_visit: int
    billing: int
    purchase: int


class HeatmapZone(BaseModel):
    zone_id: str
    visits: int
    dwell_ms: int
    average_dwell_ms: float


class HeatmapOut(BaseModel):
    store_id: str
    zones: list[HeatmapZone]


class AnomalyOut(BaseModel):
    anomaly_type: str
    severity: str
    description: str
    suggested_action: str
    detected_at: datetime


class HealthOut(BaseModel):
    status: str
    database: str
    last_event_timestamp: datetime | None
    stale_feed_warning: bool
