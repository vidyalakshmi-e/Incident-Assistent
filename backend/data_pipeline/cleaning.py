"""Step 5: repair known corruption and normalize placeholders.

Every transformation here is traceable to real source values. Nothing is invented.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ placeholders
# Explicit, documented replacement values (never silently dropped).
NOT_SET = "Not Set"          # source used "NS" / "NA" / empty for an unset ITIL field
NOT_AVAILABLE = "Not Available"  # source used "#N/B" (Dutch: niet beschikbaar)
MULTIPLE = "Multiple"        # source used "#MULTIVALUE"
UNKNOWN = "Unknown"

PLACEHOLDER_MAP = {
    "NS": NOT_SET, "NA": NOT_SET, "N/A": NOT_SET, "": NOT_SET,
    "#N/B": NOT_AVAILABLE, "#MULTIVALUE": MULTIPLE,
}

# Closure codes that are in Dutch in the source. Translated, and the original value is kept.
CLOSURE_TRANSLATIONS = {"Overig": "Other", "Kwaliteit van de output": "Output quality"}

# ------------------------------------------------------------------ timestamps


def parse_dayfirst(series: pd.Series) -> pd.Series:
    """Parse the mixed `d/m/yyyy HH:MM` and `dd-mm-yyyy HH:MM` strings.

    Profiling showed that slash-dates always have day<=12 and dash-dates always have day>=13,
    i.e. both are day-first. Parsing each shape with an explicit format avoids pandas guessing
    month-first for ambiguous slash dates.
    """
    s = series.astype("string")
    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    slash = s.str.contains("/", na=False)
    dash = s.str.contains("-", na=False)
    out[slash] = pd.to_datetime(s[slash], format="%d/%m/%Y %H:%M", errors="coerce")
    out[dash] = pd.to_datetime(s[dash], format="%d-%m-%Y %H:%M", errors="coerce")
    return out


# ------------------------------------------------------------------ handle time
_DECIMAL_COMMA = re.compile(r"^\d+,\d+$")
_GROUPED = re.compile(r"^\d{1,3}(,\d{2,3}){2,}$")


def classify_handle_time(raw: object) -> str:
    """Classify the corrupted Handle_Time_hrs strings (the column is not used for durations)."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return "missing"
    s = str(raw).strip()
    if _GROUPED.match(s):
        return "corrupted_digit_grouping"  # e.g. "3,87,16,91,111" (Indian-style grouping)
    if _DECIMAL_COMMA.match(s):
        return "decimal_comma"  # e.g. "0,862777778"
    return "unparseable"


def parse_decimal_comma(raw: object) -> float | None:
    s = str(raw).strip()
    if _DECIMAL_COMMA.match(s):
        return float(s.replace(",", "."))
    return None


# ------------------------------------------------------------------ ITIL fields


def normalize_itil_level(value: object) -> str:
    """Impact / Urgency / Priority → '1'..'5' or 'Not Set'. '5 - Very Low' → '5'."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return NOT_SET
    s = str(value).strip()
    if s in PLACEHOLDER_MAP:
        return PLACEHOLDER_MAP[s]
    m = re.match(r"^(\d)(\.0)?(\s*-.*)?$", s)
    return m.group(1) if m else NOT_SET


def normalize_placeholder(value: object) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip()
    return PLACEHOLDER_MAP.get(s, s)


# ------------------------------------------------------------------ derived rules
# Documented rule: ITIL Impact level → affected scope. Heuristic, marked "derived".
# Impact 4 and 5 are the dataset's default levels (84% of rows), so they map to cautious labels.
IMPACT_SCOPE = {
    "1": "organization-wide", "2": "department", "3": "team",
    "4": "limited (few users)", "5": "minimal (single user)",
}
# Documented rule: Priority → severity label (derived).
PRIORITY_SEVERITY = {"1": "critical", "2": "high", "3": "medium", "4": "low", "5": "planning"}


def closure_class(code: str | None) -> str:
    """Group closure codes into resolution classes used for strategy/outcome statistics."""
    if not code:
        return UNKNOWN
    c = code.lower()
    if c in {"software"}:
        return "software_fix"
    if c in {"hardware"}:
        return "hardware_fix"
    if c in {"data"}:
        return "data_fix"
    if c in {"user error", "operator error", "user manual not used"}:
        return "user_or_operator"
    if c in {"no error - works as designed"}:
        return "no_fault_found"
    if c in {"inquiry", "questions", "referred"}:
        return "information_or_referral"
    if c in {"other", "unknown", "output quality"}:
        return "unspecified"
    return "unspecified"
