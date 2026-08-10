"""Canonical record normalisation for direct producers and EdgeX events."""

import copy
import hashlib
import json
import time
from typing import Any, Dict, List


def _first(mapping: Dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    return default


def _epoch_seconds(value: Any) -> int:
    if not isinstance(value, (int, float)):
        return int(time.time())
    number = int(value)
    if number > 1_000_000_000_000_000:
        return number // 1_000_000_000
    if number > 1_000_000_000_000:
        return number // 1000
    return number


def _context_value(value: Any, resource_name: str = "value") -> Dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                decoded = json.loads(stripped)
                if isinstance(decoded, dict):
                    return decoded
                return {resource_name: decoded}
            except ValueError:
                pass
    key = resource_name or "value"
    result = {key: value}
    if key.lower() in {"event", "door", "state"} and isinstance(value, str):
        result["event"] = value
    return result


def _entity(value: Any, resource: Dict[str, Any]) -> Any:
    """Keep a structured entity structured.

    The stream schemas in ``services/core/schema`` reference ``entity.gateway_id``
    and ``entity.location``, so a dict must survive normalisation for the QoC
    completeness factor to resolve those paths. Coercing it to ``str`` here
    produced a Python repr (``"{'gateway_id': ...}"``) that matched nothing and
    silently capped completeness. ``pipeline`` flattens it to a label on the way
    into MongoDB, where the column is declared ``varchar``.
    """
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return str(value or resource.get("device_name") or "")


def entity_label(value: Any) -> str:
    """Flatten an entity to the scalar stored in MongoDB and exposed via SQL."""
    if isinstance(value, dict):
        for key in ("gateway_id", "name", "id", "location"):
            candidate = value.get(key)
            if candidate:
                return str(candidate)
        return ""
    return str(value or "")


def _stable_id(record: Dict[str, Any]) -> str:
    supplied = _first(record, "record_id", "recordId", "id")
    if supplied:
        return str(supplied)
    identity = {
        "entity": record.get("entity"),
        "contextAttribute": record.get("contextAttribute"),
        "contextValue": record.get("contextValue"),
        "resource": record.get("resource"),
        "timestamp": record.get("timestamp"),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize_direct(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("record must be a JSON object")
    raw = payload.get("record") if "record" in payload else payload
    if not isinstance(raw, dict):
        raise ValueError("record must be a JSON object")
    resource = copy.deepcopy(_first(raw, "resource", default={}) or {})
    if not isinstance(resource, dict):
        raise ValueError("resource must be a JSON object")
    attribute = str(_first(raw, "contextAttribute", "contextattribute", default="")).strip()
    if not attribute:
        raise ValueError("record is missing contextAttribute")
    value = _first(raw, "contextValue", "contextvalue", default={})
    record = copy.deepcopy(raw)
    record.update(
        {
            "entity": _entity(raw.get("entity"), resource),
            "contextAttribute": attribute,
            "contextValue": _context_value(value, attribute),
            "resource": resource,
            "timestamp": _epoch_seconds(raw.get("timestamp")),
            "refreshRate": _first(raw, "refreshRate", "refreshrate"),
            "privacy_filter": _first(raw, "privacy_filter", "privacyFilter", default=False),
            "ingested_at": int(time.time() * 1000),
        }
    )
    record["record_id"] = _stable_id(record)
    return record


def normalize_edgex(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("EdgeX payload must be a JSON object")
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    readings = event.get("readings") or event.get("Readings") or []
    if not isinstance(readings, list) or not readings:
        raise ValueError("EdgeX event contains no readings")
    device_name = str(_first(event, "deviceName", "device_name", default="")).strip()
    profile_name = str(_first(event, "profileName", "profile_name", default="")).strip()
    source_name = str(_first(event, "sourceName", "source_name", default="")).strip()
    event_id = str(_first(event, "id", "eventId", default="")).strip()
    tags = event.get("tags") if isinstance(event.get("tags"), dict) else {}
    records: List[Dict[str, Any]] = []
    for index, reading in enumerate(readings):
        if not isinstance(reading, dict):
            continue
        resource_name = str(
            _first(reading, "resourceName", "resource_name", default=source_name or "reading")
        ).strip()
        value = _first(reading, "objectValue", "value", "binaryValue")
        origin = _first(reading, "origin", default=_first(event, "origin", default=time.time()))
        reading_id = str(_first(reading, "id", default="")).strip()
        resource = {
            "device_id": str(tags.get("device_id") or device_name or profile_name),
            "device_name": device_name or str(tags.get("device_name") or "EdgeX Device"),
            "sensor_id": resource_name,
            "gateway_id": str(tags.get("gateway_id") or "edgex"),
            "profile_name": profile_name,
        }
        # Rebuild the structured entity from device tags so EdgeX-sourced
        # records resolve the same schema paths as directly posted ones.
        entity: Any = str(tags.get("entity") or device_name)
        if tags.get("gateway_id") or tags.get("location"):
            entity = {
                "gateway_id": str(tags.get("gateway_id") or "edgex"),
                "location": str(tags.get("location") or ""),
            }
        canonical = {
            "record_id": reading_id or (f"{event_id}:{index}" if event_id else ""),
            "entity": entity,
            "contextAttribute": str(tags.get("contextAttribute") or resource_name),
            "contextValue": _context_value(value, resource_name),
            "resource": resource,
            "timestamp": _epoch_seconds(origin),
            "refreshRate": tags.get("refreshRate"),
            "privacy_filter": tags.get("privacy_filter", False),
            "ingested_at": int(time.time() * 1000),
            "edgex": {
                "event_id": event_id,
                "reading_id": reading_id,
                "profile_name": profile_name,
                "source_name": source_name,
                "value_type": _first(reading, "valueType", "value_type"),
            },
        }
        if not canonical["record_id"]:
            canonical["record_id"] = _stable_id(canonical)
        records.append(canonical)
    if not records:
        raise ValueError("EdgeX event contains no valid readings")
    return records
