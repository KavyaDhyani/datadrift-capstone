import pytest

from app.drift import column_drift, drift_score, js_distance

BASELINE = {
    "plan": {"basic": 600, "pro": 300, "team": 100},
    "age": {"18-30": 400, "31-60": 500, "60+": 100},
}
SHIFTED = {
    "plan": {"basic": 100, "pro": 300, "team": 600},
    "age": {"18-30": 400, "31-60": 500, "60+": 100},
}


def profiled(snapshot, version_tag, profile, **overrides):
    return snapshot(version_tag=version_tag, drift_score=None, profile=profile, **overrides)


def test_identical_histograms_have_zero_distance():
    assert js_distance({"a": 5, "b": 5}, {"a": 50, "b": 50}) == 0.0


def test_disjoint_histograms_have_distance_one():
    assert js_distance({"a": 10}, {"b": 10}) == 1.0


def test_distance_is_symmetric_and_bounded():
    p, q = {"a": 9, "b": 1}, {"a": 2, "b": 8}
    assert js_distance(p, q) == js_distance(q, p)
    assert 0.0 < js_distance(p, q) < 1.0


def test_empty_histogram_only_matches_empty():
    assert js_distance({}, {}) == 0.0
    assert js_distance({}, {"a": 3}) == 1.0


def test_added_or_dropped_column_scores_one():
    columns = column_drift({"plan": {"basic": 1}}, {"region": {"eu": 1}})
    assert columns == {"plan": 1.0, "region": 1.0}


def test_score_is_the_worst_column():
    assert drift_score({"plan": 0.12, "age": 0.41}) == 0.41
    assert drift_score({}) == 0.0


def test_first_profiled_snapshot_becomes_the_baseline(snapshot):
    first = profiled(snapshot, "v1", BASELINE)
    assert first["drift_method"] == "baseline"
    assert first["drift_score"] == 0.0
    assert first["status"] == "VERIFIED"
    assert first["baseline_id"] is None


def test_unchanged_snapshot_is_verified_against_baseline(snapshot):
    base = profiled(snapshot, "v1", BASELINE)
    same = profiled(snapshot, "v2", {col: {k: v * 2 for k, v in hist.items()} for col, hist in BASELINE.items()})
    assert same["drift_method"] == "computed"
    assert same["baseline_id"] == base["id"]
    assert same["drift_score"] == 0.0
    assert same["column_drift"] == {"age": 0.0, "plan": 0.0}
    assert same["status"] == "VERIFIED"


def test_shifted_snapshot_is_flagged(snapshot):
    profiled(snapshot, "v1", BASELINE)
    shifted = profiled(snapshot, "v2", SHIFTED)
    assert shifted["column_drift"]["age"] == 0.0
    assert shifted["column_drift"]["plan"] == pytest.approx(shifted["drift_score"])
    assert shifted["drift_score"] >= 0.30
    assert shifted["status"] == "DRIFT_DETECTED"


def test_flagged_snapshots_never_become_the_baseline(snapshot):
    base = profiled(snapshot, "v1", BASELINE)
    profiled(snapshot, "v2", SHIFTED)
    third = profiled(snapshot, "v3", SHIFTED)
    assert third["baseline_id"] == base["id"]
    assert third["status"] == "DRIFT_DETECTED"


def test_baselines_are_per_dataset(snapshot):
    profiled(snapshot, "v1", BASELINE)
    other = profiled(snapshot, "v1", SHIFTED, dataset_name="fraud-events")
    assert other["drift_method"] == "baseline"


def test_provided_score_wins_over_profile(snapshot):
    profiled(snapshot, "v1", BASELINE)
    manual = snapshot(version_tag="v2", drift_score=0.05, profile=SHIFTED)
    assert manual["drift_method"] == "provided"
    assert manual["drift_score"] == 0.05
    assert manual["column_drift"] is None


def test_snapshot_without_score_or_profile_is_unscored(snapshot):
    created = snapshot(drift_score=None)
    assert created["drift_method"] == "unscored"
    assert created["drift_score"] == 0.0


def test_negative_counts_are_rejected(client):
    response = client.post(
        "/api/datasets",
        json={"dataset_name": "x", "version_tag": "v1", "record_count": 1, "profile": {"plan": {"basic": -1}}},
    )
    assert response.status_code == 422


def test_manual_score_update_marks_method_provided(client, snapshot):
    profiled(snapshot, "v1", BASELINE)
    shifted = profiled(snapshot, "v2", SHIFTED)
    updated = client.put(f"/api/datasets/{shifted['id']}", json={"drift_score": 0.1}).json()
    assert updated["drift_method"] == "provided"
    assert updated["status"] == "VERIFIED"
