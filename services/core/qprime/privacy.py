"""PII detection heuristics for privacy accounting.

Q-PRIME's privacy accounting in the paper counts a record as
privacy-sensitive when its payload carries personally identifiable
information (PII): identities from face recognition streams, identity fields
such as name / age / gender / SSN attached to detections, and person labels
from vision sources. The placement algorithm uses this signal when calculating
its recommendation.
"""

from typing import Any, Dict, List, Tuple

# Keys whose presence (with a non-empty value) marks direct identifiers.
DIRECT_PII_KEYS = {"name", "person", "ssn", "face_id", "identity"}
# Keys that are quasi-identifiers when they accompany a person detection.
QUASI_PII_KEYS = {"age", "gender"}
# Detection labels that indicate a person was observed.
PERSON_LABELS = {"person", "persons", "human", "face"}


def _walk(obj: Any, found: List[str], path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).lower()
            p = f"{path}.{k}" if path else str(k)
            if key in DIRECT_PII_KEYS and v not in (None, "", [], {}):
                found.append(p)
            elif key in QUASI_PII_KEYS and v not in (None, ""):
                found.append(p)
            elif key == "label" and str(v).lower() in PERSON_LABELS:
                found.append(p)
            elif key == "event" and isinstance(v, str) and "face" in v.lower():
                found.append(p)
            _walk(v, found, p)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _walk(item, found, f"{path}[{i}]")


def detect_pii(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return ``(pii_detected, matched_paths)`` for a context record."""
    found: List[str] = []
    _walk(record.get("contextValue") or {}, found)
    return (len(found) > 0, found)
