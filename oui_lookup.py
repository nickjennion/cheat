"""Offline MAC OUI manufacturer lookup backed by the OUI Master Database."""

import csv
import gzip
import os
import re
from pathlib import Path


DEFAULT_DATABASE = Path(__file__).with_name("data") / "oui-master.tsv.gz"
_CACHE: dict[str, str] | None = None


def _database_path() -> Path:
    configured = os.environ.get("CHEAT_OUI_DATABASE")
    return Path(configured).expanduser() if configured else DEFAULT_DATABASE


def _load_database() -> dict[str, str]:
    path = _database_path()
    if not path.is_file():
        return {}
    result = {}
    try:
        opener = gzip.open if path.suffix.lower() == ".gz" else open
        with opener(path, "rt", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                oui = re.sub(r"[^0-9A-Fa-f]", "", row.get("OUI", ""))[:6].upper()
                manufacturer = (row.get("Manufacturer") or "").strip()
                if oui and manufacturer:
                    result.setdefault(oui, manufacturer)
    except (OSError, UnicodeError, csv.Error):
        return {}
    return result


def lookup_manufacturer(mac: str) -> str:
    """Return the manufacturer for a MAC address, or ``Unknown``."""
    global _CACHE
    hexadecimal = re.sub(r"[^0-9A-Fa-f]", "", str(mac or ""))
    if len(hexadecimal) < 6:
        return "Unknown"
    if _CACHE is None:
        _CACHE = _load_database()
    return _CACHE.get(hexadecimal[:6].upper(), "Unknown")


def clear_cache() -> None:
    """Clear the in-process database cache (useful for tests/config changes)."""
    global _CACHE
    _CACHE = None
