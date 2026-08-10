"""Versioned, MongoDB-backed Q-PRIME policy profiles."""

import copy
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from pymongo.errors import DuplicateKeyError

from .config import RuntimeConfig, runtime_config
from .repository import MongoRepository, repository


PROFILE_SCOPES = ("global", "stream", "device")


def _merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _record_selectors(record: Dict[str, Any]) -> Tuple[str, str, str]:
    resource = record.get("resource") or {}
    device_id = str(resource.get("device_id") or "").strip()
    device_name = str(resource.get("device_name") or "").strip()
    stream = RuntimeConfig.sensor_key(record)
    return device_id, device_name, stream


class PersistentConfig:
    """Resolve and version active policy without hiding persistence semantics."""

    def __init__(self, repo: Optional[MongoRepository] = None):
        self.repository = repo or repository

    def ensure_seeded(self) -> Dict[str, Any]:
        active = self.repository.active_profile("global", "")
        if active:
            return active
        now = int(time.time() * 1000)
        config = runtime_config.snapshot()
        profile = {
            "scope": "global",
            "selector": "",
            "version": "global-default-v1",
            "label": "Paper defaults",
            "config": config,
        }
        audit = {
            "created_at": now,
            "scope": "global",
            "selector": "",
            "previous_version": None,
            "new_version": profile["version"],
            "changed_fields": sorted(config.keys()),
            "actor": "system",
            "reason": "initial paper configuration",
        }
        try:
            return self.repository.activate_profile(profile, audit)
        except DuplicateKeyError:
            # Another request seeded the defaults first, or a previous run left
            # this version inactive. Adopt it instead of failing the ingest.
            adopted = self.repository.adopt_profile("global", "", profile["version"])
            if adopted:
                return adopted
            raise

    def snapshot(self) -> Dict[str, Any]:
        self.ensure_seeded()
        profiles = self.repository.active_profiles()
        return {
            "active_profiles": profiles,
            "resolution_order": ["device", "stream", "global"],
        }

    def resolve(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_seeded()
        device_id, device_name, stream = _record_selectors(record)
        for selector in (device_id, device_name):
            if selector:
                profile = self.repository.active_profile("device", selector)
                if profile:
                    return profile
        if stream:
            profile = self.repository.active_profile("stream", stream)
            if profile:
                return profile
        profile = self.repository.active_profile("global", "")
        if not profile:
            raise RuntimeError("global Q-PRIME profile is not configured")
        return profile

    def runtime_for(self, record: Dict[str, Any]) -> Tuple[RuntimeConfig, Dict[str, Any]]:
        profile = self.resolve(record)
        runtime = RuntimeConfig()
        runtime.update(profile["config"])
        return runtime, profile

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        scope = str(payload.get("scope") or "").strip().lower()
        selector = str(payload.get("selector") or "").strip()
        if scope not in PROFILE_SCOPES:
            raise ValueError("scope must be global|stream|device")
        if scope != "global" and not selector:
            raise ValueError("selector is required for stream and device profiles")
        if scope == "global":
            selector = ""

        previous = self.repository.active_profile(scope, selector)
        global_profile = self.repository.active_profile("global", "") or self.ensure_seeded()
        base_config = (previous or global_profile)["config"]
        patch = payload.get("config")
        if not isinstance(patch, dict) or not patch:
            raise ValueError("config must be a non-empty JSON object")
        config = _merge(base_config, patch)

        runtime = RuntimeConfig()
        runtime.update(config)
        validated = runtime.snapshot()
        now = int(time.time() * 1000)
        version = f"{scope}-{now}-{uuid.uuid4().hex[:8]}"
        profile = {
            "scope": scope,
            "selector": selector,
            "version": version,
            "label": str(payload.get("label") or f"{scope} policy"),
            "config": validated,
        }
        audit = {
            "created_at": now,
            "scope": scope,
            "selector": selector,
            "previous_version": previous.get("version") if previous else None,
            "new_version": version,
            "changed_fields": sorted(patch.keys()),
            "actor": str(payload.get("actor") or "qprime-ui"),
            "reason": str(payload.get("reason") or "user configuration update"),
        }
        saved = self.repository.activate_profile(profile, audit)
        self.repository.invalidate_baselines(scope, selector)
        return saved


persistent_config = PersistentConfig()
