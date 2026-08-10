"""Edge/Cloud placement recommendation engine.

Faithful implementation of the paper's placement scoring with:

- the AHP fallback fix applied (the original release crashed when a global
  ``criteria_matrix`` was configured, because the tuple returned by
  ``ahp_weights_and_consistency`` was not unpacked);
- runtime-configurable weight modes (per-sensor direct weights, global
  direct weights, or a global AHP pairwise matrix);
- an optional privacy floor and an optional strict-override for every
  PII-carrying record (the paper's recommended mitigations);
- a rich explanation payload so applications can show *why* a tier is
  recommended, without routing or persisting the record.

Scoring (as in the paper):

    QoC_temporal = mean(timeliness, resolution)
    QoC_spatial  = mean(completeness, correctness, significance)   # content QoC
    S_edge  = w_temporal * QoC_temporal + w_privacy * P
    S_cloud = w_spatial  * QoC_spatial

where ``P`` is the sensor's privacy weight in [0, 1]. Ties recommend Both.
"""

from typing import Any, Dict, List, Optional, Tuple

from . import ahp
from .config import RuntimeConfig
from .privacy import detect_pii

METRICS = ("timeliness", "completeness", "correctness", "resolution", "significance")


def _is_strict(val) -> bool:
    if isinstance(val, bool):
        return val is True
    if isinstance(val, str):
        return val.strip().lower() == "strict"
    return False


def _privacy_weight(sensor_key: str, record: Dict[str, Any], cfg: Dict[str, Any]) -> float:
    pw_map = cfg.get("privacy_weights") or {}
    cand = pw_map.get(sensor_key)
    if cand is None:
        cand = pw_map.get((record.get("contextAttribute") or "").lower())
    if cand is not None:
        return max(0.0, min(1.0, float(cand)))
    return max(0.0, min(1.0, float(cfg.get("default_privacy_weight", 0.0) or 0.0)))


def _resolve_weights(
    sensor_key: str, cfg: Dict[str, Any]
) -> Tuple[List[float], str, Optional[float]]:
    """Return ``([w_t, w_s, w_p], source, consistency_ratio)``."""
    mode = cfg.get("weight_mode", "per_sensor")

    if mode == "metric_level":
        metric = cfg.get("metric_weights") or {}
        temporal = float(metric.get("timeliness", 0.0)) + float(
            metric.get("resolution", 0.0)
        )
        spatial = sum(
            float(metric.get(name, 0.0))
            for name in ("completeness", "correctness", "significance")
        )
        privacy = metric.get("privacy")
        privacy = (
            float(privacy)
            if privacy is not None
            else max(0.0, 1.0 - temporal - spatial)
        )
        raw = [temporal, spatial, privacy]
        total = sum(raw) if sum(raw) != 0 else 1.0
        return [weight / total for weight in raw], "metric_level", None

    if mode == "global_ahp":
        W, _lambda_max, _ci, cr = ahp.ahp_weights_and_consistency(cfg["ahp_matrix"])
        return W, "global_ahp", cr

    if mode == "global_direct":
        gw = cfg.get("global_criteria_weights") or {}
        raw = [
            float(gw.get("temporal", 1.0)),
            float(gw.get("spatial", 1.0)),
            float(gw.get("privacy", 1.0)),
        ]
        total = sum(raw) if sum(raw) != 0 else 1.0
        return [w / total for w in raw], "global_direct", None

    # per_sensor (paper default): per-sensor weights, fall back to global direct
    per = (cfg.get("criteria_weights") or {}).get(sensor_key)
    if isinstance(per, dict):
        raw = [
            float(per.get("temporal", 1.0)),
            float(per.get("spatial", 1.0)),
            float(per.get("privacy", 1.0)),
        ]
        total = sum(raw) if sum(raw) != 0 else 1.0
        return [w / total for w in raw], f"per_sensor:{sensor_key}", None

    gw = cfg.get("global_criteria_weights") or {}
    raw = [
        float(gw.get("temporal", 1.0)),
        float(gw.get("spatial", 1.0)),
        float(gw.get("privacy", 1.0)),
    ]
    total = sum(raw) if sum(raw) != 0 else 1.0
    return [w / total for w in raw], "global_direct_fallback", None


def decide(record: Dict[str, Any], runtime: RuntimeConfig) -> Dict[str, Any]:
    """Recommend a tier for ``record``. Returns a full explanation dict."""
    cfg = runtime.snapshot()
    sensor_key = RuntimeConfig.sensor_key(record)

    # QoC metric dictionary from the SLA evaluation
    metric_dict: Dict[str, Optional[float]] = {m: None for m in METRICS}
    sla = record.get("sla")
    if isinstance(sla, dict):
        for m in METRICS:
            entry = sla.get(m)
            metric_dict[m] = entry.get("score") if isinstance(entry, dict) else None

    pii_detected, pii_paths = detect_pii(record)
    privacy_weight = _privacy_weight(sensor_key, record, cfg)

    explanation: Dict[str, Any] = {
        "sensor_key": sensor_key,
        "qoc_metrics": metric_dict,
        "pii_detected": pii_detected,
        "pii_paths": pii_paths[:10],
        "privacy_weight": privacy_weight,
    }

    # 1) Hard privacy-filter override -> Edge
    if _is_strict(record.get("privacy_filter")):
        explanation.update(
            {
                "decision": "Edge",
                "reason": "privacy_filter=strict override",
                "privacy_level": "Strict",
                "privacy_weight": 1.0,
                "strict_override": True,
                "weights": None,
                "weight_source": None,
                "consistency_ratio": None,
                "score_edge": None,
                "score_cloud": None,
            }
        )
        return explanation

    # 1b) Optional mitigation: force Edge for every PII-carrying record
    if cfg.get("strict_privacy_all_pii") and pii_detected:
        explanation.update(
            {
                "decision": "Edge",
                "reason": "strict_privacy_all_pii: PII detected in payload",
                "privacy_level": "Strict",
                "strict_override": True,
                "weights": None,
                "weight_source": None,
                "consistency_ratio": None,
                "score_edge": None,
                "score_cloud": None,
            }
        )
        return explanation

    # 2) Privacy level from weight
    if privacy_weight >= 0.66:
        privacy_level = "High"
    elif privacy_weight >= 0.33:
        privacy_level = "Medium"
    else:
        privacy_level = "Low"

    # 3) Criteria weights
    W, weight_source, cr = _resolve_weights(sensor_key, cfg)

    # 4) Privacy floor enforcement (renormalise)
    floor = float(cfg.get("privacy_floor", 0.0) or 0.0)
    floored = False
    if floor and W[2] < floor:
        W = list(W)
        W[2] = floor
        s = sum(W)
        W = [w / s for w in W]
        floored = True

    w_temporal, w_spatial, w_privacy = W

    # 5) Aggregate QoC per criteria group
    temporal_vals = [metric_dict.get("timeliness") or 0.0, metric_dict.get("resolution") or 0.0]
    spatial_vals = [
        metric_dict.get("completeness") or 0.0,
        metric_dict.get("correctness") or 0.0,
        metric_dict.get("significance") or 0.0,
    ]
    qoc_temporal = sum(temporal_vals) / len(temporal_vals)
    qoc_spatial = sum(spatial_vals) / len(spatial_vals)

    # 6) Layer scores
    s_edge = w_temporal * qoc_temporal + w_privacy * privacy_weight
    s_cloud = w_spatial * qoc_spatial

    if s_edge > s_cloud:
        decision = "Edge"
    elif s_cloud > s_edge:
        decision = "Cloud"
    else:
        decision = "Both"

    explanation.update(
        {
            "decision": decision,
            "reason": "score comparison",
            "privacy_level": privacy_level,
            "strict_override": False,
            "weights": {
                "temporal": round(w_temporal, 4),
                "spatial": round(w_spatial, 4),
                "privacy": round(w_privacy, 4),
            },
            "weight_source": weight_source,
            "consistency_ratio": round(cr, 4) if cr is not None else None,
            "privacy_floor_applied": floored,
            "qoc_temporal": round(qoc_temporal, 4),
            "qoc_spatial": round(qoc_spatial, 4),
            "score_edge": round(s_edge, 4),
            "score_cloud": round(s_cloud, 4),
        }
    )
    return explanation
