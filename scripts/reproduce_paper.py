#!/usr/bin/env python3
"""Reproduce the paper's headline placement behaviour offline.

Feeds the six representative testbed records (tests/data/sample_records.json,
captured from the real deployment) through the Q-PRIME pipeline - QoC
evaluation + placement decision - without any servers, and prints:

1. the per-device placements under the paper's configuration;
2. the AHP priority profiles (all 6 orderings of temporal/content/privacy)
   with their derived weights and consistency ratio;
3. the privacy outcome (PII records leaked to cloud) under
   (a) the paper's config, (b) a no-privacy ablation, (c) the strict-all-PII
   mitigation.

Run:  python scripts/reproduce_paper.py
"""

import itertools
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "services", "core"))
from qprime import ahp, decision, sla  # noqa: E402
from qprime.config import runtime_config  # noqa: E402


def load_records():
    with open(os.path.join(ROOT, "tests", "data", "sample_records.json")) as fh:
        records = json.load(fh)
    now_ms = int(time.time() * 1000)
    for r in records:
        r["timestamp"] = now_ms  # live pipeline conditions
    return records


def run_pipeline(records):
    results = []
    sla.reset_baselines()
    for record in records:
        rec = dict(record)
        rec["sla"] = sla.evaluate(rec, runtime_config)
        results.append((rec, decision.decide(rec, runtime_config)))
    return results


def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main():
    records = load_records()

    # ---------------------------------------------------------- placements
    section("1. Placements under the paper's configuration (per-sensor weights)")
    runtime_config.reload()
    print(f"{'Device':24} {'Stream':14} {'Decision':8} {'S_edge':>8} {'S_cloud':>8}  Note")
    for rec, res in run_pipeline(records):
        name = rec["resource"].get("device_name", "?")
        note = "strict privacy filter" if res["strict_override"] else ""
        se = f"{res['score_edge']:.3f}" if res["score_edge"] is not None else "-"
        sc = f"{res['score_cloud']:.3f}" if res["score_cloud"] is not None else "-"
        print(f"{name:24} {rec['contextAttribute']:14} {res['decision']:8} {se:>8} {sc:>8}  {note}")

    # ------------------------------------------------------- AHP profiles
    section("2. AHP priority profiles (Saaty 1-2-3 matrix, all 6 orderings)")
    base = [[1, 2, 3], [1 / 2, 1, 2], [1 / 3, 1 / 2, 1]]
    labels = ("temporal", "content", "privacy")
    print(f"{'Priority order':32} {'w_t':>7} {'w_c':>7} {'w_p':>7} {'CR':>8}")
    for perm in itertools.permutations(range(3)):
        A = [[base[perm.index(i)][perm.index(j)] for j in range(3)] for i in range(3)]
        W, _lm, _ci, cr = ahp.ahp_weights_and_consistency(A)
        order = " > ".join(labels[i] for i in sorted(range(3), key=lambda k: -W[k]))
        print(f"{order:32} {W[0]:7.3f} {W[1]:7.3f} {W[2]:7.3f} {cr:8.4f}")

    # ---------------------------------------------------------- privacy
    section("3. Privacy outcome (PII records recommended for Cloud)")

    def cloud_recommendations():
        n_pii = n_cloud = 0
        for _rec, res in run_pipeline(records):
            if res["pii_detected"]:
                n_pii += 1
                if res["decision"] in ("Cloud", "Both"):
                    n_cloud += 1
        return n_pii, n_cloud

    runtime_config.reload()
    p, c = cloud_recommendations()
    print(f"(a) Paper configuration:               {c}/{p} PII records recommended for Cloud")

    runtime_config.update(
        {
            "weight_mode": "global_direct",
            "global_criteria_weights": {"temporal": 0.05, "spatial": 0.90, "privacy": 0.05},
        }
    )
    p, c = cloud_recommendations()
    print(f"(b) No-privacy ablation (content-led): {c}/{p} PII records recommended for Cloud "
          f"(strict-filter devices still protected)")

    runtime_config.update({"strict_privacy_all_pii": True})
    p, c = cloud_recommendations()
    print(f"(c) Strict-all-PII mitigation:         {c}/{p} PII records recommended for Cloud")

    runtime_config.reload()
    print("\nDone. The analysis was performed entirely in memory.")


if __name__ == "__main__":
    main()
