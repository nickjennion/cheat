# CHEAT — Cisco Homogeneous Environmental Awareness Tool

Network port discovery, inventory, and analysis tools for Cisco DNA Center (Catalyst Center).

---

## File Reference

### Core Application

| File | Purpose |
|------|---------|
| `main.py` | **Production entry point.** Interactive CLI that authenticates with DNAC, fetches the device inventory, filters by hostname wildcard, executes five diagnostic `show` commands via Command Runner on selected devices, parses the output, and generates a color-coded multi-sheet Excel report. Reads optional credentials from `dnac.env` or prompts interactively via `getpass`. |
| `main_debug.py` | **Debug variant of main.py.** Identical workflow with verbose logging enabled (`DEBUG = True`). Prints stack traces on errors, logs partial auth tokens, shows poll-by-poll task progress, and dumps raw JSON responses. **Note:** logs the username and first 30 characters of the bearer token to stdout — do not redirect output to shared files in this mode. |
| `dnac_client.py` | **DNAC REST API client.** Provides the `DNACClient` class wrapping five endpoints: auth token acquisition, paginated device listing (`/network-device`), command execution submission (`/network-device-poller/cli/read-request`), task polling (`/task/{id}`), and file retrieval (`/file/{id}`). Persists the auth token to `token.env` on every successful authentication. SSL verification is disabled by default for lab/self-signed DNAC instances. |

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

### Configuration & Dependencies

| File | Purpose |
|------|---------|
| `requirements.txt` | **Python dependencies.** Declares `requests>=2.25.0` (HTTP client for DNAC API) and `openpyxl>=3.0.0` (Excel read/write). |
| `.gitignore` | **Git exclusion rules.** Excludes Python bytecode, build artifacts, generated outputs (`all_devices.json`, `output/`, `*.xlsx`, `command_output_*.txt`), IDE config (`.vscode/`, `.idea/`), `.DS_Store`, and credential files (`dnac.env`, `token.env`). |
| `dnac.env` | **Optional credential file.** Not tracked in git. If created by the user with `DNAC_HOST=`, `DNAC_USERNAME=`, `DNAC_PASSWORD=`, the main app loads credentials from it instead of prompting interactively. |
| `token.env` | **Runtime artifact.** Written by `dnac_client.py` on every successful authentication. Contains the raw bearer token as `DNAC_TOKEN=<value>`. Gitignored but persists across sessions. |

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
| `artifacts/modifications_20260308_154207.md` | Deployment log from 2026-03-08. Records files deployed to the `` web server, nginx configuration changes, OAuth2 collector setup, Caddy allowlist updates, and cron schedules. **Note:** contains internal infrastructure details. |
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
| `sources.md` | **Data source attribution.** Records all third-party data sources, APIs, and libraries used across both CHEAT UNPLUGGED and the  flight route module. Includes AI tool attribution (Claude, Gemini). |

---

## Quick Start

```bash
pip install --user -r requirements.txt
python main.py
```

## Generated Outputs (Gitignored)

| Pattern | Source | Contents |
|---------|--------|----------|
| `all_devices.json` | `main.py` | Full DNAC device inventory |
| `command_runner_outputs/command_output_*.txt` | `main.py` | Raw command output per device |
| `excel_reports/port-information-*.xlsx` | `main.py` | Combined multi-sheet Excel report (All Ports + Port Utilisation + per-stack tabs) |
| `token.env` | `dnac_client.py` | Bearer token from last auth |
