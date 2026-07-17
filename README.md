# CHEAT — Cisco Homogenous Environment Awareness Tool

Network port discovery, inventory, and analysis tool for Cisco DNA Center (Catalyst Center).

---

## File Reference

### Core Application

| File | Purpose |
|------|---------|
| `main_latest.py` | **Interactive menu launcher (current development entry point).** Two-stage menu flow: credentials (dnac.env or manual) → device fetch → switch selection with filter → command/report selection → confirmation → execution. Pure UI — no business logic. Delegates all execution, parsing, and Excel generation to `cheat_core.py`. |
| `main.py` | **Original CLI entry point.** Argparse-driven workflow: authenticate, fetch inventory, filter by hostname wildcard, execute five diagnostic commands via Command Runner, parse output, generate combined Excel report. Imports shared constants and execution logic from `cheat_core.py`. |
| `main_debug.py` | **Debug variant of main.py.** Identical workflow with verbose logging enabled (`DEBUG = True`). Prints stack traces on errors, logs partial auth tokens, shows poll-by-poll task progress, and dumps raw JSON responses. **Note:** logs the username and first 30 characters of the bearer token to stdout — do not redirect output to shared files in this mode. |
| `cheat_core.py` | **Shared execution and reporting module.** UI-agnostic. Provides `run_commands()` (execute/poll/save loop), `parse_outputs()` (parse loop wrapper), `generate_excel()` (modes: separate-per-device, one-workbook, combined-with-utilisation), and all shared constants (`DNAC_COMMANDS`, `COMMAND_RUNNER_DIR`, `EXCEL_DIR`, polling timeouts). Import this from any entry point. |
| `dnac_client.py` | **DNAC REST API client.** Provides the `DNACClient` class wrapping six endpoints: auth token acquisition, paginated device listing (`/network-device`), hostname-filtered device query, command execution submission (`/network-device-poller/cli/read-request`), task polling (`/task/{id}`), and file retrieval (`/file/{id}`). Persists the auth token to `token.env` on every successful authentication. Includes exponential backoff retry on all calls. SSL verification is disabled by default for lab/self-signed DNAC instances. |

### Parsing & Reporting

| File | Purpose |
|------|---------|
| `interface_parser.py` | **CLI output parser.** Parses concatenated output from `show hardware`, `show interfaces`, `show interfaces status`, `show interface counters`, and `show cdp neighbors`. Extracts stack member metadata, interface state/protocol/VLAN/description/counters/last-input, CDP neighbor mappings, and computes a `suspect` flag indicating whether an interface has ever seen traffic. Returns sorted `InterfaceRecord` objects and a `StackMember` dictionary. |
| `excel_generator.py` | **Excel report writer.** Takes parsed `InterfaceRecord`/`StackMember` data and produces a multi-sheet `.xlsx` workbook. One sheet per device, color-coded by interface state (green=connected, yellow=notconnect, gray=disabled, red=err-disabled), gold highlight for interfaces with traffic, orange for stack members with <42 days uptime. Freeze panes and auto-filter enabled. |
| `consolidate_report.py` | **Report flattener.** Reads a multi-sheet port report produced by the main tool and consolidates every port from every device into a single "All Ports" sheet in a new workbook. Preserves all column styling, color coding, and formatting. Expects the standard 14-column header layout. |
| `port_utilisation.py` | **Port usage analyser.** Reads a CHEAT Excel report and calculates per-switch port utilisation statistics: counts copper ports (GiX/0/X, TeX/0/X) with recent traffic vs. idle ports based on the "Last Input" column. Supports a configurable threshold (default 42 days). Outputs a readable stdout summary table and a timestamped summary Excel file. |

### Testing

| File | Purpose |
|------|---------|
| `test_dnac.py` | **Live integration test suite.** Validates all components against a real Cisco DNAC instance (or DevNet sandbox). Runs five sequential tests: authentication, device discovery, command execution (60s timeout), output parsing, and Excel generation. Prompts for credentials at runtime. **Warning:** uses plain `input()` for the password (not `getpass`). Standalone — not called by any other tool. |
| `test_mock_dnac.py` | **Offline unit test suite.** Validates parsing and Excel generation logic using hardcoded mock Cisco IOS command output (C3850 two-member stack). No network connectivity required. Tests parsing completeness, data extraction accuracy, edge cases, and Excel file creation. Standalone. |
| `test_sandbox.py` | **Zero-config DevNet sandbox demo.** Connects to the Cisco DevNet Always-On DNAC sandbox (`sandboxdnacenter.cisco.com`) using public credentials. Credentials and host can be overridden via `DNAC_HOST`, `DNAC_USER`, `DNAC_PASS` environment variables. Useful for verifying the tool end-to-end without a private DNAC instance. |

### Configuration & Dependencies

| File | Purpose |
|------|---------|
| `requirements.txt` | **Python dependencies.** Declares `requests>=2.25.0` (HTTP client), `urllib3>=1.26.0` (transport layer), and `openpyxl>=3.0.0` (Excel read/write). |
| `.gitignore` | **Git exclusion rules.** Excludes Python bytecode, build artifacts, generated outputs (`all_devices.json`, `command_runner_outputs/`, `*.xlsx`, `command_output_*.txt`), IDE config (`.vscode/`, `.idea/`), `.DS_Store`, and all `.env` credential files. Files with `sample` in the filename are exempt from xlsx and env exclusions. |
| `dnac.env` | **Optional credential file.** Not tracked in git (never commit — contains plaintext credentials). If created with `DNAC_HOST=`, `DNAC_USERNAME=`, `DNAC_PASSWORD=`, the main app loads credentials from it instead of prompting interactively. |
| `token.env` | **Runtime artifact.** Written by `dnac_client.py` on every successful authentication. Contains the raw bearer token as `DNAC_TOKEN=<value>`. Gitignored but persists across sessions. **Treat as a live credential — grants full DNAC API access until expiry. Delete after use; never copy to shared systems.** |

### Artifacts Directory (`artifacts/`)

Contains two independent sub-projects plus archived documentation and reference images.

#### A. OpenFlights Data Pipeline

| File | Purpose |
|------|---------|
| `artifacts/convert.py` | **Data converter.** Reads the three `.dat` flat files, indexes them by IATA code, filters to valid airports with lat/lon coordinates, and writes three `.json` files for frontend consumption. Runs offline. |
| `artifacts/airports.dat` | OpenFlights airport database (CSV). 6,072 airports with name, city, country, IATA, ICAO, lat/lon. Source material for `convert.py`. |
| `artifacts/airlines.dat` | OpenFlights airline database (CSV). Airline name, IATA code, ICAO code, country, active flag. |
| `artifacts/routes.dat` | OpenFlights route database (CSV). 66,934 routes (2014 data) with airline, source/destination IATA, codeshare flag, stops, equipment. |
| `artifacts/airports-indexed.json` | **Generated output.** Airports keyed by IATA code with name, city, country, lat/lon. Deployed to the  web server. |
| `artifacts/airlines-indexed.json` | **Generated output.** Airlines keyed by IATA code with name, country, active status. |
| `artifacts/routes-indexed.json` | **Generated output.** Routes keyed by source IATA, each entry lists destination, airline, codeshare, stops, equipment. |

#### B. Session Notes (Historical Record)

| File | Purpose |
|------|---------|
| `artifacts/modifications_20260308_154207.md` | Deployment log from 2026-03-08. Records files deployed to the `` web server (Cisco DevNet sandbox), nginx configuration changes, OAuth2 collector setup, Caddy allowlist updates, and cron schedules. |
| `artifacts/SESSION-2026-03-09.md` | Development session summary from 2026-03-09. Documents the OpenSky route collector build, .com scraper, route data collected (1,264 airports across 19+ countries), and frontend feature additions (scope filters, color-coded map, flight search popups). **Note:** contains server IPs and deployment paths. |

#### C. Archived Documentation & Reference Images

| File | Purpose |
|------|---------|
| `artifacts/DNAC_README.md` | **Archived user guide.** Earlier usage instructions superseded by this README. Retained for historical reference. |
| `artifacts/TESTING.md` | **Archived testing guide.** Earlier step-by-step instructions for running the test suite against Cisco DevNet sandbox. |
| `artifacts/1772937758fe9b.png` | Screenshot/image (788×450 PNG, 429 KB). UI reference or documentation image. |
| `artifacts/Unsaved Image 1.jpg` | Screenshot/image (2249×1304 JPEG, 860 KB). UI reference or documentation image. |

### Documentation

| File | Purpose |
|------|---------|
| `README.md` | **This file.** Master reference for every file in the repository. |
| `sources.md` | **Data source attribution.** Records all third-party data sources, APIs, and libraries used in the  flight route module. Includes AI tool attribution (Claude, Gemini). |

---

## Quick Start

Requires Python 3.9+.

```bash
pip install --user -r requirements.txt
python main.py
```

## Graphviz (topology diagram)

The CDP physical topology export (`*-cdp-topology.drawio`) uses the Graphviz
`dot` engine to lay out and route the diagram. Graphviz is a **system
dependency** (a binary on your PATH), not a Python package — install it
separately:

- **Linux (Debian/Ubuntu):** `sudo apt install graphviz`
- **Linux (RHEL/Fedora):** `sudo dnf install graphviz`
- **Windows:** `winget install Graphviz.Graphviz` (or `choco install graphviz`),
  or download the installer from graphviz.org and add its `bin\` folder to PATH.
- **macOS:** `brew install graphviz`

If `dot` is not found, the tool skips the topology diagram (with a reminder) and
all other outputs are produced normally.

## Rate & Timeout Reference

Default values used by `dnac_client.py` and `cheat_core.py`. All timeouts are in seconds.

| Operation | Parameter | Default | Slow Mode |
|-----------|-----------|---------|-----------|
| Authentication (`POST /auth/token`) | `timeout` | 10s | — |
| Device listing (`GET /network-device`) | `timeout` | 30s | — |
| Device listing page size | `limit` | 500 devices/page | — |
| Command submission (`POST /cli/read-request`) | `submit_timeout` | 10s | 20s |
| Task poll interval | `poll_interval` | 1s | 3s |
| Task poll max wait | `poll_timeout` | 30s | 60s |
| Task result (`GET /task/{id}`) | `timeout` | 10s | — |
| File retrieval (`GET /file/{id}`) | `timeout` | 10s | — |
| HTTP retry count | `retry_total` | 3 | — |
| HTTP retry backoff factor | `retry_backoff` | 1 | 2 (doubled) |

**Slow mode** is toggled on the Menu 6 confirmation screen (press `s`). It applies to the current execution only and does not persist across runs. The retry backoff formula is `{backoff_factor} × (2^(N-1))` seconds between attempts, so backoff factor 2 gives 2s, 4s, 8s between retries vs 1s, 2s, 4s at default.

## Generated Outputs (Gitignored)

| Pattern | Source | Contents |
|---------|--------|----------|
| `all_devices.json` | `main.py` / `main_latest.py` | Full DNAC device inventory |
| `command_runner_outputs/command_output_*.txt` | `cheat_core.py` | Raw command output per device |
| `excel_reports/port-information-*.xlsx` | `cheat_core.py` / `main.py` | Combined multi-sheet Excel report (All Ports + Port Utilisation + per-stack tabs) |
| `excel_reports/port_utilisation_summary_*.xlsx` | `port_utilisation.py` | Per-switch port utilisation summary |
| `token.env` | `dnac_client.py` | Bearer token from last auth |
