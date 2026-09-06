from qprime.query_router import QueryRouter


class QueryMetricRepository:
    def __init__(self):
        self.metrics = []

    def store_query_metric(self, metric):
        self.metrics.append(metric)


class LocalCloud:
    @staticmethod
    def athena_configured():
        return False


class LegacyResultRouter(QueryRouter):
    def _presto(self, sql):
        if "information_schema" in sql:
            return []
        if " AS decision" in sql:
            return [{"decision": "both"}]
        return [{"recommended_tier": "both", "actual_backend": "mongodb_edge"}]


def test_query_results_project_legacy_both_as_edge():
    repository = QueryMetricRepository()
    router = LegacyResultRouter(repository, LocalCloud())

    result = router.execute(
        "SELECT recommended_tier, actual_backend FROM qprime.continuum",
        "edge",
    )

    assert result["results"] == [
        {"recommended_tier": "edge", "actual_backend": "mongodb_edge"}
    ]
    assert len(repository.metrics) == 1


def test_query_results_project_aliased_legacy_tier_as_edge():
    router = LegacyResultRouter(QueryMetricRepository(), LocalCloud())

    result = router.execute(
        "SELECT recommended_tier AS decision FROM qprime.continuum",
        "edge",
    )

    assert result["results"] == [{"decision": "edge"}]
