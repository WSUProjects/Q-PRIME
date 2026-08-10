"""Read-only placement-aware SQL routing across MongoDB/Presto and Athena."""

import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import prestodb
from sqlglot import exp, parse

from .cloud import AwsCloudAdapter, cloud_adapter
from .repository import MongoRepository, repository


LOGICAL_DATABASE = os.getenv("CONTINUUM_DB", "qprime")
LOGICAL_TABLE = os.getenv("CONTINUUM_TABLE", "continuum")
PRESTO_URL = os.getenv("PRESTO_URL", "http://presto:8080")
QUERY_MAX_ROWS = int(os.getenv("QUERY_MAX_ROWS", "1000"))
QUERY_TIMEOUT_S = int(os.getenv("QUERY_TIMEOUT_S", "60"))

# Columns the logical `qprime.continuum` table must never expose.
#
# `canonical_json` holds the full nested record, and the PrestoDB MongoDB
# connector maps it to a `json` type it cannot serialise back to a client. Any
# query that reached it — including a plain `SELECT *` — failed with
# "Unhandled type for Slice: json", which broke every dashboard card that
# issues `SELECT *`. The full record stays available in MongoDB and through the
# core's own REST endpoints.
UNSUPPORTED_COLUMNS = frozenset({"canonical_json"})

# Fallback projection, in the order written by `pipeline._record_document`, used
# only when Presto cannot be introspected. The connector infers its schema by
# sampling documents, so the real column set is authoritative and is read from
# `information_schema` at runtime — `fallback_reason`, for instance, is absent
# whenever the sampled edge record left it null.
DEFAULT_CONTINUUM_COLUMNS = (
    "record_id",
    "entity",
    "contextattribute",
    "contextvalue",
    "resource",
    "timestamp",
    "ingested_at",
    "refreshrate",
    "source",
    "recommended_tier",
    "storage_location",
    "actual_backend",
    "cloud_fallback",
    "pii_detected",
)


def normalize_scope(value: Any) -> str:
    text = str(value or "continuum").strip().lower()
    if text in {"false", "0", "edge"}:
        return "edge"
    if text in {"true", "1", "cloud"}:
        return "cloud"
    return "continuum"


class QueryValidationError(ValueError):
    pass


class QueryRouter:
    def __init__(
        self,
        repo: Optional[MongoRepository] = None,
        cloud: Optional[AwsCloudAdapter] = None,
    ):
        self.repository = repo or repository
        self.cloud = cloud or cloud_adapter
        self._column_cache: Dict[str, Tuple[str, ...]] = {}

    def health(self) -> Dict[str, Any]:
        parsed = urlparse(PRESTO_URL)
        try:
            connection = prestodb.dbapi.connect(
                host=parsed.hostname or "presto",
                port=parsed.port or 8080,
                user="qprime-health",
                http_scheme=parsed.scheme or "http",
                request_timeout=3,
            )
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return {"status": "connected", "url": PRESTO_URL}
        except Exception as exc:
            return {"status": "unavailable", "url": PRESTO_URL, "error": str(exc)}

    def execute(self, sql: str, scope_value: Any) -> Dict[str, Any]:
        started = time.perf_counter()
        expression = self._validate(sql)
        scope = normalize_scope(scope_value)
        source = "mongodb"

        if scope == "edge":
            results = self._presto(self._rewrite(expression, "edge_records"))
            edge_rows, cloud_rows = len(results), 0
            sources = ["presto:mongodb.edge_records"]
        elif scope == "cloud" and self.cloud.athena_configured():
            results = self.cloud.query(self._athena_sql(expression))
            edge_rows, cloud_rows = 0, len(results)
            sources = ["athena"]
            source = "aws"
        elif scope == "cloud":
            results = self._presto(self._rewrite(expression, "cloud_records"))
            edge_rows, cloud_rows = 0, len(results)
            sources = ["presto:mongodb.cloud_records"]
        elif self.cloud.athena_configured():
            if any(expression.find(kind) for kind in (exp.Avg,)):
                edge_results, cloud_results, results = self._federated_average(expression)
            else:
                edge_results = self._presto(self._rewrite(expression, "edge_records"))
                cloud_results = self.cloud.query(self._athena_sql(expression))
                results = self._merge_external(expression, edge_results, cloud_results)
            edge_rows, cloud_rows = len(edge_results), len(cloud_results)
            sources = ["presto:mongodb.edge_records", "athena"]
            source = "federated"
        else:
            results = self._presto(self._rewrite_continuum(expression))
            # The per-tier executions exist only to report how much of the
            # answer came from each tier. For an aggregate that split counts
            # aggregate rows rather than records, so it is neither meaningful
            # nor displayed — and running the statement three times over both
            # collections is exactly the load that used to exhaust Presto.
            if self._aggregated(expression):
                edge_rows = cloud_rows = 0
            else:
                edge_rows = len(self._presto(self._rewrite(expression, "edge_records")))
                cloud_rows = len(self._presto(self._rewrite(expression, "cloud_records")))
            sources = ["presto:mongodb.edge_records", "presto:mongodb.cloud_records"]

        elapsed = round((time.perf_counter() - started) * 1000, 3)
        metric = {
            "created_at": int(time.time() * 1000),
            "scope": scope,
            "latency_ms": elapsed,
            "result_rows": len(results),
            "edge_rows": edge_rows,
            "cloud_rows": cloud_rows,
            "source": source,
            "success": True,
        }
        self.repository.store_query_metric(metric)
        return {
            "results": results,
            "edge_count": edge_rows,
            "cloud_count": cloud_rows,
            "scope": scope,
            "query_latency_ms": elapsed,
            "sources": sources,
        }

    def _validate(self, sql: str) -> exp.Expression:
        text = str(sql or "").strip()
        if not text:
            raise QueryValidationError("query is empty")
        if "--" in text or "/*" in text or "*/" in text:
            raise QueryValidationError("SQL comments are not allowed")
        try:
            statements = parse(text, read="presto")
        except Exception as exc:
            raise QueryValidationError(f"invalid SQL: {exc}") from exc
        if len(statements) != 1:
            raise QueryValidationError("exactly one SQL statement is allowed")
        expression = statements[0]
        prohibited = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command)
        if isinstance(expression, prohibited) or any(expression.find(kind) for kind in prohibited):
            raise QueryValidationError("only read-only SELECT queries are allowed")
        if not isinstance(expression, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            raise QueryValidationError("only SELECT or WITH ... SELECT is allowed")
        logical_tables = [table for table in expression.find_all(exp.Table) if self._is_logical(table)]
        if not logical_tables:
            raise QueryValidationError(f"query must read {LOGICAL_DATABASE}.{LOGICAL_TABLE}")
        for table in expression.find_all(exp.Table):
            if not self._is_logical(table):
                raise QueryValidationError("query may only access the Q-PRIME logical table")
        if not self._aggregated(expression):
            if expression.args.get("limit") is None:
                expression = expression.limit(QUERY_MAX_ROWS)
        return expression

    @staticmethod
    def _aggregated(expression: exp.Expression) -> bool:
        """True when rows are summarised rather than returned one per record."""
        return any(
            expression.find(kind)
            for kind in (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)
        )

    @staticmethod
    def _is_logical(table: exp.Table) -> bool:
        return table.name.lower() == LOGICAL_TABLE.lower() and (
            not table.db or table.db.lower() == LOGICAL_DATABASE.lower()
        )

    @staticmethod
    def _physical_table(collection: str) -> exp.Table:
        return exp.to_table(f"mongodb.qprime.{collection}")

    def _discover_columns(self, collection: str) -> Tuple[str, ...]:
        """Serialisable columns of one physical collection, as Presto sees them.

        The MongoDB connector infers its schema from sampled documents, so the
        column set is discovered rather than assumed. Successful lookups are
        cached; an empty result is not, so a collection that Presto has not
        sampled yet is retried on the next query.
        """
        cached = self._column_cache.get(collection)
        if cached:
            return cached
        try:
            rows = self._presto(
                "SELECT column_name FROM mongodb.information_schema.columns "
                f"WHERE table_schema = 'qprime' AND table_name = '{collection}'"
            )
            columns = tuple(
                str(row["column_name"])
                for row in rows
                if str(row.get("column_name", "")) not in UNSUPPORTED_COLUMNS
            )
        except Exception:
            columns = ()
        if columns:
            self._column_cache[collection] = columns
        return columns

    def _columns(self, collection: str) -> Tuple[str, ...]:
        return self._discover_columns(collection) or DEFAULT_CONTINUUM_COLUMNS

    def _continuum_columns(self) -> Tuple[str, ...]:
        """Columns common to both collections, so the UNION ALL stays valid."""
        edge = self._discover_columns("edge_records")
        cloud = self._discover_columns("cloud_records")
        if edge and cloud:
            shared = set(cloud)
            common = tuple(name for name in edge if name in shared)
            if common:
                return common
        return edge or cloud or DEFAULT_CONTINUUM_COLUMNS

    def _projection(self, collection: str, columns: Optional[Tuple[str, ...]] = None) -> exp.Select:
        """SELECT the supported continuum columns from one physical collection."""
        return exp.select(*(columns or self._columns(collection))).from_(
            self._physical_table(collection)
        )

    @staticmethod
    def _as_source(select: exp.Select, alias_name: str) -> exp.Subquery:
        return exp.Subquery(
            this=select,
            alias=exp.TableAlias(this=exp.to_identifier(alias_name)),
        )

    def _rewrite(self, expression: exp.Expression, collection: str) -> str:
        rewritten = expression.copy()
        for table in list(rewritten.find_all(exp.Table)):
            if self._is_logical(table):
                alias_name = table.alias_or_name or LOGICAL_TABLE
                table.replace(
                    self._as_source(self._projection(collection), alias_name)
                )
        return rewritten.sql(dialect="presto")

    def _rewrite_continuum(self, expression: exp.Expression) -> str:
        rewritten = expression.copy()
        columns = self._continuum_columns()
        union = exp.union(
            self._projection("edge_records", columns),
            self._projection("cloud_records", columns),
            distinct=False,
        )
        for table in list(rewritten.find_all(exp.Table)):
            if self._is_logical(table):
                alias_name = table.alias_or_name or LOGICAL_TABLE
                table.replace(self._as_source(union.copy(), alias_name))
        return rewritten.sql(dialect="presto")

    def _athena_sql(self, expression: exp.Expression) -> str:
        rewritten = expression.copy()
        # AWS Glue database names may contain characters (for example `-`)
        # that are not valid in an unquoted SQL identifier. Build the AST from
        # quoted identifier nodes instead of parsing a dotted string.
        physical = exp.Table(
            this=exp.to_identifier(self.cloud.athena_table, quoted=True),
            db=exp.to_identifier(self.cloud.athena_database, quoted=True),
        )
        for table in list(rewritten.find_all(exp.Table)):
            if self._is_logical(table):
                replacement = physical.copy()
                if table.alias:
                    replacement.set("alias", table.args.get("alias"))
                table.replace(replacement)
        return rewritten.sql(dialect="presto")

    def _presto(self, sql: str) -> List[Dict[str, Any]]:
        parsed = urlparse(PRESTO_URL)
        connection = prestodb.dbapi.connect(
            host=parsed.hostname or "presto",
            port=parsed.port or 8080,
            user="qprime",
            catalog="mongodb",
            schema="qprime",
            http_scheme=parsed.scheme or "http",
            request_timeout=QUERY_TIMEOUT_S,
        )
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description or []]
        return [dict(zip(columns, row)) for row in rows]

    def _federated_average(
        self, expression: exp.Expression
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Compute a correct weighted average over separate Edge and AWS data."""
        averages = list(expression.find_all(exp.Avg))
        if (
            len(averages) != 1
            or not isinstance(expression, exp.Select)
            or len(expression.expressions) != 1
            or expression.args.get("group") is not None
        ):
            raise QueryValidationError(
                "Continuum currently supports one ungrouped AVG expression at a time"
            )
        average = averages[0]
        value_expression = average.this.copy()
        statistics = expression.copy()
        statistics.set(
            "expressions",
            [
                exp.alias_(exp.Sum(this=value_expression.copy()), "__qprime_sum", quoted=True),
                exp.alias_(exp.Count(this=value_expression.copy()), "__qprime_count", quoted=True),
            ],
        )
        edge_rows = self._presto(self._rewrite(statistics, "edge_records"))
        cloud_rows = self.cloud.query(self._athena_sql(statistics))

        def numeric(rows: List[Dict[str, Any]], key: str) -> float:
            if not rows or rows[0].get(key) is None:
                return 0.0
            return float(rows[0][key])

        total = numeric(edge_rows, "__qprime_sum") + numeric(cloud_rows, "__qprime_sum")
        count = numeric(edge_rows, "__qprime_count") + numeric(cloud_rows, "__qprime_count")
        alias = expression.expressions[0].alias_or_name or "average"
        return edge_rows, cloud_rows, [{alias: total / count if count else None}]

    def _merge_external(
        self,
        expression: exp.Expression,
        edge_rows: List[Dict[str, Any]],
        cloud_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        aggregates = list(
            expression.find_all(exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)
        )
        if not aggregates:
            merged = edge_rows + cloud_rows
            if merged and "timestamp" in merged[0]:
                merged.sort(key=lambda row: row.get("timestamp") or 0, reverse=True)
            limit = expression.args.get("limit")
            if limit and isinstance(limit.expression, exp.Literal):
                merged = merged[: int(limit.expression.this)]
            return merged[:QUERY_MAX_ROWS]

        if any(isinstance(item, exp.Avg) for item in aggregates):
            raise QueryValidationError("unsupported federated AVG query shape")
        if any(
            isinstance(item, exp.Count) and isinstance(item.this, exp.Distinct)
            for item in aggregates
        ):
            raise QueryValidationError(
                "COUNT DISTINCT across external Edge/Cloud sources is not supported"
            )
        return self._merge_additive_rows(edge_rows, cloud_rows)

    @staticmethod
    def _merge_additive_rows(
        edge_rows: List[Dict[str, Any]], cloud_rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if not edge_rows:
            return cloud_rows
        if not cloud_rows:
            return edge_rows
        numeric_keys = {
            key
            for row in edge_rows + cloud_rows
            for key, value in row.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        group_keys = [key for key in edge_rows[0] if key not in numeric_keys]
        merged: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for row in edge_rows + cloud_rows:
            identity = tuple(row.get(key) for key in group_keys)
            target = merged.setdefault(identity, {key: row.get(key) for key in group_keys})
            for key in numeric_keys:
                target[key] = (target.get(key) or 0) + (row.get(key) or 0)
        return list(merged.values())


query_router = QueryRouter()
