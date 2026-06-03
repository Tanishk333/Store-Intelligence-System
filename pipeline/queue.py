from dataclasses import dataclass, field

from pipeline.events import PipelineEvent


@dataclass
class QueueState:
    threshold: int = 3
    active_visitors: set[str] = field(default_factory=set)
    queued_visitors: set[str] = field(default_factory=set)

    def update(self, store_id: str, camera_id: str, billing_visitors: set[str], staff_flags: dict[str, bool]) -> list[PipelineEvent]:
        events: list[PipelineEvent] = []
        self.active_visitors = billing_visitors
        queue_exists = len([v for v in billing_visitors if not staff_flags.get(v, False)]) >= self.threshold

        if queue_exists:
            for visitor_id in billing_visitors - self.queued_visitors:
                events.append(
                    PipelineEvent(
                        store_id=store_id,
                        camera_id=camera_id,
                        visitor_id=visitor_id,
                        event_type="BILLING_QUEUE_JOIN",
                        is_staff=staff_flags.get(visitor_id, False),
                        metadata={"queue_depth": len(billing_visitors)},
                    )
                )
                self.queued_visitors.add(visitor_id)

        abandoned = self.queued_visitors - billing_visitors
        for visitor_id in abandoned:
            events.append(
                PipelineEvent(
                    store_id=store_id,
                    camera_id=camera_id,
                    visitor_id=visitor_id,
                    event_type="BILLING_QUEUE_ABANDON",
                    is_staff=staff_flags.get(visitor_id, False),
                    metadata={"queue_depth": len(billing_visitors)},
                )
            )
            self.queued_visitors.remove(visitor_id)
        return events
