import time

from qprime import sla
from qprime.config import runtime_config


def _cfg():
    return runtime_config.snapshot()


def test_fresh_record_scores_high(sample_records):
    door = dict(next(r for r in sample_records if r["contextAttribute"] == "door"))
    door["timestamp"] = int(time.time() * 1000)
    s = sla.compute_slas(door, _cfg())
    assert s["timeliness"]["score"] > 0.9
    assert s["completeness"]["score"] > 0.8
    assert s["correctness"]["score"] == 1.0
    assert s["significance"]["score"] == 1.0


def test_stale_record_fails_timeliness(sample_records):
    door = dict(next(r for r in sample_records if r["contextAttribute"] == "door"))
    door["timestamp"] = int(time.time()) - 3600
    s = sla.compute_slas(door, _cfg())
    assert s["timeliness"]["score"] == 0.0
    assert not s["timeliness"]["passed"]


def test_missing_fields_lower_completeness(sample_records):
    thp = dict(next(r for r in sample_records if r["contextAttribute"] == "thp"))
    thp["timestamp"] = int(time.time())
    full = sla.compute_slas(thp, _cfg())["completeness"]["score"]
    thp2 = dict(thp)
    thp2["contextValue"] = {"battery": 100}  # drop most fields
    partial = sla.compute_slas(thp2, _cfg())["completeness"]["score"]
    assert partial < full


def test_heartbeat_is_low_significance(sample_records):
    door = dict(next(r for r in sample_records if r["contextAttribute"] == "door"))
    door["timestamp"] = int(time.time())
    door["contextValue"] = dict(door["contextValue"], event="heartbeat")
    s = sla.compute_slas(door, _cfg())
    assert s["significance"]["score"] == 0.2


def test_default_correctness_rules_reject_invalid_sensor_values(sample_records):
    thp = dict(next(r for r in sample_records if r["contextAttribute"] == "thp"))
    valid = sla.compute_slas(thp, _cfg())

    thp["contextValue"] = dict(thp["contextValue"], humidity=150)
    invalid = sla.compute_slas(thp, _cfg())

    assert valid["correctness"]["checks_total"] > 1
    assert invalid["correctness"]["score"] < valid["correctness"]["score"]


def test_completeness_resolves_tello_schema_and_array_paths(sample_records):
    tello = dict(next(r for r in sample_records if r["contextAttribute"] == "tello_vision"))
    expected = sla._find_expected("tello_vision", _cfg())

    assert "contextValue.detections[].name" in expected
    full = sla.compute_slas(tello, _cfg())

    tello["contextValue"] = dict(tello["contextValue"])
    tello["contextValue"]["detections"] = [dict(tello["contextValue"]["detections"][0])]
    del tello["contextValue"]["detections"][0]["name"]
    partial = sla.compute_slas(tello, _cfg())

    assert partial["completeness"]["score"] < full["completeness"]["score"]
