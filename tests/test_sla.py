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
