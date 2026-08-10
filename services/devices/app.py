"""Idle, user-controlled record producers for the Q-PRIME demonstration.

The container intentionally does nothing at startup.  The dashboard starts one
of two mutually exclusive modes through the Q-PRIME core: a configurable
direct simulator, or the complete paper testbed delivered through EdgeX.
"""

import copy
import logging
import os
import random
import threading
import time
from typing import Any, Dict, List
from urllib.parse import quote

import requests
from flask import Flask, jsonify, request

from devices import DEVICES, build_catalogue, make_record

app = Flask(__name__)
log = logging.getLogger("qprime-producer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

CORE_URL = os.getenv("QPRIME_CORE_URL", "http://qprime-analysis:5005").rstrip("/")
EDGEX_METADATA_URL = os.getenv("EDGEX_METADATA_URL", "http://edgex-core-metadata:59881").rstrip("/")
EDGEX_DEVICE_REST_URL = os.getenv("EDGEX_DEVICE_REST_URL", "http://edgex-device-rest:59986").rstrip("/")
SAMPLE_RATE = max(1.0, float(os.getenv("QPRIME_SAMPLE_RATE_PER_MIN", "60")))
CATALOGUE = build_catalogue()
BY_NAME = {device["device_name"]: device for device in CATALOGUE}
STREAMS = sorted({device["stream"] for device in CATALOGUE})
LOCK = threading.Lock()
STATE: Dict[str, Any] = {"mode": "off", "running": False, "run_id": 0, "started_at": None, "sent": 0, "failed": 0, "message": "No generated data source is running."}


def _catalog_public() -> List[Dict[str, Any]]:
    return [{key: device.get(key) for key in ("device_name", "stream", "refresh_rate", "privacy_filter")} for device in CATALOGUE]


def _active(run_id: int) -> bool:
    with LOCK:
        return STATE["running"] and STATE["run_id"] == run_id


def _result(run_id: int, ok: bool) -> None:
    with LOCK:
        if STATE["run_id"] == run_id:
            STATE["sent" if ok else "failed"] += 1


def _post(url: str, payload: Dict[str, Any], timeout: int = 10) -> bool:
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return True


def _profile(stream: str) -> Dict[str, Any]:
    return {"apiVersion": "v3", "profile": {"name": f"qprime-demo-{stream}", "manufacturer": "Q-PRIME", "model": "paper-testbed", "deviceResources": [{"name": stream, "properties": {"valueType": "Object", "readWrite": "W"}}]}}


def _edgex_device(device: Dict[str, Any]) -> Dict[str, Any]:
    return {"apiVersion": "v3", "device": {"name": device["device_name"], "description": "Q-PRIME sample EdgeX device", "adminState": "UNLOCKED", "operatingState": "UP", "serviceName": "device-rest", "profileName": f"qprime-demo-{device['stream']}", "protocols": {"other": {}}, "tags": {"contextAttribute": device["stream"], "refreshRate": device["refresh_rate"], "privacy_filter": device.get("privacy_filter", False), "device_id": device["device_id"], "device_name": device["device_name"], "gateway_id": device["gateway_id"], "location": device["location"], "entity": device["gateway_id"]}}}


def _edgex_create(path: str, payload: Dict[str, Any]) -> bool:
    try:
        response = requests.post(f"{EDGEX_METADATA_URL}{path}", json=[payload], timeout=10)
        if response.status_code == 409:
            return True
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.warning("EdgeX provisioning failed: %s", exc)
        return False


def _provision_edgex() -> bool:
    try:
        requests.get(f"{EDGEX_METADATA_URL}/api/v3/ping", timeout=5).raise_for_status()
    except requests.RequestException:
        return False
    return all(_edgex_create("/api/v3/deviceprofile", _profile(stream)) for stream in STREAMS) and all(_edgex_create("/api/v3/device", _edgex_device(device)) for device in CATALOGUE)


def _direct_worker(run_id: int, device: Dict[str, Any], settings: Dict[str, Any]) -> None:
    interval = max(100, int(settings.get("interval_ms", 1000))) / 1000
    degraded = max(0, min(1, float(settings.get("degraded_pct", 0))))
    while _active(run_id):
        record = make_record(device, degraded_pct=degraded, overrides=settings)
        try:
            _post(f"{CORE_URL}/api/ingest", record)
            _result(run_id, True)
        except requests.RequestException as exc:
            log.warning("Simulator delivery failed for %s: %s", device["device_name"], exc)
            _result(run_id, False)
        time.sleep(interval)


def _sample_edgex_worker(run_id: int) -> None:
    if not _provision_edgex():
        with LOCK:
            if STATE["run_id"] == run_id:
                STATE.update({"running": False, "mode": "off", "message": "Sample EdgeX feed could not provision EdgeX."})
        return
    interval = 60.0 / SAMPLE_RATE
    while _active(run_id):
        device = random.choice(CATALOGUE)
        record = make_record(device)
        url = f"{EDGEX_DEVICE_REST_URL}/api/v3/resource/{quote(device['device_name'], safe='')}/{quote(device['stream'], safe='')}"
        try:
            _post(url, record["contextValue"])
            _result(run_id, True)
        except requests.RequestException as exc:
            log.warning("Sample EdgeX delivery failed: %s", exc)
            _result(run_id, False)
        time.sleep(interval)


@app.get("/api/catalog")
def catalog():
    return jsonify({"devices": _catalog_public()})


@app.get("/api/status")
def status():
    with LOCK:
        return jsonify(copy.deepcopy(STATE))


@app.post("/api/stop")
def stop():
    with LOCK:
        STATE.update({"running": False, "mode": "off", "run_id": STATE["run_id"] + 1, "message": "No generated data source is running."})
        return jsonify(copy.deepcopy(STATE))


@app.post("/api/start")
def start():
    body = request.get_json(force=True) or {}
    mode = body.get("mode")
    if mode not in {"simulator", "sample_edgex"}:
        return jsonify({"error": "mode must be simulator or sample_edgex"}), 400
    selected = body.get("devices") or []
    if mode == "simulator" and not selected:
        return jsonify({"error": "Select at least one sensor for the simulator."}), 400
    with LOCK:
        STATE.update({"mode": mode, "running": True, "run_id": STATE["run_id"] + 1, "started_at": int(time.time() * 1000), "sent": 0, "failed": 0, "message": "Starting simulator…" if mode == "simulator" else "Starting sample EdgeX feed…"})
        run_id = STATE["run_id"]
    if mode == "sample_edgex":
        threading.Thread(target=_sample_edgex_worker, args=(run_id,), daemon=True).start()
    else:
        for spec in selected:
            device = BY_NAME.get(spec.get("device_name"))
            if not device:
                continue
            settings = dict(spec)
            threading.Thread(target=_direct_worker, args=(run_id, device, settings), daemon=True).start()
        with LOCK:
            STATE["message"] = f"Simulator running with {len(selected)} sensor(s)."
    return jsonify({"status": "started", **copy.deepcopy(STATE)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("QPRIME_PRODUCER_PORT", "5010")), threaded=True)
