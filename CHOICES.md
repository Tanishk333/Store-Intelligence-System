# Engineering Choices

## Decision 1: YOLOv8 vs Alternatives

Options considered:

- YOLOv8n pretrained
- Faster R-CNN
- OpenCV HOG person detector
- Training a custom detector

AI suggestion:

Use a pretrained detector and avoid custom training unless the dataset demands it.

Final choice:

YOLOv8n pretrained for person detection only.

Reasoning:

YOLOv8n is fast, accurate enough for retail CCTV, easy to run locally, and integrates directly with ByteTrack through Ultralytics. The challenge explicitly says not to train YOLO, so pretrained YOLOv8n maximizes correctness while keeping setup simple.

Risks:

Small or occluded people may be missed, especially in crowded entry areas.

Trade-offs:

YOLOv8n is less accurate than larger YOLO variants but faster and easier to run on commodity hardware. For this challenge, an explainable end-to-end system is more valuable than squeezing out marginal detector accuracy.

## Decision 2: MobileNetV2 vs Alternatives

Options considered:

- MobileNetV2 transfer learning
- ResNet18 transfer learning
- CLIP zero-shot classification
- Uniform color rules

AI suggestion:

Use a compact supervised classifier because staff/customer distinction is domain-specific and should be testable.

Final choice:

MobileNetV2 with frozen backbone and trained classifier head.

Reasoning:

MobileNetV2 is small, fast, and suitable for cropped person images. Freezing the backbone reduces training cost and overfitting risk. The classifier head is easy to explain in an interview and the training script reports accuracy, precision, recall, and confusion matrix.

Risks:

It needs representative staff/customer examples. Uniform changes or poor lighting can reduce precision.

Trade-offs:

Rules based on uniform color are simpler but brittle. ResNet18 may be more accurate but heavier. MobileNetV2 is the best balance for edge deployment and hiring-challenge clarity.

## Decision 3: SQLite vs PostgreSQL

Options considered:

- SQLite
- PostgreSQL
- In-memory storage

AI suggestion:

Use SQLite for deterministic local deployment unless concurrent write volume requires PostgreSQL.

Final choice:

SQLite with SQLAlchemy.

Reasoning:

The challenge requires Docker Compose and no complex infrastructure. SQLite starts with no service dependency, persists data, supports indexes, and is adequate for a five-video evaluation dataset.

Risks:

SQLite has limited write concurrency compared with PostgreSQL.

Trade-offs:

PostgreSQL is better for multi-store production scale, but SQLite improves reproducibility and makes the reviewer experience simpler.

## Decision 4: ByteTrack vs DeepSORT

Options considered:

- ByteTrack
- DeepSORT
- SORT
- Optical-flow-only tracking

AI suggestion:

Use ByteTrack for stable tracking and keep ReID as a separate re-entry concern.

Final choice:

ByteTrack through Ultralytics tracking.

Reasoning:

ByteTrack performs well with detector outputs and handles low-confidence detections better than basic SORT. DeepSORT includes appearance embeddings, but this project already uses TorchReID for cross-exit re-identification, so ByteTrack keeps within-camera tracking simple.

Risks:

Long occlusions can still switch track IDs.

Trade-offs:

DeepSORT can improve identity continuity but adds another appearance model and more tuning. ByteTrack is simpler and appropriate for an explainable pipeline.

## Decision 5: Monolith vs Microservices

Options considered:

- FastAPI monolith
- Separate ingestion, analytics, and dashboard services
- Event bus with workers

AI suggestion:

Prefer a monolith because the rubric rewards working end-to-end behavior, production hygiene, and explainable decisions.

Final choice:

FastAPI monolith plus React dashboard.

Reasoning:

The entire system can be understood in one process: ingest events, update sessions, compute metrics, serve dashboards. This avoids Kafka, Redis, Kubernetes, and operational complexity that would not improve challenge scoring.

Risks:

At very high camera counts the monolith would need scaling or worker separation.

Trade-offs:

Microservices could scale independently, but they add deployment and failure modes. The monolith is the right engineering choice for a local hiring challenge and a five-video dataset.
