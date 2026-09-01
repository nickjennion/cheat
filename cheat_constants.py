"""
CHEAT — lightweight constants and pure utility functions.

Zero heavy imports (no rich, no openpyxl, no requests). Both main.py and
cheat_core.py import from here so there's a single source of truth without
pulling in expensive dependencies at module load time.
"""

from typing import Optional


# ============================================================================
# Command lists
# ============================================================================

DNAC_COMMANDS = [
    "show hardware",
    "show interfaces",
    "show interfaces status",
    "show interface counters",
    "show cdp neighbors detail",
]

LINK_STATE_COMMANDS = ["show logging", "show clock"]

AV_MAC_COMMANDS = ["show mac address-table", "show cdp neighbors detail"]

# SISF binding table (Catalyst 9000-class IOS-XE): IP, MAC, interface, VLAN and
# reachability state on one line. Older platforms reject it — ip_mac_report
# detects that and reports which switches could not run it.
DEVICE_TRACKING_COMMANDS = ["show device-tracking database"]

# Legacy IP Device Tracking table used by Palantir mode. Collect the full table
# because a device-side ``include /0/`` drops standalone ports such as Gi0/3.
# Palantir applies the physical-port restriction locally during correlation.
PALANTIR_IP_TRACKING_COMMAND = "show ip device tracking all"


def build_palantir_command_list(link_state: bool) -> list:
    """Option 3's inventory commands plus MAC and legacy IP tracking data."""
    return build_command_list(link_state) + [
        "show mac address-table",
        PALANTIR_IP_TRACKING_COMMAND,
    ]


# ============================================================================
# Paths / dirs
# ============================================================================

COMMAND_RUNNER_DIR = "command_runner_outputs"
EXCEL_DIR = "excel_reports"
DRAWIO_DIR = "drawio_exports"
COMMAND_POLLING_TIMEOUT_SECONDS = 30
COMMAND_POLLING_INTERVAL_SECONDS = 1
# Catalyst Center Command Runner accepts no more than five CLI commands in one
# read-request. Larger report command lists are split per device in cheat_core.
COMMAND_RUNNER_MAX_COMMANDS = 5


# ============================================================================
# Concurrency helpers
# ============================================================================

DEFAULT_CONCURRENCY = 2
MAX_CONCURRENCY = 5


def build_command_list(link_state: bool) -> list:
    """Base report commands, plus link-state commands when enabled."""
    return (DNAC_COMMANDS + LINK_STATE_COMMANDS) if link_state else list(DNAC_COMMANDS)


def clamp_concurrency(n: int) -> int:
    """Clamp n into [1, MAX_CONCURRENCY]: n < 1 -> 1, n > MAX -> MAX."""
    return max(1, min(int(n), MAX_CONCURRENCY))


def next_concurrency(n: int) -> int:
    """Cycle 1->2->3->4->5->1 for the menu toggle."""
    return clamp_concurrency(n) % MAX_CONCURRENCY + 1
