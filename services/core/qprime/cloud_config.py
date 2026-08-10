"""Encrypted, MongoDB-backed AWS configuration for the Q-PRIME Cloud layer."""

import base64
import copy
import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from .cloud import AwsCloudAdapter, cloud_adapter
from .repository import MongoRepository, repository, utc_ms


SETTINGS = (
    "enabled", "mode", "region", "kinesis_stream", "firehose_stream",
    "athena_database", "athena_table", "athena_workgroup", "athena_output",
)
SECRET_FIELDS = ("access_key_id", "secret_access_key", "session_token")


class CloudConfiguration:
    """Owns encrypted credential persistence and live adapter reconfiguration."""

    def __init__(self, repo: Optional[MongoRepository] = None, adapter: Optional[AwsCloudAdapter] = None):
        self.repository = repo or repository
        self.adapter = adapter or cloud_adapter
        self._lock = threading.RLock()
        self._loaded = False
        self._source = "environment"

    @staticmethod
    def _key_path() -> Path:
        return Path(os.getenv("QPRIME_CONFIG_KEY_PATH", "/var/lib/qprime/secrets/aws-config.key"))

    def _fernet(self) -> Fernet:
        supplied = os.getenv("QPRIME_CONFIG_ENCRYPTION_KEY", "").strip()
        if supplied:
            return Fernet(supplied.encode("utf-8"))
        path = self._key_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            key = path.read_bytes().strip()
        except FileNotFoundError:
            key = base64.urlsafe_b64encode(secrets.token_bytes(32))
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                key = path.read_bytes().strip()
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(key + b"\n")
        return Fernet(key)

    @staticmethod
    def _settings(payload: Dict[str, Any]) -> Dict[str, Any]:
        values = {key: payload.get(key) for key in SETTINGS}
        values["enabled"] = bool(values["enabled"])
        values["mode"] = str(values["mode"] or "firehose").strip().lower()
        if values["mode"] not in {"firehose", "kinesis"}:
            raise ValueError("AWS ingest mode must be firehose or kinesis")
        for key in SETTINGS:
            if key not in {"enabled", "mode"}:
                values[key] = str(values[key] or "").strip()
        values["athena_workgroup"] = values["athena_workgroup"] or "primary"
        return values

    def _decrypt(self, document: Dict[str, Any]) -> Dict[str, Any]:
        encrypted = document.get("encrypted_credentials")
        if not encrypted:
            return {}
        try:
            result = json.loads(self._fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8"))
        except (InvalidToken, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Saved AWS credentials cannot be decrypted; enter them again.") from exc
        return {key: str(result.get(key) or "") for key in SECRET_FIELDS}

    @staticmethod
    def _public(document: Optional[Dict[str, Any]], source: str, adapter: AwsCloudAdapter) -> Dict[str, Any]:
        if not document:
            result = adapter.public_configuration()
            result.update({"persisted": False, "source": source, "updated_at": None})
            return result
        result = {key: document.get(key, "") for key in SETTINGS}
        result.update(
            {
                "persisted": True,
                "source": source,
                "updated_at": document.get("updated_at"),
                "access_key_configured": bool(document.get("encrypted_credentials")),
                "session_token_configured": bool(document.get("has_session_token")),
            }
        )
        return result

    def initialise(self) -> None:
        with self._lock:
            if self._loaded:
                return
            document = self.repository.cloud_configuration()
            if document:
                values = self._settings(document)
                values.update(self._decrypt(document))
                self.adapter.configure(values)
                self._source = "mongodb"
            self._loaded = True

    def snapshot(self) -> Dict[str, Any]:
        self.initialise()
        return self._public(self.repository.cloud_configuration(), self._source, self.adapter)

    def save(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("AWS configuration must be a JSON object")
        with self._lock:
            previous = self.repository.cloud_configuration()
            values = self._settings(payload)
            provided = {key: str(payload.get(key) or "").strip() for key in SECRET_FIELDS}
            supplied = any(provided.values())
            if supplied and not (provided["access_key_id"] and provided["secret_access_key"]):
                raise ValueError("Provide both AWS access key ID and secret access key.")
            credentials = provided if supplied else self._decrypt(previous) if previous else {}
            if values["enabled"] and not (credentials.get("access_key_id") and credentials.get("secret_access_key")):
                raise ValueError("Static AWS access key ID and secret access key are required when Cloud is enabled.")
            encrypted = self._fernet().encrypt(json.dumps(credentials).encode("utf-8")).decode("utf-8") if credentials else ""
            now = utc_ms()
            document = {**values, "encrypted_credentials": encrypted, "has_session_token": bool(credentials.get("session_token")), "updated_at": now}
            audit = {
                "created_at": now,
                "kind": "aws_cloud_configuration",
                "actor": str(payload.get("actor") or "qprime-ui"),
                "reason": "AWS Cloud configuration update",
                "changed_fields": sorted([*SETTINGS, *(SECRET_FIELDS if supplied else [])]),
            }
            saved = self.repository.save_cloud_configuration(document, audit)
            live = copy.deepcopy(values)
            live.update(credentials)
            self.adapter.configure(live)
            self._source = "mongodb"
            self._loaded = True
            return self._public(saved, self._source, self.adapter)

    def probe(self) -> Dict[str, Any]:
        self.initialise()
        return self.adapter.health(probe=True)


cloud_configuration = CloudConfiguration()
