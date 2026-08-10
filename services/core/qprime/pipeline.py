"""Canonical Q-PRIME evaluation, placement, and persistence pipeline."""

import copy
import json
import time
from typing import Any, Dict, List, Optional

from . import decision as decision_mod
from . import sla as sla_mod
from .cloud import AwsCloudAdapter, cloud_adapter
from .cloud_config import cloud_configuration
from .normalization import entity_label, normalize_direct, normalize_edgex
from .profiles import PersistentConfig, persistent_config
from .repository import MongoRepository, repository


def _record_document(
    record: Dict[str, Any], analysis: Dict[str, Any], fields: Dict[str, Any]
) -> Dict[str, Any]:
    context_value = copy.deepcopy(record.get("contextValue") or {})
    resource = copy.deepcopy(record.get("resource") or {})
    return {
        "record_id": record["record_id"],
        # `entity` is declared varchar in repository.RECORD_FIELDS, so a
        # structured entity is flattened to its label before storage.
        "entity": entity_label(record.get("entity")),
        "contextattribute": record.get("contextAttribute") or "",
        "contextvalue": context_value,
        "resource": {
            "device_id": str(resource.get("device_id") or ""),
            "device_name": str(resource.get("device_name") or ""),
            "sensor_id": str(resource.get("sensor_id") or ""),
            "gateway_id": str(resource.get("gateway_id") or ""),
        },
        "timestamp": int(record.get("timestamp") or 0),
        "ingested_at": int(record.get("ingested_at") or time.time() * 1000),
        "refreshrate": float(record["refreshRate"])
        if isinstance(record.get("refreshRate"), (int, float))
        else None,
        "source": fields["source"],
        "recommended_tier": analysis["decision"].lower(),
        "storage_location": fields["storage_location"],
        "actual_backend": fields["actual_backend"],
        "cloud_fallback": bool(fields.get("cloud_fallback")),
        "fallback_reason": fields.get("fallback_reason"),
        "pii_detected": bool(analysis.get("pii_detected")),
        "canonical_json": copy.deepcopy(record),
    }


class PlacementPipeline:
    def __init__(
        self,
        repo: Optional[MongoRepository] = None,
        config: Optional[PersistentConfig] = None,
        cloud: Optional[AwsCloudAdapter] = None,
    ):
        self.repository = repo or repository
        self.config = config or persistent_config
        self.cloud = cloud or cloud_adapter

    def initialise(self) -> None:
        self.repository.ensure_indexes()
        cloud_configuration.initialise()
        self.config.ensure_seeded()

    def ingest_direct(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.ingest(normalize_direct(payload), "direct")

    def ingest_edgex(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [self.ingest(record, "edgex") for record in normalize_edgex(payload)]

    def ingest(self, record: Dict[str, Any], source: str) -> Dict[str, Any]:
        started = time.perf_counter()
        self.repository.require()
        existing = self.repository.find_decision(record["record_id"])
        if existing:
            return {"duplicate": True, "decision": existing}

        runtime, profile = self.config.runtime_for(record)
        evaluated = copy.deepcopy(record)
        evaluated["sla"] = sla_mod.evaluate_with_baseline(
            evaluated, runtime, self.repository, profile["version"]
        )
        analysis = decision_mod.decide(evaluated, runtime)
        recommendation = analysis["decision"].lower()
        actual_backends: List[str] = []
        storage_details: List[Dict[str, Any]] = []

        if recommendation in {"edge", "both"}:
            fields = {
                "source": source,
                "storage_location": "edge",
                "actual_backend": "mongodb_edge",
            }
            self.repository.store_record(
                "edge_records", _record_document(record, analysis, fields)
            )
            actual_backends.append("mongodb_edge")
            storage_details.append(fields)

        if recommendation in {"cloud", "both"}:
            cloud_fields = self._store_cloud(record, analysis, source)
            actual_backends.append(cloud_fields["actual_backend"])
            storage_details.append(cloud_fields)

        resource = record.get("resource") or {}
        decision = {
            "record_id": record["record_id"],
            "created_at": int(time.time() * 1000),
            "timestamp": record.get("timestamp"),
            "device_id": str(resource.get("device_id") or ""),
            "device_name": str(resource.get("device_name") or ""),
            "contextattribute": record.get("contextAttribute") or "",
            "source": source,
            "profile_scope": profile["scope"],
            "profile_selector": profile.get("selector", ""),
            "profile_version": profile["version"],
            "qoc": evaluated["sla"],
            "analysis": analysis,
            "recommended_tier": recommendation,
            "actual_backends": actual_backends,
            "storage": storage_details,
            "pii_detected": bool(analysis.get("pii_detected")),
            "pii_paths": analysis.get("pii_paths") or [],
            "placement_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        self.repository.store_decision(decision)
        return {"duplicate": False, "decision": decision}

    def _store_cloud(
        self, record: Dict[str, Any], analysis: Dict[str, Any], source: str
    ) -> Dict[str, Any]:
        if self.cloud.configured():
            try:
                result = self.cloud.write(record)
                return {
                    "source": source,
                    "storage_location": "cloud",
                    "actual_backend": result["backend"],
                    "cloud_reference": result.get("reference"),
                    "cloud_fallback": False,
                }
            except RuntimeError as exc:
                reason = "cloud_write_failed"
                error = str(exc)
        else:
            reason = "cloud_not_configured"
            error = None
        fields = {
            "source": source,
            "storage_location": "cloud",
            "actual_backend": "mongodb_cloud_fallback",
            "cloud_fallback": True,
            "fallback_reason": reason,
            "cloud_error": error,
        }
        self.repository.store_record(
            "cloud_records", _record_document(record, analysis, fields)
        )
        return fields


pipeline = PlacementPipeline()
