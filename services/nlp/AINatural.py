#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AINatural.py — NL → Presto/Athena SQL (flat schema) with safe identifier
quoting and real device mapping.

Generated SQL targets a configurable logical table exposed by the user's
external read-only query API. The query scope defaults to the combined
edge/cloud view, with either tier available as an explicit filter.

Highlights
- Quotes DB/catalog names with hyphens:  FROM "qprime".continuum
- Uses actual stored device_name(s) (e.g., 'Misty Robot 1') and prefers device_id when known
- Fast-paths for single-device and ±window multi-device correlations
- Programmatic API: generate_sql("faces seen by Misty last month")

Env (override as needed)
- CONTINUUM_DB         (default: qprime)
- CONTINUUM_TABLE      (default: continuum)
- EPOCH_SCALE          (s|ms|ns, default: s)
- MODEL                (default: qwen2.5:7b-instruct-q4_K_M)
- OLLAMA_HOST          (default: http://127.0.0.1:11434)
- LOCAL_TZ_NAME        (default: Australia/Sydney)
"""

import os, re, json, difflib, pytz, requests
from datetime import datetime, timedelta
from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta
from textwrap import dedent
from typing import Dict, List, Any, Optional

# ---------- Optional fuzzy ----------
try:
    from rapidfuzz import process as rf_process, fuzz as rf_fuzz
except Exception:
    rf_process = None
    rf_fuzz = None

# ---------- Config ----------
MODEL = os.getenv("MODEL", "qwen2.5:7b-instruct-q4_K_M")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

# The LLM is an optional accelerator, never a requirement: Q-PRIME ships
# without one, so SQL generation must succeed on the rule-based path alone.
# Set USE_LLM_SQL=1 (with `docker compose --profile llm up -d`) to let an
# unmatched question be routed to the model first.
USE_LLM_SQL = os.getenv("USE_LLM_SQL", "").strip().lower() in ("1", "true", "yes")

# Rows returned by open-ended questions ("what happened in the last hour").
DEFAULT_ROW_LIMIT = int(os.getenv("NL_ROW_LIMIT", "200"))
LOCAL_TZ_NAME = os.getenv("LOCAL_TZ_NAME", "Australia/Sydney")
EPOCH_SCALE = os.getenv("EPOCH_SCALE", "s").lower().strip()

# Logical table exposed by the Q-PRIME query API.
CONTINUUM_DB = os.getenv("CONTINUUM_DB", "qprime")
CONTINUUM_TABLE = os.getenv("CONTINUUM_TABLE", "continuum")

# ---- Actionability gate: avoid querying the continuum on chit-chat ----------
GREETINGS = (r"\bhi\b|\bhello\b|\bhey\b|\bthanks\b|\bthank you\b|^\?$",)

# Anything naming a device, a measurement, an event, a quantity or a time is
# worth a query - the generator always produces *some* SQL for these, so a
# question does not have to match a hand-written template to be answered.
DOMAIN_TERMS = re.compile(
    r"\b("
    r"misty|robot|door|doors|smoke|fire|alarm|camera|zed|drone|tello|thp|soil|moisture|"
    r"heart|bpm|sensor|sensors|device|devices|gateway|"
    r"intruder|face|faces|person|people|event|events|activity|detection|detections|"
    r"temperature|temp|humidity|pressure|reading|readings|record|records|data|"
    r"avg|average|count|total|how\s+many|number\s+of|list|show|give\s+me|"
    r"latest|recent|newest|summary|overview|"
    r"last|past|today|yesterday|now|hour|hours|day|days|week|weeks|month|months|between|since"
    r")\b",
    re.I,
)


def is_actionable(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if t.startswith(("select ", "with ")):
        return True
    if re.fullmatch(r"(hi|hello|hey|thanks|thank you|help|\?|yo|sup|hola)", t):
        return False
    # treat single tokens (no verbs/numbers) as vague → let Inf handle
    if len(t.split()) == 1 and t in {
        "temperature",
        "humidity",
        "door",
        "smoke",
        "camera",
        "misty",
    }:
        return False
    return bool(DOMAIN_TERMS.search(t))


# ---------- Identifier quoting ----------
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(ident: str) -> str:
    """Quote identifiers that contain non-alphanumerics/underscores (Athena/Trino uses double quotes)."""
    return ident if IDENT_RE.match(ident) else f'"{ident}"'


def table_fqn(db: str, table: str) -> str:
    return f"{quote_ident(db)}.{quote_ident(table)}"


CONTINUUM_TABLE_FQN = table_fqn(CONTINUUM_DB, CONTINUUM_TABLE)

# Which slice of the external data source the answer should cover. The SQL
# always targets the configured logical table; scope travels separately to
# the query API.
CONTINUUM = "continuum"
_CURRENT_SCOPE = CONTINUUM

SCOPE_ALIASES = {
    "true": "cloud", "1": "cloud", "cloud": "cloud", "yes": "cloud",
    "false": "edge", "0": "edge", "edge": "edge", "no": "edge",
}


def normalize_scope(value) -> str:
    """``True``/``'cloud'`` -> cloud, ``False``/``'edge'`` -> edge, else continuum."""
    return SCOPE_ALIASES.get(str(value).strip().lower(), CONTINUUM)


def set_cloud_context(is_cloud=None):
    """Record which slice of the continuum this query is scoped to."""
    global _CURRENT_SCOPE
    _CURRENT_SCOPE = normalize_scope(is_cloud)
    return _CURRENT_SCOPE


def get_scope() -> str:
    return _CURRENT_SCOPE


def get_table_fqn() -> str:
    """The logical table exposed by the Q-PRIME query API."""
    return CONTINUUM_TABLE_FQN


def get_db_table_names() -> tuple[str, str]:
    return CONTINUUM_DB, CONTINUUM_TABLE


# ---------- Epoch helpers ----------
def ts_expr() -> str:
    if EPOCH_SCALE == "ms":
        return 'from_unixtime("timestamp"/1000.0)'
    if EPOCH_SCALE == "ns":
        return 'from_unixtime("timestamp"/1000000000.0)'
    return 'from_unixtime("timestamp")'


def epoch_now_seconds() -> int:
    return int(datetime.now(tz=pytz.UTC).timestamp())


# ---------- Devices & mappings ----------
# Canonical names used in NL; map to stored device_name / ids in the table.
DEVICE_ALIASES: Dict[str, List[str]] = {
    "MistyRobot1": ["misty", "misty robot", "misty robot 1", "robot", "camera robot"],
    "LabDoorSensor": [
        "LabDoorSensor_1",
        "LabDoorSensor_2",
        "door",
        "doors",
        "door sensor",
        "lab door",
        "back door",
        "back door sensor",
        "main door",
        "main door sensor",
        "front door",
        "front door sensor",
    ],
    "LabSmokeSensor": [
        "smoke",
        "smokes",
        "smoke alarm",
        "smoke alarms",
        "fire",
        "smoke sensor 1",
    ],
    "LabCamera": [
        "camera",
        "ZED camera",
        "zed camera",
        "lab camera",
        "ZED2i",
        "camera 1",
    ],
    "TemperatureSensor": [
        "LabTHPSensor",
        "temperature",
        "temp",
        "temperature sensor",
        "temperature sensor 1",
        "thp",
        "thp sensor",
        "humidity sensor",
        "pressure sensor",
    ],
    "TelloDrone1": ["Tello Drone 1", "tello drone", "drone", "drone camera"],
    "SoilMoistureSensor": [
        "soil",
        "moisture",
        "soil moisture",
        "soil moisture sensor",
    ],
    "HeartRateMonitor": [
        "heart",
        "heart rate",
        "heart rate monitor",
        "bpm",
    ],
}
# Actual stored names/ids: the SDC-lab testbed of the paper plus the device
# names commonly used for the same streams.
DEVICE_DB_NAME: Dict[str, List[str]] = {
    "MistyRobot1": ["Misty Robot 1", "MistyRobot1"],
    "LabDoorSensor": [
        "LabDoorSensor_1",
        "LabDoorSensor_2",
        "Door Sensor",
        "Back Door Sensor",
        "Main Door Sensor",
        "Front Door Sensor",
    ],
    "LabSmokeSensor": [
        "Lab Smoke Sensor",
        "Smoke Sensor",
        "Smoke Sensor 1",
        "SmokeDetector_1",
    ],
    "LabCamera": ["Lab Camera", "Camera", "ZED2i", "RGBCamera_1"],
    "TemperatureSensor": ["Temperature Sensor 1", "LabTHPSensor"],
    "PressureSensor": ["LabTHPSensor", "pressure sensor"],
    "HumiditySensor": ["LabTHPSensor", "humiditiy sensor"],
    "SoilMoistureSensor": ["Soil Moisture Sensor 1", "SoilMoisture_1"],
    "HeartRateMonitor": ["HeartMonitor_1"],
    "TelloDrone1": ["Tello Drone 1", "Tello Drone"],
}
DEVICE_IDS: Dict[str, List[str]] = {
    "MistyRobot1": ["misty_03953"],
    "ZED2i": ["zed2i-001"],
    "Tello Drone 1": ["92f4d0e3-6940-49d4-9d2f-4f049aba10ed"],
}


def _alias_key(text: str) -> str:
    """Normalize alias text for lookup (lowercase, collapsed whitespace)."""
    return re.sub(r"\s+", " ", text.strip().lower())


# A bare "door" means every door in the deployment - the SDC lab's single
# sensor and the Q-PRIME testbed's pair.
ANY_DOOR = ["Door Sensor", "LabDoorSensor_1", "LabDoorSensor_2"]

DEVICE_DB_ALIAS_OVERRIDES: Dict[str, Dict[str, List[str]]] = {
    "LabDoorSensor": {
        _alias_key("door"): ANY_DOOR,
        _alias_key("doors"): ANY_DOOR,
        _alias_key("door sensor"): ANY_DOOR,
        _alias_key("lab door"): ANY_DOOR,
        _alias_key("lab door sensor"): ANY_DOOR,
        _alias_key("back door"): ["Back Door Sensor"],
        _alias_key("back door sensor"): ["Back Door Sensor"],
        _alias_key("main door"): ["Main Door Sensor"],
        _alias_key("main door sensor"): ["Main Door Sensor"],
        _alias_key("front door"): ["Front Door Sensor"],
        _alias_key("front door sensor"): ["Front Door Sensor"],
    },
}

CANON_DEVICES = list(DEVICE_ALIASES.keys())
CONTEXT = {"device_hints": [], "time_hint": None}

EVENT_ALIASES = {
    "intruder": "intruder_detected",
    "faces": "familiar_face_detected",
    "people": "familiar_face_detected",
    "familiar_face": "familiar_face",  # keep both familiar_face & face_detected
}
EVENT_CANON_SAFE = {
    "MistyRobot1": [
        "intruder_detected",
        "intruder",
        "face_detected",
        "familiar_face",
        "familiar_face_detected",
        "person_detected",
    ],
    "LabCamera": ["motion", "face_detected", "person_detected"],
    # "LabDoorSensor": [
    #     "open",
    #     "close",
    # ],  # but door event may be null → avoid unless asked
    "LabSmokeSensor": [
        "alarm",
        "smoke_detected",
        "test",
    ],  # may be null → avoid unless asked
}


def sql_str(s: str) -> str:
    # escape single quotes for SQL literals
    return "'" + s.replace("'", "''") + "'"


def extract_sql_only(obj: dict) -> Optional[str]:
    """
    Accepts {"sql": "<query>"} (optionally with extra keys).
    Returns the SQL string or None.
    """
    if not isinstance(obj, dict):
        return None
    val = obj.get("sql")
    return val if isinstance(val, str) and val.strip() else None


def sql_list(vals) -> str:
    return ", ".join(sql_str(v) for v in vals)


def normalize_device_aliases(text: str) -> str:
    out = text
    for canon, aliases in DEVICE_ALIASES.items():
        for a in sorted(aliases, key=len, reverse=True):
            out = re.sub(rf"\b{re.escape(a)}\b", canon, out, flags=re.I)
    return out


def fuzzy_match_device(term: str) -> Optional[str]:
    if term in CANON_DEVICES:
        return term
    if rf_process:
        m = rf_process.extractOne(term, CANON_DEVICES, scorer=rf_fuzz.WRatio)
        if m and m[1] >= 80:
            return m[0]
    else:
        m = difflib.get_close_matches(term, CANON_DEVICES, n=1, cutoff=0.8)
        if m:
            return m[0]
    return None


def _window_seconds(val: int, unit: str) -> int:
    """unit: 'second' or 'minute'"""
    return val if unit == "second" else val * 60


def devices_predicate_for(canon: str, alias_hint: Optional[str] = None) -> str:
    """Match a canonical device by name, and by ID where an ID is known.

    ``DEVICE_IDS`` holds identifiers recorded in one specific SDC-lab
    deployment. Filtering on them *exclusively* meant every Misty, ZED and
    drone question answered zero against any other deployment — including the
    testbed this repository ships — because those devices carry different IDs.
    The ID is now an additional way to match, not the only one.
    """
    names: Optional[List[str]] = None
    if alias_hint:
        alias_key = _alias_key(alias_hint)
        overrides = DEVICE_DB_ALIAS_OVERRIDES.get(canon, {})
        names = overrides.get(alias_key)
        if not names:
            for candidate in DEVICE_DB_NAME.get(canon, []):
                if _alias_key(candidate) == alias_key:
                    names = [candidate]
                    break

    if not names:
        names = DEVICE_DB_NAME.get(canon, [canon])

    predicate = f"resource.device_name IN ({', '.join(sql_str(n) for n in names)})"
    ids = DEVICE_IDS.get(canon, [])
    if ids:
        by_id = f"resource.device_id IN ({', '.join(sql_str(i) for i in ids)})"
        return f"({by_id} OR {predicate})"
    return predicate


# ---------- Time parsing ----------
def _tz():
    try:
        return pytz.timezone(LOCAL_TZ_NAME)
    except Exception:
        return pytz.timezone("Australia/Sydney")


def _as_table_epoch(dt_local: datetime) -> int:
    secs = int(dt_local.astimezone(pytz.UTC).timestamp())
    if EPOCH_SCALE == "ms":
        return secs * 1000
    if EPOCH_SCALE == "ns":
        return secs * 1_000_000_000
    return secs


def _month_bounds(tz, year, mon):
    start = tz.localize(datetime(year, mon, 1, 0, 0, 0))
    end = start + relativedelta(months=1)
    return start, end


RANGE_PATTERNS = [
    re.compile(r"\bbetween\s+(.*?)\s+and\s+(.*)", re.I),
    re.compile(r"\bfrom\s+(.*?)\s+to\s+(.*)", re.I),
]


def parse_time_range(user_text: str) -> Optional[Dict[str, int]]:
    tz = _tz()
    now_local = datetime.now(tz)
    text = (user_text or "").strip()

    # --- helpers -------------------------------------------------------------
    MONTHS = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sep": 9,
        "sept": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }
    ORD = r"(?:st|nd|rd|th)?"

    def _mk(day_start: datetime, day_end: datetime) -> Dict[str, int]:
        return {
            "start_epoch": _as_table_epoch(day_start),
            "end_epoch": _as_table_epoch(day_end),
        }

    def _day_bounds(d: datetime):
        s = d.replace(hour=0, minute=0, second=0, microsecond=0)
        return s, s + timedelta(days=1)

    # --- 1) explicit ranges: "between X and Y" / "from X to Y" ---------------
    # supports:
    #   between September 22 and September 30 2025
    #   between 22 Sep and 30 Sep 2025
    #   between 2025-09-22 and 2025-09-30
    #   from Sep 22 to Sep 30 2025
    pat_pairs = [
        re.compile(
            rf"\bbetween\s+([A-Za-z]{{3,9}}\s+\d{{1,2}}{ORD}(?:,\s*\d{{4}})?)\s+and\s+([A-Za-z]{{3,9}}\s+\d{{1,2}}{ORD}(?:\s*,?\s*\d{{4}})?)",
            re.I,
        ),
        re.compile(
            rf"\bfrom\s+([A-Za-z]{{3,9}}\s+\d{{1,2}}{ORD}(?:,\s*\d{{4}})?)\s+to\s+([A-Za-z]{{3,9}}\s+\d{{1,2}}{ORD}(?:\s*,?\s*\d{{4}})?)",
            re.I,
        ),
        re.compile(
            r"\bbetween\s+(20\d{2}-\d{1,2}-\d{1,2})\s+and\s+(20\d{2}-\d{1,2}-\d{1,2})",
            re.I,
        ),
        re.compile(
            r"\bfrom\s+(20\d{2}-\d{1,2}-\d{1,2})\s+to\s+(20\d{2}-\d{1,2}-\d{1,2})", re.I
        ),
    ]
    for pat in pat_pairs:
        mm = pat.search(text)
        if mm:
            left, right = mm.group(1), mm.group(2)
            ldt = dateparser.parse(left)
            right_has_year = re.search(r"\b20\d{2}\b", right)
            rdt = dateparser.parse(
                right if right_has_year else (f"{right} {ldt.year}" if ldt else right)
            )
            if ldt and rdt:
                if ldt.tzinfo is None:
                    ldt = tz.localize(ldt)
                if rdt.tzinfo is None:
                    rdt = tz.localize(rdt)
                s = tz.localize(datetime(ldt.year, ldt.month, ldt.day, 0, 0, 0))
                e = tz.localize(
                    datetime(rdt.year, rdt.month, rdt.day, 0, 0, 0)
                ) + timedelta(
                    days=1
                )  # half-open
                return _mk(s, e)

    # --- 2) whole month: "October 2025" / "in Oct 2025" ----------------------
    # Avoid matching "Oct 3" as a month-only by requiring either:
    #   (a) month + 4-digit year, or
    #   (b) month with NO following 1–2 digit day.
    m_mon_year = re.search(
        r"(?:\bin\s+|\bfor\s+)?\b([A-Za-z]{3,9})\b\s+(\d{4})\b", text, re.I
    )
    if m_mon_year:
        mon_name = m_mon_year.group(1).lower()
        if mon_name in MONTHS:
            mon = MONTHS[mon_name]
            year = int(m_mon_year.group(2))
            s, e = _month_bounds(tz, year, mon)  # [month_start, next_month_start)
            return _mk(s, e)

    m_mon_only = re.search(
        r"(?:\bin\s+|\bfor\s+)?\b([A-Za-z]{3,9})\b(?!\s+\d{1,2}\b)", text, re.I
    )
    if m_mon_only:
        mon_name = m_mon_only.group(1).lower()
        if mon_name in MONTHS:
            mon = MONTHS[mon_name]
            year = now_local.year
            s, e = _month_bounds(tz, year, mon)
            return _mk(s, e)

    # --- 3) single explicit day (after ranges/month) -------------------------
    m = re.search(
        rf"(?:\bon\s+)?\b([A-Za-z]{{3,9}})\b[\s,]+(\d{{1,2}}){ORD}(?:[\s,]+(\d{{4}}))?",
        text,
        re.I,
    )
    if m and m.group(1).lower() in MONTHS:
        mon = MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now_local.year
        s = tz.localize(datetime(year, mon, day, 0, 0, 0))
        e = s + timedelta(days=1)
        return _mk(s, e)

    # numeric explicit day (YYYY-MM-DD or DD-MM-YYYY)
    m = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)  # YYYY-MM-DD
    if m:
        y, mon, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        s = tz.localize(datetime(y, mon, day, 0, 0, 0))
        e = s + timedelta(days=1)
        return _mk(s, e)
    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", text)  # DD-MM-YYYY
    if m:
        day, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        s = tz.localize(datetime(y, mon, day, 0, 0, 0))
        e = s + timedelta(days=1)
        return _mk(s, e)

    # --- 4) keywords: today / yesterday --------------------------------------
    if re.search(r"\btoday\b", text, re.I):
        s, e = _day_bounds(now_local)
        return _mk(s, e)
    if re.search(r"\byesterday\b", text, re.I):
        s, _ = _day_bounds(now_local - timedelta(days=1))
        e = s + timedelta(days=1)
        return _mk(s, e)

    # --- 5) relatives: last/past N days|hours|minutes ------------------------
    m_days = re.search(r"\b(last|past)\s+(\d+)\s+days?\b", text, re.I)
    if m_days:
        n = int(m_days.group(2))
        s = now_local - timedelta(days=n)
        return _mk(s, now_local)

    m_hours = re.search(r"\b(last|past)\s+(\d+)\s+hours?\b", text, re.I)
    if m_hours:
        n = int(m_hours.group(2))
        s = now_local - timedelta(hours=n)
        return _mk(s, now_local)

    m_mins = re.search(r"\b(last|past)\s+(\d+)\s+min(ute)?s?\b", text, re.I)
    if m_mins:
        n = int(m_mins.group(2))
        s = now_local - timedelta(minutes=n)
        return _mk(s, now_local)

    # --- 6) single date fallback via dateparser ------------------------------
    try:
        dt = dateparser.parse(text)
        if dt:
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            s = tz.localize(datetime(dt.year, dt.month, dt.day, 0, 0, 0))
            e = s + timedelta(days=1)
            return _mk(s, e)
    except Exception:
        pass

    return None


# ---------- Intent helpers ----------
def infer_device_events(user: str, device: str) -> Optional[List[str]]:
    t = user.lower()
    if device == "LabDoorSensor":
        mentions_events = bool(re.search(r"\bevent(s)?\b|\bopening(s)?\b", t))
        if mentions_events and re.search(r"\bopen(s|ed|ing|ings)?\b", t):
            return ["open", "opened"]
        if mentions_events and re.search(r"\bclose(s|d|ed|ing)?\b", t):
            return ["close", "closed"]
        return None
    if device == "LabSmokeSensor":
        if "smoke_detected" in t:
            return ["smoke_detected"]
        if re.search(r"\balarm(s)?\b", t):
            return ["alarm", "smoke_alarm", "smoke_detected"]
        if re.search(r"\btest(s)?\b", t):
            return ["test"]
        return None
    if device == "LabCamera":
        if "motion" in t:
            return ["motion"]
        if "face" in t:
            return ["face_detected"]
        if "person" in t or "people" in t:
            return ["person_detected"]
    if device == "MistyRobot1":
        if "intruder" in t:
            return ["intruder_detected", "intruder"]
        if "face" in t:
            return ["face_detected", "familiar_face", "familiar_face_detected"]
        if "person" in t or "people" in t:
            return ["person_detected"]
    return None


# ---------- LLM plumbing ----------
def system_prompt() -> str:
    return dedent(f"""
    You are an expert Athena (Trino) standard SQL generator that returns STRICT JSON only.
    Target table: {get_table_fqn()}

    DATA MODEL (flat)
    - type INT, event_source INT, gateway_id STRING, resource.device_id STRING, resource.device_name STRING,
      timestamp BIGINT, temperature DOUBLE, event STRING, ip_address STRING, sensor_id STRING,
      contextvalue.person STRING, contextvalue.yaw INT, contextvalue.pitch INT, contextvalue.distance INT, partition_0..3 STRING

    RULES
    - Output ONLY JSON with keys: sql (string), title (string), explanation (string), suggestions (array of strings).
    - Single SELECT (or WITH ... SELECT); end with semicolon.
    - Use flat columns (timestamp, contextvalue.event, contextvalue.person, resource.device_name, resource.device_id). Do NOT use value.*.
    - Prefer WHERE timestamp BETWEEN <start> AND <end> for time ranges.
    - "latest" → ORDER BY {ts_expr()} DESC LIMIT 1.
    - ±N minutes/seconds correlations → use CTEs and BETWEEN join on {ts_expr()}.
    - Door/Smoke may have NULL/empty event → avoid event filters unless explicitly asked.
    - Misty/LabCamera can be filtered by event/person/yaw/pitch/distance.
    """).strip()


FEWSHOTS = [
    {
        "user": "How many intruder detections did Misty record last 7 days?",
        "sql": f"SELECT COUNT(*) AS intruder_count FROM {get_table_fqn()} WHERE resource.device_name IN ('Misty Robot 1','MistyRobot1') AND contextvalue.event IN ('intruder_detected','intruder') AND {ts_expr()} >= current_timestamp - INTERVAL '7' day;",
    },
    {
        "user": "Find door activity within ±2 minutes of any smoke reading on July 24, 2025",
        "sql": (
            "WITH door AS ("
            f"  SELECT {ts_expr()} AS ts FROM {get_table_fqn()} "
            "  WHERE resource.device_name IN ('Door Sensor') "
            '    AND "timestamp" >= 1753315200 AND "timestamp" < 1753401600'
            "), smoke AS ("
            f"  SELECT {ts_expr()} AS ts FROM {get_table_fqn()} "
            "  WHERE resource.device_name IN ('Lab Smoke Sensor','Smoke Sensor') "
            '    AND "timestamp" >= 1753315200 AND "timestamp" < 1753401600'
            ") "
            "SELECT d.ts AS door_time, s.ts AS smoke_time "
            "FROM door d JOIN smoke s "
            "ON d.ts BETWEEN s.ts - INTERVAL '2' minute AND s.ts + INTERVAL '2' minute "
            "ORDER BY s.ts, d.ts;"
        ),
    },
    {
        "user": "Give me an overview of the Misty Robot 1",
        "sql": f"SELECT * FROM {get_table_fqn()} WHERE resource.device_name IN ('Misty Robot 1','MistyRobot1');",
    },
    {
        "user": "How many door events on July 15, 2025",
        "sql": (
            f"SELECT COUNT(*) FROM {get_table_fqn()} "
            "WHERE resource.device_name = 'Door Sensor' "
            "AND from_unixtime(\"timestamp\") >= TIMESTAMP '2025-07-15 00:00:00' "
            "AND from_unixtime(\"timestamp\") <  TIMESTAMP '2025-07-16 00:00:00';"
        ),
    },
    {
        "user": "Who was the last person to enter the room?",
        "sql": (
            f'SELECT "timestamp", resource.device_id, resource.device_name, contextvalue.event, contextvalue.person, contextvalue.yaw, contextvalue.pitch, contextvalue.distance '
            f"FROM {get_table_fqn()} "
            "WHERE resource.device_name IN ('Misty Robot 1','MistyRobot1') "
            "  AND contextvalue.event = 'familiar_face_detected' "
            'ORDER BY "timestamp" DESC LIMIT 1;'
        ),
    },
    {
        "user": "Show me the latest sensor activity",
        "sql": f'SELECT * FROM {get_table_fqn()} ORDER BY "timestamp" DESC LIMIT 10;',
    },
    {
        "user": "When was the last fire/smoke alarm?",
        "sql": (
            f"SELECT * FROM {get_table_fqn()} "
            "WHERE resource.device_name IN ('Lab Smoke Sensor','Smoke Sensor') "
            "AND COALESCE(contextvalue.event,'') <> '' "
            'ORDER BY "timestamp" DESC LIMIT 1;'
        ),
    },
    {
        "user": "List all devices that had any event on July 28, 2025",
        "sql": (
            f"SELECT DISTINCT resource.device_name FROM {get_table_fqn()} "
            "WHERE from_unixtime(\"timestamp\") >= TIMESTAMP '2025-07-28 00:00:00' "
            "  AND from_unixtime(\"timestamp\") <  TIMESTAMP '2025-07-29 00:00:00';"
        ),
    },
    {
        "user": "Show me the average temperature today.",
        "sql": (
            f"SELECT AVG(contextvalue.temperature) AS avg_temperature_today "
            f"FROM {get_table_fqn()} "
            "WHERE resource.device_name = 'LabTHPSensor' "
            "  AND from_unixtime(\"timestamp\") >= date_trunc('day', now()) "
            '  AND from_unixtime("timestamp") <  now();'
        ),
    },
    {
        "user": "Was there an unauthorised entry in room 1 today?",
        "sql": (
            f'SELECT "timestamp", resource.device_id, resource.device_name, contextvalue.event, contextvalue.person, contextvalue.yaw, contextvalue.pitch, contextvalue.distance '
            f"FROM {get_table_fqn()} "
            "WHERE resource.device_name IN ('Misty Robot 1','MistyRobot1') "
            "  AND contextvalue.event = 'intruder_detected' "
            "  AND from_unixtime(\"timestamp\") >= date_trunc('day', now()) "
            '  AND from_unixtime("timestamp") <  now();'
        ),
    },
    {
        "user": "Did someone fall in the last hour?",
        "sql": (
            f"SELECT * FROM {get_table_fqn()} "
            "WHERE resource.device_name = 'Fall Sensor' "
            "  AND from_unixtime(\"timestamp\") >= (now() - interval '1' hour) "
            '  AND from_unixtime("timestamp") <  now();'
        ),
    },
]


def build_messages(
    user_query: str, time_hint: Optional[Dict[str, int]]
) -> List[Dict[str, str]]:
    sys = {"role": "system", "content": system_prompt()}
    msgs = [sys]
    for fs in FEWSHOTS:
        msgs.append({"role": "user", "content": fs["user"]})
        msgs.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "sql": (
                            fs["sql"]
                            if fs["sql"].strip().endswith(";")
                            else (fs["sql"].strip() + ";")
                        ),
                        "title": "Sample",
                        "explanation": "Demonstration of SQL style.",
                        "suggestions": [
                            "Show raw events",
                            "Group by day",
                            "Filter by person",
                        ],
                    }
                ),
            }
        )
    norm = normalize_device_aliases(user_query)
    if time_hint:
        norm += f" (Time hint: start_epoch={time_hint['start_epoch']}, end_epoch={time_hint['end_epoch']})"
    msgs.append({"role": "user", "content": norm})
    return msgs


def call_ollama(messages: List[Dict[str, str]]) -> Optional[str]:
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/v1/chat/completions",
            json={
                "model": MODEL,
                "messages": messages,
                "temperature": 0.2,
                "stream": False,
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[Ollama error] {e}")
        return None


def try_json(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None


def extract_sql_fields(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    need = {"sql": str, "title": str, "explanation": str, "suggestions": list}
    for k, t in need.items():
        if k not in obj or not isinstance(obj[k], t):
            return None
    return obj


# ---------- SQL post-processing & validation ----------
SQL_DANGEROUS = re.compile(
    r"\b(DROP|TRUNCATE|DELETE|INSERT|MERGE|UPDATE|CREATE|ALTER)\b", re.I
)


def sanitize_sql_for_null_event_devices(sql: str) -> str:
    """
    Strip event predicates only inside CTE blocks that clearly target Door/Smoke.
    Avoid spanning across ') , next_cte' by limiting the match to inside the CTE.
    """
    # Find CTE blocks:  name AS ( ... )
    cte_pat = re.compile(r"(\b\w+\b\s+AS\s*\()\s*(.*?)\s*(\))", re.I | re.S)
    devices = ("Door Sensor", "Lab Smoke Sensor", "Smoke Sensor")

    def scrub_cte_body(body: str) -> str:
        # Only scrub if body filters for a door/smoke device_name
        if not re.search(
            r"device_name\s+IN\s*\(\s*('(?:Door Sensor|Lab Smoke Sensor|Smoke Sensor)'\s*(?:,\s*'[^']*')*)\s*\)",
            body,
            re.I,
        ):
            return body
        # Remove event predicates inside this body only
        body = re.sub(
            r"(\s+(AND|OR)\s+)\(?\s*event\s*(=|IN|LIKE)\s*(\([^)]*\)|'[^']*')\s*\)?",
            " ",
            body,
            flags=re.I,
        )
        body = re.sub(
            r"(\s+(AND|OR)\s+)\(?\s*event\s+IS\s+(NOT\s+)?NULL\s*\)?",
            " ",
            body,
            flags=re.I,
        )
        body = re.sub(r"\s{2,}", " ", body)
        body = re.sub(r"(WHERE)\s+(AND|OR)\b", r"\1 ", body, flags=re.I)
        return body

    def repl(m):
        open_tok, body, close_tok = m.group(1), m.group(2), m.group(3)
        return open_tok + scrub_cte_body(body) + close_tok

    return cte_pat.sub(repl, sql)


def fix_between_epoch_mismatch(sql: str) -> str:
    return re.sub(
        r"from_unixtime\s*\(\s*\"?timestamp\"?(?:\/\s*1000\.0|\/\s*1000000000\.0)?\s*\)\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)",
        r"\"timestamp\" BETWEEN \1 AND \2",
        sql,
        flags=re.I,
    )


def drop_redundant_time_filters(sql: str) -> str:
    """
    Remove cases where both epoch and from_unixtime filters are mixed.
    Preference:
      - If epoch ints are used, drop from_unixtime(...) comparisons.
      - If TIMESTAMP literals are used, drop raw epoch comparisons.
    """
    # Case 1: remove from_unixtime(...) >= <int>
    sql = re.sub(
        r'from_unixtime\("timestamp"\)\s*>=\s*\d+\s*(AND\s*)?', "", sql, flags=re.I
    )
    sql = re.sub(
        r'from_unixtime\("timestamp"\)\s*<\s*\d+\s*(AND\s*)?', "", sql, flags=re.I
    )

    # Case 2: remove raw epoch comparisons if proper TIMESTAMP literals are present
    if "TIMESTAMP" in sql.upper():
        sql = re.sub(r'"\s*timestamp\s*"\s*>=\s*\d+\s*(AND\s*)?', "", sql, flags=re.I)
        sql = re.sub(r'"\s*timestamp\s*"\s*<\s*\d+\s*(AND\s*)?', "", sql, flags=re.I)
    # collapse duplicate epoch pairs
    sql = re.sub(
        r'(\bAND\s+)?("?\s*timestamp\s*"?\s*>=\s*\d+\s+AND\s+"?\s*timestamp\s*"?\s*<\s*\d+)\s+(AND\s+)?\2',
        r"\1\2",
        sql,
        flags=re.I,
    )
    sql = re.sub(r"\bWHERE\s+AND\b", "WHERE ", sql, flags=re.I)
    sql = re.sub(r"\s+AND\s*;", ";", sql, flags=re.I)
    sql = re.sub(r"\s{2,}", " ", sql)
    return sql


def inject_time_into_outer_select(sql: str, start_epoch: int, end_epoch: int) -> str:
    clause = f'"timestamp" >= {start_epoch} AND "timestamp" < {end_epoch}'
    q = sql.strip()
    head, tail = "", q
    if q.lower().startswith("with"):
        idx = q.lower().rfind(") select")
        if idx == -1:
            idx = q.lower().find("select", 0)
        if idx != -1:
            head, tail = q[: idx + 1], q[idx + 1 :]
    m_where = re.search(r"\bwhere\b", tail, re.I)
    m_stop = re.search(r"\b(group\s+by|order\s+by|limit)\b", tail, re.I)
    if m_where and (not m_stop or m_where.start() < m_stop.start()):
        tail = re.sub(
            r"\bwhere\b", "WHERE " + clause + " AND ", tail, flags=re.I, count=1
        )
    else:
        m_from = re.search(rf"\bfrom\s+{re.escape(get_table_fqn())}\b", tail, re.I)
        if m_from:
            insert_at = m_from.end()
            tail = tail[:insert_at] + f" WHERE {clause} " + tail[insert_at:]
        else:
            if m_stop:
                pos = m_stop.start()
                tail = tail[:pos] + f" WHERE {clause} " + tail[pos:]
            else:
                tail = tail.rstrip(";") + f" WHERE {clause};"
    return (head + tail).strip()


def _has_epoch_pair(sql: str) -> bool:
    # Accept quoted or unquoted on either side
    return bool(
        re.search(
            r'"?timestamp"?\s*>=\s*\d+\s+AND\s+"?timestamp"?\s*<\s*\d+', sql, re.I
        )
    )


EPOCH_PAIR_RE = re.compile(
    r'"\s*timestamp\s*"\s*>=\s*(\d+)\s+AND\s+"?\s*timestamp\s*"?\s*<\s*(\d+)', re.I
)


def _extract_epoch_pair(sql: str) -> Optional[tuple[int, int]]:
    m = EPOCH_PAIR_RE.search(sql)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _replace_epoch_pair(sql: str, start_epoch: int, end_epoch: int) -> str:
    return EPOCH_PAIR_RE.sub(
        f'"timestamp" >= {start_epoch} AND "timestamp" <  {end_epoch}', sql, count=1
    )


def patch_time_hint(sql: str, time_hint: Optional[Dict[str, int]]) -> str:
    """
    Inject or correct the time filter using the parsed time_hint.

    Rules:
    - If there's a BETWEEN on timestamp, leave it (assume author intent).
    - If there's an existing epoch pair:
        * If its span is < the hint span (e.g., a stray 24h window
          when the user asked for a month), override it with the hint.
        * Otherwise, keep it.
    - If there's no time filter, inject the hint.
    """
    if not time_hint:
        return sql

    start_epoch = time_hint["start_epoch"]
    end_epoch = time_hint["end_epoch"]
    hint_span = end_epoch - start_epoch  # seconds

    # Respect explicit BETWEEN clause
    if re.search(r'\b"?timestamp"?\s+between\b', sql, re.I):
        return sql

    # If an epoch pair already exists, decide whether to override
    pair = _extract_epoch_pair(sql)
    if pair:
        cur_start, cur_end = pair
        cur_span = max(0, cur_end - cur_start)

        # If current span is clearly shorter than the hint (e.g., < 0.8 of hint),
        # treat it as too-narrow and override with the hint.
        if hint_span > 0 and cur_span < int(0.8 * hint_span):
            return _replace_epoch_pair(sql, start_epoch, end_epoch)
        return sql

    # No time filter → inject
    return inject_time_into_outer_select(sql, start_epoch, end_epoch)


def validate_sql(sql: str) -> Optional[str]:
    q = sql.strip()

    # must be SELECT/CTE
    if not (q.lower().startswith("select") or q.lower().startswith("with")):
        return "Only SELECT/CTE queries are allowed."

    # deny dangerous ops
    if SQL_DANGEROUS.search(q):
        return "Refusing non-SELECT SQL."

    # enforce table match with regex (allow quotes, whitespace, newlines)
    db, table = get_db_table_names()
    target_re = re.compile(
        rf'\bfrom\s+["\']?{re.escape(db)}["\']?\s*\.\s*["\']?{re.escape(table)}["\']?\b',
        re.IGNORECASE | re.DOTALL,
    )

    # must end with ;
    if not q.endswith(";"):
        return "SQL must end with a semicolon."

    return None


# ---------- Templates (fast-paths) ----------
def try_single_device_template(
    user: str, time_hint: Optional[Dict[str, int]]
) -> Optional[str]:
    user_lower = (user or "").lower()
    t_norm = normalize_device_aliases(user).lower()
    device = None
    alias_hint = None
    for canon, aliases in DEVICE_ALIASES.items():
        alias_match = None
        for alias in sorted(aliases, key=len, reverse=True):
            alias_low = alias.lower()
            if re.search(rf"\b{re.escape(alias_low)}\b", user_lower):
                alias_match = alias_low
                break
        if alias_match:
            device = canon
            alias_hint = alias_match
            break
        if re.search(rf"\b{re.escape(canon.lower())}\b", t_norm):
            device = canon
            alias_hint = None
            break
    if not device:
        return None

    wants_count = bool(re.search(r"\b(count|how\s+many)\b", t_norm))
    wants_daily = any(
        w in t_norm for w in ("daily", "per day", "by day", "group by day")
    )
    wants_latest = False
    if re.search(r"\b(latest|most\s+recent)\b", t_norm):
        wants_latest = True
    elif re.search(r"\blast\b", t_norm):
        # treat "last" as latest only when it isn't followed by a number/time unit (e.g. "last 2 hours")
        if not re.search(
            r"\blast\s+(?:\d+\s*)?(?:hour|hours|day|days|week|weeks|month|months|min|mins|minute|minutes)\b",
            t_norm,
        ):
            wants_latest = True

    th = ""
    if time_hint and not wants_latest:
        th = f"\n  AND \"timestamp\" >= {time_hint['start_epoch']}\n  AND \"timestamp\" <  {time_hint['end_epoch']}"

    event_clause = ""
    evs = infer_device_events(user, device)
    if device in ("MistyRobot1", "LabCamera"):
        if evs:
            if len(evs) == 1:
                event_clause = f"\n  AND contextvalue.event = '{evs[0]}'"
            else:
                event_clause = "\n  AND contextvalue.event IN (" + sql_list(evs) + ")"
    else:
        # Door/Smoke: only add if explicitly asked (already handled via infer_device_events)
        if evs:
            if len(evs) == 1:
                event_clause = f"\n  AND contextvalue.event = '{evs[0]}'"
            else:
                event_clause = "\n  AND contextvalue.event IN (" + sql_list(evs) + ")"

    # External producers may choose their own door device names. The
    # canonical stream attribute is the stable contract for every door.
    dev_pred = "contextattribute = 'door'" if device == "LabDoorSensor" else devices_predicate_for(device, alias_hint)

    if wants_count:
        return f"SELECT COUNT(*) AS n\nFROM {get_table_fqn()}\nWHERE {dev_pred}{th}{event_clause};"

    if wants_daily:
        return (
            f"SELECT date_trunc('day', {ts_expr()}) AS day_utc, COUNT(*) AS cnt\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE {dev_pred}{th}{event_clause}\n"
            f"GROUP BY 1\nORDER BY 1;"
        )

    if wants_latest:
        # Build/expand the event set intelligently for Misty
        evs = infer_device_events(user, device) or []
        # Only expand to faces if user actually asked about faces or people
        if (
            device == "MistyRobot1"
            and re.search(r"\b(face|faces|person|people|seen|see)\b", t_norm)
            and not re.search(r"\bintruder\b", t_norm)
        ):
            wanted = {"familiar_face", "familiar_face_detected", "person_detected"}
            evs = sorted(set(evs).union(wanted))

        event_clause_latest = ""
        if evs:
            event_clause_latest = (
                f"\n  AND contextvalue.event IN ({sql_list(evs)})"
                if len(evs) > 1
                else f"\n  AND contextvalue.event = {sql_str(evs[0])}"
            )

        # Return just the most recent row (order by raw epoch)
        # print(device)
        if device in ("TemperatureSensor", "PressureSensor", "HumiditySensor"):
            # telemetry devices carry no event - return the readings instead
            return (
                f'SELECT {ts_expr()} AS ts, "timestamp", resource.device_name, '
                f"contextvalue.temperature, contextvalue.humidity, contextvalue.pressure\n"
                f"FROM {get_table_fqn()}\n"
                f"WHERE {dev_pred}\n"
                f'ORDER BY "timestamp" DESC\n'
                f"LIMIT 1;"
            )

        if device in (
            "Door Sensor",
            "LabDoorSensor",
            "LabDoorSensor_1",
            "LabDoorSensor_2",
        ):
            return (
                f'SELECT {ts_expr()} AS ts, "timestamp", resource.device_name, contextvalue.event\n'
                f"FROM {get_table_fqn()}\n"
                f"WHERE {dev_pred}{event_clause_latest}\n"
                f'ORDER BY "timestamp" DESC\n'
                f"LIMIT 1;"
            )

        return (
            f'SELECT {ts_expr()} AS ts, "timestamp", resource.device_name, contextvalue.event, contextvalue.person\n'
            f"FROM {get_table_fqn()}\n"
            f"WHERE {dev_pred}{event_clause_latest}\n"
            f'ORDER BY "timestamp" DESC\n'
            f"LIMIT 1;"
        )

    if device in ("TemperatureSensor", "PressureSensor", "HumiditySensor"):
        # telemetry devices carry no event - return the readings instead
        return (
            f'SELECT {ts_expr()} AS ts, "timestamp", resource.device_name, '
            f"contextvalue.temperature, contextvalue.humidity, contextvalue.pressure\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE {dev_pred}{th}\n"
            f'ORDER BY "timestamp" DESC\n'
            f"LIMIT {DEFAULT_ROW_LIMIT};"
        )

    if device in ("Door Sensor", "LabDoorSensor", "LabDoorSensor_1", "LabDoorSensor_2"):
        return (
            f"SELECT {ts_expr()} AS ts, resource.device_name, COALESCE(contextvalue.event,'') AS event\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE {dev_pred}{th}{event_clause}\n"
            f"ORDER BY ts;"
        )
    return (
        f"SELECT {ts_expr()} AS ts, resource.device_name, "
        f"COALESCE(contextvalue.event,'') AS event, COALESCE(contextvalue.person,'') AS person\n"
        f"FROM {get_table_fqn()}\n"
        f"WHERE {dev_pred}{th}{event_clause}\n"
        f"ORDER BY ts;"
    )


def try_strict_intruder_template(
    user: str, time_hint: Optional[Dict[str, int]]
) -> Optional[str]:
    """
    Forces intruder-only counts for Misty when the user asks for a count and mentions 'intruder'.
    Avoids any face/person expansions.
    """
    t = (user or "").lower()
    if not (
        re.search(r"\bcount\b|\bhow\s+many\b", t)
        and "intruder" in t
        and re.search(r"\bmisty\b|\bmisty\s+robot\b", t)
    ):
        return None

    th = ""
    if time_hint:
        th = (
            f'\n  AND "timestamp" >= {time_hint["start_epoch"]}'
            f'\n  AND "timestamp" <  {time_hint["end_epoch"]}'
        )
    dev_pred = devices_predicate_for("MistyRobot1")
    return (
        f"SELECT COUNT(*) AS intruder_count\n"
        f"FROM {get_table_fqn()}\n"
        f"WHERE {dev_pred}\n"
        f"  AND contextvalue.event IN ('intruder_detected','intruder'){th};"
    )


def try_temperature_template(user: str) -> Optional[str]:
    """
    'Average Temperature in the last N hour/day/week/…' → flat columns, NOW()-based window.
    """

    t = (user or "").lower().strip()
    mentions_temp = bool(re.search(r"\b(temp|temperature|thermostat)\b", t))
    avg_temp = bool(re.search(r"\b(avg|average)\b.*\btemperature\b", t))

    if mentions_temp and not avg_temp:
        # Detect whether the user wants a time-series/history of temperature
        is_history = bool(
            re.search(r"\bhistory\b", t)
            or re.search(r"\b(history|show|plot|list)\b.*\b(temp|temperature)\b", t)
            or re.search(
                r"\bover\b.*\b(\d+)\s*(hour|hours|day|days|week|weeks|month|months)\b",
                t,
            )
            or re.search(
                r"\blast\b.*\b(\d+)\s*(hour|hours|day|days|week|weeks|month|months)\b",
                t,
            )
        )
    else:
        is_history = False
    print(f"[Template] is_history={is_history}")

    # If neither history nor average is requested, skip this template
    if not (is_history or avg_temp):
        return None

    # default window
    n, unit = 1, "hour"

    # A calendar day is not the same as the previous 24 hours. Keep this
    # explicit so "average temperature yesterday" does not fall through to
    # the one-hour default window below.
    if avg_temp and re.search(r"\byesterday\b", t):
        return (
            f"SELECT AVG(contextvalue.temperature) AS avg_temperature\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'LabTHPSensor'\n"
            f"  AND contextattribute = 'thp'\n"
            f'  AND from_unixtime("timestamp") >= date_add(\'day\', -1, date_trunc(\'day\', now()))\n'
            f'  AND from_unixtime("timestamp") <  date_trunc(\'day\', now());'
        )

    m_h = re.search(r"\b(last|past)\s+(\d+)\s+hours?\b", t)
    m_d = re.search(r"\b(last|past)\s+(\d+)\s+days?\b", t)
    m_w = re.search(
        r"\b(last|past)\s+(\d+)?\s*weeks?\b", t
    )  # handles "last week" or "last 2 weeks"

    # Handle phrases like '2 weeks ago', 'from 3 days ago', etc.
    m_ago = re.search(
        r"\b(\d+)\s+(hour|hours|day|days|week|weeks|month|months)\s+ago\b",
        t,
    )
    # months (special handling to respect calendar month boundaries)
    m_last_month = re.search(r"\blast\s+month\b", t)
    m_past_month = re.search(r"\bpast\s+month\b", t)
    m_this_month = re.search(r"\bthis\s+month\b", t)
    m_this_week = re.search(r"\bthis\s+week\b", t)
    m_n_months = re.search(r"\b(last|past)\s+(\d+)\s*months?\b", t)

    # also accept "over 1 week", "for 2 days", etc.
    m_over = re.search(
        r"\b(over|for)\s+(\d+)\s*(hour|hours|day|days|week|weeks|month|months)\b", t
    )
    if m_h:
        n, unit = int(m_h.group(2)), "hour"
    elif m_d:
        n, unit = int(m_d.group(2)), "day"
    elif m_w:
        n = int(m_w.group(2)) if m_w.group(2) else 1
        unit = "week"
    elif m_ago:
        # e.g., '2 weeks ago' or '3 days ago' -> treat as past N <unit>
        n = int(m_ago.group(1))
        u = m_ago.group(2).lower()
        if u.startswith("hour"):
            unit = "hour"
        elif u.startswith("day"):
            unit = "day"
        elif u.startswith("week"):
            unit = "week"
        else:
            unit = "month"
    elif m_over:
        n = int(m_over.group(2))
        u = m_over.group(3).lower()
        if u.startswith("hour"):
            unit = "hour"
        elif u.startswith("day"):
            unit = "day"
        elif u.startswith("week"):
            unit = "week"
        else:
            unit = "month"
    elif m_last_month or m_past_month:
        # Previous full calendar month
        start_expr = "date_trunc('month', date_add('month', -1, current_timestamp))"
        end_expr = "date_trunc('month', current_timestamp)"
        return (
            f"SELECT AVG(contextvalue.temperature) AS avg_temperature\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'LabTHPSensor'\n"
            f'  AND from_unixtime("timestamp") >= {start_expr}\n'
            f'  AND from_unixtime("timestamp") <  {end_expr};'
        )
    elif m_this_month:
        # From start of current month up to now
        start_expr = "date_trunc('month', current_timestamp)"
        end_expr = "now()"
        return (
            f"SELECT AVG(contextvalue.temperature) AS avg_temperature\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'LabTHPSensor'\n"
            f'  AND from_unixtime("timestamp") >= {start_expr}\n'
            f'  AND from_unixtime("timestamp") <  {end_expr};'
        )
    elif m_this_week:
        # From start of current week up to now
        start_expr = "date_trunc('week', current_timestamp)"
        end_expr = "now()"
        return (
            f"SELECT AVG(contextvalue.temperature) AS avg_temperature\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE device_name = 'LabTHPSensor'\n"
            f'  AND from_unixtime("timestamp") >= {start_expr}\n'
            f'  AND from_unixtime("timestamp") <  {end_expr};'
        )
    elif m_n_months:
        # Last/past N months as full months window (start of month N months ago → start of current month)
        mon = int(m_n_months.group(2))
        start_expr = (
            f"date_trunc('month', date_add('month', -{mon}, current_timestamp))"
        )
        end_expr = "date_trunc('month', current_timestamp)"
        return (
            f"SELECT AVG(contextvalue.temperature) AS avg_temperature\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'LabTHPSensor'\n"
            f'  AND from_unixtime("timestamp") >= {start_expr}\n'
            f'  AND from_unixtime("timestamp") <  {end_expr};'
        )

    # Athena/Trino doesn't accept INTERVAL 'n week' for date arithmetic on from_unixtime(...),
    # so convert weeks → days
    if unit == "week":
        n = n * 7
        unit = "day"
    unit_sql = {"day": "DAY", "hour": "HOUR", "minute": "MINUTE"}[unit]

    # If the user asked for a history/time-series, return raw rows (timestamp, temperature, event)
    if is_history:
        return (
            f'SELECT "timestamp", temperature, contextvalue.event\n'
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'LabTHPSensor'\n"
            f"  AND from_unixtime(\"timestamp\") >= NOW() - INTERVAL '{n}' {unit}\n"
            f'  AND from_unixtime("timestamp") <  NOW()\n'
            f'ORDER BY "timestamp";'
        )

    # Default: return an average over the requested window
    return (
        f"SELECT AVG(contextvalue.temperature) AS avg_temperature\n"
        f"FROM {get_table_fqn()}\n"
        f"WHERE resource.device_name = 'LabTHPSensor'\n"
        f"  AND from_unixtime(\"timestamp\") >= NOW() - INTERVAL '{n}' {unit}\n"
        f'  AND from_unixtime("timestamp") <  NOW();'
    )


def try_correlation_template(
    user: str, time_hint: Optional[Dict[str, int]]
) -> Optional[str]:
    """
    Correlate ≥2 devices within a ±N window.
    DEFAULT: strict correlations (INNER JOIN + abs diff guard).
    RELAXED: LEFT JOIN (keep all base events) if user explicitly asks for unmatched/all doors, etc.
    """
    user_lower = (user or "").lower()
    t = normalize_device_aliases(user).lower()

    # --- window parsing (default ±2 minutes) ---
    window_val, window_unit = None, "minute"
    for p in [
        r"\+/-\s*(\d+)\s*(sec|secs|second|seconds|min|mins|minute|minutes)\b",
        r"\bwithin\s+(\d+)\s*(sec|secs|second|seconds|min|mins|minute|minutes)\b",
        r"\b(\d+)\s*(m|min|mins|minute|minutes|s|sec|secs|second|seconds)\b",
    ]:
        m = re.search(p, t)
        if m:
            window_val = int(m.group(1))
            u = (m.group(2) if len(m.groups()) >= 2 else "min").lower()
            window_unit = "second" if u.startswith(("s", "sec")) else "minute"
            break
    if window_val is None:
        window_val = 2
    window = f"INTERVAL '{abs(window_val)}' {window_unit}"
    window_sec = _window_seconds(
        abs(window_val), "second" if window_unit == "second" else "minute"
    )

    # --- relaxed mode trigger (otherwise strict by default) ---
    relaxed = bool(
        re.search(
            r"\b(all|every|including unmatched|include unmatched|show unmatched|left join)\b",
            t,
        )
    )

    # --- detect devices (need ≥2) ---
    mentioned_raw: List[tuple[str, Optional[str]]] = []
    for canon, aliases in DEVICE_ALIASES.items():
        alias_match = None
        for alias in sorted(aliases, key=len, reverse=True):
            alias_low = alias.lower()
            if re.search(rf"\b{re.escape(alias_low)}\b", user_lower):
                alias_match = alias_low
                break
        if alias_match:
            mentioned_raw.append((canon, alias_match))
            continue
        if re.search(rf"\b{re.escape(canon.lower())}\b", t):
            mentioned_raw.append((canon, None))

    dedup: Dict[str, Optional[str]] = {}
    for canon, alias_hint in mentioned_raw:
        if canon not in dedup:
            dedup[canon] = alias_hint

    mentioned: List[tuple[str, Optional[str]]] = [(c, dedup[c]) for c in dedup]
    if len(mentioned) < 2:
        return None

    # --- alias mapping ---
    def alias_for(dev: str) -> str:
        return {
            "LabDoorSensor": "door",
            "LabSmokeSensor": "smoke",
            "LabCamera": "camera",
            "MistyRobot1": "misty",
        }.get(dev, re.sub(r"[^a-z]", "", dev.lower()))

    # --- time hint clause (replicated into each CTE) ---
    th = ""
    if time_hint:
        th = (
            f'\n    AND "timestamp" >= {time_hint["start_epoch"]}'
            f'\n    AND "timestamp" <  {time_hint["end_epoch"]}'
        )

    # --- build each CTE as a closed block ---
    cte_blocks: List[str] = []
    aliases_in_order: List[str] = []

    for dev, alias_hint in mentioned:
        a = alias_for(dev)
        aliases_in_order.append(a)

        # Event inference
        evs = infer_device_events(user, dev) or []
        # If prompt mentions faces, ensure Misty face variants are included
        if dev == "MistyRobot1" and ("face" in t or "faces" in t):
            for extra in ("face_detected", "familiar_face", "familiar_face_detected"):
                if extra not in evs:
                    evs.append(extra)

        evt_clause = ""
        if evs:
            if len(evs) == 1:
                evt_clause = f"\n    AND contextvalue.event = {sql_str(evs[0])}"
            else:
                evt_clause = "\n    AND contextvalue.event IN (" + sql_list(evs) + ")"

        cte_blocks.append(
            "  {a} AS (\n"
            "    SELECT {ts} AS ts, *\n"
            "    FROM {fqn}\n"
            "    WHERE {dev_pred}{th}{evt}\n"
            "  )".format(
                a=a,
                ts=ts_expr(),
                fqn=get_table_fqn(),
                dev_pred=devices_predicate_for(dev, alias_hint),
                th=th,
                evt=evt_clause,
            )
        )

    # --- choose base (prefer door if present) ---
    base = "door" if "door" in aliases_in_order else aliases_in_order[0]
    others = [x for x in aliases_in_order if x != base]

    # --- assemble final SQL ---
    select_cols = [f"{base}.ts AS {base}_time"] + [
        f"{x}.ts AS {x}_time" for x in others
    ]
    sql = "WITH\n" + ",\n".join(cte_blocks) + "\n"
    sql += "SELECT " + ", ".join(select_cols) + f"\nFROM {base}\n"

    join_kw = "LEFT JOIN" if relaxed else "JOIN"
    for x in others:
        sql += f"{join_kw} {x} ON {base}.ts BETWEEN {x}.ts - {window} AND {x}.ts + {window}\n"

    # In strict (default) mode, enforce absolute diff guard to prevent >window slips
    if not relaxed:
        guards = [
            f"abs(date_diff('second', {base}.ts, {x}.ts)) <= {window_sec}"
            for x in others
        ]
        sql += "WHERE " + " AND ".join(guards) + "\n"

    sql += f"ORDER BY {base}_time"
    return sql


# ---------- LLM path + wrappers ----------
def prettify_sql_reply(
    title: str, explanation: str, sql: str, suggestions: List[str]
) -> str:
    body = "\n".join(
        [
            f"• Target table: {get_table_fqn()}",
            "• Flat columns (timestamp, event, person, device_name/device_id).",
            '• Epoch predicates on "timestamp" for tz safety.',
        ]
    )
    out = dedent(f"""{title}
{explanation}

{body}

SQL:
{sql}
""").strip()
    if suggestions:
        out += "\n\nTry next:\n- " + "\n- ".join(suggestions[:3])
    return out


def build_messages_llm(user_query: str, time_hint: Optional[Dict[str, int]]):
    return build_messages(user_query, time_hint)


# ---------- Special-case Templates ----------
def try_special_templates(user: str) -> Optional[str]:
    """
    Handle special NL queries that map 1:1 to canonical example SQL patterns.
    These take precedence over correlation/single-device templates.
    """
    t = user.lower().strip()

    # --- Misty overview ---
    if re.search(
        r"\boverview\b.*\b(misty|misty robot|misty robot 1)\b", t
    ) or re.search(r"\bgive me an overview of\b.*\bmisty\b", t):
        return (
            f"SELECT *\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name IN ('Misty Robot 1','MistyRobot1');"
        )

    # --- How many door events on <date> ---
    m = re.search(r"how\s+many\s+door\s+events(?:\s+on)?\s+(.+)$", t)
    if m:
        time_range = parse_time_range(m.group(1))
        if time_range:
            return (
                f"SELECT COUNT(*) AS door_events\n"
                f"FROM {get_table_fqn()}\n"
                f"WHERE contextattribute = 'door'\n"
                f"  AND \"timestamp\" >= {time_range['start_epoch']}\n"
                f"  AND \"timestamp\" <  {time_range['end_epoch']};"
            )

    # --- Who was the last person to enter the room? ---
    if re.search(r"who\s+was\s+the\s+last\s+person\s+to\s+enter\s+the\s+room\??", t):
        return (
            f'SELECT "timestamp", resource.device_id, resource.device_name, contextvalue.event, contextvalue.person, contextvalue.yaw, contextvalue.pitch, contextvalue.distance\n'
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name IN ('Misty Robot 1','MistyRobot1')\n"
            f"  AND contextvalue.event = 'familiar_face_detected'\n"
            f'ORDER BY "timestamp" DESC\n'
            f"LIMIT 1;"
        )

    # --- Latest sensor activity (global) ---
    if re.search(r"\b(latest|recent)\b.*\b(sensor|activity|events?)\b", t) or re.search(
        r"\bshow me the latest sensor activity\b", t
    ):
        return (
            f'SELECT "timestamp", resource.device_id, resource.device_name, '
            f"contextattribute, contextvalue.event, storage_location\n"
            f"FROM {get_table_fqn()}\n"
            f'ORDER BY "timestamp" DESC\n'
            f"LIMIT 10;"
        )

    # --- Last fire/smoke alarm ---
    if re.search(r"last\s+(fire|smoke)\s+alarm", t) or re.search(
        r"when\s+was\s+the\s+last\s+(fire|smoke)\s+alarm\??", t
    ):
        return (
            f"SELECT *\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE {devices_predicate_for('LabSmokeSensor')}\n"
            f"  AND COALESCE(event,'') <> ''\n"
            f'ORDER BY "timestamp" DESC\n'
            f"LIMIT 1;"
        )

    # --- List all devices that had any event on <date> ---
    m = re.search(r"list\s+all\s+devices.*\bon\s+(.+)$", t)
    if m:
        dt = dateparser.parse(m.group(1), settings={"PREFER_DATES_FROM": "past"})
        if dt:
            s = f"{dt:%Y-%m-%d} 00:00:00"
            e = f"{(dt + timedelta(days=1)):%Y-%m-%d} 00:00:00"
            return (
                f"SELECT DISTINCT resource.device_name\n"
                f"FROM {get_table_fqn()}\n"
                f"WHERE from_unixtime(\"timestamp\") >= TIMESTAMP '{s}'\n"
                f"  AND from_unixtime(\"timestamp\") <  TIMESTAMP '{e}';"
            )

    # --- Average temperature today ---
    if re.search(r"(show|what).*average\s+temperature\s+today", t) or re.search(
        r"\baverage\s+temperature\s+today\b", t
    ):
        return (
            f"SELECT AVG(contextvalue.temperature) AS avg_temperature_today\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE contextattribute = 'thp'\n"
            f"  AND contextvalue.temperature IS NOT NULL\n"
            f"  AND from_unixtime(\"timestamp\") >= date_trunc('day', now())\n"
            f'  AND from_unixtime("timestamp") <  now();'
        )

    # --- Unauthorised entry today (assume now) ---
    if re.search(r"\b(unauthori[sz]ed|intruder).*(today|now)\b", t) or re.search(
        r"was there an unauthori[sz]ed entry.*today", t
    ):
        return (
            f'SELECT "timestamp", resource.device_id, resource.device_name, contextvalue.event, contextvalue.person, contextvalue.yaw, contextvalue.pitch, contextvalue.distance\n'
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name IN ('Misty Robot 1','MistyRobot1')\n"
            f"  AND contextvalue.event = 'intruder_detected'\n"
            f"  AND from_unixtime(\"timestamp\") >= date_trunc('day', now())\n"
            f'  AND from_unixtime("timestamp") <  now();'
        )

    # --- Fall in the last hour ---
    if re.search(r"\b(fall|fallen)\b.*\b(last|past)\s+1\s+hour\b", t) or re.search(
        r"\bdid someone fall in the last hour\??", t
    ):
        return (
            f"SELECT *\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'Fall Sensor'\n"
            f"  AND from_unixtime(\"timestamp\") >= (now() - interval '1' hour)\n"
            f'  AND from_unixtime("timestamp") <  now();'
        )

    # Overview of a specific device (e.g., Misty Robot 1)
    if re.search(r"\boverview\b.*misty", t) or re.search(
        r"give me an overview of\b", t
    ):
        return (
            f"SELECT *\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'Misty Robot 1';"
        )

    # Latest sensor activity (global)
    m = re.search(
        r"\blatest\s+(sensor\s+)?(activity|events|readings)(?:\s+(\d+))?\b", t
    )
    if m:
        limit = int(m.group(3)) if m and m.group(3) else 10
        return (
            f"SELECT *\n"
            f"FROM {get_table_fqn()}\n"
            f'ORDER BY "timestamp" DESC\n'
            f"LIMIT {limit};"
        )

    # How many door events on a given day
    m = re.search(r"how many door events on (\w+ \d{1,2}, \d{4})", t)
    if m:
        day = dateparser.parse(m.group(1))
        s = f"{day.strftime('%Y-%m-%d')} 00:00:00"
        e = f"{day.strftime('%Y-%m-%d')} 23:59:59"
        return (
            f"SELECT COUNT(*)\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE {devices_predicate_for('LabDoorSensor')}\n"
            f"AND from_unixtime(\"timestamp\") >= TIMESTAMP '{s}'\n"
            f"AND from_unixtime(\"timestamp\") < TIMESTAMP '{e}';"
        )

    # Last person to enter the room
    if re.search(r"last person.*enter.*room", t):
        return (
            f'SELECT "timestamp", resource.device_id, resource.device_name, contextvalue.event, contextvalue.person, contextvalue.yaw, contextvalue.pitch, contextvalue.distance\n'
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'Misty Robot 1'\n"
            f"  AND contextvalue.event = 'familiar_face_detected'\n"
            f'ORDER BY "timestamp" DESC\n'
            f"LIMIT 1;"
        )

    # Last smoke/fire alarm
    if re.search(r"last (fire|smoke).*alarm", t):
        return (
            f"SELECT *\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE {devices_predicate_for('LabSmokeSensor')};"
        )

    # List all devices that had events on a specific day
    m = re.search(r"all devices.*on (\w+ \d{1,2}, \d{4})", t)
    if m:
        day = dateparser.parse(m.group(1))
        s = f"{day.strftime('%Y-%m-%d')} 00:00:00"
        e = f"{day.strftime('%Y-%m-%d')} 23:59:59"
        return (
            f"SELECT resource.device_name\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE from_unixtime(\"timestamp\") >= TIMESTAMP '{s}'\n"
            f"AND from_unixtime(\"timestamp\") < TIMESTAMP '{e}';"
        )

    # Average temperature today
    if "average temperature today" in t:
        return (
            f"SELECT AVG(contextvalue.temperature) AS avg_temperature_today\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'LabTHPSensor'\n"
            f"  AND from_unixtime(\"timestamp\") >= date_trunc('day', now())\n"
            f'  AND from_unixtime("timestamp") < now();'
        )

    # Unauthorised entry today
    if re.search(r"unauthorised entry.*today", t):
        return (
            f'SELECT "timestamp", resource.device_id, resource.device_name, contextvalue.event, contextvalue.person, contextvalue.yaw, contextvalue.pitch, contextvalue.distance\n'
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'Misty Robot 1'\n"
            f"  AND contextvalue.event = 'intruder_detected'\n"
            f"  AND from_unixtime(\"timestamp\") >= date_trunc('day', now())\n"
            f'  AND from_unixtime("timestamp") < now();'
        )

    # Fall detection in the last hour
    if re.search(r"fall.*last hour", t):
        return (
            f"SELECT *\n"
            f"FROM {get_table_fqn()}\n"
            f"WHERE resource.device_name = 'Fall Sensor'\n"
            f"  AND from_unixtime(\"timestamp\") >= (now() - interval '1' hour)\n"
            f'  AND from_unixtime("timestamp") < now();'
        )

    # Summary of all events for a month (e.g., "summary of all events in October 2025")
    if re.search(r"\b(summary|overview)\b.*\ball events\b", t) or re.search(
        r"\bgive me a summary\b.*\b(in|for)\b", t
    ):
        tr = parse_time_range(user)
        if tr:
            s, e = tr["start_epoch"], tr["end_epoch"]
            return (
                f"SELECT resource.device_name, event, COUNT(*) AS event_count\n"
                f"FROM {get_table_fqn()}\n"
                f'WHERE "timestamp" >= {s}\n'
                f'  AND "timestamp" <  {e}\n'
                f"GROUP BY resource.device_name, event"
            )

    return None


def try_overview_all_template(user: str) -> Optional[str]:
    """
    NL shortcuts that mean 'SELECT * FROM table' for a quick overview.
    Triggers on: 'overview' (alone), 'table overview', 'overview of all', etc.
    NOTE: This intentionally avoids time filters to act as a true full-table dump.
    """
    t = (user or "").lower().strip()

    # If user already specified a device (e.g., "overview misty"), let existing
    # try_special_templates handle it; this one is for global overview only.
    mentions_device = any(
        re.search(rf"\b{re.escape(a)}\b", t)
        for canon, aliases in DEVICE_ALIASES.items()
        for a in ([canon] + aliases)
    )
    if mentions_device:
        return None

    # Fire for simple overview intents
    triggers = [
        r"^\s*overview\s*$",
        r"\boverview of all\b",
        r"\btable overview\b",
        r"\boverview data\b",
        r"\boverview everything\b",
        r"\bshow overview\b",
    ]
    if any(re.search(p, t) for p in triggers):
        return f"SELECT * FROM {get_table_fqn()};"
    return None


def try_generic_fallback(user: str, time_hint: Optional[Dict[str, int]]) -> str:
    """Answer anything the hand-written templates did not recognise.

    The original app sent these to a local LLM and failed outright when none
    was running. Q-PRIME ships without a model, so the last resort is
    deterministic instead: read whatever intent *is* present - a device, a
    time window, a counting or listing verb - and build a query from it.
    Worst case that is "the most recent records", which is a defensible
    answer to an open question and lets the summariser describe the data.
    """
    t = normalize_device_aliases(user or "").lower()
    raw = (user or "").lower()

    where = []

    # device, if one was named
    for canon, aliases in DEVICE_ALIASES.items():
        if re.search(rf"\b{re.escape(canon.lower())}\b", t) or any(
            re.search(rf"\b{re.escape(a.lower())}\b", raw) for a in aliases
        ):
            where.append(devices_predicate_for(canon))
            break

    # time window, if one was expressed
    if time_hint:
        where.append(f'"timestamp" >= {time_hint["start_epoch"]}')
        where.append(f'"timestamp" <  {time_hint["end_epoch"]}')

    clause = ("\nWHERE " + "\n  AND ".join(where)) if where else ""

    wants_count = bool(re.search(r"\b(count|how\s+many|number\s+of|total)\b", raw))
    wants_devices = bool(
        re.search(r"\b(device|devices|sensor|sensors)\b", raw)
        and re.search(r"\b(list|which|what|show|all|active|reporting)\b", raw)
    )

    if wants_devices:
        return (
            f"SELECT resource.device_name, COUNT(*) AS events\n"
            f"FROM {get_table_fqn()}{clause}\n"
            f"GROUP BY resource.device_name\n"
            f"ORDER BY events DESC;"
        )

    if wants_count:
        return f"SELECT COUNT(*) AS n\nFROM {get_table_fqn()}{clause};"

    return (
        f'SELECT {ts_expr()} AS ts, "timestamp", resource.device_name, '
        f"contextvalue.event, contextvalue.person\n"
        f"FROM {get_table_fqn()}{clause}\n"
        f'ORDER BY "timestamp" DESC\n'
        f"LIMIT {DEFAULT_ROW_LIMIT};"
    )


import shlex, subprocess


def main():
    print(BANNER)
    while True:
        try:
            user = input("Ask me: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user:
            print(
                "Try: door openings yesterday | smoke alarms in July | faces seen by Misty last 48 hours\n"
            )
            continue
        if user.lower() in {"exit", "quit", "q"}:
            print("Bye!")
            break

        # Multi-line SQL capture (unchanged) ...
        if user.lower().startswith(("select", "with")) and not user.strip().endswith(
            ";"
        ):
            lines = [user]
            while True:
                more = input().rstrip()
                lines.append(more)
                if more.strip().endswith(";"):
                    break
            user = "\n".join(lines)

        try:
            sql_out = generate_sql(user)  # returns str now
            print(sql_out)  # print ONLY the SQL
            print()
        except Exception as e:
            print(f"[Error] {e}\n")


# ---- Programmatic API --------------------------------------------------------
def generate_sql(user_query: str, is_cloud=None) -> str:
    """
    Generate SQL from natural language query.

    Args:
        user_query: Natural language query string
        is_cloud: optional tier filter (True cloud-only / False edge-only);
                  anything else - including the default - spans the continuum

    Returns:
        Generated SQL query string (always against the continuum table)
    """
    set_cloud_context(is_cloud)
    qtext = (user_query or "").strip()

    # --- RAW SQL passthrough ---
    if qtext.lower().startswith(("select", "with")):
        raw_sql = qtext if qtext.endswith(";") else (qtext + ";")
        print("[Info] Detected raw SQL input; validating...")
        print(raw_sql)
        err = validate_sql(raw_sql)
        print(f"[Info] Validation result: {err or 'OK'}")
        if err:
            raise RuntimeError(f"Unsafe/invalid SQL: {err}")
        return raw_sql

    # --- NL → time hint (no stale fallback unless query has no time words) ---
    HAS_TIME_WORDS = bool(
        re.search(
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
            r"january|february|march|april|may|june|july|august|september|october|november|december|"
            r"today|yesterday|last|past|between|from|to|until|since|"
            r"\d{4}-\d{1,2}-\d{1,2})\b",
            qtext,
            re.I,
        )
    )

    time_hint_local = parse_time_range(qtext)
    if not time_hint_local and not HAS_TIME_WORDS:
        # only reuse an old hint when this query has no time words at all
        time_hint_local = CONTEXT.get("time_hint")
    else:
        CONTEXT["time_hint"] = time_hint_local

    # --- SPECIAL (incl. temperature) → correlation → single-device ---
    sql = try_strict_intruder_template(qtext, time_hint_local)
    if not sql:
        sql = try_overview_all_template(qtext)
    if not sql:
        sql = try_special_templates(qtext)
    if not sql:
        sql = try_temperature_template(qtext)
    if not sql:
        sql = try_correlation_template(qtext, time_hint_local)
    if not sql:
        sql = try_single_device_template(qtext, time_hint_local)
    if sql:
        if not sql.strip().endswith(";"):
            sql = sql.strip() + ";"
        err = validate_sql(sql)
        if err:
            raise RuntimeError(f"Unsafe/invalid SQL: {err}")
        return sql

    # --- Optional LLM pass: accept ONLY {"sql": "..."} ---
    # Off by default. Q-PRIME ships without a model, so a question that no
    # template recognised must still be answered - the deterministic
    # fallback below does that, and the model only ever gets a chance to do
    # better first.
    if USE_LLM_SQL:
        sql2 = _generate_sql_with_llm(qtext, time_hint_local)
        if sql2:
            return sql2
        print("[Info] LLM unavailable or unusable; using the rule-based fallback")

    sql = try_generic_fallback(qtext, time_hint_local)
    if not sql.strip().endswith(";"):
        sql = sql.strip() + ";"
    err = validate_sql(sql)
    if err:
        raise RuntimeError(f"Unsafe/invalid SQL: {err}")
    return sql


def _generate_sql_with_llm(qtext: str, time_hint_local) -> Optional[str]:
    """Ask the local model for SQL. Returns None if it cannot deliver."""
    msgs = build_messages_llm(qtext, time_hint_local)
    raw = call_ollama(msgs)
    if raw is None:
        return None

    obj = try_json(raw)
    attempts = 0
    while extract_sql_only(obj) is None and attempts < 2:
        attempts += 1
        msgs.append({"role": "assistant", "content": raw})
        msgs.append(
            {
                "role": "user",
                "content": "Return ONLY valid minified JSON with key: sql (string). No other text.",
            }
        )
        raw = call_ollama(msgs)
        if raw is None:
            break
        obj = try_json(raw)
    sql2 = extract_sql_only(obj)
    if sql2 is None:
        return None

    # Post-process + validate
    sql2 = re.sub(r"\bFROM\b\s+\S+\.\S+", f"FROM {get_table_fqn()}", sql2, flags=re.I)
    sql2 = sanitize_sql_for_null_event_devices(sql2)
    sql2 = fix_between_epoch_mismatch(sql2)
    sql2 = drop_redundant_time_filters(sql2)
    sql2 = patch_time_hint(sql2, time_hint_local)
    if not sql2.endswith(";"):
        sql2 += ";"
    if validate_sql(sql2):
        return None  # unusable - fall back to the deterministic generator
    return sql2


# ---------- CLI runner (optional) ----------
BANNER = f"""
────────────────────────────────────────────────────────────────
 NL → Q-PRIME query SQL (flat schema)  (model: {MODEL})
 Dataset: {get_table_fqn()}   Local TZ: {LOCAL_TZ_NAME}   Epoch scale: {EPOCH_SCALE}
 Type a query (e.g., "latest misty", "faces near door within 2m last week").  'exit' to quit.
────────────────────────────────────────────────────────────────
"""


def main():
    print(BANNER)
    while True:
        try:
            user = input("Ask me: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user:
            print(
                "Try: door openings yesterday | smoke alarms in July | faces seen by Misty last 48 hours\n"
            )
            continue
        if user.lower() in {"exit", "quit", "q"}:
            print("Bye!")
            break

        # Multi-line SQL capture
        if user.lower().startswith(("select", "with")) and not user.strip().endswith(
            ";"
        ):
            lines = [user]
            while True:
                more = input().rstrip()
                lines.append(more)
                if more.strip().endswith(";"):
                    break
            user = "\n".join(lines)

        try:
            sql_out = generate_sql(user)  # returns str now
            print(sql_out)  # print ONLY the SQL
            print()
        except Exception as e:
            print(f"[Error] {e}\n")


if __name__ == "__main__":
    main()
