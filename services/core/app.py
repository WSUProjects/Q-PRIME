"""HTTP API for the Q-PRIME paper intelligence and placement pipeline.

Direct producers and EdgeX events enter one QoC/privacy/AHP pipeline. Records
are stored according to the resulting Edge/Cloud/Both decision and every
placement explanation is retained in MongoDB.
"""

import copy
import os
import time

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from pymongo.errors import PyMongoError

from qprime import __version__
from qprime import ahp as ahp_mod
from qprime import decision as decision_mod
from qprime import sla as sla_mod
from qprime.config import RuntimeConfig, runtime_config
from qprime.cloud import cloud_adapter
from qprime.cloud_config import cloud_configuration
from qprime.metrics import dashboard_metrics
from qprime.normalization import normalize_direct
from qprime.pipeline import pipeline
from qprime.profiles import persistent_config
from qprime.query_router import QueryValidationError, query_router
from qprime.repository import repository

load_dotenv()

app = Flask(__name__)
START_MS = int(time.time() * 1000)
EDGEX_METADATA_URL = os.getenv("EDGEX_METADATA_URL", "http://edgex-core-metadata:59881")
PRODUCER_URL = os.getenv("QPRIME_PRODUCER_URL", "http://qprime-devices:5010").rstrip("/")


def _edgex_health():
    try:
        response = requests.get(f"{EDGEX_METADATA_URL.rstrip('/')}/api/v3/ping", timeout=2)
        return {
            "status": "connected" if response.ok else "degraded",
            "url": EDGEX_METADATA_URL,
            "http_status": response.status_code,
        }
    except requests.RequestException as exc:
        return {"status": "unavailable", "url": EDGEX_METADATA_URL, "error": str(exc)}


def _producer_request(method, path, payload=None):
    try:
        response = requests.request(method, f"{PRODUCER_URL}{path}", json=payload, timeout=10)
        data = response.json()
        if not response.ok:
            raise ValueError(data.get("error") or f"Producer returned HTTP {response.status_code}")
        return data
    except requests.RequestException as exc:
        raise RuntimeError(f"Producer controller unavailable: {exc}") from exc


@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
    return response


@app.route("/")
def index():
    return jsonify(
        {
            "service": "qprime-analysis",
            "version": __version__,
            "mode": "paper-pipeline",
            "uptime_ms": int(time.time() * 1000) - START_MS,
        }
    )


@app.route("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "qprime-analysis",
            "version": __version__,
            "mode": "paper-pipeline",
            "mongodb": repository.health(),
            "presto": query_router.health(),
            "edgex": _edgex_health(),
            "cloud": cloud_adapter.health(probe=request.args.get("probe") == "true"),
        }
    )


@app.route("/api/config", methods=["GET", "PUT", "OPTIONS"])
def config_endpoint():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        if request.method == "GET":
            return jsonify(persistent_config.snapshot())
        patch = request.get_json(force=True) or {}
        payload = {
            "scope": "global",
            "selector": "",
            "config": patch.get("config", patch),
            "label": patch.get("label", "Global Q-PRIME policy"),
            "actor": patch.get("actor", "qprime-ui"),
            "reason": patch.get("reason", "global policy update"),
        }
        return jsonify(persistent_config.create(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/config/profiles", methods=["GET", "POST", "OPTIONS"])
def config_profiles():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        if request.method == "GET":
            return jsonify(persistent_config.snapshot())
        return jsonify(persistent_config.create(request.get_json(force=True) or {})), 201
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/config/history")
def config_history():
    try:
        pipeline.initialise()
        return jsonify(
            {
                "history": repository.configuration_history(
                    request.args.get("limit", 100)
                )
            }
        )
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/config/ahp", methods=["POST", "OPTIONS"])
def config_ahp():
    """Evaluate a 3x3 pairwise matrix and optionally apply it to defaults."""
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        body = request.get_json(force=True) or {}
        if "matrix" in body:
            matrix = body["matrix"]
        else:
            judgements = body.get("judgements") or {}
            matrix = ahp_mod.matrix_from_judgements(
                float(judgements.get("temporal_vs_spatial", 1.0)),
                float(judgements.get("temporal_vs_privacy", 1.0)),
                float(judgements.get("spatial_vs_privacy", 1.0)),
            )
        ahp_mod.validate_matrix(matrix)
        weights, lambda_max, consistency_index, consistency_ratio = (
            ahp_mod.ahp_weights_and_consistency(matrix)
        )
        result = {
            "matrix": matrix,
            "weights": {
                "temporal": round(weights[0], 4),
                "spatial": round(weights[1], 4),
                "privacy": round(weights[2], 4),
            },
            "lambda_max": round(lambda_max, 4),
            "consistency_index": round(consistency_index, 4),
            "consistency_ratio": round(consistency_ratio, 4),
            "consistent": consistency_ratio <= 0.10,
            "applied": False,
        }
        if body.get("apply"):
            pipeline.initialise()
            persistent_config.create(
                {
                    "scope": body.get("scope", "global"),
                    "selector": body.get("selector", ""),
                    "config": {"ahp_matrix": matrix, "weight_mode": "global_ahp"},
                    "label": body.get("label", "AHP policy"),
                    "actor": body.get("actor", "qprime-ui"),
                    "reason": body.get("reason", "AHP matrix update"),
                }
            )
            result["applied"] = True
        return jsonify(result)
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/cloud/config", methods=["GET", "PUT", "OPTIONS"])
def cloud_config_endpoint():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        if request.method == "GET":
            return jsonify(cloud_configuration.snapshot())
        return jsonify(cloud_configuration.save(request.get_json(force=True) or {}))
    except (TypeError, ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/cloud/config/probe", methods=["POST", "OPTIONS"])
def cloud_config_probe():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        return jsonify(cloud_configuration.probe())
    except (TypeError, ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/producer/catalog")
def producer_catalog():
    try:
        return jsonify(_producer_request("GET", "/api/catalog"))
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/api/producer/status")
def producer_status():
    try:
        pipeline.initialise()
        current = _producer_request("GET", "/api/status")
        saved = repository.producer_configuration() or {"mode": "off", "devices": []}
        return jsonify({"current": current, "saved": saved})
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/producer/start", methods=["POST", "OPTIONS"])
def producer_start():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        body = request.get_json(force=True) or {}
        result = _producer_request("POST", "/api/start", body)
        # Persist configuration only. Runtime state is deliberately never
        # restored, keeping every Docker startup in the Off mode.
        saved = repository.save_producer_configuration({"mode": body.get("mode"), "devices": body.get("devices") or []})
        return jsonify({"current": result, "saved": saved})
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/producer/stop", methods=["POST", "OPTIONS"])
def producer_stop():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        current = _producer_request("POST", "/api/stop")
        saved = repository.save_producer_configuration({"mode": "off", "devices": []})
        return jsonify({"current": current, "saved": saved})
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/query", methods=["GET", "POST", "OPTIONS"])
def query_records():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        if request.method == "GET":
            sql = request.args.get("query", "")
            scope = request.args.get("isCloud", request.args.get("scope", "continuum"))
        else:
            body = request.get_json(force=True) or {}
            sql = body.get("query") or body.get("sql") or ""
            scope = body.get("scope", body.get("isCloud", "continuum"))
        return jsonify(query_router.execute(sql, scope))
    except QueryValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        return jsonify({"error": f"query failed: {exc}"}), 502


@app.route("/api/results/overview")
def results_overview():
    try:
        pipeline.initialise()
        return jsonify(dashboard_metrics.overview())
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/results/decisions")
def results_decisions():
    filters = {
        key: request.args.get(key)
        for key in ("device", "stream", "source", "recommendation", "backend")
        if request.args.get(key)
    }
    if request.args.get("pii") is not None:
        filters["pii"] = request.args.get("pii", "").lower() in {"1", "true", "yes"}
    for key in ("from_ms", "to_ms"):
        if request.args.get(key):
            filters[key] = request.args[key]
    try:
        pipeline.initialise()
        return jsonify(dashboard_metrics.decisions(filters, request.args.get("limit", 200)))
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/results/qoc")
def results_qoc():
    try:
        pipeline.initialise()
        return jsonify(dashboard_metrics.qoc(request.args.get("limit", 500)))
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/results/privacy")
def results_privacy():
    try:
        pipeline.initialise()
        return jsonify(dashboard_metrics.privacy())
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/results/performance")
def results_performance():
    try:
        pipeline.initialise()
        return jsonify(dashboard_metrics.performance(request.args.get("limit", 500)))
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


@app.route("/api/results/sensitivity", methods=["POST", "OPTIONS"])
def results_sensitivity():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        body = request.get_json(force=True) or {}
        weights = body.get("weights") or {}
        return jsonify(
            dashboard_metrics.sensitivity(
                weights,
                float(body.get("privacy_floor", 0)),
                bool(body.get("force_pii_edge", False)),
            )
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


def _analysis_runtime(config_patch):
    if config_patch is None:
        return runtime_config
    if not isinstance(config_patch, dict):
        raise ValueError("config must be a JSON object")
    runtime = RuntimeConfig()
    runtime.update(config_patch)
    return runtime


@app.route("/api/ingest", methods=["POST", "OPTIONS"])
def ingest_direct():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        body = request.get_json(force=True, silent=False)
        return jsonify(pipeline.ingest_direct(body)), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/api/ingest/edgex", methods=["POST", "OPTIONS"])
def ingest_edgex():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        pipeline.initialise()
        body = request.get_json(force=True, silent=False)
        results = pipeline.ingest_edgex(body)
        return jsonify({"count": len(results), "results": results}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/api/analyze", methods=["POST", "OPTIONS"])
def analyze():
    """Return an in-memory analysis of one record, without side effects.

    Accepted body:
        {"record": {...}, "config": {...optional runtime overrides...}}

    A raw record object is also accepted when no per-request configuration is
    needed.
    """
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        body = request.get_json(force=True, silent=False)
        if not isinstance(body, dict):
            return jsonify({"error": "request body must be a JSON object"}), 400

        wrapped = "record" in body
        record = body.get("record") if wrapped else body
        config_patch = body.get("config") if wrapped else None
        if not isinstance(record, dict):
            return jsonify({"error": "record must be a JSON object"}), 400
        if not str(record.get("contextAttribute") or "").strip():
            return jsonify({"error": "record is missing contextAttribute"}), 400

        profile = None
        if config_patch is None:
            pipeline.initialise()
            runtime, profile = persistent_config.runtime_for(record)
        else:
            runtime = _analysis_runtime(config_patch)
        evaluated = copy.deepcopy(record)
        evaluated = normalize_direct(evaluated)
        evaluated["sla"] = sla_mod.evaluate(evaluated, runtime)
        recommendation = decision_mod.decide(evaluated, runtime)

        return jsonify(
            {
                "analysis": recommendation,
                "qoc": evaluated["sla"],
                "config": runtime.snapshot(),
                "profile": profile,
            }
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PyMongoError as exc:
        return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503


if __name__ == "__main__":
    port = int(os.getenv("QPRIME_ANALYSIS_PORT", "5005"))
    app.run(host="0.0.0.0", port=port, threaded=True)
