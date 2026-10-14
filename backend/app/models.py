from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("dataset_name", "version_tag", name="uq_dataset_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version_tag: Mapped[str] = mapped_column(String(60), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    drift_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="VERIFIED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
