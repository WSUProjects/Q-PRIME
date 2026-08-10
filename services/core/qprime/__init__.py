"""Q-PRIME: Quality- and PRIvacy-aware Edge-cloud continuum framework for IoT.

This package implements the Q-PRIME analysis algorithm described in:

    K. S. Jagarlamudi et al., "A Quality- and Privacy-Aware Edge-Cloud
    Continuum Framework for Internet of Things Applications",
    submitted to IEEE Access, 2026.

Modules
-------
ahp       : Analytic Hierarchy Process weight derivation + consistency ratio.
sla       : Quality-of-Context (QoC) / SLA metric evaluation per record.
privacy   : PII detection heuristics used for privacy accounting.
config    : Thread-safe runtime configuration (weights, thresholds, modes).
decision  : Edge/Cloud recommendation engine (QoC + privacy scoring).
The package has no integration or persistence layer. Callers supply records
and receive analysis results synchronously.
"""

__version__ = "1.0.0"
