from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import Any


def clean_number(x: Any):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return float(x)
    except Exception:
        return None


def fmt_number(x, digits=2):
    x = clean_number(x)
    if x is None:
        return "N/A"
    ax = abs(x)
    if ax >= 1e12:
        return f"{x/1e12:.{digits}f}T"
    if ax >= 1e9:
        return f"{x/1e9:.{digits}f}B"
    if ax >= 1e6:
        return f"{x/1e6:.{digits}f}M"
    if ax >= 1e3:
        return f"{x/1e3:.{digits}f}K"
    return f"{x:.{digits}f}"


def pct(x, digits=1):
    x = clean_number(x)
    return "N/A" if x is None else f"{x*100:.{digits}f}%"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def first_not_none(*values):
    for v in values:
        if v is not None:
            return v
    return None
