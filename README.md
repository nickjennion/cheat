# CHEAT — Cisco Homogenous Environment Awareness Tool

Network port discovery, inventory, and analysis tool for Cisco DNA Center (Catalyst Center).

---

## File Reference

### Core Application

| File | Purpose |
|------|---------|
| `main_latest.py` | **Interactive menu launcher (current development entry point).** Two-stage menu flow: credentials (Legacy DNAC `dnac.env` / New DNAC `dnac2.env` / manual) → device fetch → switch selection with filter → command/report selection → confirmation → execution. Menu 2 also hosts the ISE endpoint inventory (option 5), which reuses the DNAC credentials plus an optional `ISE_HOST=` line from the same env file. UI-centric: delegates the main port-report run/parse/Excel path to `cheat_core.py`; MAC/IP client searches, the AV and IP/MAC VLAN exports, the MAC-by-port export, the AP monitor, and ISE are handled directly in the menu layer. Persists preferences to `prefs.env` (**Options** menu): slow mode, output dir, filename prefix, auto-consolidation, colours, email, AI, logging, splash style/logo, and topology layout (**Options → `K`**, `auto` vs `pyramid` distribution/access/desk). Session-scoped toggles on Menu 5 (slow mode, copper-only, link-state) are not persisted; command concurrency (Menu 5 `c`, 1–5) is **session-only** and is *not* saved to `prefs.env`. |
| `main.py` | **Original CLI entry point.** Argparse-driven workflow: authenticate, fetch inventory, filter by hostname wildcard, execute five diagnostic commands via Command Runner, parse output, generate combined Excel report. Imports shared constants and execution logic from `cheat_core.py`. |
| `main_debug.py` | **Debug variant of main.py.** Identical workflow with verbose logging enabled (`DEBUG = True`). Prints stack traces on errors, logs partial auth tokens, shows poll-by-poll task progress, and dumps raw JSON responses. **Note:** logs the username and first 30 characters of the bearer token to stdout — do not redirect output to shared files in this mode. Unlike `main.py` it does **not** import `cheat_core.py` — it carries its own copies of the constants and uses `show cdp neighbors` (no `detail`) in its command list. |
| `cheat_core.py` | **Shared execution and reporting module.** UI-agnostic. Provides `run_commands()` (execute/poll/save loop), `parse_outputs()` (parse loop wrapper), `generate_excel()` (modes: separate-per-device, one-workbook, combined-with-utilisation), `generate_cdp_topology()` (Graphviz `.drawio` export), and all shared constants (`DNAC_COMMANDS`, `COMMAND_RUNNER_DIR`, `EXCEL_DIR`, polling timeouts, concurrency helpers). Import this from any entry point. |
| `ap_monitor.py` | **Access Point movement monitor (Menu 2 → 4).** Filters/selects Unified APs, then live-refreshes a table comparing previous upstream (Assurance events, 24h) vs current upstream (physical topology), flags moved APs, and exports to Excel. |
| `ise_client.py` | **ISE REST API client (Menu 2 → 5).** Thin wrapper over Cisco's official `ciscoisesdk`: an `ISEConfig` dataclass mirroring the credential-file keys and an `ISEClient` that queries all ISE endpoints (paginated via the SDK generator) and resolves endpoint-group names. The SDK import is deferred, so CHEAT runs without `ciscoisesdk` installed — ISE use reports a clear install message. An `api` may be injected for offline tests. |
| `ise_parser.py` | **ISE endpoint parser.** Pure normalisation of SDK endpoint resources into flat `IseEndpoint` records (name, MAC, description, profile/group IDs, portal user, static-assignment flags), resolving group ids to names. Feeds the ISE endpoint inventory Excel/CSV writers. |
| `dnac_client.py` | **DNAC REST API client.** Provides the `DNACClient` class wrapping the DNAC API: auth token acquisition (`/auth/token`), paginated device listing and hostname-filtered query (`/network-device`), client search (`/clients`), client detail (`/client-detail`), site hierarchy (`/site`), Unified AP inventory, AP topology and Assurance events, command execution submission (`/network-device-poller/cli/read-request`), task polling (`/task/{id}`), and file retrieval (`/file/{id}`). Persists the auth token to `token.env` on every successful authentication. Includes exponential backoff retry on all calls. SSL verification is disabled by default for lab/self-signed DNAC instances. |

### Parsing & Reporting

| File | Purpose |
|------|---------|
| `interface_parser.py` | **CLI output parser.** Parses concatenated output from `show hardware`, `show interfaces`, `show interfaces status`, `show interface counters`, `show cdp neighbors`, and — for the link-state column — `show logging` / `show clock`. Extracts stack member metadata, interface state/protocol/VLAN/description/counters/last-input, CDP neighbor mappings, computes a `suspect` flag indicating whether an interface has ever seen traffic, and derives a per-interface last-link-change age from UPDOWN syslog lines. Returns sorted `InterfaceRecord` objects and a `StackMember` dictionary. |
| `excel_generator.py` | **Excel + CSV report writer.** Takes parsed `InterfaceRecord`/`StackMember` data and produces a multi-sheet `.xlsx` workbook. One sheet per device, color-coded by interface state (green=connected, yellow=notconnect, gray=disabled, red=err-disabled), gold highlight for interfaces with traffic, orange for stack members with <42 days uptime. Freeze panes and auto-filter enabled. Also hosts the combined-workbook writer, the client-search export, and the AV MAC, MAC-by-port, IP/MAC, and ISE endpoint report writers — each with a matching CSV export. |
| `consolidate_report.py` | **Report flattener.** Reads a multi-sheet port report produced by the main tool and consolidates every port from every device into a single "All Ports" sheet in a new workbook. Preserves all column styling, color coding, and formatting. Expects the standard `HEADERS` layout from `excel_generator.py` (18 columns; 19 when link-state is enabled) and skips the `All Ports`/`Port Utilisation` summary sheets. |
| `port_utilisation.py` | **Port usage analyser.** Reads a CHEAT Excel report and calculates per-switch port utilisation statistics: counts copper ports (stacked `GiX/Y/Z`/`TeX/Y/Z` and non-stacked `GiX/Y`/`FaX/Y`) with recent traffic vs. idle ports based on the "Last Input" column. Supports a configurable threshold (default 42 days). Outputs a readable stdout summary table and a timestamped summary Excel file. Includes an **unscanned Cisco switches** block listing CDP neighbours (with mgmt IP) not scanned in the session. |
| `unscanned_switches.py` | **Coverage gap finder.** From CDP data and the set of scanned hostnames, computes the list of Cisco switches seen as CDP neighbours but never explicitly scanned in the session ("rogue" switches). Feeds the unscanned-switches block in the port-utilisation report and the rogue nodes in the CDP topology. |
| `time_utils.py` | **Shared time parsing.** Provides `parse_duration_days()` converting colon (`00:00:13`), prose (`45 weeks, 3 days`), and compact (`2d3h`, `5w`) durations to fractional days. Drives the uptime highlighting and last-input/port-utilisation thresholds. |

### VLAN Exports (Menu 5 `m`, `e` and `d`)

Three per-VLAN/per-port exports built on the same three-layer split — a pure parser,
a pure correlator, then Excel + CSV writers in `excel_generator.py`. All reuse the
switch selection already made in Menu 4 and flag ambiguity rather than resolving it.

| File | Purpose |
|------|---------|
| `mac_table.py` | **`show mac address-table` parser.** Pure parsing into per-switch MAC/port entries. Skips `All`-VLAN and CPU rows (control-plane MACs, not end devices) and lower-cases MACs so cross-switch comparison works. |
| `av_mac_report.py` | **MAC/port correlator (Menu 5 `m`).** Correlates MAC tables with `show cdp neighbors detail` across a switch group, dropping any interface whose CDP neighbour is itself a switch/router — that collapses the same MAC learned on every uplink between the AV device and the top of the stack. Flags a port holding several MACs (`possible unmanaged switch`) and a MAC surviving on several switches (`Ambiguous`). Each surviving row carries a `Device Type` derived from the port's CDP neighbour (IP phone, access point, etc.), and the summary block lists the MAC count per requested VLAN. Writes Excel + CSV. |
| `mac_by_port.py` | **Full MAC-table correlator (Menu 5 `e`).** Lists **every** MAC entry (all VLANs) grouped by port, including child-switch uplinks: unlike `av_mac_report` it keeps switch/router neighbours and labels them, so MACs learned beyond a downstream switch stay visible under that port. Same per-port CDP device-type labelling and multi-MAC/ambiguous flags. Writes Excel + CSV. |
| `device_tracking.py` | **`show device-tracking database` parser.** Pure parsing of the SISF binding table (Catalyst 9000-class IOS-XE) into IP/MAC/interface/VLAN/state records. Returns local (`L`) and static (`S`) rows for the caller to decide on, counts IPv6 bindings rather than dropping them silently, and detects the `% Invalid input` reply from pre-SISF platforms. |
| `ip_mac_report.py` | **IP/MAC correlator (Menu 5 `d`).** Filters bindings to the requested VLANs and drops the switch's own `L`/`S` rows (counting them), giving a per-VLAN inventory of devices and the addresses they hold. Flags one IP held by several MACs (an address conflict) and one MAC seen on several switches. Records which switches could not run the command versus which ran it and returned nothing, so a part-9000 fleet never looks like an empty result. |

### CDP Topology

| File | Purpose |
|------|---------|
| `cdp_detail.py` | **`show cdp neighbors detail` parser.** Parses the detail output into rich neighbour records carrying management IP and full platform/model string. Source of truth for both the topology diagram and the report's CDP-neighbour columns. Also provides the device-type classifier `classify_neighbor()` (IP phone / access point / switch-router / camera / printer) used by the AV MAC and MAC-by-port exports. |
| `cdp_topology.py` | **Topology graph builder.** Turns parsed CDP data into a graph of `TopologyNode` objects (hostname, model, mgmt IP, rogue flag, feeding-port description), distinguishing scanned switches from unscanned "rogue" neighbours. |
| `topology_dot.py` | **Graphviz DOT generator + layout parser.** Emits the topology as a Graphviz `dot` graph (tree ranking, aggregation-on-top, A3 sizing, selectable spline mode; or the `pyramid` distribution/access/desk three-tier ranking by hostname model), parses `dot -Tplain` output back into coordinates, detects aggregation switches, and splits large sites into multiple pages. |
| `drawio_generator.py` | **draw.io / mxGraph XML emitter.** Two jobs. (1) Renders the laid-out CDP topology pages into a multi-page `.drawio` file: curved edges, aggregated port labels near the downstream switch, and colour-coded nodes (green=scanned switch, red=rogue/unscanned, blue ellipse=access point). The `icons` style parameter is currently inert — nodes always render as plain rectangles. (2) `generate_drawio()` builds the SDA site-hierarchy, per-building fabric topology, and per-floor AP-layout pages for Menu 2's site export, using Cisco stencil shapes. |
| `splash.py` | **Base ASCII splash layout.** Pure text layout (no colour) — renders the 9-bar Cisco "bridge" logo, wordmark, title/subtitle, and menu options into a framed block. Shared by `main_latest.py` (classic splash fallback) and `splash_preview.py`. |
| `splash_rich.py` | **Rich splash banner.** Truecolour-gradient variant of the splash (per-character gradients, rounded menu panel). Supports co-brand designs (`mark`/`lockup`/`stacked`) plus the plain `generic` Cisco mark, and falls back to `splash.py` when Rich is unavailable. |
| `splash_generic.py` | **Cisco-only Rich splash.** Earlier standalone copy of the Rich splash without co-branding. Superseded by `splash_rich.py`'s `generic` design; retained as a reference/preview. |
| `splash_preview.py` | **Splash preview harness.** Standalone script to eyeball the splash layout/colours (`python splash_preview.py`, `--plain` for no colour). |

### Testing

| File | Purpose |
|------|---------|
| `test_dnac.py` | **Live integration test suite.** Validates all components against a real Cisco DNAC instance (or DevNet sandbox). Runs five sequential tests: authentication, device discovery, command execution (60s timeout), output parsing, and Excel generation. Prompts for credentials at runtime. **Warning:** uses plain `input()` for the password (not `getpass`). Standalone — not called by any other tool. |
| `test_mock_dnac.py` | **Offline unit test suite.** Validates parsing and Excel generation logic using hardcoded mock Cisco IOS command output (C3850 two-member stack). No network connectivity required. Tests parsing completeness, data extraction accuracy, edge cases, and Excel file creation. Standalone. |
| `test_sandbox.py` | **Zero-config DevNet sandbox demo.** Connects to the Cisco DevNet Always-On DNAC sandbox (`sandboxdnacenter.cisco.com`) using public credentials. Credentials and host can be overridden via `DNAC_HOST`, `DNAC_USER`, `DNAC_PASS` environment variables. Useful for verifying the tool end-to-end without a private DNAC instance. |

The remaining `test_*.py` files are offline unit tests (pytest, no network) exercising a single module against fixtures:

| Test file | Module under test |
|-----------|-------------------|
| `test_interface_parser.py` | `interface_parser.py` — stack/interface parsing, link-state ages |
| `test_excel_generator.py` | `excel_generator.py` — sheet writing, link-state column presence |
| `test_cheat_core.py` | `cheat_core.py` — `run_commands` with a stub client, `build_command_list` |
| `test_mac_table.py` | `mac_table.py` — MAC-table row parsing, All/CPU skipping |
| `test_av_mac_report.py` | `av_mac_report.py` — AV MAC/port correlation and flags |
| `test_mac_by_port.py` | `mac_by_port.py` — full-MAC-table by-port correlation, uplink/device-type labels, Excel+CSV |
| `test_device_tracking.py` | `device_tracking.py` — SISF binding-table parsing |
| `test_ip_mac_report.py` | `ip_mac_report.py` — IP/MAC per-VLAN correlation and flags |
| `test_ip_mac_excel.py` | `excel_generator.py` — IP/MAC export sheet output |
| `test_cdp_detail.py` | `cdp_detail.py` — `show cdp neighbors detail` parsing |
| `test_cdp_topology.py` | `cdp_topology.py` — topology graph building, rogue detection |
| `test_topology_dot.py` | `topology_dot.py` + `drawio_generator.py` — DOT emission, `-Tplain` parsing, node styling |
| `test_unscanned_switches.py` | `unscanned_switches.py` — rogue-switch discovery |
| `test_port_utilisation.py` | `port_utilisation.py` — utilisation sheet & analysis |
| `test_ap_client.py` | `dnac_client.py` — AP inventory/topology/events methods |
| `test_ap_monitor.py` | `ap_monitor.py` — table-row building |
| `test_credential_files.py` | `main_latest.py` — Menu 1 credential-file load/view/mask |
| `test_av_mac_export_wiring.py` | `main_latest.py` — Menu 5 `m` wiring |
| `test_ip_mac_export_wiring.py` | `main_latest.py` — Menu 5 `d` wiring |
| `test_main_latest_concurrency.py` | `main_latest.py` — concurrency helpers and param wiring |
| `test_splash_rich.py` | `splash_rich.py` — logo alignment regression |
| `test_ise_client.py` | `ise_client.py` — endpoint paging, injected fake api, SDK-missing error |
| `test_ise_parser.py` | `ise_parser.py` + ISE Excel/CSV writers — field normalisation, group-name resolution |
| `test_ise_wiring.py` | `main_latest.py` — Menu 2 ISE action wiring |

### Configuration & Dependencies

| File | Purpose |
|------|---------|
| `requirements.txt` | **Python dependencies.** Declares `requests>=2.25.0` (HTTP client), `urllib3>=1.26.0` (transport layer), `openpyxl>=3.0.0` (Excel read/write), `colorama>=0.4.6` (ANSI colour on legacy Windows consoles), `rich>=13.0.0` (progress bars, styled output, splash), and `ciscoisesdk>=2.4.5` (ISE REST client — only needed for the ISE endpoint inventory). |
| `.gitignore` | **Git exclusion rules.** Excludes Python bytecode, build artifacts, generated outputs (`all_devices.json`, `command_output_*.txt`, `*.xlsx`), IDE config (`.vscode/`, `.idea/`), `.DS_Store`, and all `.env` credential files. Files with `sample` in the filename are exempt from xlsx and env exclusions. **Note:** `.drawio` files are *not* ignored — `drawio_exports/` is committed. |
| `dnac.env` | **Optional credential file — legacy DNA Center.** Not tracked in git (never commit — contains plaintext credentials). If created with `DNAC_HOST=`, `DNAC_USERNAME=`, `DNAC_PASSWORD=`, **Menu 1 → `1) Use Legacy DNAC`** loads credentials from it instead of prompting interactively. May also carry optional `ISE_HOST=` and `ISE_VERSION=` lines for the ISE endpoint inventory (**Menu 2 → 5**), which reuses the same username/password. |
| `dnac2.env` | **Optional credential file — new DNA Center.** Same keys and same rules as `dnac.env` (including the optional `ISE_HOST=` / `ISE_VERSION=` lines); loaded by **Menu 1 → `2) Use New DNAC`**. A missing `dnac2.env` never falls back to `dnac.env` — the tool reports the miss rather than silently targeting the wrong controller. `Enter manually · remember` asks which of the two files to write, and `View credential files` shows both with the password masked. |
| `token.env` | **Runtime artifact.** Written by `dnac_client.py` on every successful authentication. Contains the raw bearer token as `DNAC_TOKEN=<value>`. Gitignored but persists across sessions. **Treat as a live credential — grants full DNAC API access until expiry. Delete after use; never copy to shared systems.** |
| `sample_dnac.env` | **Credential template.** Tracked example of `dnac.env` with placeholder values (`localhost` / `your_username` / `your_password`). Referenced by Menu 1 when a credential file is missing. Documents the optional `ISE_HOST=` / `ISE_VERSION=` lines. |

### Documentation

| File | Purpose |
|------|---------|
| `README.md` | **This file.** Master reference for every file in the repository. |
| `CHANGELOG.md` | **Change log.** Chronological record of features, fixes, and refactors by date. |

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

**Slow mode** is toggled in Menu 5 (press `s`). It applies to the current execution only and does not persist across runs. (The **Options → A** setting of the same name is stored in `prefs.env` but is scaffold-only — not yet wired into execution.) The retry backoff formula is `{backoff_factor} × (2^(N-1))` seconds between attempts, so backoff factor 2 gives 2s, 4s, 8s between retries vs 1s, 2s, 4s at default.

## Generated Outputs

| Pattern | Source | Contents | Git status |
|---------|--------|----------|------------|
| `all_devices.json` | `main.py` / `main_latest.py` | Full DNAC device inventory | ignored |
| `command_runner_outputs/command_output_*.txt` | `cheat_core.py` | Raw command output per device | ignored |
| `excel_reports/port-information-*.xlsx` | `cheat_core.py` / `main.py` | Combined multi-sheet Excel report (All Ports + Port Utilisation + per-stack tabs) | ignored |
| `excel_reports/port_utilisation_summary_*.xlsx` | `port_utilisation.py` | Per-switch port utilisation summary (+ unscanned Cisco switches block) | ignored |
| `drawio_exports/*-cdp-topology.drawio` | `cheat_core.py` | Multi-page draw.io CDP physical topology diagram (Graphviz-laid-out) | **committed** (no `.drawio` rule in `.gitignore`) |
| `token.env` | `dnac_client.py` | Bearer token from last auth | ignored |
