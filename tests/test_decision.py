"""Placement decisions for the six representative testbed records must match
the behaviour reported in the paper (fresh timestamps = live pipeline):

- Tello drone     -> Edge (strict privacy filter override)
- Misty II robot  -> Edge (privacy-led weights)
- ZED 2i          -> Edge
- Door sensors    -> Edge (temporal-led weights)
- THP sensor      -> Cloud (content-led weights, low privacy)
"""

import pytest

from qprime import decision, sla
from qprime.config import runtime_config

EXPECTED = {
    "tello_vision": "Edge",
    "misty_vision": "Edge",
    "zed_vision": "Edge",
    "door": "Edge",
    "thp": "Cloud",
}


@pytest.fixture(autouse=True)
def fresh_state():
    runtime_config.reload()
    sla.reset_baselines()
    yield
    runtime_config.reload()


def _process(record):
    record["sla"] = sla.evaluate(record, runtime_config)
    return decision.decide(record, runtime_config)


def test_paper_placements(sample_records):
    for record in sample_records:
        result = _process(dict(record))
        stream = record["contextAttribute"]
        assert result["decision"] == EXPECTED[stream], (
            f"{stream}: expected {EXPECTED[stream]}, got {result['decision']} "
            f"(S_edge={result['score_edge']}, S_cloud={result['score_cloud']})"
        )


def test_tello_strict_override(sample_records):
    tello = next(r for r in sample_records if r["contextAttribute"] == "tello_vision")
    result = _process(dict(tello))
    assert result["strict_override"] is True
    assert result["decision"] == "Edge"
    assert result["score_edge"] is None  # scores are not computed under override


def test_no_pii_leak_with_default_config(sample_records):
    """With the paper's configuration no PII record may be placed in Cloud."""
    for record in sample_records:
        result = _process(dict(record))
        if result["pii_detected"]:
            assert result["decision"] == "Edge", (
                f"PII record ({record['contextAttribute']}) leaked to {result['decision']}"
            )


def test_strict_all_pii_mitigation(sample_records):
    """The strict-all-PII mitigation pins every PII record to Edge even under
    content-led adversarial weights."""
    runtime_config.update(
        {
            "weight_mode": "global_direct",
            "global_criteria_weights": {"temporal": 0.05, "spatial": 0.9, "privacy": 0.05},
            "strict_privacy_all_pii": True,
        }
    )
    for record in sample_records:
        result = _process(dict(record))
        if result["pii_detected"]:
            assert result["decision"] == "Edge"


def test_content_led_weights_push_to_cloud(sample_records):
    """Content-led global weights move non-strict records to Cloud (paper's
    content-led profile: everything Cloud except the Tello override)."""
    runtime_config.update(
        {
            "weight_mode": "global_direct",
            "global_criteria_weights": {"temporal": 0.16, "spatial": 0.54, "privacy": 0.30},
        }
    )
    decisions = {}
    for record in sample_records:
        result = _process(dict(record))
        decisions[record["contextAttribute"]] = result["decision"]
    assert decisions["tello_vision"] == "Edge"  # strict override survives
    assert decisions["thp"] == "Cloud"
    assert decisions["door"] == "Cloud"


def test_privacy_floor_renormalises(sample_records):
    runtime_config.update(
        {
            "weight_mode": "global_direct",
            "global_criteria_weights": {"temporal": 0.6, "spatial": 0.4, "privacy": 0.0},
            "privacy_floor": 0.5,
        }
    )
    thp = next(r for r in sample_records if r["contextAttribute"] == "thp")
    result = _process(dict(thp))
    assert result["privacy_floor_applied"] is True
    assert result["weights"]["privacy"] >= 0.33


def test_ahp_mode_decision(sample_records):
    runtime_config.update(
        {
            "weight_mode": "global_ahp",
            "ahp_matrix": [[1, 2, 3], [0.5, 1, 2], [1 / 3, 0.5, 1]],
        }
    )
    door = next(r for r in sample_records if r["contextAttribute"] == "door")
    result = _process(dict(door))
    assert result["weight_source"] == "global_ahp"
    assert result["consistency_ratio"] is not None
    assert result["consistency_ratio"] < 0.10
