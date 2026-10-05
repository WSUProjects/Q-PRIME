"""Q-PRIME: Quality- and PRIvacy-aware Edge-cloud continuum framework for IoT.

This package implements the Q-PRIME analysis algorithm described in:

    K. S. Jagarlamudi, J. Anowar, K. Islam, F. Mirhakimi, R. N. Calheiros
    and B. Javadi, "A Quality and Privacy-Aware Edge-Cloud Continuum
    Framework for Internet of Things Applications", IEEE Access, vol. 14,
    2026. doi:10.1109/ACCESS.2026.3737473

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
