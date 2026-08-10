"""MongoDB-backed read models for the Q-PRIME results dashboard."""

import time
from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Dict, List, Optional

from .repository import MongoRepository, json_safe, repository


METRICS = ("timeliness", "completeness", "correctness", "resolution", "significance")


def _limit(value: Any, default: int = 200, maximum: int = 1000) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


class DashboardMetrics:
    def __init__(self, repo: Optional[MongoRepository] = None):
        self.repository = repo or repository

    def overview(self) -> Dict[str, Any]:
        db = self.repository.db
        total = db.placement_decisions.count_documents({})
        decisions = {
            item["_id"]: int(item["count"])
            for item in db.placement_decisions.aggregate(
                [{"$group": {"_id": "$recommended_tier", "count": {"$sum": 1}}}]
            )
        }
        fallbacks = db.placement_decisions.count_documents(
            {"actual_backends": "mongodb_cloud_fallback"}
        )
        pii = db.placement_decisions.count_documents({"pii_detected": True})
        devices = self._placement_by("device_name")
        return {
            "records_processed": int(total),
            "stored_at_edge": decisions.get("edge", 0),
            "sent_to_cloud": decisions.get("cloud", 0),
            "both_tiers": decisions.get("both", 0),
            "cloud_fallback_records": int(fallbacks),
            "pii_records": int(pii),
            "edge_records": self.repository.record_count("edge_records"),
            "cloud_records_retained": self.repository.record_count("cloud_records"),
            "placement_split": decisions,
            "placement_by_device": devices,
            "generated_at": int(time.time() * 1000),
        }

    def decisions(self, filters: Dict[str, Any], limit: Any = 200) -> Dict[str, Any]:
        rows = self.repository.placements(filters, _limit(limit))
        return {"count": len(rows), "decisions": rows}

    def qoc(self, limit: Any = 500) -> Dict[str, Any]:
        documents = list(
            self.repository.db.placement_decisions.find(
                {}, {"created_at": 1, "device_name": 1, "contextattribute": 1, "qoc": 1}
            )
            .sort("created_at", -1)
            .limit(_limit(limit, 500))
        )
        documents.reverse()
        per_device: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        timeline: List[Dict[str, Any]] = []
        for document in documents:
            device = document.get("device_name") or document.get("contextattribute") or "unknown"
            point: Dict[str, Any] = {"timestamp": document.get("created_at"), "device": device}
            for metric in METRICS:
                entry = (document.get("qoc") or {}).get(metric) or {}
                score = entry.get("score")
                if isinstance(score, (int, float)):
                    score = float(score)
                    point[metric] = score
                    per_device[device][metric].append(score)
            timeline.append(point)
        means = {
            device: {
                metric: round(mean(values), 4)
                for metric, values in metric_values.items()
                if values
            }
            for device, metric_values in per_device.items()
        }
        return {"timeline": timeline, "mean_by_device": means, "metrics": list(METRICS)}

    def privacy(self) -> Dict[str, Any]:
        db = self.repository.db
        total_pii = db.placement_decisions.count_documents({"pii_detected": True})
        leaked = db.placement_decisions.count_documents(
            {
                "pii_detected": True,
                "actual_backends": {"$in": ["aws_kinesis", "aws_firehose"]},
            }
        )
        by_device = list(
            db.placement_decisions.aggregate(
                [
                    {"$match": {"pii_detected": True}},
                    {
                        "$group": {
                            "_id": "$device_name",
                            "pii_records": {"$sum": 1},
                            "leaked_to_cloud": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$gt": [
                                                {
                                                    "$size": {
                                                        "$setIntersection": [
                                                            "$actual_backends",
                                                            ["aws_kinesis", "aws_firehose"],
                                                        ]
                                                    }
                                                },
                                                0,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                    {"$sort": {"_id": 1}},
                ]
            )
        )
        return {
            "pii_records": int(total_pii),
            "pii_leaked_to_cloud": int(leaked),
            "leak_rate": round((leaked / total_pii * 100.0) if total_pii else 0.0, 2),
            "by_device": [
                {
                    "device": row.get("_id") or "unknown",
                    "pii_records": row["pii_records"],
                    "leaked_to_cloud": row["leaked_to_cloud"],
                }
                for row in by_device
            ],
        }

    def performance(self, limit: Any = 500) -> Dict[str, Any]:
        size = _limit(limit, 500)
        decisions = list(
            self.repository.db.placement_decisions.find(
                {}, {"created_at": 1, "placement_latency_ms": 1}
            )
            .sort("created_at", -1)
            .limit(size)
        )
        queries = list(
            self.repository.db.query_metrics.find({}).sort("created_at", -1).limit(size)
        )
        placement_values = [
            float(row["placement_latency_ms"])
            for row in decisions
            if isinstance(row.get("placement_latency_ms"), (int, float))
        ]
        query_values = [
            float(row["latency_ms"])
            for row in queries
            if isinstance(row.get("latency_ms"), (int, float))
        ]
        return {
            "placement_count": len(decisions),
            "placement_latency_mean_ms": round(mean(placement_values), 3)
            if placement_values
            else 0,
            "query_count": len(queries),
            "query_latency_mean_ms": round(mean(query_values), 3) if query_values else 0,
            "placement_timeline": [json_safe(row) for row in reversed(decisions)],
            "query_timeline": [json_safe(row) for row in reversed(queries)],
        }

    def sensitivity(
        self, weights: Dict[str, float], privacy_floor: float, force_pii_edge: bool
    ) -> Dict[str, Any]:
        total_weight = sum(max(0.0, float(weights.get(key, 0.0))) for key in ("temporal", "spatial", "privacy"))
        if total_weight <= 0:
            raise ValueError("sensitivity weights must have a positive sum")
        normalized = {
            key: max(0.0, float(weights.get(key, 0.0))) / total_weight
            for key in ("temporal", "spatial", "privacy")
        }
        if not 0 <= privacy_floor <= 1:
            raise ValueError("privacy_floor must be in [0,1]")
        if normalized["privacy"] < privacy_floor:
            normalized["privacy"] = privacy_floor
            denominator = sum(normalized.values())
            normalized = {key: value / denominator for key, value in normalized.items()}

        original = Counter()
        replayed = Counter()
        changed = 0
        pii_cloud = 0
        by_device: Dict[str, Counter] = defaultdict(Counter)
        documents = self.repository.db.placement_decisions.find({})
        replayed_records = 0
        for document in documents:
            replayed_records += 1
            prior = str(document.get("recommended_tier") or "unknown")
            original[prior] += 1
            analysis = document.get("analysis") or {}
            qoc = document.get("qoc") or {}
            pii = bool(document.get("pii_detected"))
            if analysis.get("strict_override") or (force_pii_edge and pii):
                tier = "edge"
            else:
                temporal = mean(
                    float((qoc.get(name) or {}).get("score") or 0)
                    for name in ("timeliness", "resolution")
                )
                spatial = mean(
                    float((qoc.get(name) or {}).get("score") or 0)
                    for name in ("completeness", "correctness", "significance")
                )
                privacy_weight = float(analysis.get("privacy_weight") or 0)
                edge_score = normalized["temporal"] * temporal + normalized["privacy"] * privacy_weight
                cloud_score = normalized["spatial"] * spatial
                tier = "edge" if edge_score > cloud_score else "cloud" if cloud_score > edge_score else "both"
            replayed[tier] += 1
            by_device[document.get("device_name") or "unknown"][tier] += 1
            changed += int(tier != prior)
            pii_cloud += int(pii and tier in {"cloud", "both"})
        return {
            "replayed_records": replayed_records,
            "placements_changed": changed,
            "pii_cloud_placements": pii_cloud,
            "weights": normalized,
            "original": dict(original),
            "replayed": dict(replayed),
            "by_device": {device: dict(counts) for device, counts in by_device.items()},
        }

    def _placement_by(self, field: str) -> List[Dict[str, Any]]:
        rows = self.repository.db.placement_decisions.aggregate(
            [
                {"$group": {"_id": {"key": f"${field}", "tier": "$recommended_tier"}, "count": {"$sum": 1}}},
                {"$sort": {"_id.key": 1}},
            ]
        )
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            key = row["_id"].get("key") or "unknown"
            grouped.setdefault(key, {"device": key, "edge": 0, "cloud": 0, "both": 0})
            grouped[key][row["_id"].get("tier") or "unknown"] = int(row["count"])
        return list(grouped.values())


dashboard_metrics = DashboardMetrics()
