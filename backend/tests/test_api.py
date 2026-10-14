def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_ready_checks_database(client):
    assert client.get("/ready").json() == {"status": "READY"}


def test_register_low_drift_snapshot_is_verified(snapshot):
    created = snapshot(drift_score=0.05)
    assert created["id"] > 0
    assert created["status"] == "VERIFIED"
    assert created["version_tag"] == "v1.0-raw"


def test_register_high_drift_snapshot_is_flagged(snapshot):
    created = snapshot(version_tag="v2.0-raw", drift_score=0.72)
    assert created["status"] == "DRIFT_DETECTED"


def test_register_duplicate_version_conflicts(client, snapshot):
    snapshot()
    response = client.post(
        "/api/datasets",
        json={"dataset_name": "customer-churn", "version_tag": "v1.0-raw", "record_count": 10},
    )
    assert response.status_code == 409


def test_register_rejects_out_of_range_drift(client):
    response = client.post(
        "/api/datasets",
        json={"dataset_name": "fraud-events", "version_tag": "v1", "record_count": 10, "drift_score": 1.5},
    )
    assert response.status_code == 422


def test_list_datasets_and_filter_by_status(client, snapshot):
    snapshot(version_tag="v1", drift_score=0.1)
    snapshot(version_tag="v2", drift_score=0.9)
    assert len(client.get("/api/datasets").json()) == 2
    flagged = client.get("/api/datasets", params={"status": "DRIFT_DETECTED"}).json()
    assert [d["version_tag"] for d in flagged] == ["v2"]


def test_get_unknown_dataset_returns_404(client):
    assert client.get("/api/datasets/9999").status_code == 404


def test_flag_drift_with_put(client, snapshot):
    created = snapshot(drift_score=0.1)
    response = client.put(f"/api/datasets/{created['id']}", json={"status": "DRIFT_DETECTED"})
    assert response.status_code == 200
    assert response.json()["status"] == "DRIFT_DETECTED"


def test_new_drift_score_recomputes_status(client, snapshot):
    created = snapshot(drift_score=0.1)
    updated = client.put(f"/api/datasets/{created['id']}", json={"drift_score": 0.45}).json()
    assert updated["drift_score"] == 0.45
    assert updated["status"] == "DRIFT_DETECTED"


def test_delete_archives_by_default(client, snapshot):
    created = snapshot()
    response = client.delete(f"/api/datasets/{created['id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "ARCHIVED"
    assert client.get(f"/api/datasets/{created['id']}").status_code == 200


def test_delete_with_purge_removes_snapshot(client, snapshot):
    created = snapshot()
    assert client.delete(f"/api/datasets/{created['id']}", params={"purge": True}).status_code == 204
    assert client.get(f"/api/datasets/{created['id']}").status_code == 404


def test_summary_averages_non_archived_drift(client, snapshot):
    snapshot(version_tag="v1", drift_score=0.1)
    snapshot(version_tag="v2", drift_score=0.5)
    archived = snapshot(version_tag="v0", drift_score=0.9)
    client.delete(f"/api/datasets/{archived['id']}")
    summary = client.get("/api/datasets/summary").json()
    assert summary["total"] == 3
    assert summary["verified"] == 1
    assert summary["drift_detected"] == 1
    assert summary["archived"] == 1
    assert summary["avg_drift_score"] == 0.3


def test_metrics_expose_registry_state(client, snapshot):
    snapshot(drift_score=0.9)
    body = client.get("/metrics").text
    assert 'datadrift_datasets{status="DRIFT_DETECTED"} 1.0' in body
    assert "datadrift_drift_flags_total" in body
    assert "http_requests_total" in body
