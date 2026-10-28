from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["VERIFIED", "DRIFT_DETECTED", "ARCHIVED"]
DriftMethod = Literal["provided", "computed", "baseline", "unscored"]
# Column name -> histogram (bucket or category label -> count).
Profile = dict[str, dict[str, Annotated[float, Field(ge=0.0)]]]


class DatasetCreate(BaseModel):
    dataset_name: str = Field(min_length=1, max_length=120, examples=["customer-churn"])
    version_tag: str = Field(min_length=1, max_length=60, examples=["v1.2-cleaned"])
    record_count: int = Field(ge=0, examples=[125000])
    missing_pct: float = Field(default=0.0, ge=0.0, le=100.0, examples=[1.8])
    # Leave drift_score out and send a profile to have drift computed against the last verified baseline.
    drift_score: float | None = Field(default=None, ge=0.0, le=1.0, examples=[0.12])
    profile: Profile | None = Field(
        default=None, examples=[{"plan": {"basic": 610, "pro": 290, "team": 100}, "age": {"18-30": 400, "31-60": 600}}]
    )


class DatasetUpdate(BaseModel):
    record_count: int | None = Field(default=None, ge=0)
    missing_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    drift_score: float | None = Field(default=None, ge=0.0, le=1.0)
    status: Status | None = None


class DatasetOut(BaseModel):
    id: int
    dataset_name: str
    version_tag: str
    record_count: int
    missing_pct: float
    drift_score: float
    status: Status
    drift_method: DriftMethod
    column_drift: dict[str, float] | None
    baseline_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SummaryOut(BaseModel):
    total: int
    verified: int
    drift_detected: int
    archived: int
    avg_drift_score: float
    drift_threshold: float
