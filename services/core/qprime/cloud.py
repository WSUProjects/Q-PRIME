"""Optional AWS write and Athena query adapter for the paper Cloud layer."""

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


def _enabled(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class AwsCloudAdapter:
    def __init__(self):
        self._lock = threading.RLock()
        self.timeout_s = int(os.getenv("AWS_QUERY_TIMEOUT_S", "60"))
        self._last_error: Optional[str] = None
        self._last_write_at: Optional[int] = None
        self._config = Config(
            connect_timeout=3,
            read_timeout=10,
            retries={"max_attempts": 2, "mode": "standard"},
        )
        self.configure(self.environment_configuration())

    @staticmethod
    def environment_configuration() -> Dict[str, Any]:
        """Legacy deployment fallback when no dashboard configuration is saved."""
        return {
            "enabled": _enabled(os.getenv("AWS_CLOUD_ENABLED")),
            "mode": os.getenv("AWS_INGEST_MODE", "firehose").strip().lower(),
            "region": os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "")).strip(),
            "kinesis_stream": os.getenv("AWS_KINESIS_STREAM", "").strip(),
            "firehose_stream": os.getenv("AWS_FIREHOSE_STREAM", "").strip(),
            "athena_database": os.getenv("AWS_ATHENA_DATABASE", "").strip(),
            "athena_table": os.getenv("AWS_ATHENA_TABLE", "").strip(),
            "athena_workgroup": os.getenv("AWS_ATHENA_WORKGROUP", "primary").strip(),
            "athena_output": os.getenv("AWS_ATHENA_OUTPUT", "").strip(),
            "access_key_id": os.getenv("AWS_ACCESS_KEY_ID", "").strip(),
            "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", "").strip(),
            "session_token": os.getenv("AWS_SESSION_TOKEN", "").strip(),
        }

    def configure(self, values: Dict[str, Any]) -> None:
        """Atomically replace the settings used by future AWS operations."""
        mode = str(values.get("mode") or "firehose").strip().lower()
        if mode not in {"firehose", "kinesis"}:
            raise ValueError("AWS ingest mode must be firehose or kinesis")
        with self._lock:
            self.enabled = bool(values.get("enabled"))
            self.mode = mode
            self.region = str(values.get("region") or "").strip()
            self.kinesis_stream = str(values.get("kinesis_stream") or "").strip()
            self.firehose_stream = str(values.get("firehose_stream") or "").strip()
            self.athena_database = str(values.get("athena_database") or "").strip()
            self.athena_table = str(values.get("athena_table") or "").strip()
            self.athena_workgroup = str(values.get("athena_workgroup") or "primary").strip() or "primary"
            self.athena_output = str(values.get("athena_output") or "").strip()
            self.access_key_id = str(values.get("access_key_id") or "").strip()
            self.secret_access_key = str(values.get("secret_access_key") or "").strip()
            self.session_token = str(values.get("session_token") or "").strip()
            self._last_error = None

    def public_configuration(self) -> Dict[str, Any]:
        """Return settings safe to show in HTTP responses; never include credentials."""
        with self._lock:
            return {
                "enabled": self.enabled, "mode": self.mode, "region": self.region,
                "kinesis_stream": self.kinesis_stream, "firehose_stream": self.firehose_stream,
                "athena_database": self.athena_database, "athena_table": self.athena_table,
                "athena_workgroup": self.athena_workgroup, "athena_output": self.athena_output,
                "access_key_configured": bool(self.access_key_id and self.secret_access_key),
                "session_token_configured": bool(self.session_token),
            }

    def _client(self, service: str):
        kwargs: Dict[str, Any] = {"region_name": self.region, "config": self._config}
        if self.access_key_id and self.secret_access_key:
            kwargs.update({"aws_access_key_id": self.access_key_id, "aws_secret_access_key": self.secret_access_key})
            if self.session_token:
                kwargs["aws_session_token"] = self.session_token
        return boto3.client(service, **kwargs)

    @staticmethod
    def _athena_value(value: Optional[str], column_type: str) -> Any:
        """Convert Athena's string result cells to JSON-native scalar values."""
        if value is None:
            return None
        kind = str(column_type or "").lower()
        try:
            if kind in {"tinyint", "smallint", "integer", "int", "bigint"}:
                return int(value)
            if kind.startswith(("decimal", "double", "real", "float")):
                return float(value)
            if kind == "boolean":
                return value.strip().lower() == "true"
        except ValueError:
            return value
        return value

    def configured(self) -> bool:
        if not self.enabled or not self.region:
            return False
        if self.mode == "kinesis":
            return bool(self.kinesis_stream)
        return self.mode == "firehose" and bool(self.firehose_stream)

    def athena_configured(self) -> bool:
        return bool(
            self.configured()
            and self.athena_database
            and self.athena_table
            and self.athena_output
        )

    def health(self, probe: bool = False) -> Dict[str, Any]:
        if not self.configured():
            return {
                "status": "local_fallback",
                "configured": False,
                "mode": "mongodb_cloud_fallback",
            }
        result: Dict[str, Any] = {
            "status": "degraded" if self._last_error else "configured",
            "configured": True,
            "mode": self.mode,
            "region": self.region,
            "athena_configured": self.athena_configured(),
            "last_write_at": self._last_write_at,
            "last_error": self._last_error,
        }
        if not probe:
            return result
        try:
            if self.mode == "kinesis":
                self._client("kinesis").describe_stream_summary(
                    StreamName=self.kinesis_stream
                )
            else:
                self._client("firehose").describe_delivery_stream(
                    DeliveryStreamName=self.firehose_stream,
                    Limit=1,
                )
            result["status"] = "connected"
            result["last_error"] = None
        except (BotoCoreError, ClientError) as exc:
            result["status"] = "degraded"
            result["last_error"] = str(exc)
        return result

    def write(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("AWS Cloud is not configured")
        data = (json.dumps(record, separators=(",", ":"), default=str) + "\n").encode("utf-8")
        try:
            if self.mode == "kinesis":
                response = self._client("kinesis").put_record(
                    StreamName=self.kinesis_stream,
                    Data=data,
                    PartitionKey=str(record.get("record_id") or "qprime"),
                )
                reference = response.get("SequenceNumber")
            else:
                response = self._client("firehose").put_record(
                    DeliveryStreamName=self.firehose_stream,
                    Record={"Data": data},
                )
                reference = response.get("RecordId")
            self._last_error = None
            self._last_write_at = int(time.time() * 1000)
            return {"backend": f"aws_{self.mode}", "reference": reference}
        except (BotoCoreError, ClientError) as exc:
            self._last_error = str(exc)
            raise RuntimeError(f"AWS {self.mode} write failed: {exc}") from exc

    def query(self, sql: str) -> List[Dict[str, Any]]:
        if not self.athena_configured():
            raise RuntimeError("AWS Athena is not configured")
        client = self._client("athena")
        execution = client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": self.athena_database},
            ResultConfiguration={"OutputLocation": self.athena_output},
            WorkGroup=self.athena_workgroup,
        )
        execution_id = execution["QueryExecutionId"]
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            state_payload = client.get_query_execution(QueryExecutionId=execution_id)
            status = state_payload["QueryExecution"]["Status"]
            state = status["State"]
            if state == "SUCCEEDED":
                break
            if state in {"FAILED", "CANCELLED"}:
                reason = status.get("StateChangeReason") or state
                raise RuntimeError(f"Athena query {state.lower()}: {reason}")
            time.sleep(0.25)
        else:
            client.stop_query_execution(QueryExecutionId=execution_id)
            raise RuntimeError("Athena query timed out")

        paginator = client.get_paginator("get_query_results")
        rows: List[List[Optional[str]]] = []
        column_types: List[str] = []
        for page in paginator.paginate(QueryExecutionId=execution_id):
            if not column_types:
                column_types = [
                    str(column.get("Type") or "")
                    for column in page["ResultSet"].get("ResultSetMetadata", {}).get("ColumnInfo", [])
                ]
            for row in page["ResultSet"].get("Rows", []):
                rows.append([cell.get("VarCharValue") for cell in row.get("Data", [])])
        if not rows:
            return []
        headers = [str(value or "") for value in rows[0]]
        return [
            {
                header: self._athena_value(value, column_types[index] if index < len(column_types) else "")
                for index, (header, value) in enumerate(zip(headers, values))
            }
            for values in rows[1:]
        ]


cloud_adapter = AwsCloudAdapter()
