import json
import os
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DIR = os.path.join(REPO_ROOT, "services", "core")
sys.path.insert(0, CORE_DIR)

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sample_records.json")


@pytest.fixture()
def sample_records():
    """The six representative records from the paper's testbed, with fresh
    timestamps so timeliness reflects a live pipeline."""
    with open(DATA_PATH) as fh:
        records = json.load(fh)
    now_ms = int(time.time() * 1000)
    for r in records:
        r["timestamp"] = now_ms
    return records


@pytest.fixture(scope="session")
def nlp_modules():
    """The AI/NLP service's SQL generator, loaded from services/nlp."""
    nlp_dir = os.path.join(REPO_ROOT, "services", "nlp")
    sys.path.insert(0, nlp_dir)
    pytest.importorskip("rapidfuzz", reason="NLP service dependencies not installed")
    pytest.importorskip("dateutil", reason="NLP service dependencies not installed")
    import AINatural

    return AINatural
