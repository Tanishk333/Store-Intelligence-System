# Store Intelligence System

End-to-end store analytics from CCTV events to business metrics. The system is intentionally monolithic and reviewer-friendly: FastAPI, SQLite, YOLOv8/ByteTrack pipeline, staff classifier tooling, POS correlation, anomaly detection, and a React dashboard.

## What The System Computes

North star metric:

```text
Conversion Rate = Converted Visitors / Total Unique Visitors
```

Staff are excluded from business metrics. Re-entry does not inflate unique visitors. Purchases are correlated from POS transactions when a visitor was in the billing zone within the previous five minutes.

## Quick Start

```bash
docker compose up --build
```

Services:

- API: http://localhost:8000
- Dashboard: http://localhost:5173
- Health: http://localhost:8000/health

The API creates `data/store_intelligence.db` automatically and can ingest events from the CV pipeline or tests.

## Local Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Dashboard:

```bash
cd dashboard
npm install
npm run dev
```

Run tests:

```bash
pytest --cov=app --cov=pipeline
```

## Processing CCTV Footage

```bash
python -m pipeline.runner ^
  --videos "CCTV Footage/CAM 1.mp4" "CCTV Footage/CAM 2.mp4" ^
  --layout data/store_layout.json ^
  --store-id ST1008 ^
  --api-url http://localhost:8000/events/ingest
```

The runner emits each event to:

- SQLite through `POST /events/ingest`
- JSONL at `data/events.jsonl`

## Staff Classifier

Training data format:

```text
training/
  staff/
  customer/
```

Train/evaluate/predict:

```bash
python -m pipeline.staff.train_staff_classifier --data-dir training --output staff_classifier.pth
python -m pipeline.staff.evaluate_staff_classifier --data-dir training --model staff_classifier.pth
python -m pipeline.staff.predict_staff --model staff_classifier.pth --image crop.jpg
```

## Important Files

- `DESIGN.md`: architecture, event flow, database, edge cases, and diagrams
- `CHOICES.md`: trade-offs for YOLOv8, MobileNetV2, SQLite, ByteTrack, and monolith
- `app/`: FastAPI backend and business logic
- `pipeline/`: CV event generation, staff classifier, ReID, zones, queue logic
- `dashboard/`: React dashboard
- `tests/`: unit and API tests for the challenge edge cases
