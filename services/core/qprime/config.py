"""Thread-safe runtime configuration for Q-PRIME analysis.

The defaults ship in ``config/qoc_thresholds.json`` (the exact configuration
used for the experiments in the paper). At runtime the configuration can be
inspected and updated through the REST API (``GET/PUT /api/config``). Callers
can also supply temporary overrides with an individual analysis request.

Weight resolution modes
-----------------------
``per_sensor``     use ``criteria_weights[<sensor>]`` (paper default).
``global_direct``  use ``global_criteria_weights`` for every sensor.
``global_ahp``     derive weights from the pairwise ``ahp_matrix`` via AHP.
``metric_level``   derive criteria weights from the six metric weights.
"""

import copy
import json
import os
import threading
from typing import Any, Dict, Optional

from . import ahp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.environ.get(
    "QPRIME_CONFIG", os.path.join(BASE_DIR, "config", "qoc_thresholds.json")
)

# Aliases map free-form contextAttribute values onto config keys.
SENSOR_ALIASES = {
    "misty": "misty_vision",
    "misty_vision": "misty_vision",
    "zed": "zed_vision",
    "zed_vision": "zed_vision",
    "door": "door",
    "thp": "thp",
    "tello": "tello_vision",
    "tello_vision": "tello_vision",
}

_FALLBACK_DEFAULTS: Dict[str, Any] = {
    "latency_unit": "ms",
    "default_latency_threshold_ms": 30,
    "latency_thresholds": {},
    "pass_threshold": 0.6,
    "default_privacy_weight": 0.0,
    "privacy_weights": {},
    "weight_mode": "per_sensor",
    "criteria_weights": {},
    "global_criteria_weights": {"temporal": 1 / 3, "spatial": 1 / 3, "privacy": 1 / 3},
    "ahp_matrix": [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
    "metric_weights": {
        "timeliness": 1 / 6,
        "completeness": 1 / 6,
        "correctness": 1 / 6,
        "resolution": 1 / 6,
        "significance": 1 / 6,
        "privacy": 1 / 6,
    },
    "privacy_floor": 0.0,
    "strict_privacy_all_pii": False,
    "required_fields": {},
    "correctness_rules": {},
    "baseline_alpha": 0.2,
    "baseline_min_samples": 5,
    "adaptive_threshold_multiplier": 1.5,
    "adaptive_threshold_min_ratio": 0.5,
    "adaptive_threshold_max_ratio": 3.0,
}


class RuntimeConfig:
    """In-memory configuration with a lock, seeded from the JSON defaults."""

    def __init__(self, path: Optional[str] = None):
        self._lock = threading.RLock()
        self._path = path or DEFAULT_CONFIG_PATH
        self._cfg = copy.deepcopy(_FALLBACK_DEFAULTS)
        self.reload()

    # ------------------------------------------------------------------ io
    def reload(self) -> None:
        """(Re)load defaults from disk, keeping fallback values for gaps."""
        with self._lock:
            try:
                with open(self._path, "r") as fh:
                    on_disk = json.load(fh)
            except Exception:
                on_disk = {}
            merged = copy.deepcopy(_FALLBACK_DEFAULTS)
            merged.update(on_disk or {})
            # Back-compat with the original file's key name.
            if "default_privacy_weight" in merged and "privacy_floor" not in (
                on_disk or {}
            ):
                merged["privacy_floor"] = float(merged.get("default_privacy_weight", 0.0))
            self._cfg = merged

    # ---------------------------------------------------------------- reads
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._cfg)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(self._cfg.get(key, default))

    # --------------------------------------------------------------- writes
    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Merge ``patch`` into the config after validation. Returns snapshot."""
        with self._lock:
            candidate = copy.deepcopy(self._cfg)
            for key, value in patch.items():
                if key not in candidate:
                    raise ValueError(f"unknown config key: {key}")
                candidate[key] = value
            self._validate(candidate)
            self._cfg = candidate
            return copy.deepcopy(self._cfg)

    @staticmethod
    def _validate(cfg: Dict[str, Any]) -> None:
        if cfg["weight_mode"] not in (
            "per_sensor",
            "global_direct",
            "global_ahp",
            "metric_level",
        ):
            raise ValueError(
                "weight_mode must be per_sensor|global_direct|global_ahp|metric_level"
            )
        gw = cfg["global_criteria_weights"]
        for k in ("temporal", "spatial", "privacy"):
            if float(gw.get(k, -1)) < 0:
                raise ValueError("global_criteria_weights must be non-negative")
        ahp.validate_matrix(cfg["ahp_matrix"])
        if cfg["weight_mode"] == "global_ahp":
            _weights, _lambda_max, _ci, cr = ahp.ahp_weights_and_consistency(
                cfg["ahp_matrix"]
            )
            if cr > 0.10:
                raise ValueError("AHP consistency ratio must be <= 0.10")
        for name, value in (cfg.get("metric_weights") or {}).items():
            if float(value) < 0:
                raise ValueError(f"metric weight for {name} must be non-negative")
        pf = float(cfg["privacy_floor"])
        if not (0.0 <= pf <= 1.0):
            raise ValueError("privacy_floor must be in [0,1]")
        pt = float(cfg["pass_threshold"])
        if not (0.0 < pt <= 1.0):
            raise ValueError("pass_threshold must be in (0,1]")
        for name, w in (cfg.get("privacy_weights") or {}).items():
            if not (0.0 <= float(w) <= 1.0):
                raise ValueError(f"privacy weight for {name} must be in [0,1]")
        alpha = float(cfg.get("baseline_alpha", 0.2))
        if not (0.0 < alpha <= 1.0):
            raise ValueError("baseline_alpha must be in (0,1]")
        if int(cfg.get("baseline_min_samples", 5)) < 1:
            raise ValueError("baseline_min_samples must be >= 1")
        if float(cfg.get("adaptive_threshold_multiplier", 1.5)) <= 0:
            raise ValueError("adaptive_threshold_multiplier must be positive")

    # -------------------------------------------------------------- helpers
    @staticmethod
    def sensor_key(record: Dict[str, Any]) -> str:
        """Resolve the config key for a record (same logic as the paper code)."""
        raw = (
            (record.get("contextAttribute") or record.get("contextattribute") or "").strip()
            or (record.get("stream_type") or "").strip()
            or ((record.get("resource") or {}).get("sensor_id") or "").strip()
        )
        return SENSOR_ALIASES.get(raw.lower(), raw)


# A single process-wide instance used by the Flask app.
runtime_config = RuntimeConfig()
