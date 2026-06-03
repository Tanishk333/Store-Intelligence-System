import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import cv2
except Exception:
    cv2 = None


@dataclass(frozen=True)
class Zone:
    zone_id: str
    name: str
    type: str
    polygon: list[tuple[int, int]]

    def contains(self, point: tuple[float, float]) -> bool:
        if cv2 is None:
            return _point_in_polygon(point, self.polygon)
        contour = np.array(self.polygon, dtype=np.int32)
        return cv2.pointPolygonTest(contour, point, False) >= 0


@dataclass(frozen=True)
class StoreLayout:
    store_id: str
    zones: list[Zone]
    entry_line: tuple[tuple[int, int], tuple[int, int]]
    exit_line: tuple[tuple[int, int], tuple[int, int]]
    queue_threshold: int

    @property
    def billing_zone_ids(self) -> set[str]:
        return {zone.zone_id for zone in self.zones if zone.type == "billing" or zone.zone_id == "billing"}


def load_layout(path: str | Path) -> StoreLayout:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    defaults = data.get("camera_defaults", {})
    zones = [
        Zone(
            zone_id=item["zone_id"],
            name=item.get("name", item["zone_id"]),
            type=item.get("type", "shopping"),
            polygon=[tuple(point) for point in item["polygon"]],
        )
        for item in data.get("zones", [])
    ]
    return StoreLayout(
        store_id=data.get("store_id", "UNKNOWN"),
        zones=zones,
        entry_line=tuple(tuple(point) for point in defaults.get("entry_line", [[0, 0], [1, 0]])),
        exit_line=tuple(tuple(point) for point in defaults.get("exit_line", [[0, 1], [1, 1]])),
        queue_threshold=int(data.get("queue_threshold", 3)),
    )


def crossed_line(previous: tuple[float, float] | None, current: tuple[float, float], line: tuple[tuple[int, int], tuple[int, int]]) -> bool:
    if previous is None:
        return False
    return _side(previous, line) * _side(current, line) < 0


def _side(point: tuple[float, float], line: tuple[tuple[int, int], tuple[int, int]]) -> float:
    (x1, y1), (x2, y2) = line
    return (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1)


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[int, int]]) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, current in enumerate(polygon):
        xi, yi = current
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        if intersects:
            inside = not inside
        j = i
    return inside
