"""
Unified time parsing utilities for CHEAT UNPLUGGED.

Provides a single function to parse duration strings in multiple formats
into fractional days for use across the application.
"""

from typing import Optional
import re


def parse_duration_days(value: str) -> Optional[float]:
    """Parse a duration string into fractional days.

    Handles colon format ("00:00:13", "01:30:00"),
    prose format ("45 weeks, 3 days, 2 hours"),
    and compact format ("2d3h", "5w", "222h").
    Returns None for empty/"never" or unparseable input.

    Unit weights:
      - week → × 7
      - day → × 1
      - hour → × 1/24
      - minute → × 1/(24×60)
      - second → × 1/(24×3600)
    """
    if not value or not str(value).strip():
        return None

    s = str(value).strip()

    # Check for "never" (case-insensitive)
    if s.lower() == "never":
        return None

    total = 0.0

    # Try HH:MM:SS / MM:SS colon format first
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 3:  # HH:MM:SS
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                total = (hours + minutes / 60 + seconds / 3600) / 24
                return total if total > 0 else None
            elif len(parts) == 2:  # MM:SS
                minutes = int(parts[0])
                seconds = int(parts[1])
                total = (minutes / 60 + seconds / 3600) / 24
                return total if total > 0 else None
        except (ValueError, IndexError):
            pass  # Fall through to regex-based parsing

    # Try prose format first: r'(\d+)\s*(week|day|hour|minute|second)'
    # Regex matches "week" within "weeks", so plurals are handled automatically
    prose_matches = re.findall(r'(\d+)\s*(week|day|hour|minute|second)', s, re.I)
    if prose_matches:
        for val, unit in prose_matches:
            v = int(val)
            unit_lower = unit.lower()
            if "week" in unit_lower:
                total += v * 7
            elif "day" in unit_lower:
                total += v
            elif "hour" in unit_lower:
                total += v / 24
            elif "minute" in unit_lower:
                total += v / (24 * 60)
            elif "second" in unit_lower:
                total += v / (24 * 3600)
        return total if total > 0 else None

    # Try compact format: r'(\d+)\s*([a-z]+)'
    # First letter of unit determines the multiplier (w/d/h/m/s)
    compact_matches = re.findall(r'(\d+)\s*([a-z]+)', s, re.I)
    if compact_matches:
        for val, unit in compact_matches:
            v = int(val)
            unit_lower = unit.lower()
            if unit_lower.startswith("w"):
                total += v * 7
            elif unit_lower.startswith("d"):
                total += v
            elif unit_lower.startswith("h"):
                total += v / 24
            elif unit_lower.startswith("m"):
                total += v / (24 * 60)
            elif unit_lower.startswith("s"):
                total += v / (24 * 3600)
        return total if total > 0 else None

    return None
