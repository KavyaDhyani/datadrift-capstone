"""Drift between two snapshot profiles, scored with the Jensen-Shannon distance.

A profile maps each column to a histogram: bucket or category label -> count. Two histograms of the same column
are compared with the Jensen-Shannon distance (base 2), which is symmetric and always between 0.0 (identical) and
1.0 (no overlap). A column present in only one of the two profiles is a schema change and scores 1.0.
The snapshot's drift score is its worst column.
"""

import math

Histogram = dict[str, float]
Profile = dict[str, Histogram]


def _probabilities(counts: Histogram, buckets: list[str]) -> list[float] | None:
    total = sum(counts.get(bucket, 0.0) for bucket in buckets)
    if total <= 0:
        return None
    return [counts.get(bucket, 0.0) / total for bucket in buckets]


def js_distance(baseline: Histogram, current: Histogram) -> float:
    buckets = sorted(set(baseline) | set(current))
    p = _probabilities(baseline, buckets)
    q = _probabilities(current, buckets)
    if p is None or q is None:
        # An empty histogram only matches another empty one.
        return 0.0 if p is None and q is None else 1.0
    m = [(a + b) / 2 for a, b in zip(p, q, strict=True)]

    def kl_to_m(dist: list[float]) -> float:
        return sum(a * math.log2(a / b) for a, b in zip(dist, m, strict=True) if a > 0)

    divergence = (kl_to_m(p) + kl_to_m(q)) / 2
    return round(min(1.0, math.sqrt(max(0.0, divergence))), 4)


def column_drift(baseline: Profile, current: Profile) -> dict[str, float]:
    columns = sorted(set(baseline) | set(current))
    return {
        column: js_distance(baseline[column], current[column]) if column in baseline and column in current else 1.0
        for column in columns
    }


def drift_score(columns: dict[str, float]) -> float:
    return max(columns.values(), default=0.0)
