"""Q-PRIME AI / NLP query service.

Turns a natural-language question into SQL, sends the SQL to the Q-PRIME
read-only query API, and summarises the returned rows. Edge-only, cloud-only,
and combined scopes are routed by the core placement-aware query service.

Summaries are produced by the rule-based ``InfSummary`` - no LLM, no
network. ``LLMInference`` (Ollama) is optional and only used when
``USE_LLM_SUMMARY`` is enabled.

Run standalone:  python app.py            (listens on :5500)
In Docker:       see services/nlp/Dockerfile
"""

import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

import AINatural
import InfSummary

load_dotenv()

app = Flask(__name__)
CORS(app)

QUERY_API_URL = os.getenv("QUERY_API_URL", "").strip()
EPOCH_SCALE = os.getenv("EPOCH_SCALE", "s").lower().strip() or "s"
QUERY_TIMEOUT_S = int(os.getenv("QUERY_TIMEOUT_S", "60"))
USE_LLM_SUMMARY = os.getenv("USE_LLM_SUMMARY", "").strip().lower() in ("1", "true", "yes")

# What the core is asked for, per scope.
SCOPE_TO_IS_CLOUD = {"continuum": "continuum", "edge": "false", "cloud": "true"}


def now_ms() -> int:
    return int(time.time() * 1000)


def _empty(scope: str, query: str = "", message: Optional[str] = None, code: int = 400):
    body = {
        "sql-query": None,
        "nl-query": query,
        "sensor-data": {"success": False, "result": [], "results": []},
        "inferred-results": {"ok": False, "text": message or "", "meta": {"scope": scope}},
        "layer": scope,
        "scope": scope,
        "edge-count": 0,
        "cloud-count": 0,
        "status": {"code": code, "message": message},
    }
    return jsonify(body), code


def tier_note(edge_count: int, cloud_count: int) -> str:
    """'(12 records: 9 edge, 3 cloud)' - where the answer's data came from."""
    total = int(edge_count or 0) + int(cloud_count or 0)
    if total <= 0:
        return ""
    noun = "record" if total == 1 else "records"
    return f" ({total} {noun}: {edge_count} edge, {cloud_count} cloud)"


def summary_envelope(summary: Any, scope: str, edge_count: int = 0, cloud_count: int = 0) -> Dict[str, Any]:
    """Normalise a summary to ``{ok, text, meta}`` and record the tier split.

    The tier note goes on the headline sentence, which is what the chat UI
    renders: "Latest THP reading ... (12 records: 9 edge, 3 cloud)".
    """
    if isinstance(summary, dict):
        envelope = dict(summary)
        envelope.setdefault("ok", True)
        envelope.setdefault("meta", {})
    else:
        envelope = {"ok": True, "text": str(summary or ""), "meta": {}}

    # Aggregate SQL produces one result row per source, not one row per
    # underlying record. Do not present that implementation detail as a data
    # record count in the chat answer.
    is_aggregate = bool((envelope.get("meta") or {}).get("aggregate"))
    note = "" if is_aggregate else tier_note(edge_count, cloud_count)
    text = envelope.get("text") or ""
    if note and text:
        lines = text.split("\n")
        # skip the summariser's "Summary" banner - the note belongs on the
        # first sentence, which is the line the chat UI renders
        index = 0
        while index < len(lines) and (
            not lines[index].strip() or lines[index].strip().lower() == "summary"
        ):
            index += 1
        if index < len(lines):
            lines[index] = lines[index].rstrip() + note
        else:
            lines.append(note.strip())
        envelope["text"] = "\n".join(lines)

    meta = dict(envelope.get("meta") or {})
    meta.update({"scope": scope, "edge_count": edge_count, "cloud_count": cloud_count})
    envelope["meta"] = meta
    return envelope


def fetch_rows(sql: str, scope: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], int, int]:
    """Ask the Q-PRIME query API for the selected rows."""
    if not QUERY_API_URL:
        raise RuntimeError("Q-PRIME query service is not configured. Set QUERY_API_URL.")
    response = requests.get(
        QUERY_API_URL,
        params={
            "query": sql,
            "isCloud": SCOPE_TO_IS_CLOUD.get(scope, "continuum"),
            "query_timestamp": now_ms(),
        },
        timeout=QUERY_TIMEOUT_S,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Q-PRIME query API returned a non-JSON response") from exc
    if not response.ok:
        message = payload.get("error") or payload.get("message") or f"HTTP {response.status_code}"
        raise RuntimeError(f"Q-PRIME query API error: {message}")
    rows = payload.get("results")
    if rows is None:
        rows = payload.get("result") or []
    # 'result' is the key the original deployment's UI reads
    payload["result"] = rows
    payload["results"] = rows
    payload["success"] = not payload.get("error")
    return (
        payload,
        rows,
        int(payload.get("edge_count") or 0),
        int(payload.get("cloud_count") or 0),
    )


def device_inventory_summary(rows: List[Dict[str, Any]]) -> Optional[str]:
    """Answer for "which devices are active" / "list all devices".

    Those queries group by device and have no timestamp column, which the
    general summariser reads as a timeline starting at the epoch. The shape
    is unambiguous, so describe it directly.
    """
    if not rows or len(rows) > 50:
        return None
    name_key = count_key = None
    for key in rows[0]:
        low = str(key).lower()
        if name_key is None and low in ("device_name", "resource_device_name"):
            name_key = key
        elif count_key is None and low in ("events", "n", "count", "cnt", "event_count"):
            count_key = key
    if not name_key or not count_key:
        return None
    if not all(name_key in row and count_key in row for row in rows):
        return None

    try:
        ranked = sorted(
            ((str(r[name_key]), int(r[count_key])) for r in rows if r[name_key]),
            key=lambda pair: -pair[1],
        )
    except (TypeError, ValueError):
        return None
    if not ranked:
        return None

    total = sum(count for _, count in ranked)
    listed = ", ".join(f"{name} ({count:,})" for name, count in ranked[:10])
    more = f" and {len(ranked) - 10} more" if len(ranked) > 10 else ""
    devices = "device" if len(ranked) == 1 else "devices"
    return f"{len(ranked)} {devices} reported {total:,} records: {listed}{more}."


READING_UNITS = [
    ("temperature", "°C"),
    ("humidity", "%"),
    ("pressure", " hPa"),
    ("moisture_pct", "% moisture"),
    ("smoke_ppm", " ppm smoke"),
    ("bpm", " bpm"),
]


def latest_reading_summary(rows: List[Dict[str, Any]]) -> Optional[str]:
    """Answer for "latest temperature reading" and friends.

    A single telemetry row has no event to describe, so the generic
    summariser can only report that one record exists. State the values.
    """
    if len(rows) != 1:
        return None
    row = {str(k).lower(): v for k, v in rows[0].items()}
    parts = [
        f"{name.replace('_pct', '').replace('_ppm', '')} {row[name]:g}{unit}"
        for name, unit in READING_UNITS
        if isinstance(row.get(name), (int, float)) and not isinstance(row.get(name), bool)
    ]
    if not parts:
        return None

    device = row.get("device_name") or row.get("resource_device_name")
    when = row.get("ts")
    where = f" from {device}" if device else ""
    at = f" at {when}" if when else ""
    return f"Latest reading{where}{at}: {', '.join(parts)}."


def aggregate_summary(rows: List[Dict[str, Any]], question: str) -> Optional[Dict[str, Any]]:
    """Describe the one-row COUNT/AVG shapes used by the shipped examples."""
    if len(rows) != 1:
        return None
    row = {str(key).lower(): value for key, value in rows[0].items()}
    question_lower = question.lower()

    for key in ("door_events", "n", "count", "records", "events"):
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            count = int(value)
            location = row.get("storage_location")
            if location and key == "records":
                noun = "record" if count == 1 else "records"
                return {
                    "ok": True,
                    "text": f"{count:,} {noun} stored at {location}.",
                    "meta": {"aggregate": True},
                }
            if "door" in question_lower:
                noun = "event" if count == 1 else "events"
                period = " today" if "today" in question_lower else ""
                text = f"{count:,} door {noun}{period}."
            else:
                noun = "record" if count == 1 else "records"
                text = f"{count:,} {noun}."
            return {"ok": True, "text": text, "meta": {"aggregate": True}}

    for key, value in row.items():
        if not key.startswith(("avg_", "average_", "mean_")):
            continue
        metric = key.split("_", 1)[1].replace("_", " ") or "value"
        if metric.endswith(" today"):
            metric = metric[:-6]
            period = " today"
        elif "yesterday" in question_lower:
            period = " yesterday"
        elif "today" in question_lower:
            period = " today"
        else:
            period = ""
        if value is None:
            return {
                "ok": True,
                "text": f"No {metric} readings were found{period}.",
                "meta": {"aggregate": True, "empty": True},
            }
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        units = {"temperature": "\N{DEGREE SIGN}C", "humidity": "%", "pressure": " hPa"}
        return {
            "ok": True,
            "text": f"Average {metric}{period} is {float(value):.1f}{units.get(metric, '')}.",
            "meta": {"aggregate": True},
        }
    return None


def latest_activity_summary(rows: List[Dict[str, Any]], question: str) -> Optional[Dict[str, Any]]:
    """Describe the safe, flat projection used for latest-activity requests."""
    if not rows or "latest" not in question.lower():
        return None
    row = {str(key).lower(): value for key, value in rows[0].items()}
    device = row.get("device_name") or row.get("resource_device_name") or "a device"
    stream = row.get("contextattribute") or "sensor activity"
    event = row.get("event")
    detail = f" ({event})" if event else ""
    return {
        "ok": True,
        "text": f"Latest activity: {device} reported {stream}{detail}.",
        "meta": {"rows_considered": len(rows)},
    }


def tabular_activity_summary(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Avoid applying vision-specific language to ordinary SQL result rows."""
    if not rows:
        return None
    keys = {str(key).lower() for key in rows[0]}
    if not ({"device_name", "resource_device_name"} & keys):
        return None
    devices = []
    for row in rows:
        value = row.get("device_name") or row.get("resource_device_name")
        if value and value not in devices:
            devices.append(str(value))
    if not devices:
        return None
    noun = "record" if len(rows) == 1 else "records"
    listed = ", ".join(devices[:3])
    more = " and others" if len(devices) > 3 else ""
    return {
        "ok": True,
        "text": f"Showing {len(rows):,} {noun} from {listed}{more}.",
        "meta": {"rows_considered": len(rows)},
    }


def summarize(rows: List[Dict[str, Any]], question: str, sql: str) -> Any:
    for shaped in (
        aggregate_summary(rows, question),
        latest_activity_summary(rows, question),
        device_inventory_summary(rows),
        latest_reading_summary(rows),
        tabular_activity_summary(rows),
    ):
        if shaped:
            if isinstance(shaped, dict):
                return shaped
            return {"ok": True, "text": shaped, "meta": {"rows_considered": len(rows)}}
    if USE_LLM_SUMMARY:
        try:
            import LLMInference

            summary = LLMInference.summarize_short_safe(
                rows, sql, question, timeout=10, fallback=""
            )
            if summary:
                return summary
        except Exception as exc:
            print(f"[nlp] LLM summary unavailable ({exc}); using the rule-based summariser")
    return InfSummary.summarize_for_api(rows, question, EPOCH_SCALE)


@app.route("/api/health")
def health():
    query_api_reachable = False
    if QUERY_API_URL:
        try:
            response = requests.get(QUERY_API_URL, timeout=3)
            query_api_reachable = response.status_code < 500
        except Exception:
            pass
    return jsonify(
        {
            "status": "ok",
            "service": "qprime-nlp",
            "query_api_configured": bool(QUERY_API_URL),
            "query_api_reachable": query_api_reachable,
            "default_scope": AINatural.CONTINUUM,
            "table": AINatural.get_table_fqn(),
            "llm_summary": USE_LLM_SUMMARY,
        }
    )


@app.route("/api/query", methods=["POST"])
def query():
    """
    Main query endpoint that handles both natural language and SQL queries.

    Request body:
    {
        "query":   "user query string",
        "type":    "natural" | "sql",
        "scope": "edge" | "cloud" | "continuum"   (optional)
    }
    """
    try:
        if not request.is_json:
            return _empty(AINatural.CONTINUUM, message="Request must be JSON")

        data = request.get_json() or {}
        user_query = data.get("query")
        query_type = data.get("type")
        scope = AINatural.normalize_scope(
            data.get("scope", data.get("isCloud", AINatural.CONTINUUM))
        )

        if not user_query:
            return _empty(scope, message="Query is required")

        # Vague / chit-chat: answer without touching the continuum at all.
        if not AINatural.is_actionable(user_query):
            print(f"[nlp] non-actionable or vague query: {user_query!r}")
            try:
                inferred = InfSummary.summarize_for_api([], user_query, EPOCH_SCALE)
            except Exception as exc:
                inferred = (
                    "Assistant: I can help you explore IoT data across the edge-cloud "
                    "continuum. Try: 'latest misty', 'door openings yesterday', "
                    f"'average temperature past 3 days'. ({exc})"
                )
            return (
                jsonify(
                    {
                        "sql-query": None,
                        "nl-query": user_query,
                        "sensor-data": {"success": True, "result": [], "results": []},
                        "inferred-results": summary_envelope(inferred, scope),
                        "layer": scope,
                        "scope": scope,
                        "edge-count": 0,
                        "cloud-count": 0,
                        "status": True,
                    }
                ),
                200,
            )

        print(f"\n[nlp] processing ({scope}): {user_query}")
        try:
            sql_query = AINatural.generate_sql(user_query, is_cloud=scope)
        except Exception as exc:
            # The rule-based generator always produces SQL for a question, so
            # this is a rejected hand-written statement - say so plainly
            # rather than returning a server error.
            print(f"[nlp] could not build a query: {exc}")
            return (
                jsonify(
                    {
                        "sql-query": None,
                        "nl-query": user_query,
                        "sensor-data": {"success": False, "result": [], "results": []},
                        "inferred-results": summary_envelope(
                            {"ok": False, "text": f"I could not turn that into a query: {exc}"},
                            scope,
                        ),
                        "layer": scope,
                        "scope": scope,
                        "edge-count": 0,
                        "cloud-count": 0,
                        "status": True,
                    }
                ),
                200,
            )
        print(f"[nlp] generated SQL: {sql_query}")

        if not QUERY_API_URL:
            message = "Q-PRIME query service is not configured. Set QUERY_API_URL."
            return (
                jsonify(
                    {
                        "sql-query": sql_query,
                        "nl-query": user_query if query_type == "natural" else "",
                        "sensor-data": {"success": False, "result": [], "results": []},
                        "inferred-results": summary_envelope(
                            {"ok": False, "text": message}, scope
                        ),
                        "layer": scope,
                        "scope": scope,
                        "edge-count": 0,
                        "cloud-count": 0,
                        "status": {"code": 503, "message": message},
                    }
                ),
                503,
            )

        edge_count = cloud_count = 0
        sensor_data: Dict[str, Any] = {"success": False, "result": [], "results": []}
        response_status = 200
        try:
            sensor_data, rows, edge_count, cloud_count = fetch_rows(sql_query, scope)
            if sensor_data.get("error"):
                inferred = summary_envelope(
                    {"ok": False, "text": f"Query error: {sensor_data['error']}"}, scope
                )
            else:
                print(f"[nlp] {len(rows)} row(s): {edge_count} edge, {cloud_count} cloud")
                inferred = summary_envelope(
                    summarize(rows, user_query, sql_query), scope, edge_count, cloud_count
                )
        except Exception as exc:
            response_status = 502
            inferred = summary_envelope({"ok": False, "text": str(exc)}, scope)

        return (
            jsonify(
                {
                    "sql-query": sql_query,
                    "nl-query": user_query if query_type == "natural" else "",
                    "sensor-data": sensor_data,
                    "inferred-results": inferred,
                    "layer": scope,
                    "scope": scope,
                    "edge-count": edge_count,
                    "cloud-count": cloud_count,
                    "status": True,
                }
            ),
            response_status,
        )

    except Exception as exc:
        print(f"[nlp] error: {exc}")
        return _empty(AINatural.CONTINUUM, message=str(exc), code=500)


if __name__ == "__main__":
    port = int(os.getenv("NLP_PORT", "5500"))
    app.run(host="0.0.0.0", port=port)
