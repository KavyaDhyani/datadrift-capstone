import os

# Point the app at a throwaway SQLite file before it is imported, so tests never touch Postgres.
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def snapshot(client):
    def register(**overrides):
        payload = {
            "dataset_name": "customer-churn",
            "version_tag": "v1.0-raw",
            "record_count": 120_000,
            "missing_pct": 2.5,
            "drift_score": 0.08,
        } | overrides
        # drift_score=None means "leave it out", so the backend scores the profile.
        payload = {key: value for key, value in payload.items() if value is not None}
        response = client.post("/api/datasets", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return register
