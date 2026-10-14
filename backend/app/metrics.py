"""Business metrics for Prometheus, on top of the HTTP metrics from the instrumentator."""

from prometheus_client import REGISTRY, Counter
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from .db import SessionLocal
from .models import Dataset

SNAPSHOTS_REGISTERED = Counter("datadrift_snapshots_registered_total", "Dataset snapshots registered through the API")
DRIFT_FLAGS = Counter("datadrift_drift_flags_total", "Times a snapshot was moved into DRIFT_DETECTED", ["dataset_name"])


class RegistryCollector:
    """Reads registry state from the database at scrape time.

    Every backend replica reports the same values, so dashboards should use max() rather than sum().
    """

    def collect(self):
        by_status = GaugeMetricFamily(
            "datadrift_datasets", "Dataset snapshots in the registry by status", labels=["status"]
        )
        avg_drift = GaugeMetricFamily("datadrift_avg_drift_score", "Average drift score of non-archived snapshots")
        drift = GaugeMetricFamily(
            "datadrift_drift_score",
            "Drift score of each non-archived snapshot",
            labels=["dataset_name", "version_tag", "status"],
        )
        try:
            with SessionLocal() as db:
                counts = dict(db.execute(select(Dataset.status, func.count(Dataset.id)).group_by(Dataset.status)).all())
                active = db.execute(
                    select(Dataset.dataset_name, Dataset.version_tag, Dataset.drift_score, Dataset.status).where(
                        Dataset.status != "ARCHIVED"
                    )
                ).all()
        except SQLAlchemyError:
            # Database unreachable: skip business metrics, keep the HTTP metrics flowing.
            return

        for status in ("VERIFIED", "DRIFT_DETECTED", "ARCHIVED"):
            by_status.add_metric([status], counts.get(status, 0))
        avg_drift.add_metric([], sum(row.drift_score for row in active) / len(active) if active else 0.0)
        for row in active:
            drift.add_metric([row.dataset_name, row.version_tag, row.status], row.drift_score)
        yield by_status
        yield avg_drift
        yield drift


REGISTRY.register(RegistryCollector())
