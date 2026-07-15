"""
CHEAT — shared execution, parsing, and reporting logic.

This module is UI-agnostic. Import it from any entry point (main.py,
main_latest.py, test harnesses) without pulling in CLI or menu code.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from interface_parser import parse_output
from excel_generator import write_excel, write_combined_excel
from unscanned_switches import find_unscanned_switches
from cdp_topology import build_topology, layout_topology
from drawio_generator import generate_cdp_topology_xml


# ============================================================================
# Constants
# ============================================================================

DNAC_COMMANDS = [
    "show hardware",
    "show interfaces",
    "show interfaces status",
    "show interface counters",
    "show cdp neighbors",
]

LINK_STATE_COMMANDS = ["show logging", "show clock"]


def build_command_list(link_state: bool) -> list:
    """Base report commands, plus link-state commands when enabled."""
    return (DNAC_COMMANDS + LINK_STATE_COMMANDS) if link_state else list(DNAC_COMMANDS)


COMMAND_RUNNER_DIR = "command_runner_outputs"
EXCEL_DIR = "excel_reports"
DRAWIO_DIR = "drawio_exports"
COMMAND_POLLING_TIMEOUT_SECONDS = 30
COMMAND_POLLING_INTERVAL_SECONDS = 1


# ============================================================================
# Command Execution
# ============================================================================

def _run_device_commands(
    device: dict,
    client,
    commands: list,
    cmd_dir: Path,
    timestamp: str,
    poll_timeout: int,
    poll_interval: int,
    submit_timeout: int,
) -> tuple[str, Optional[str], list]:
    """Submit commands to one device, poll for completion, fetch and save output.

    UI-agnostic: returns (hostname, output_text_or_None, messages). output_text is
    None on any failure; messages are human-readable status lines for the caller
    to display however it likes.
    """
    hostname = device.get("hostname", "unknown")
    device_id = device.get("id")
    msgs: list = []

    task_id = client.execute_commands(device_id, commands, timeout=submit_timeout)
    if not task_id:
        msgs.append(f"✗ {hostname}: failed to start command execution")
        return hostname, None, msgs

    result = None
    for _ in range(poll_timeout):
        time.sleep(poll_interval)
        task_result = client.get_task_result(task_id)
        if task_result and task_result.get("endTime"):
            result = task_result
            break

    if not result:
        msgs.append(f"✗ {hostname}: timed out after {poll_timeout}s")
        return hostname, None, msgs

    output_text = None
    try:
        progress_json = json.loads(result.get("progress", "{}"))
        file_id = progress_json.get("fileId")
        if file_id:
            output_text = client.get_file_output(file_id)
    except Exception as e:
        msgs.append(f"✗ {hostname}: could not extract file ID: {e}")

    if not output_text:
        msgs.append(f"✗ {hostname}: no output received")
        return hostname, None, msgs

    # Unwrap commandResponses JSON envelope if present
    try:
        response_data = json.loads(output_text)
        if isinstance(response_data, list) and response_data:
            cmd_responses = (
                response_data[0].get("commandResponses", {}).get("SUCCESS", {})
            )
            if cmd_responses:
                output_text = "\n\n".join(cmd_responses.values())
    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    out_file = cmd_dir / f"command_output_{hostname}_{timestamp}.txt"
    try:
        out_file.write_text(output_text)
        msgs.append(f"✓ {hostname}: saved {out_file.name}")
        return hostname, output_text, msgs
    except IOError as e:
        msgs.append(f"✗ {hostname}: could not save output: {e}")
        return hostname, None, msgs


def run_commands(
    selected_devices: list,
    client,
    commands: list,
    poll_timeout: int = COMMAND_POLLING_TIMEOUT_SECONDS,
    poll_interval: int = COMMAND_POLLING_INTERVAL_SECONDS,
    submit_timeout: int = 10,
) -> dict:
    """Execute commands on devices via an authenticated DNACClient.

    Shows a live Rich progress bar (one step per device) with a spinner and
    elapsed timer that animate through each device's poll wait. Saves raw output
    to COMMAND_RUNNER_DIR/<hostname>_<timestamp>.txt and returns
    {hostname: output_text} for every device that succeeded.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    cmd_dir = Path(COMMAND_RUNNER_DIR).resolve()
    cmd_dir.mkdir(exist_ok=True)
    outputs = {}
    failed = []

    console = Console()
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Running {len(commands)} command(s)", total=len(selected_devices)
        )
        for device in selected_devices:
            hostname = device.get("hostname", "unknown")
            progress.update(task, description=hostname)

            host, output_text, msgs = _run_device_commands(
                device, client, commands, cmd_dir, timestamp,
                poll_timeout, poll_interval, submit_timeout,
            )
            for msg in msgs:
                colour = "green" if msg.startswith("✓") else "red"
                progress.console.print(f"  [{colour}]{msg}[/{colour}]", highlight=False)

            if output_text is not None:
                outputs[host] = output_text
            else:
                failed.append(host)
            progress.advance(task)

    if failed:
        console.print(f"\n  [yellow]⚠ Failed on: {', '.join(failed)}[/yellow]")
    return outputs


# ============================================================================
# Parsing
# ============================================================================

def parse_outputs(outputs: dict) -> dict:
    """Parse command runner outputs into structured data.

    Returns {hostname: (records, stack_members)}.
    """
    devices_data = {}
    for hostname, output_text in outputs.items():
        print(f"  Parsing {hostname}...", end=" ", flush=True)
        try:
            records, stack_members = parse_output(output_text, hostname)
            if records:
                devices_data[hostname] = (records, stack_members)
                print(f"✓ {len(records)} interfaces")
            else:
                print("⚠ no interfaces found")
        except Exception as e:
            print(f"✗ {e}")
    return devices_data


# ============================================================================
# Excel Generation
# ============================================================================

def generate_excel(
    devices_data: dict,
    mode: int,
    filename_stem: str,
    threshold: int = 42,
    raw_outputs: dict | None = None,
) -> list[tuple[bool, str]]:
    """Write Excel output from parsed device data.

    Modes:
      1 — one workbook per device  (write_excel per hostname)
      2 — one workbook, one sheet per device  (write_excel, all devices)
      3 — combined workbook: All Ports + Port Utilisation + per-device tabs

    Returns a list of (success, message) tuples — one per file written.
    """
    excel_dir = Path(EXCEL_DIR).resolve()
    excel_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
    results = []

    if mode == 1:
        for hostname, data in devices_data.items():
            outpath = str(excel_dir / f"{filename_stem}-{hostname}-{ts}.xlsx")
            ok, msg = write_excel({hostname: data}, outpath)
            results.append((ok, msg))

    elif mode == 2:
        outpath = str(excel_dir / f"{filename_stem}-{ts}.xlsx")
        ok, msg = write_excel(devices_data, outpath)
        results.append((ok, msg))

    elif mode == 3:
        outpath = str(excel_dir / f"{filename_stem}-{ts}.xlsx")
        unscanned = None
        if raw_outputs is not None:
            unscanned = find_unscanned_switches(raw_outputs, raw_outputs.keys())
        ok, msg = write_combined_excel(devices_data, threshold, outpath, unscanned=unscanned)
        results.append((ok, msg))

    else:
        results.append((False, f"Unknown mode: {mode}"))

    return results


def generate_cdp_topology(
    raw_outputs: dict, scanned_hostnames, filename_stem: str
) -> tuple[bool, str]:
    """Build and write the CDP physical topology .drawio for a scan.

    Returns (success, message). Writes nothing and returns (False, message)
    when there are no scanned switches to anchor the diagram.
    """
    topology = build_topology(raw_outputs, scanned_hostnames)
    scanned_nodes = [n for n in topology.nodes if not n.is_rogue]
    if not scanned_nodes:
        return False, "⚠ CDP topology skipped: no scanned switches"

    positions = layout_topology(topology)
    xml = generate_cdp_topology_xml(topology, positions)

    out_dir = Path(DRAWIO_DIR).resolve()
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
    outpath = str(out_dir / f"{filename_stem}-{ts}-cdp-topology.drawio")
    try:
        Path(outpath).write_text(xml, encoding="utf-8")
    except IOError as e:
        return False, f"✗ Failed to write CDP topology: {e}"

    rogue = sum(1 for n in topology.nodes if n.is_rogue)
    return True, (
        f"✓ CDP topology: {outpath} "
        f"({len(scanned_nodes)} switch(es), {rogue} unscanned)"
    )
