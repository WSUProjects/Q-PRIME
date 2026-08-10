"""Paper-faithful full and cached Quality-of-Context evaluation."""

import hashlib
import json
import os
import threading
import time
from glob import glob
from typing import Any, Dict, List, Optional, Tuple

from .config import RuntimeConfig

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.environ.get("QPRIME_SCHEMA_DIR", os.path.join(BASE_DIR, "schema"))

_schema_lock = threading.RLock()
_expected_keys: Optional[Dict[str, list]] = None


def _collect(obj: Any, prefix: str = "") -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_prefix = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                keys.extend(_collect(value, new_prefix))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                keys.extend(_collect(value[0], new_prefix))
            else:
                keys.append(new_prefix)
    return keys


def expected_keys() -> Dict[str, list]:
    global _expected_keys
    with _schema_lock:
        if _expected_keys is None:
            result: Dict[str, list] = {}
            for path in glob(os.path.join(SCHEMA_DIR, "*-schema.json")):
                try:
                    with open(path, "r", encoding="utf-8") as schema_file:
                        schema = json.load(schema_file)
                except (OSError, ValueError):
                    continue
                name = os.path.basename(path).replace("-schema.json", "")
                result[name.lower()] = _collect(schema)
            _expected_keys = result
        return _expected_keys


def reset_baselines() -> None:
    """Compatibility hook; persistent baselines are invalidated by profiles."""


def _has_path(obj: Any, path: str) -> bool:
    current = obj
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _value_at(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _stream_key(data: Dict[str, Any]) -> str:
    return RuntimeConfig.sensor_key(data).lower()


def _latency_threshold(stream_key: str, config: Dict[str, Any]) -> int:
    thresholds = {
        str(key).lower(): int(value)
        for key, value in (config.get("latency_thresholds") or {}).items()
    }
    if stream_key in thresholds:
        return thresholds[stream_key]
    for key, value in thresholds.items():
        if key in stream_key or stream_key in key:
            return value
    return int(config.get("default_latency_threshold_ms", 30))


def _configured_for_stream(mapping: Dict[str, Any], stream_key: str, default: Any) -> Any:
    if stream_key in mapping:
        return mapping[stream_key]
    for key, value in mapping.items():
        key = str(key).lower()
        if key in stream_key or stream_key in key:
            return value
    return default


def _find_expected(stream_key: str, config: Dict[str, Any]) -> List[str]:
    configured = _configured_for_stream(config.get("required_fields") or {}, stream_key, None)
    if isinstance(configured, list) and configured:
        return [str(path) for path in configured]
    schemas = expected_keys()
    if stream_key in schemas:
        return schemas[stream_key]
    for key, fields in schemas.items():
        if key in stream_key or stream_key in key:
            return fields
    return ["timestamp", "resource.device_id"]


def _correctness_rules(stream_key: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    configured = _configured_for_stream(config.get("correctness_rules") or {}, stream_key, [])
    return configured if isinstance(configured, list) else []


def _timestamp_ms(value: Any) -> Optional[int]:
    if not isinstance(value, (int, float)):
        return None
    integer = int(value)
    if integer > 1_000_000_000_000_000:
        return integer // 1_000_000
    return integer if integer > 1_000_000_000_000 else integer * 1000


def _delay_ms(data: Dict[str, Any]) -> Optional[int]:
    timestamp_ms = _timestamp_ms(data.get("timestamp"))
    if timestamp_ms is None:
        return None
    arrival = int(data.get("ingested_at") or time.time() * 1000)
    return max(0, arrival - timestamp_ms)


def _significance(data: Dict[str, Any]) -> float:
    value = data.get("contextValue") or data.get("contextvalue") or {}
    event = str(value.get("event") or "").lower()
    if event and event not in {"heartbeat", "status", "ok"}:
        return 1.0
    if event:
        return 0.2
    return 0.5


def _check_rule(data: Dict[str, Any], rule: Dict[str, Any]) -> bool:
    path = str(rule.get("path") or "")
    value = _value_at(data, path) if path else None
    if rule.get("required") and value is None:
        return False
    if value is None:
        return True
    expected_type = str(rule.get("type") or "").lower()
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    if expected_type in type_map and not isinstance(value, type_map[expected_type]):
        return False
    if isinstance(value, bool) and expected_type in {"number", "integer"}:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if rule.get("min") is not None and value < float(rule["min"]):
            return False
        if rule.get("max") is not None and value > float(rule["max"]):
            return False
    allowed = rule.get("allowed")
    return not isinstance(allowed, list) or value in allowed


def _correctness(data: Dict[str, Any], rules: List[Dict[str, Any]]) -> Tuple[float, int, int]:
    checks = [_check_rule(data, rule) for rule in rules]
    checks.append(_has_path(data, "resource.device_id"))
    passed = sum(1 for result in checks if result)
    return passed / len(checks), passed, len(checks)


def _resolution(refresh_rate: Any) -> float:
    if isinstance(refresh_rate, (int, float)) and refresh_rate > 0:
        return 1.0 - min(1.0, max(0.0, (float(refresh_rate) - 1.0) / 9999.0))
    return 0.5


def _result(
    scores: Dict[str, Dict[str, Any]], pass_threshold: float, mode: str, baseline_key: str
) -> Dict[str, Any]:
    for metric in scores.values():
        metric["score"] = round(float(metric["score"]), 3)
        metric["passed"] = bool(metric["score"] >= pass_threshold)
    scores["evaluation_mode"] = mode
    scores["baseline_key"] = baseline_key
    return scores


def _baseline_identity(record: Dict[str, Any], profile_version: str) -> Tuple[str, str, str, str]:
    resource = record.get("resource") or {}
    device_id = str(resource.get("device_id") or "").strip()
    device_name = str(resource.get("device_name") or "").strip()
    stream_key = _stream_key(record)
    identity = device_id or device_name or stream_key
    digest = hashlib.sha256(f"{identity}|{stream_key}|{profile_version}".encode()).hexdigest()
    return digest, device_id, device_name, stream_key


def compute_slas(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Run the paper's continuous full evaluation without persistence."""
    pass_threshold = float(config.get("pass_threshold", 0.6))
    stream_key = _stream_key(data)
    threshold = _latency_threshold(stream_key, config)
    delay = _delay_ms(data)
    timeliness = 0.0 if delay is None else max(0.0, 1.0 - delay / max(threshold, 1))
    expected = _find_expected(stream_key, config)
    present = sum(1 for path in expected if _has_path(data, path))
    completeness = present / len(expected) if expected else 0.0
    correctness, checks_passed, checks_total = _correctness(
        data, _correctness_rules(stream_key, config)
    )
    scores = {
        "timeliness": {"score": timeliness, "latency_ms": delay, "threshold_ms": threshold},
        "completeness": {"score": completeness, "present": present, "expected": len(expected)},
        "correctness": {
            "score": correctness,
            "checks_passed": checks_passed,
            "checks_total": checks_total,
        },
        "resolution": {"score": _resolution(data.get("refreshRate"))},
        "significance": {"score": _significance(data)},
    }
    return _result(scores, pass_threshold, "full", "preview")


def evaluate(data: Dict[str, Any], runtime: RuntimeConfig) -> Dict[str, Any]:
    return compute_slas(data, runtime.snapshot())


def evaluate_with_baseline(
    data: Dict[str, Any], runtime: RuntimeConfig, repository: Any, profile_version: str
) -> Dict[str, Any]:
    """Evaluate and persist the paper's compact version-bound device baseline."""
    config = runtime.snapshot()
    pass_threshold = float(config.get("pass_threshold", 0.6))
    baseline_key, device_id, device_name, stream_key = _baseline_identity(
        data, profile_version
    )
    baseline = repository.get_baseline(baseline_key)

    if not baseline:
        scores = compute_slas(data, config)
        delay = scores["timeliness"].get("latency_ms")
        threshold = _latency_threshold(stream_key, config)
        refresh = data.get("refreshRate")
        repository.upsert_baseline(
            baseline_key,
            {
                "device_id": device_id,
                "device_name": device_name,
                "stream_key": stream_key,
                "profile_version": profile_version,
                "sla_threshold_ms": threshold,
                "adaptive_threshold_ms": threshold,
                "expected_fields": _find_expected(stream_key, config),
                "correctness_rules": _correctness_rules(stream_key, config),
                "refresh_interval_ms": float(refresh) if isinstance(refresh, (int, float)) else None,
                "delay_ewma_ms": float(delay) if delay is not None else float(threshold),
                "sample_count": 1,
            },
        )
        scores["baseline_key"] = baseline_key
        scores["profile_version"] = profile_version
        return scores

    delay = _delay_ms(data)
    adaptive = float(baseline.get("adaptive_threshold_ms") or baseline["sla_threshold_ms"])
    timeliness = 0.0 if delay is None else float(delay <= adaptive)
    expected = baseline.get("expected_fields") or []
    present = sum(1 for path in expected if _has_path(data, path))
    completeness = present / len(expected) if expected else 0.0
    correctness, checks_passed, checks_total = _correctness(
        data, baseline.get("correctness_rules") or []
    )
    baseline_refresh = baseline.get("refresh_interval_ms")
    refresh = data.get("refreshRate")
    if isinstance(refresh, (int, float)) and isinstance(baseline_refresh, (int, float)):
        resolution = float(float(refresh) <= 1.5 * float(baseline_refresh))
    else:
        resolution = 0.0

    scores = {
        "timeliness": {"score": timeliness, "latency_ms": delay, "threshold_ms": adaptive},
        "completeness": {"score": completeness, "present": present, "expected": len(expected)},
        "correctness": {
            "score": correctness,
            "checks_passed": checks_passed,
            "checks_total": checks_total,
        },
        "resolution": {"score": resolution, "baseline_refresh_ms": baseline_refresh},
        "significance": {"score": _significance(data)},
    }

    count = int(baseline.get("sample_count") or 1) + 1
    alpha = float(config.get("baseline_alpha", 0.2))
    previous_ewma = float(baseline.get("delay_ewma_ms") or baseline["sla_threshold_ms"])
    ewma = previous_ewma if delay is None else alpha * delay + (1.0 - alpha) * previous_ewma
    sla_threshold = float(baseline["sla_threshold_ms"])
    violation = delay is not None and delay > adaptive
    if violation or count >= int(config.get("baseline_min_samples", 5)):
        lower = max(10.0, float(config.get("adaptive_threshold_min_ratio", 0.5)) * sla_threshold)
        upper = float(config.get("adaptive_threshold_max_ratio", 3.0)) * sla_threshold
        candidate = float(config.get("adaptive_threshold_multiplier", 1.5)) * ewma
        adaptive = min(upper, max(lower, candidate))
    baseline.update(
        {
            "adaptive_threshold_ms": adaptive,
            "delay_ewma_ms": ewma,
            "sample_count": count,
        }
    )
    repository.upsert_baseline(baseline_key, baseline)
    result = _result(scores, pass_threshold, "lightweight", baseline_key)
    result["profile_version"] = profile_version
    return result
