import numpy as np

from pipeline.queue import QueueState
from pipeline.reid import cosine_similarity
from pipeline.zones import crossed_line


def test_entry_detection_line_crossing():
    line = ((0, 10), (100, 10))
    assert crossed_line((50, 0), (50, 20), line) is True


def test_exit_detection_no_crossing():
    line = ((0, 10), (100, 10))
    assert crossed_line((50, 0), (60, 0), line) is False


def test_queue_join_and_abandon():
    queue = QueueState(threshold=2)
    events = queue.update("ST1008", "CAM_1", {"v1", "v2"}, {"v1": False, "v2": False})
    assert [event.event_type for event in events].count("BILLING_QUEUE_JOIN") == 2
    events = queue.update("ST1008", "CAM_1", {"v2"}, {"v1": False, "v2": False})
    assert any(event.event_type == "BILLING_QUEUE_ABANDON" and event.visitor_id == "v1" for event in events)


def test_reid_cosine_similarity():
    assert cosine_similarity(np.array([1, 0]), np.array([1, 0])) == 1.0
    assert cosine_similarity(np.array([0, 0]), np.array([1, 0])) == 0.0
