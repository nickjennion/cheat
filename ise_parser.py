"""
Pure parsing of ISE endpoint resources into report records.

The ciscoisesdk returns endpoint resources as AttrDict-like objects carrying
id, name, description, mac, profileId, groupId, portalUser and the static
assignment booleans. This module normalises them into a flat dataclass the
Excel/CSV writers can consume — no IO, no SDK import.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class IseEndpoint:
    name: str = ""
    mac: str = ""
    description: str = ""
    profile_id: str = ""
    group_id: str = ""
    group_name: str = ""
    portal_user: str = ""
    static_group: str = ""
    static_profile: str = ""
    id: str = ""


def _as_str(value) -> str:
    return "" if value is None else str(value)


def _as_bool_flag(value) -> str:
    """'yes'/'no' for the static-assignment booleans; '' when absent."""
    if value is None:
        return ""
    return "yes" if str(value).lower() == "true" else "no"


def parse_endpoint(resource) -> IseEndpoint:
    """Normalise one SDK endpoint resource into an IseEndpoint record."""
    return IseEndpoint(
        name=_as_str(getattr(resource, "name", "")),
        mac=_as_str(getattr(resource, "mac", "")),
        description=_as_str(getattr(resource, "description", "")),
        profile_id=_as_str(getattr(resource, "profileId", "")),
        group_id=_as_str(getattr(resource, "groupId", "")),
        portal_user=_as_str(getattr(resource, "portalUser", "")),
        static_group=_as_bool_flag(getattr(resource, "staticGroupAssignment", None)),
        static_profile=_as_bool_flag(getattr(resource, "staticProfileAssignment", None)),
        id=_as_str(getattr(resource, "id", "")),
    )


def parse_endpoints(resources: list, group_names: Optional[dict] = None) -> list[IseEndpoint]:
    """Normalise a list of endpoint resources, resolving group ids to names.

    group_names maps group_id -> group name (from the client's
    get_endpoint_group_name calls); unknown ids fall back to the raw id.
    """
    group_names = group_names or {}
    out = [parse_endpoint(r) for r in resources]
    for e in out:
        if e.group_id:
            e.group_name = group_names.get(e.group_id, e.group_id)
    return out
