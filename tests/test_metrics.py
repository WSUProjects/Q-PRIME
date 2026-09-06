from types import SimpleNamespace

from qprime.metrics import DashboardMetrics


class PlacementCollection:
    def __init__(self, documents):
        self.documents = documents

    def find(self, _query):
        return iter(self.documents)


class OverviewCollection:
    def count_documents(self, query):
        return 3 if not query else 0

    def aggregate(self, pipeline):
        group_id = pipeline[0]["$group"]["_id"]
        if group_id == "$recommended_tier":
            return [
                {"_id": "edge", "count": 1},
                {"_id": "cloud", "count": 1},
                {"_id": "both", "count": 1},
            ]
        return [
            {"_id": {"key": "Legacy device", "tier": "edge"}, "count": 1},
            {"_id": {"key": "Legacy device", "tier": "both"}, "count": 1},
            {"_id": {"key": "Cloud device", "tier": "cloud"}, "count": 1},
        ]


def test_overview_projects_legacy_both_counts_as_edge():
    repository = SimpleNamespace(
        db=SimpleNamespace(placement_decisions=OverviewCollection()),
        record_count=lambda _collection: 0,
    )

    result = DashboardMetrics(repository).overview()

    assert result["records_processed"] == 3
    assert result["stored_at_edge"] == 2
    assert result["sent_to_cloud"] == 1
    assert result["placement_split"] == {"edge": 2, "cloud": 1}
    assert result["placement_by_device"] == [
        {"device": "Legacy device", "edge": 2, "cloud": 0},
        {"device": "Cloud device", "edge": 0, "cloud": 1},
    ]


def test_sensitivity_replay_resolves_equal_scores_to_edge():
    document = {
        "recommended_tier": "both",
        "device_name": "Boundary device",
        "pii_detected": False,
        "analysis": {"strict_override": False, "privacy_weight": 0.0},
        "qoc": {
            metric: {"score": 0.0}
            for metric in (
                "timeliness",
                "completeness",
                "correctness",
                "resolution",
                "significance",
            )
        },
    }
    repository = SimpleNamespace(
        db=SimpleNamespace(placement_decisions=PlacementCollection([document]))
    )

    result = DashboardMetrics(repository).sensitivity(
        {"temporal": 1, "spatial": 1, "privacy": 1},
        privacy_floor=0,
        force_pii_edge=False,
    )

    assert result["replayed"] == {"edge": 1}
    assert result["original"] == {"edge": 1}
    assert result["placements_changed"] == 0
    assert result["by_device"] == {"Boundary device": {"edge": 1}}


def test_decisions_projects_legacy_both_as_edge_without_losing_history():
    legacy = {
        "recommended_tier": "both",
        "analysis": {"decision": "Both", "reason": "score comparison"},
        "actual_backends": ["mongodb_edge", "mongodb_cloud_fallback"],
    }
    repository = SimpleNamespace(placements=lambda _filters, _limit: [legacy])

    result = DashboardMetrics(repository).decisions({}, 10)

    assert result["decisions"] == [
        {
            "recommended_tier": "edge",
            "legacy_recommended_tier": "both",
            "analysis": {
                "decision": "Edge",
                "legacy_decision": "Both",
                "reason": "score comparison",
            },
            "actual_backends": ["mongodb_edge", "mongodb_cloud_fallback"],
        }
    ]
