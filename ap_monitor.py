"""
Access Point — Monitor Physical Movements.

Filter/select Unified APs, then display a live-refreshed table comparing
previous upstream (Assurance events, 24h) vs current upstream (physical topology).
"""

from typing import Optional

# Sentinel display strings
_NO_CHANGE = "N/A — No Change"
_OFFLINE   = "— (offline)"
_NO_DATA   = "— (no data)"
_ERROR     = "— (error)"

_SENTINELS = (_OFFLINE, _ERROR, _NO_DATA, _NO_CHANGE)


# ============================================================================
# Data Layer
# ============================================================================

def build_table_rows(
    selected_aps: list[dict],
    topology: dict[str, Optional[str]],
    events: dict[str, Optional[str]],
    topology_error: bool = False,
    events_error: bool = False,
) -> list[dict]:
    """Build display rows from AP dicts and upstream lookup dicts.

    Each row: {"hostname": str, "uptime": str, "previous": str, "current": str}
    """
    rows = []
    for ap in selected_aps:
        ap_id = ap.get("id", "")
        hostname = str(ap.get("hostname") or "unknown")
        uptime = str(ap.get("upTime") or "—")

        if topology_error:
            current = _ERROR
        else:
            val = topology.get(ap_id)
            current = val if val is not None else _OFFLINE

        if events_error:
            previous = _ERROR
        else:
            val = events.get(ap_id)
            previous = val if val is not None else _NO_DATA

        # No change: both valid, same value
        if (current not in _SENTINELS
                and previous not in _SENTINELS
                and current == previous):
            current = _NO_CHANGE
            previous = _NO_CHANGE

        rows.append({
            "hostname": hostname,
            "uptime": uptime,
            "previous": previous,
            "current": current,
        })
    return rows


def _ap_matches(ap: dict, filter_terms: list[str], exclude_terms: list[str]) -> bool:
    """Return True if AP matches all include terms and no exclude terms.

    '|' within a term = OR alternatives. Matches hostname and platformId.
    """
    text = (
        (ap.get("hostname") or "") + " " + (ap.get("platformId") or "")
    ).lower()
    for term in filter_terms:
        alts = [a.strip() for a in term.split("|") if a.strip()]
        if not any(a in text for a in alts):
            return False
    for term in exclude_terms:
        alts = [a.strip() for a in term.split("|") if a.strip()]
        if any(a in text for a in alts):
            return False
    return True


def _filter_label(filter_terms: list[str], exclude_terms: list[str]) -> str:
    """Return a human-readable summary of the active filter."""
    parts = []
    if filter_terms:
        parts.append("  AND  ".join(f"[{t}]" for t in filter_terms))
    if exclude_terms:
        parts.append("NOT " + "  NOT ".join(f"[{t}]" for t in exclude_terms))
    return "  ".join(parts) if parts else "(none)"


def _parse_numbers(entry: str, max_idx: int) -> list[int]:
    """Parse a comma-separated list of numbers and ranges into a sorted list.

    Numbers outside [1, max_idx] are silently dropped.
    Example: "1,3-5,7" with max_idx=6 → [1, 3, 4, 5]
    """
    result = set()
    for part in entry.split(","):
        part = part.strip()
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                result.update(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            result.add(int(part))
    return sorted(i for i in result if 1 <= i <= max_idx)
