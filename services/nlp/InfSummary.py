#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inf.py — chatty summarizer & inference for IoT JSON/JSONL dumps (API-friendly).

What it does (chatty-only)
- Loads JSON array, nested JSON (e.g., Athena ResultSet), or JSONL.
- Auto-detects a time field and parses epoch (s/ms/ns) or common timestamp strings.
- Understands devices, events, people, and numeric sensor fields.
- Query routing:
    * Empty/"overview" → CHATTY overview for the whole dataset.
    * People/face asks (e.g., "faces seen by misty") → CHATTY Misty-style story.
    * Other asks (e.g., "door activity", "smoke alarms", "temperature last week") → filtered, CHATTY overview.
- API entrypoint:
    summarize_for_api(data, query="", epoch_scale="s") → {"ok": bool, "text": str, "meta": {...}}

Plus:
- NL date windows: explicit dates (“on October 3, 2025”, “between Sep 22 and Sep 30 2025”) and relative (“last week”) (end exclusive).
- SQL bypass: if query looks like SQL (SELECT/WITH), skip intent filtering and just summarize provided rows.
"""

from __future__ import annotations
import argparse, json, math, os, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

# ---------------- I/O & parsing ----------------

NAN_FIX_RE = re.compile(r"(?<=[:\s])NaN(?=[,\}\]\s])")


def _load_as_json(content: str):
    fixed = NAN_FIX_RE.sub("null", content)
    return json.loads(fixed)


def _rows_from_athena_result(obj: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Parse AWS Athena ResultSet to a list of dicts. Casts scalars using ColumnInfo."""
    try:
        rs = obj.get("ResultSet", {})
        rows = rs.get("Rows", [])
        if not rows:
            return None

        # header row
        hdr_cells = rows[0].get("Data", [])
        headers_raw = [c.get("VarCharValue") for c in hdr_cells]
        headers, seen = [], set()
        for i, h in enumerate(headers_raw):
            name = str(h or f"col_{i}")
            base, j = name, 1
            while name in seen:
                name = f"{base}_{j}"
                j += 1
            seen.add(name)
            headers.append(name)

        # column type casters
        colinfo = (rs.get("ResultSetMetadata") or {}).get("ColumnInfo") or []

        def _mk_caster(t: str):
            t = (t or "").lower()
            if t in {"tinyint", "smallint", "int", "integer", "bigint"}:
                return lambda x: int(x) if x not in (None, "") else None
            if t in {"double", "float", "real", "decimal"}:
                return lambda x: float(x) if x not in (None, "") else None
            if t in {"boolean"}:
                return lambda x: (
                    (str(x).lower() == "true") if x not in (None, "") else None
                )
            return lambda x: x

        casters = [_mk_caster(ci.get("Type")) for ci in colinfo] or [lambda x: x] * len(
            headers
        )

        # data rows
        out: List[Dict[str, Any]] = []
        for row in rows[1:]:
            vals = [d.get("VarCharValue") for d in row.get("Data", [])]
            n = min(len(headers), len(vals), len(casters))
            coerced = [casters[i](vals[i]) for i in range(n)]
            out.append(dict(zip(headers[:n], coerced)))
        return out or None
    except Exception:
        return None


def _maybe_metric_mode(rows: List[Dict[str, Any]]) -> Optional[str]:
    """If dataset is a single row with no obvious time key, return a metric-friendly text."""
    if not rows or len(rows) != 1:
        return None
    r0 = rows[0]

    # check direct time keys
    has_time = any(k in r0 for k in ("timestamp", "ts", "time", "event_time"))
    # also consider nested under "value.*"
    if not has_time:
        v = r0.get("value")
        if isinstance(v, dict) and any(
            k in v for k in ("timestamp", "ts", "time", "event_time")
        ):
            has_time = True

    if not has_time:
        lines = ["Metric result:"]
        for k, v in r0.items():
            if isinstance(v, float):
                lines.append(f"- {k}: {v:.4f}")
            else:
                lines.append(f"- {k}: {v}")
        lines.append(
            "\n Tip: for trends/freshness, return a time series (GROUP BY day/hour)."
        )
        return "\n".join(lines)
    return None


def report_from_rows(
    rows: List[Dict[str, Any]], query: str, epoch_key: Optional[str], scale: str
) -> str:
    mm = _maybe_metric_mode(rows)
    if mm:
        return mm
    intent = infer_intent(query)
    if intent == "people_focus":
        return friendly_people_summary(rows, epoch_key, scale)
    return chatty_overview(rows, epoch_key, scale)


def _rows_from_common_wrappers(obj: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Handle common containers like {'records': [...]}, {'rows': [...]}, {'items': [...]}, {'data': [...]}."""
    for key in ("records", "rows", "items", "data"):
        v = obj.get(key)
        if isinstance(v, list):
            return v
    return None


def read_any_rows(path: str) -> List[Dict[str, Any]]:
    """Accept JSON array / nested JSON / JSONL; return list of dict rows."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Try whole-file JSON
    try:
        obj = _load_as_json(content)
        if isinstance(obj, list):
            return [x if isinstance(x, dict) else {"value": x} for x in obj]
        if isinstance(obj, dict):
            ath = _rows_from_athena_result(obj)
            if ath is not None:
                return ath
            wrapped = _rows_from_common_wrappers(obj)
            if wrapped is not None:
                return wrapped
            return [obj]
    except Exception:
        pass

    # Fallback: JSONL
    rows: List[Dict[str, Any]] = []
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        s = NAN_FIX_RE.sub("null", s)
        try:
            obj = json.loads(s)
            rows.append(obj if isinstance(obj, dict) else {"value": obj})
        except Exception:
            continue
    return rows


# ---------------- Time utilities ----------------


def _parse_ts_string(s: str) -> Optional[float]:
    """
    Parse common timestamp strings to epoch seconds (UTC).
    Accepts:
      - 'YYYY-MM-DD HH:MM:SS'
      - 'YYYY-MM-DD HH:MM:SS.sss'
      - ISO-8601 with T and optional Z
    """
    s2 = s.strip().replace("T", " ").rstrip("Zz")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s2, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(
            s.strip().replace("Z", "+00:00").replace("z", "+00:00")
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def to_seconds(v: Any, scale: str) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        xs = _parse_ts_string(str(v))
        if xs is not None:
            return xs
        try:
            x = float(str(v).strip())
        except Exception:
            return None
    if x < 0:
        return None
    if scale == "s":
        return x
    if scale == "ms":
        return x / 1000.0
    if scale == "ns":
        return x / 1_000_000_000.0
    return x


def as_dt(epoch_seconds: float) -> datetime:
    return datetime.fromtimestamp(epoch_seconds, tz=OUTPUT_TZ)


def iso_utc(epoch_seconds: float) -> str:
    return as_dt(epoch_seconds).strftime(f"%Y-%m-%d %H:%M {OUTPUT_TZ_LABEL}")


def _parse_month_day_optional_year(
    token: str, fallback_year: Optional[int]
) -> Optional[datetime]:
    """
    Accepts: 'September 22', 'Sep 22', 'September 22, 2025', 'Sep 22, 2025'
    If year is missing, use fallback_year (if provided).
    Returns a timezone-aware UTC midnight datetime.
    """
    m = re.match(r"^\s*([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?\s*$", token)
    if not m:
        return None
    mon, day, yr = m.group(1), m.group(2), m.group(3)
    year = (
        int(yr)
        if yr
        else (fallback_year if fallback_year else datetime.now(timezone.utc).year)
    )
    try:
        dt = datetime.strptime(f"{mon} {int(day)} {year}", "%B %d %Y")
    except ValueError:
        try:
            dt = datetime.strptime(f"{mon} {int(day)} {year}", "%b %d %Y")
        except ValueError:
            return None
    return dt.replace(tzinfo=timezone.utc, hour=0, minute=0, second=0, microsecond=0)


def parse_relative_time_window(q: str) -> Optional[Tuple[float, float]]:
    """Understands 'today', 'yesterday', 'last week', 'last 7 days', 'last month'."""
    if not q:
        return None
    qn = normalize(q)

    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if re.search(r"\btoday\b", qn):
        start = today
        end = start + timedelta(days=1)
        return (start.timestamp(), end.timestamp())
    if re.search(r"\byesterday\b", qn):
        end = today
        start = end - timedelta(days=1)
        return (start.timestamp(), end.timestamp())

    # last week: previous Monday → this Monday (UTC)
    if re.search(r"\blast\s+week\b", qn):
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        return (last_monday.timestamp(), this_monday.timestamp())

    m = re.search(r"\blast\s+(\d+)\s+days?\b", qn)
    if m:
        n = max(1, int(m.group(1)))
        end = today
        start = end - timedelta(days=n)
        return (start.timestamp(), end.timestamp())

    if re.search(r"\blast\s+month\b", qn):
        first_of_this_month = today.replace(day=1)
        last_of_prev = first_of_this_month - timedelta(days=1)
        first_of_prev = last_of_prev.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return (first_of_prev.timestamp(), first_of_this_month.timestamp())

    return None


# ---------------- Helpers & detection ----------------


def get_time_window(q: str) -> Optional[Tuple[float, float]]:
    """Try explicit dates first, then relative phrases like 'last week'."""
    return parse_nl_time_window(q) or parse_relative_time_window(q)


def get_nested(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


OUTPUT_TZ = timezone(timedelta(hours=11))
OUTPUT_TZ_LABEL = "GMT+11"

TIME_KEYS = [
    "timestamp",
    "ts",
    "time",
    "event_time",
    "value.timestamp",
    "value.ts",
]


def detect_time_key(rows: List[Dict[str, Any]]) -> Optional[str]:
    # Prefer keys that actually appear
    for k in TIME_KEYS:
        for r in rows:
            v = get_nested(r, k) if "." in k else r.get(k)
            if v is not None:
                return k
    # Last-resort: pick any key that successfully parses to epoch seconds on at least a few rows
    candidates = Counter()
    sample = rows[: min(50, len(rows))]
    for r in sample:
        for k, v in r.items():
            if isinstance(v, (int, float, str)) and to_seconds(v, "s") is not None:
                candidates[k] += 1
    if candidates:
        return candidates.most_common(1)[0][0]
    return None


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def top_counter(vals: Iterable[Any], n: int = 5) -> List[Tuple[str, int]]:
    c = Counter([str(v) for v in vals if v not in (None, "")])
    return c.most_common(n)


def freshness_label(epoch_last: Optional[float]) -> str:
    if not epoch_last:
        return "unknown freshness"
    age = datetime.now(timezone.utc).timestamp() - epoch_last
    if age <= 24 * 3600:
        return "up to date (last 24 hours)"
    if age <= 7 * 24 * 3600:
        return "recent (within a week)"
    if age <= 30 * 24 * 3600:
        return "a bit old (over a week)"
    return "stale (over a month)"


def human_list(items: List[str], limit: int = 5) -> str:
    items = [str(x) for x in items if str(x).strip()]
    items = list(dict.fromkeys(items))  # dedupe order-preserving
    if not items:
        return "none"
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f" … (+{len(items)-limit} more)"


def human_count(n: int) -> str:
    if n < 1_000:
        return str(n)
    if n < 10_000:
        return f"{n/1000:.1f}".rstrip("0").rstrip(".") + "k"
    if n < 1_000_000:
        return f"{round(n/1000)}k"
    return f"{n/1_000_000:.1f}".rstrip("0").rstrip(".") + "M"


# ---------------- Query → filter ----------------

EVENT_FACE_SYNS = {
    "face_detected",
    "familiar_face",
    "familiar_face_detected",
    "person_detected",
}
DEVICE_HINTS = {
    "misty": ["misty", "misty robot", "misty robot 1"],
    "door": ["door", "door sensor"],
    "smoke": ["smoke", "smoke sensor", "alarm"],
    "camera": ["camera", "cam"],
}


def build_alias_map_from_data(rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    devices = set()
    for r in rows:
        dn = r.get("device_name")
        if not dn and isinstance(r.get("value"), dict):
            dn = r["value"].get("device_name")
        did = r.get("device_id") or (
            r.get("value", {}).get("device_id")
            if isinstance(r.get("value"), dict)
            else None
        )
        if dn:
            devices.add(str(dn))
        if did:
            devices.add(str(did))
    aliases: Dict[str, List[str]] = {}
    for d in devices:
        base = d.lower()
        simple = base.replace(" robot", "").replace(" sensor", "")
        aliases[d] = [base, simple]
    for key, vals in DEVICE_HINTS.items():
        for v in vals:
            aliases.setdefault(key, []).append(v)
    return aliases


def filter_rows_by_query(
    rows: List[Dict[str, Any]], q: str
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (filtered_rows, applied_filters)."""
    qn = normalize(q)
    if not qn or qn in {"overview", "summary", "report"}:
        return rows, {}

    aliases = build_alias_map_from_data(rows)
    applied: Dict[str, Any] = {}

    # device detection (simple contains)
    match_device = None
    for canonical, vals in aliases.items():
        for v in vals:
            if re.search(rf"\b{re.escape(v)}\b", qn):
                match_device = canonical
                break
        if match_device:
            break

    # faces intent
    wants_faces = bool(re.search(r"\b(face|faces|people|person)\b", qn))

    # event detection (basic)
    event_filters: List[str] = []
    if wants_faces or "misty" in qn:
        event_filters = list(EVENT_FACE_SYNS)

    # check if rows actually have device_name
    has_device_field = any(
        ("device_name" in r)
        or (isinstance(r.get("value"), dict) and "device_name" in r["value"])
        for r in rows
    )

    # apply
    filtered = []
    for r in rows:
        keep = True
        if match_device and has_device_field:
            dn = r.get("device_name") or (
                r.get("value", {}).get("device_name")
                if isinstance(r.get("value"), dict)
                else None
            )
            dn_s = str(dn).lower() if dn is not None else ""
            if match_device.lower() not in dn_s:
                keep = False
        if keep and event_filters:
            ev = (r.get("event") or "").lower()
            if ev not in event_filters:
                keep = False
        if keep:
            filtered.append(r)

    if match_device and has_device_field:
        applied["device"] = match_device
    elif match_device and not has_device_field:
        applied["note"] = (
            applied.get("note") or ""
        ) or "skipped_device_filter_no_device_field"
    if event_filters:
        applied["events"] = event_filters
    if wants_faces:
        applied["people"] = True

    return filtered, applied


# ---------------- Chatty reporting ----------------


def _ordinal_day(dt: datetime) -> str:
    day = int(dt.strftime("%d"))
    suffix = (
        "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    )
    return f"{day}{suffix}"


def friendly_people_summary(
    rows: List[Dict[str, Any]], time_key: Optional[str], scale: str, query: str = ""
) -> str:
    """Concise, human-like summary: who Misty saw last and when."""
    if not rows:
        return "No face detections were found."

    # --- find last valid person and timestamp ---
    last_person, last_ts = None, None
    for r in rows:
        person = r.get("person") or (
            r.get("value", {}).get("person")
            if isinstance(r.get("value"), dict)
            else None
        )
        if not person:
            continue
        raw = (
            get_nested(r, time_key)
            if (time_key and "." in time_key)
            else (r.get(time_key) if time_key else None)
        )
        t = to_seconds(raw, scale) if raw is not None else None
        if t is not None and (last_ts is None or t > last_ts):
            last_person, last_ts = person, t

    if not last_person or not last_ts:
        return "Misty detected someone, but no valid time or name was available."

    # --- format output ---
    dt = as_dt(last_ts)
    date_str = dt.strftime("%B %d, %Y")
    time_str = dt.strftime(f"%H:%M {OUTPUT_TZ_LABEL}")

    text = f"{last_person} was last seen by Misty on {date_str} at {time_str}."

    # --- optional follow-up suggestions ---
    try:
        suggestions = suggest_related_queries(query)
        if suggestions:
            text += "\n\nTry:\n" + "\n".join(f"- {s}" for s in suggestions)
    except Exception:
        pass

    return text


def _normalize_event_label(ev: str, row: Dict[str, Any]) -> str:
    # If there is a temperature-like numeric field and event is a single letter (e.g., "C"), call it "reading"
    if ev and len(ev.strip()) == 1:
        if any(
            k
            for k, v in row.items()
            if k.lower() in {"temp", "temperature", "humidity", "moisture"}
            and isinstance(v, (int, float))
        ):
            return "reading"
    return ev


def chatty_overview(
    rows: List[Dict[str, Any]], epoch_key: Optional[str], scale: str
) -> str:
    """Chatty, sectioned Markdown-style overview for all sensors (or filtered subset)."""
    if not rows:
        return "I didn’t find any data to summarize."

    devs, events, persons, ts = [], [], [], []
    numeric_stats: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"min": math.inf, "max": -math.inf, "sum": 0.0, "count": 0}
    )

    # --- collect facts ---
    for r in rows:
        dn = r.get("device_name") or (
            r.get("value", {}).get("device_name")
            if isinstance(r.get("value"), dict)
            else None
        )
        if dn:
            devs.append(str(dn))

        ev = r.get("event")
        if ev:
            ev = _normalize_event_label(
                str(ev), r
            )  # keep the normalization (e.g., "c" -> "reading")
            events.append(ev)

        pe = r.get("person") or (
            r.get("value", {}).get("person")
            if isinstance(r.get("value"), dict)
            else None
        )
        if pe:
            persons.append(str(pe))

        # time
        t_raw = (
            get_nested(r, epoch_key)
            if (epoch_key and "." in epoch_key)
            else (r.get(epoch_key) if epoch_key else None)
        )
        t = to_seconds(t_raw, scale) if t_raw is not None else None
        if t is not None:
            ts.append(t)

        # numeric fields
        timeish = {"timestamp", "ts", "time", "event_time"}
        for k, v in r.items():
            if isinstance(v, (int, float)) and k not in timeish:
                ns = numeric_stats[k]
                val = float(v)
                ns["min"] = min(ns["min"], val)
                ns["max"] = max(ns["max"], val)
                ns["sum"] += val
                ns["count"] += 1

    total_rows = len(rows)
    rows_h = human_count(total_rows)

    # --- time coverage / freshness ---
    coverage_line_1 = ""
    coverage_line_2 = ""
    gaps_line = None
    peak_hour_line = None
    busiest_day_line = None

    if ts:
        start, end = min(ts), max(ts)
        s_dt, e_dt = as_dt(start), as_dt(end)
        coverage_line_1 = f"Between {_ordinal_day(s_dt)} {s_dt.strftime('%B %Y')} and {_ordinal_day(e_dt)} {e_dt.strftime('%B %Y')}, the system recorded about {rows_h} events."
        latest_str = e_dt.strftime(f"%Y-%m-%d %H:%M {OUTPUT_TZ_LABEL}")
        coverage_line_2 = (
            f"The latest entry was {latest_str}, so the data is {freshness_label(end)}."
        )

        # simple temporal patterns
        hour_hist = Counter(as_dt(t).hour for t in ts)
        wd_hist = Counter(as_dt(t).strftime("%A") for t in ts)
        if hour_hist:
            h, _ = hour_hist.most_common(1)[0]
            peak_hour_line = f"Peak activity around {h:02d}:00 {OUTPUT_TZ_LABEL}"
        if wd_hist:
            d, _ = wd_hist.most_common(1)[0]
            busiest_day_line = f"{d} was the busiest day of the week"

        # gaps
        t_sorted = sorted(as_dt(x) for x in ts)
        for a, b in zip(t_sorted, t_sorted[1:]):
            if (b - a) >= timedelta(hours=24):
                start_gap = a.strftime(f"%b %d, %H:%M {OUTPUT_TZ_LABEL}")
                end_gap = b.strftime(f"%b %d, %H:%M {OUTPUT_TZ_LABEL}")
                gaps_line = f"Notable no-data window from {start_gap} to {end_gap}"
                break
    else:
        coverage_line_1 = f"This dataset contains about {rows_h} events, but I couldn’t determine a time range because timestamps were missing."

    # --- devices text ---
    devices_text = ""
    if devs:
        devices_text = human_list(devs, limit=6)

    # --- top activity (events) as bullet lines ---
    activity_lines: List[str] = []
    if events:
        for k, v in top_counter(events, n=5):
            activity_lines.append(f"{k} ({v})")

    # --- people list ---
    people_text = ""
    if persons:
        pe_top = top_counter(persons, n=5)
        known = [
            k
            for k, _ in pe_top
            if k.strip().lower() not in {"", "none", "nan", "unknown", "unknown person"}
        ]
        if known:
            people_text = ", ".join(known)

    # --- build sectioned output ---
    sections: List[str] = []

    # Summary header + two coverage lines
    summary_block = [
        "Summary",
        "",
        coverage_line_1,
        coverage_line_2 if coverage_line_2 else "",
    ]
    sections.append("\n".join([ln for ln in summary_block if ln]))

    # Devices
    if devices_text:
        sections.append("\n".join(["Devices: ", "", devices_text]))

    # Top activity
    # if activity_lines:
    #     sections.append("\n".join([
    #         "Top activity",
    #         "",
    #         "\n".join(activity_lines)
    #     ]))

    # People
    if people_text:
        sections.append("\n".join(["People identified: ", "", people_text]))

    # Patterns
    pattern_lines = [ln for ln in [peak_hour_line, busiest_day_line] if ln]
    if pattern_lines:
        sections.append("\n".join(["Patterns: ", "", "\n".join(pattern_lines)]))

    # Gaps
    if gaps_line:
        sections.append("\n".join(["Gaps: ", "", gaps_line]))

    # Closing
    # sections.append("In short: a plain-language overview to help you quickly understand what’s happening across devices and events.")

    # Join sections with a blank line between each block
    return "\n\n".join(sections)


# ---------------- Intent & router ----------------


def infer_intent(q: str) -> Optional[str]:
    """
    - 'people_focus': asks about faces/people
    - 'overview': 'overview'/'summary' or empty query
    """
    qn = normalize(q)
    if qn in {"", "overview", "summary", "report"}:
        return "overview"
    if re.search(r"\b(face|faces|people|person)\b", qn):
        return "people_focus"
    return None


# ---------------- NL time windows & SQL detection ----------------

DATE_FORMATS = [
    "%B %d, %Y",  # October 3, 2025
    "%b %d, %Y",  # Oct 3, 2025
    "%d %B %Y",  # 3 October 2025
    "%d %b %Y",  # 3 Oct 2025
    "%Y-%m-%d",  # 2025-10-03
    "%d/%m/%Y",  # 03/10/2025 (D/M/Y)
    "%m/%d/%Y",  # 10/03/2025 (M/D/Y)
]


def _parse_date_token(tok: str) -> Optional[datetime]:
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(tok, fmt).replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def parse_nl_time_window(q: str) -> Optional[Tuple[float, float]]:
    """
    Returns (start_epoch, end_epoch_exclusive).
    Supports:
      - 'between <DATE> and <DATE>'
      - 'from <DATE> to <DATE>'
      - 'on <DATE>'
      - single date token anywhere
    Accepts dates like: 'September 22', 'September 22, 2025', 'Sep 30 2025', '2025-09-30', '22/09/2025'
    """
    q = q or ""

    # ---- Range with optional comma/year on either side (Month Day [, Year]) ----
    m = re.search(
        r"\b(?:between|from)\s+([A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?)\s+(?:and|to)\s+([A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?)\b",
        q,
        flags=re.IGNORECASE,
    )
    if m:
        a, b = m.group(1), m.group(2)
        m_year = re.search(r"(\d{4})\s*$", b)
        fallback_year = int(m_year.group(1)) if m_year else None
        d1 = _parse_month_day_optional_year(a, fallback_year)
        d2 = _parse_month_day_optional_year(b, fallback_year)
        if d1 and d2:
            start = d1
            end = d2 + timedelta(days=1)
            return (start.timestamp(), end.timestamp())

    # ---- ISO / D/M/Y / M/D/Y single-day window ----
    m = re.search(
        r"\bon\s+([A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\b",
        q,
        flags=re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"([A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})",
            q,
            flags=re.IGNORECASE,
        )
    if not m:
        return None

    token = m.group(1)
    d = _parse_month_day_optional_year(token, None)
    if not d:
        dt = _parse_date_token(token)
        if not dt:
            return None
        d = dt
    day_start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    return (day_start.timestamp(), day_end.timestamp())


SQL_LIKE_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


def is_sqlish(q: str) -> bool:
    return bool(SQL_LIKE_RE.search(q or ""))


# ---------------- Metric helpers (smart one-liner) ----------------


def _metric_count_from_row(row: dict) -> Optional[int]:
    for k in ("n", "count", "total", "events"):
        if k in row:
            try:
                return int(float(row[k]))
            except Exception:
                pass
    for v in row.values():
        try:
            return int(float(v))
        except Exception:
            continue
    return None


DEVICE_NAME_SYNS = {
    "door": ["door", "door sensor"],
    "misty": ["misty", "misty robot", "misty robot 1"],
    "smoke": ["smoke", "smoke sensor", "alarm"],
    "camera": ["camera", "cam"],
}


def device_hint_from_query(q: str) -> Optional[str]:
    qn = normalize(q)
    for canonical, syns in DEVICE_NAME_SYNS.items():
        for s in syns:
            if re.search(rf"\b{re.escape(s)}\b", qn):
                return canonical
    return None


def human_range_label(
    start_epoch: Optional[float], end_epoch_exclusive: Optional[float]
) -> str:
    """Pretty range label. Collapses to single day if start==end-1day."""
    if not start_epoch or not end_epoch_exclusive:
        return ""
    s = as_dt(start_epoch)
    e_inclusive = as_dt(end_epoch_exclusive - 1)

    # same day?
    if (s.year, s.month, s.day) == (
        e_inclusive.year,
        e_inclusive.month,
        e_inclusive.day,
    ):
        return f"{s.strftime('%b %d, %Y')} ({OUTPUT_TZ_LABEL})"

    # same month / same year
    if (s.year, s.month) == (e_inclusive.year, e_inclusive.month):
        return f"{s.strftime('%b %d')}–{e_inclusive.strftime('%d, %Y')} ({OUTPUT_TZ_LABEL})"
    if s.year == e_inclusive.year:
        return f"{s.strftime('%b %d')}–{e_inclusive.strftime('%b %d, %Y')} ({OUTPUT_TZ_LABEL})"
    return f"{s.strftime('%b %d, %Y')}–{e_inclusive.strftime('%b %d, %Y')} ({OUTPUT_TZ_LABEL})"


def when_phrase(tw: Optional[Tuple[float, float]]) -> str:
    """Return ' on <date>' for same-day, else ' between <range>'."""
    if not tw:
        return ""
    s = as_dt(tw[0])
    e_inclusive = as_dt(tw[1] - 1)
    if (s.year, s.month, s.day) == (
        e_inclusive.year,
        e_inclusive.month,
        e_inclusive.day,
    ):
        return f" on {s.strftime('%b %d, %Y')} ({OUTPUT_TZ_LABEL})"
    return f" between {human_range_label(tw[0], tw[1])}"


def _classify_metric(row: Dict[str, Any], query: str) -> Tuple[str, float, str]:
    """Return (metric_type, value, subject)."""
    qn = normalize(query)
    subject = "events"
    if re.search(r"\btemp|temperature\b", qn):
        subject = "temperature"
    elif re.search(r"\bhumidity\b", qn):
        subject = "humidity"
    elif re.search(r"\bpressure\b", qn):
        subject = "pressure"
    elif re.search(r"\bvoltage\b", qn):
        subject = "voltage"

    key_types = [
        (r"^(n|count|total|events)$", "count"),
        (r"^(avg|average|mean)", "avg"),
        (r"^(median)", "median"),
        (r"^(min|minimum)", "min"),
        (r"^(max|maximum)", "max"),
        (r"^(sum|total_sum)", "sum"),
    ]

    for k, v in row.items():
        ks = normalize(str(k))
        for pat, mtype in key_types:
            if re.match(pat, ks):
                try:
                    return (mtype, float(v), subject)
                except Exception:
                    pass

    inferred_type = "count"
    if re.search(r"\bavg|average|mean\b", qn):
        inferred_type = "avg"
    elif re.search(r"\bmedian\b", qn):
        inferred_type = "median"
    elif re.search(r"\bmin|minimum\b", qn):
        inferred_type = "min"
    elif re.search(r"\bmax|maximum\b", qn):
        inferred_type = "max"
    elif re.search(r"\bsum\b", qn):
        inferred_type = "sum"

    for v in row.values():
        try:
            return (inferred_type, float(v), subject)
        except Exception:
            continue

    return ("value", 0.0, subject)


def nice_metric_sentence(rows: List[Dict[str, Any]], query: str) -> str:
    """Human-sounding summary for aggregates (avg, min, max, count, etc.)."""
    if not rows:
        return "No results."
    metric_type, value, subject = _classify_metric(rows[0], query)
    tw = get_time_window(query)
    when = when_phrase(tw)

    def metric_verb(present: str, past: str = "was") -> str:
        base = (when or "").lower()
        if not base or " today" in base or " now" in base:
            return present
        return past

    if metric_type == "count":
        dev = device_hint_from_query(query)
        n = int(round(value))

        # Device display (capitalize proper names, avoid 'the' for Misty)
        dev_disp = dev.title() if dev else "device"

        if dev == "door":
            return f"The door was opened {n} time{'s' if n != 1 else ''}{when}."
        if dev == "misty":
            if n == 1:
                return f"{dev_disp} recognized a face once{when}."
            return f"{dev_disp} recognized faces {n} times{when}."
        if dev == "smoke":
            return (
                f"The smoke sensor raised alerts {n} time{'s' if n != 1 else ''}{when}."
            )
        if dev == "camera":
            return f"The camera made detections {n} time{'s' if n != 1 else ''}{when}."

        # generic count - `subject` may already be plural ("events")
        plural = "" if (n == 1 or subject.endswith("s")) else "s"
        return f"There were {n:,} {subject}{plural}{when}."

    # numeric metrics (avg/min/max/median/sum)
    val_str = f"{value:.2f}".rstrip("0").rstrip(".")
    if metric_type == "avg":
        return f"The average {subject}{when} {metric_verb('is')} {val_str}."
    if metric_type == "min":
        return f"The minimum {subject}{when} {metric_verb('is')} {val_str}."
    if metric_type == "max":
        return f"The maximum {subject}{when} {metric_verb('is')} {val_str}."
    if metric_type == "median":
        return f"The median {subject}{when} {metric_verb('is')} {val_str}."
    if metric_type == "sum":
        return f"The total {subject}{when} {metric_verb('is')} {val_str}."
    return f"The {subject}{when} {metric_verb('is')} {val_str}."


def suggest_related_queries(query: str) -> List[str]:
    """Offer context-aware follow-ups for both counts and readings."""
    qn = normalize(query)
    tw = get_time_window(query)

    def period_label(tw: Optional[Tuple[float, float]]) -> str:
        if not tw:
            return "in the same period"
        s = as_dt(tw[0])
        e_incl = as_dt(tw[1] - 1)
        if (s.year, s.month, s.day) == (e_incl.year, e_incl.month, e_incl.day):
            return f"on {s.strftime('%Y-%m-%d')}"
        start_s = s.strftime("%Y-%m-%d")
        end_s = e_incl.strftime("%Y-%m-%d")
        return f"between {start_s} and {end_s}"

    period = period_label(tw)

    # Reading-oriented follow-ups
    if re.search(r"\btemp|temperature\b", qn):
        subj = "temperature"
        return [
            f"Show daily average {subj} {period}",
            f"Show min/max {subj} {period}",
            f"Show hourly {subj} profile {period}",
            f"Compare {subj} to the prior week",
            f"Show distribution of {subj} {period}",
        ]

    # Event/count-oriented follow-ups
    dev = device_hint_from_query(query) or "device"
    dev_disp = "Misty" if dev == "misty" else dev
    noun = "recognitions" if dev == "misty" else "events"

    return [
        f"Show daily {dev} counts {period}",
        f"Which hour was {dev} busiest {period}?",
        f"List the last 10 {dev} {noun} {period}",
        f"Show first and last {dev} {noun} times {period}",
        f"Break down {dev} {noun} by day and hour {period}",
    ]


# ---------------- API entrypoint ----------------


def summarize_for_api(
    data: Union[str, List[Dict[str, Any]], Dict[str, Any]],
    query: str = "",
    epoch_scale: str = "s",
) -> Dict[str, Any]:
    """
    API-friendly entrypoint.
    - data: either a file path (str) to JSON/JSONL or in-memory rows (list[dict]) or nested JSON (e.g., Athena ResultSet).
    - query: natural language (e.g., "overview", "faces seen by misty", "door activity", or even raw SQL).
    - epoch_scale: 's' | 'ms' | 'ns' for numeric timestamps (ignored for string timestamps).
    Returns:
      { "ok": bool, "text": str, "meta": {...} }
    """

    # --- Gibberish / small-talk guard ---
    qn = (query or "").strip().lower()

    # --- Hardened gibberish / small-talk guard ---
    # 1) single token, only letters, length >= 5 (e.g., "dsadasda")
    if re.fullmatch(r"[a-z]+", qn) and len(qn) >= 5:
        suggestions = [
            "Overview",
            "Latest Misty activity",
            "Door openings yesterday",
            "Average temperature last week",
        ]
        return {
            "ok": True,
            "text": "I didn’t detect a clear IoT intent.\nAre you trying to find one of these?\n"
            + "\n".join(f"- {s}" for s in suggestions),
            "meta": {
                "rows_considered": 0,
                "applied_filters": {"note": "gibberish_token"},
                "time_key": None,
                "latest_iso": None,
            },
        }

    # 2) no domain keywords → treat as vague/gibberish
    # Kept in step with AINatural.DOMAIN_TERMS: if the generator was willing
    # to build a query for a question, the summariser must be willing to
    # describe the rows it came back with.
    DOMAIN_HINTS = (
        r"(misty|robot|door|smoke|fire|alarm|camera|zed|drone|tello|thp|soil|moisture|heart|bpm|"
        r"sensor|sensors|device|devices|gateway|"
        r"temp|temperature|humidity|pressure|voltage|reading|readings|record|records|data|"
        r"face|faces|person|people|intruder|event|events|activity|detection|detections|"
        r"overview|summary|report|list|show|latest|recent|newest|"
        r"count|total|number|average|avg|how many|"
        r"yesterday|today|now|last|past|between|from|to|since|hour|hours|day|days|week|weeks|month|months)"
    )
    if not re.search(DOMAIN_HINTS, qn):
        suggestions = [
            "Misty intruder detections last week",
            "Average temperature today",
            "Door and smoke correlation yesterday",
            "Overview",
        ]
        return {
            "ok": True,
            "text": "I didn’t detect a clear IoT intent.\nAre you trying to find one of these?\n"
            + "\n".join(f"- {s}" for s in suggestions),
            "meta": {
                "rows_considered": 0,
                "applied_filters": {"note": "no_domain_keywords"},
                "time_key": None,
                "latest_iso": None,
            },
        }

    # --- Main logic ---
    try:
        # Normalize data type
        if isinstance(data, str):
            rows = read_any_rows(data)
        elif isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = (
                _rows_from_athena_result(data)
                or _rows_from_common_wrappers(data)
                or [data]
            )
        else:
            return {"ok": False, "text": "Unsupported input type.", "meta": {}}

        # ---- SQL bypass + NL time window ----
        time_window = get_time_window(query)
        sqlish = is_sqlish(query)

        # Single-row aggregate with no time field → short summary
        metric_mode = _maybe_metric_mode(rows)
        if metric_mode:
            sentence = nice_metric_sentence(rows, query)
            suggestions = suggest_related_queries(query)
            hint = "\n\nTry:\n- " + "\n- ".join(suggestions) if suggestions else ""
            return {
                "ok": True,
                "text": sentence + hint,
                "meta": {
                    "rows_considered": 1,
                    "applied_filters": {"note": "single_row_metric"},
                    "time_key": None,
                    "latest_iso": None,
                },
            }

        # Normal filtering
        if sqlish:
            filtered_rows, applied = rows, {"note": "sqlish_query_no_intent_filters"}
        else:
            filtered_rows, applied = filter_rows_by_query(rows, query)

        # Apply time window filter
        if time_window and not sqlish:
            start_epoch, end_epoch = time_window
            epoch_key_tw = detect_time_key(filtered_rows) or detect_time_key(rows)
            if epoch_key_tw:
                wr = []
                for r in filtered_rows:
                    raw = (
                        get_nested(r, epoch_key_tw)
                        if "." in epoch_key_tw
                        else r.get(epoch_key_tw)
                    )
                    t = to_seconds(raw, epoch_scale) if raw is not None else None
                    if t is not None and (start_epoch <= t < end_epoch):
                        wr.append(r)
                filtered_rows = wr
                applied["time_window_utc"] = {
                    "start_iso": iso_utc(start_epoch),
                    "end_iso_exclusive": iso_utc(end_epoch),
                }

        # --- Epoch key for all reporting ---
        epoch_key = detect_time_key(filtered_rows) or detect_time_key(rows)

        # --- Yes/No style summary when the question is human-like ---
        qn2 = (query or "").lower().strip()
        is_yesno = re.search(
            r"\b(was there|is there|did (someone|anybody)|has there been)\b", qn2
        )

        subject = None
        if re.search(r"\bunauthori[sz]ed\b|\bintruder\b|\bentry\b", qn2):
            subject = "unauthorised entry"
        elif re.search(r"\bfall(s|ing)?\b", qn2):
            subject = "fall"
        elif re.search(r"\bmotion\b", qn2):
            subject = "motion event"

        if is_yesno and subject:
            n = len(filtered_rows)
            period = when_phrase(get_time_window(query)) or "in the specified period"

            # find latest timestamp for nicer reporting
            latest_ts = None
            if epoch_key:
                for r in filtered_rows:
                    raw = (
                        get_nested(r, epoch_key)
                        if "." in epoch_key
                        else r.get(epoch_key)
                    )
                    t = to_seconds(raw, epoch_scale) if raw is not None else None
                    if t is not None and (latest_ts is None or t > latest_ts):
                        latest_ts = t

            if n == 0:
                return {
                    "ok": True,
                    "text": f"No, there was no {subject} detected {period}.",
                    "meta": {
                        "rows_considered": 0,
                        "applied_filters": {"note": "yesno_zero_result"},
                        "time_key": epoch_key,
                        "latest_iso": None,
                    },
                }
            else:
                latest_tail = f" Latest at {iso_utc(latest_ts)}." if latest_ts else ""
                plural = "" if n == 1 else "s"
                return {
                    "ok": True,
                    "text": f"Yes — {n} {subject}{plural} detected {period}.{latest_tail}",
                    "meta": {
                        "rows_considered": n,
                        "applied_filters": {"note": "yesno_positive"},
                        "time_key": epoch_key,
                        "latest_iso": iso_utc(latest_ts) if latest_ts else None,
                    },
                }

        # --- Keyword-based suggestion fallback (domain hints) ---
        if re.fullmatch(
            r"(temp|temperature|humidit(y|ies)|pressure|voltage|door(s)?|smoke(rs)?|camera(s)?|misty)(\s.*)?",
            qn2,
        ):
            suggestions = suggest_related_queries(query)
            if suggestions:
                return {
                    "ok": True,
                    "text": "Are you trying to find one of these?\n"
                    + "\n".join(f"- {s}" for s in suggestions),
                    "meta": {
                        "rows_considered": 0,
                        "applied_filters": {"note": "keyword_only_suggestion"},
                        "time_key": None,
                        "latest_iso": None,
                    },
                }

        # --- Empty data fallback ---
        if not filtered_rows:
            return {
                "ok": True,
                "text": "I checked your data based on the query, but I couldn’t find any data.",
                "meta": {
                    "rows_considered": 0,
                    "applied_filters": applied,
                    "time_key": epoch_key,
                    "latest_iso": None,
                },
            }

        # --- Default detailed summary ---
        text = report_from_rows(filtered_rows, query, epoch_key, epoch_scale)
        latest_ts = None
        if epoch_key:
            for r in filtered_rows:
                raw = get_nested(r, epoch_key) if "." in epoch_key else r.get(epoch_key)
                t = to_seconds(raw, epoch_scale) if raw is not None else None
                if t is not None:
                    latest_ts = t if (latest_ts is None or t > latest_ts) else latest_ts

        return {
            "ok": True,
            "text": text,
            "meta": {
                "rows_considered": len(filtered_rows),
                "applied_filters": applied,
                "time_key": epoch_key,
                "latest_iso": iso_utc(latest_ts) if latest_ts else None,
            },
        }

    except Exception as e:
        return {"ok": False, "text": f"Error: {e}", "meta": {}}


# ---------------- CLI ----------------


def parse_args():
    p = argparse.ArgumentParser(
        description="Chatty summarizer for IoT JSON/JSONL dumps."
    )
    p.add_argument(
        "-i", "--input", dest="input", required=True, help="Path to JSON/JSONL file"
    )
    p.add_argument(
        "-q",
        "--query",
        dest="query",
        default="",
        help="Natural language query (e.g., 'overview', 'faces seen by misty')",
    )
    p.add_argument(
        "--epoch-scale",
        choices=("s", "ms", "ns"),
        default="s",
        help="Epoch units for numeric timestamps",
    )
    p.add_argument(
        "--raw",
        action="store_true",
        help="(debug) return API JSON instead of chatty text",
    )
    return p.parse_args()  # ✅ must CALL parse_args(), not return p


def main():
    args = parse_args()
    result = summarize_for_api(args.input, args.query, args.epoch_scale)
    if args.raw:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(result.get("text", ""))
        else:
            print(result.get("text", ""), file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)


def summarize_text_only(data, query: str = "", epoch_scale: str = "s") -> str:
    """
    Convenience wrapper for summarize_for_api that always returns only text.
    """
    res = summarize_for_api(data, query, epoch_scale)
    if isinstance(res, dict):
        # Only return the text field even if meta exists
        return res.get("text", "")
    return str(res)
