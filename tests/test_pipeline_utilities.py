import json
from datetime import datetime, timedelta, timezone

import numpy as np

from pipeline.layout_converter import convert_xlsx_to_layout
from pipeline.reid import ReIdentifier
from pipeline.zones import Zone, load_layout


def test_zone_contains_without_opencv():
    zone = Zone("z1", "Zone 1", "shopping", [(0, 0), (10, 0), (10, 10), (0, 10)])
    assert zone.contains((5, 5)) is True
    assert zone.contains((20, 5)) is False


def test_load_layout(tmp_path):
    path = tmp_path / "layout.json"
    path.write_text(
        json.dumps(
            {
                "store_id": "S1",
                "camera_defaults": {"entry_line": [[0, 0], [1, 0]], "exit_line": [[0, 1], [1, 1]]},
                "queue_threshold": 2,
                "zones": [{"zone_id": "billing", "name": "Billing", "type": "billing", "polygon": [[0, 0], [1, 0], [1, 1]]}],
            }
        ),
        encoding="utf-8",
    )
    layout = load_layout(path)
    assert layout.store_id == "S1"
    assert layout.billing_zone_ids == {"billing"}


def test_reidentifier_fallback_match():
    reid = ReIdentifier(threshold=0.7, max_age_minutes=1)
    crop = np.ones((8, 8, 3), dtype=np.uint8) * 120
    reid.remember_exit("v1", crop, datetime.now(timezone.utc))
    visitor_id, score = reid.match(crop, datetime.now(timezone.utc))
    assert visitor_id == "v1"
    assert score >= 0.7


def test_reidentifier_ignores_old_exit():
    reid = ReIdentifier(threshold=0.7, max_age_minutes=1)
    crop = np.ones((8, 8, 3), dtype=np.uint8)
    reid.remember_exit("v1", crop, datetime.now(timezone.utc) - timedelta(minutes=5))
    visitor_id, _ = reid.match(crop, datetime.now(timezone.utc))
    assert visitor_id is None


def test_layout_converter_fallback_for_sparse_xlsx(tmp_path):
    import openpyxl

    source = tmp_path / "layout.xlsx"
    workbook = openpyxl.Workbook()
    workbook.save(source)
    output = convert_xlsx_to_layout(source, tmp_path / "store_layout.json", "ST1008")
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["store_id"] == "ST1008"
    assert any(zone["zone_id"] == "billing" for zone in data["zones"])
