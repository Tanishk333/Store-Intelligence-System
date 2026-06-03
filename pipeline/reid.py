from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

try:
    import cv2
except Exception:
    cv2 = None


@dataclass
class ExitEmbedding:
    visitor_id: str
    embedding: np.ndarray
    timestamp: datetime


class ReIdentifier:
    def __init__(self, threshold: float = 0.78, max_age_minutes: int = 30) -> None:
        self.threshold = threshold
        self.max_age = timedelta(minutes=max_age_minutes)
        self.exits: deque[ExitEmbedding] = deque(maxlen=1000)
        self.model = None
        try:
            import torchreid

            self.model = torchreid.models.build_model("osnet_x0_25", num_classes=1, pretrained=True)
            self.model.eval()
        except Exception:
            self.model = None

    def embedding(self, crop: np.ndarray) -> np.ndarray:
        if self.model is not None:
            return self._torchreid_embedding(crop)
        return self._histogram_embedding(crop)

    def remember_exit(self, visitor_id: str, crop: np.ndarray, timestamp: datetime | None = None) -> None:
        self.exits.append(ExitEmbedding(visitor_id, self.embedding(crop), timestamp or datetime.now(timezone.utc)))

    def match(self, crop: np.ndarray, now: datetime | None = None) -> tuple[str | None, float]:
        now = now or datetime.now(timezone.utc)
        candidate = self.embedding(crop)
        best_id: str | None = None
        best_score = -1.0
        for item in list(self.exits):
            if now - item.timestamp > self.max_age:
                continue
            score = cosine_similarity(candidate, item.embedding)
            if score > best_score:
                best_id = item.visitor_id
                best_score = score
        if best_score >= self.threshold:
            return best_id, best_score
        return None, best_score

    def _torchreid_embedding(self, crop: np.ndarray) -> np.ndarray:
        if cv2 is None:
            return self._histogram_embedding(crop)
        import torch

        image = cv2.resize(crop, (128, 256))
        image = image[:, :, ::-1].astype("float32") / 255.0
        tensor = torch.from_numpy(image.transpose(2, 0, 1)).unsqueeze(0)
        with torch.no_grad():
            output = self.model(tensor)
        return output.detach().cpu().numpy().reshape(-1)

    def _histogram_embedding(self, crop: np.ndarray) -> np.ndarray:
        if crop.size == 0:
            return np.zeros(48, dtype=np.float32)
        if cv2 is None:
            flat = crop.astype("float32").reshape(-1)
            buckets = np.array_split(np.sort(flat), 48)
            hist = np.array([bucket.mean() if len(bucket) else 0 for bucket in buckets], dtype=np.float32)
            norm = np.linalg.norm(hist)
            return hist / norm if norm else hist
        resized = cv2.resize(crop, (64, 128))
        hist = cv2.calcHist([resized], [0, 1, 2], None, [4, 4, 3], [0, 256, 0, 256, 0, 256]).flatten()
        norm = np.linalg.norm(hist)
        return hist / norm if norm else hist


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
