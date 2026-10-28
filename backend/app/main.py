from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .drift import column_drift, drift_score
from .metrics import DRIFT_FLAGS, SNAPSHOTS_REGISTERED
from .models import Dataset
from .schemas import DatasetCreate, DatasetOut, DatasetUpdate, Status, SummaryOut

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Instrumentator(excluded_handlers=["/metrics", "/health", "/ready"]).instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)


def status_for(drift_score: float) -> str:
    return "DRIFT_DETECTED" if drift_score >= settings.drift_threshold else "VERIFIED"


def latest_baseline(db: Session, dataset_name: str) -> Dataset | None:
    """The newest VERIFIED snapshot of this dataset that carries a profile."""
    query = (
        select(Dataset)
        .where(Dataset.dataset_name == dataset_name, Dataset.status == "VERIFIED", Dataset.profile.is_not(None))
        .order_by(Dataset.created_at.desc(), Dataset.id.desc())
        .limit(1)
    )
    return db.scalars(query).first()


def score_snapshot(db: Session, payload: DatasetCreate) -> dict:
    """Decide the drift score: the client's score wins; otherwise compare the profile with the baseline."""
    if payload.drift_score is not None:
        return {"drift_score": payload.drift_score, "drift_method": "provided"}
    if payload.profile is None:
        return {"drift_score": 0.0, "drift_method": "unscored"}
    baseline = latest_baseline(db, payload.dataset_name)
    if baseline is None:
        return {"drift_score": 0.0, "drift_method": "baseline"}
    columns = column_drift(baseline.profile, payload.profile)
    return {
        "drift_score": drift_score(columns),
        "drift_method": "computed",
        "column_drift": columns,
        "baseline_id": baseline.id,
    }


def get_or_404(db: Session, dataset_id: int) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset snapshot not found")
    return dataset


@app.get("/")
def root():
    return {"service": settings.app_name, "version": settings.app_version, "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "UP"}


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "READY"}


@app.get("/api/datasets", response_model=list[DatasetOut])
def list_datasets(status_filter: Status | None = Query(default=None, alias="status"), db: Session = Depends(get_db)):
    query = select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id.desc())
    if status_filter:
        query = query.where(Dataset.status == status_filter)
    return list(db.scalars(query))


@app.get("/api/datasets/summary", response_model=SummaryOut)
def summary(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Dataset.status, func.count(Dataset.id)).group_by(Dataset.status)).all())
    avg = db.scalar(select(func.avg(Dataset.drift_score)).where(Dataset.status != "ARCHIVED"))
    return SummaryOut(
        total=sum(counts.values()),
        verified=counts.get("VERIFIED", 0),
        drift_detected=counts.get("DRIFT_DETECTED", 0),
        archived=counts.get("ARCHIVED", 0),
        avg_drift_score=round(avg or 0.0, 3),
        drift_threshold=settings.drift_threshold,
    )


@app.get("/api/datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, dataset_id)


@app.post("/api/datasets", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
def register_dataset(payload: DatasetCreate, db: Session = Depends(get_db)):
    scored = score_snapshot(db, payload)
    dataset = Dataset(**payload.model_dump(exclude={"drift_score"}), **scored, status=status_for(scored["drift_score"]))
    db.add(dataset)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"{payload.dataset_name}@{payload.version_tag} is already registered"
        ) from exc
    db.refresh(dataset)
    SNAPSHOTS_REGISTERED.inc()
    if dataset.status == "DRIFT_DETECTED":
        DRIFT_FLAGS.labels(dataset.dataset_name).inc()
    return dataset


@app.put("/api/datasets/{dataset_id}", response_model=DatasetOut)
def update_dataset(dataset_id: int, payload: DatasetUpdate, db: Session = Depends(get_db)):
    dataset = get_or_404(db, dataset_id)
    previous_status = dataset.status
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(dataset, key, value)
    if "drift_score" in changes:
        dataset.drift_method = "provided"
    # A new drift score re-evaluates the status unless the caller set one explicitly.
    if "drift_score" in changes and "status" not in changes and dataset.status != "ARCHIVED":
        dataset.status = status_for(dataset.drift_score)
    db.commit()
    db.refresh(dataset)
    if dataset.status == "DRIFT_DETECTED" and previous_status != "DRIFT_DETECTED":
        DRIFT_FLAGS.labels(dataset.dataset_name).inc()
    return dataset


@app.delete("/api/datasets/{dataset_id}", response_model=DatasetOut)
def delete_dataset(dataset_id: int, purge: bool = False, db: Session = Depends(get_db)):
    """Archive a snapshot (default) or permanently purge it with ?purge=true."""
    dataset = get_or_404(db, dataset_id)
    if purge:
        db.delete(dataset)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    dataset.status = "ARCHIVED"
    db.commit()
    db.refresh(dataset)
    return dataset
