import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import requests
from ultralytics import YOLO

from pipeline.events import PipelineEvent
from pipeline.queue import QueueState
from pipeline.reid import ReIdentifier
from pipeline.zones import crossed_line, load_layout


class StorePipeline:
    def __init__(self, layout_path: str, store_id: str, api_url: str | None, events_path: str) -> None:
        self.layout = load_layout(layout_path)
        self.store_id = store_id or self.layout.store_id
        self.api_url = api_url
        self.events_path = Path(events_path)
        self.model = YOLO("yolov8n.pt")
        self.reid = ReIdentifier()
        self.queue = QueueState(self.layout.queue_threshold)
        self.positions: dict[str, tuple[float, float]] = {}
        self.zones_by_visitor: dict[str, set[str]] = defaultdict(set)
        self.last_dwell_frame: dict[tuple[str, str], int] = {}
        self.staff_flags: dict[str, bool] = {}

    def process_video(self, video_path: str, camera_id: str) -> int:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        frame_index = 0
        emitted = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            results = self.model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0], verbose=False)
            events = self._events_from_frame(frame, results[0], camera_id, frame_index, fps)
            for event in events:
                self._emit(event)
                emitted += 1
            frame_index += 1
        cap.release()
        return emitted

    def _events_from_frame(self, frame, result, camera_id: str, frame_index: int, fps: float) -> list[PipelineEvent]:
        events: list[PipelineEvent] = []
        billing_visitors: set[str] = set()
        if result.boxes is None or result.boxes.id is None:
            return events
        boxes = result.boxes.xyxy.cpu().numpy()
        ids = result.boxes.id.cpu().numpy().astype(int)
        confidences = result.boxes.conf.cpu().numpy()

        for box, track_id, confidence in zip(boxes, ids, confidences):
            visitor_id = f"{camera_id}-{track_id}"
            x1, y1, x2, y2 = [int(v) for v in box]
            center = ((x1 + x2) / 2, y2)
            previous = self.positions.get(visitor_id)
            crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
            is_staff = self.staff_flags.get(visitor_id, False)

            if crossed_line(previous, center, self.layout.entry_line):
                reid_id, score = self.reid.match(crop)
                if reid_id:
                    visitor_id = reid_id
                    event_type = "REENTRY"
                else:
                    event_type = "ENTRY"
                    score = float(confidence)
                events.append(self._event(camera_id, visitor_id, event_type, is_staff, score, {"track_id": int(track_id)}))

            if crossed_line(previous, center, self.layout.exit_line):
                self.reid.remember_exit(visitor_id, crop)
                events.append(self._event(camera_id, visitor_id, "EXIT", is_staff, float(confidence), {"track_id": int(track_id)}))

            current_zones = {zone.zone_id for zone in self.layout.zones if zone.contains(center)}
            previous_zones = self.zones_by_visitor[visitor_id]
            for zone_id in current_zones - previous_zones:
                events.append(self._event(camera_id, visitor_id, "ZONE_ENTER", is_staff, float(confidence), {"track_id": int(track_id)}, zone_id))
            for zone_id in previous_zones - current_zones:
                events.append(self._event(camera_id, visitor_id, "ZONE_EXIT", is_staff, float(confidence), {"track_id": int(track_id)}, zone_id))
            for zone_id in current_zones:
                key = (visitor_id, zone_id)
                last = self.last_dwell_frame.get(key, frame_index)
                if frame_index - last >= int(fps * 30):
                    events.append(self._event(camera_id, visitor_id, "ZONE_DWELL", is_staff, float(confidence), {"track_id": int(track_id)}, zone_id, 30000))
                    self.last_dwell_frame[key] = frame_index
                elif key not in self.last_dwell_frame:
                    self.last_dwell_frame[key] = frame_index
            if current_zones & self.layout.billing_zone_ids:
                billing_visitors.add(visitor_id)
            self.zones_by_visitor[visitor_id] = current_zones
            self.positions[visitor_id] = center
            self.staff_flags[visitor_id] = is_staff

        events.extend(self.queue.update(self.store_id, camera_id, billing_visitors, self.staff_flags))
        return events

    def _event(self, camera_id: str, visitor_id: str, event_type: str, is_staff: bool, confidence: float, metadata: dict, zone_id: str | None = None, dwell_ms: int | None = None) -> PipelineEvent:
        return PipelineEvent(
            store_id=self.store_id,
            camera_id=camera_id,
            visitor_id=visitor_id,
            event_type=event_type,
            zone_id=zone_id,
            dwell_ms=dwell_ms,
            is_staff=is_staff,
            confidence=confidence,
            metadata=metadata,
        )

    def _emit(self, event: PipelineEvent) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        if self.api_url:
            requests.post(self.api_url, json=json.loads(event.model_dump_json()), timeout=5).raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", nargs="+", required=True)
    parser.add_argument("--layout", default="data/store_layout.json")
    parser.add_argument("--store-id", default="ST1008")
    parser.add_argument("--api-url", default="http://localhost:8000/events/ingest")
    parser.add_argument("--events-path", default="data/events.jsonl")
    args = parser.parse_args()

    pipeline = StorePipeline(args.layout, args.store_id, args.api_url, args.events_path)
    total = 0
    for video in args.videos:
        camera_id = Path(video).stem.replace(" ", "_")
        total += pipeline.process_video(video, camera_id)
    print(f"emitted_events={total}")


if __name__ == "__main__":
    main()
