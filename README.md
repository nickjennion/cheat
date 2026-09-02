# CHEAT

**Cisco Homogeneous Environment Awareness Tool**

CHEAT collects live switch data through Cisco DNA Center or Cisco Catalyst Center.
It converts that data into Excel reports and draw.io topology diagrams.

<p align="center">
  <img src="docs/readme/screenshots/network-cutover.png" alt="Network technician connecting switch cables during a network cutover" width="900">
</p>

Use CHEAT to answer these questions:

- Which switch ports are active, idle, disabled, or disconnected?
- Which media access control (MAC) addresses appear on each port?
- Which client Internet Protocol (IP) addresses map to those MAC addresses?
- Which virtual local area networks (VLANs) contain the clients?
- Which Cisco Discovery Protocol (CDP) neighbors connect to each port?
- Which switches appear in CDP but were not included in the scan?
- Which access points moved between switches?

CHEAT uses read-only commands for network data collection.
It writes reports and command output to the local computer.

## Key benefits

- **One workflow for many switches.** Select a switch group once and run multiple reports.
- **Useful Excel output.** Filter, sort, and share the generated workbooks.
- **Port-level context.** Combine interface state, description, VLAN, counters, MAC, IP, and CDP data.
- **Stack-aware reports.** Create one combined sheet and one sheet for each switch stack.
- **Coverage checks.** Find Cisco switches that CDP detects but the selected scan does not include.
- **Topology export.** Create multi-page draw.io diagrams from live CDP data.
- **Safe ambiguity handling.** Flag duplicate or uncertain mappings instead of selecting an unverified result.
- **Scalable collection.** Run jobs across devices concurrently.
- **Automatic API batching.** Split command sets into groups of five for Catalyst Center Command Runner.

## Product tour

### Start with a credential profile

Select a saved Catalyst Center profile.
You can also enter credentials for the current session.

![CHEAT credential menu](docs/readme/screenshots/credentials-menu.png)

### Collect the device inventory

CHEAT uses pagination to collect large Catalyst Center inventories.
It displays each device with its platform and management IP address.

![CHEAT device inventory collection](docs/readme/screenshots/device-inventory.png)

### Filter the switch list

Add inclusion or exclusion filters.
Select one switch or a range of switches.

![CHEAT switch selection filters](docs/readme/screenshots/switch-filters.png)

### Select a report

Choose a port report, client search, topology action, or Palantir Mode.
Set session controls before you start the job.

![CHEAT report and command menu](docs/readme/screenshots/commands-menu.png)

## Main reports

| Report | Menu 5 option | Result |
|---|---:|---|
| Per-device port report | `1` | Create one Excel file for each device. |
| Multi-sheet port report | `2` | Create one Excel file with one sheet for each device. |
| Consolidated port report | `3` | Create `All Ports`, `Port Utilisation`, and per-device sheets. |
| AV MAC and port report | `m` | Map selected VLAN MAC addresses to likely physical access ports. |
| Full MAC report | `e` | List all MAC entries by port, including child-switch uplinks. |
| IP and MAC report | `d` | List device-tracking bindings for selected VLANs. |
| Palantir Mode | `x` | Combine port, MAC, client IP, VLAN, and CDP data in one workbook. |

Palantir Mode keeps empty physical ports in the report.
It creates a separate row for each client address.
It flags missing correlations and VLAN mismatches.

## Other functions

- Search Catalyst Center Assurance for a MAC address.
- Search Catalyst Center Assurance for an IP address.
- Monitor access point movement.
- Export Cisco Identity Services Engine (ISE) endpoints.
- Export CDP topology to draw.io.
- Export Catalyst Center site and fabric topology to draw.io.
- Run custom read-only commands.

## Requirements

- Python 3.10 or later
- Network access to Cisco DNA Center or Cisco Catalyst Center
- A Catalyst Center account with API and Command Runner access
- Graphviz for automatic CDP topology layout
- Cisco ISE access for the optional ISE inventory

## Installation

1. Clone the repository.

   ```bash
   git clone https://github.com/nickjennion/cheat.git
   cd cheat
   ```

2. Create a Python virtual environment.

   ```bash
   python3 -m venv .venv
   ```

3. Activate the virtual environment.

   Linux or macOS:

   ```bash
   source .venv/bin/activate
   ```

   Windows PowerShell:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

4. Install the Python packages.

   ```bash
   python -m pip install -r requirements.txt
   ```

5. Start CHEAT.

   ```bash
   python main.py
   ```

## Credential setup

CHEAT can request credentials at run time.
CHEAT can also read credentials from `dnac.env` or `dnac2.env`.

Copy the sample file to create the first profile:

```bash
cp sample_dnac.env dnac.env
```

Use this format:

```dotenv
DNAC_HOST=catalyst-center.example.com
DNAC_USERNAME=your_username
DNAC_PASSWORD=your_password
ISE_HOST=ise.example.com
ISE_VERSION=3.3_patch_1
```

The ISE values are optional.
The Git ignore rules exclude all `.env` files.

> [!WARNING]
> Credential files contain plaintext passwords.
> Restrict file access to the required user.
> Do not commit credential files.

## Basic workflow

1. Start `main.py`.
2. Select a Catalyst Center credential profile.
3. Fetch the device inventory.
4. Filter and select the required switches.
5. Select a report from Menu 5.
6. Review the command list and device list.
7. Confirm the operation.
8. Open the report in `excel_reports/`.

Use Menu 5 option `r` to request a new authentication token.
The refresh request uses a new HTTP session.
The client keeps the previous token if the refresh fails.

## Palantir Mode

Palantir Mode sends these data requests:

- Standard interface inventory commands
- `show cdp neighbors detail`
- `show mac address-table`
- `show device-tracking database`
- `show ip device tracking all`
- `show ip arp`
- `show vlan brief`
- `show interfaces vlan`

Catalyst Center accepts a maximum of five Command Runner commands in one request.
CHEAT splits larger command sets into sequential batches for each device.
CHEAT still processes different devices concurrently.

Palantir Mode creates these sheets:

- `All Ports`
- `Port Utilisation`
- `VLAN Inventory`
- One sheet for each selected stack

Palantir Mode also creates a tiered CDP topology in `drawio_exports/`.

The output can include these fields:

- Switch and stack member
- Interface and description
- Interface state and protocol
- Port VLAN and client VLAN
- MAC address and MAC type
- Client IP address
- MAC manufacturer (from the bundled OUI Master Database)

The manufacturer lookup uses the compressed `data/oui-master.tsv.gz` snapshot
from [OUI-Master-Database](https://github.com/Ringmast4r/OUI-Master-Database).
Set `CHEAT_OUI_DATABASE` to use a different compatible TSV/TSV.GZ file.
- Device-tracking state
- CDP device type and neighbor
- Traffic counters and last input
- Correlation notes

The client IP fields depend on the switch device-tracking output.
CHEAT reports switches that return no recognized device-tracking rows.

## Session controls

Menu 5 provides these session controls:

| Control | Key | Function |
|---|---:|---|
| Slow mode | `s` | Use longer polling and submission times. |
| Copper-only filter | `p` | Exclude non-copper interfaces from port reports. |
| Link-state data | `l` | Add recent link-change information. |
| Concurrency | `c` | Select one to five concurrent device jobs. |
| Token refresh | `r` | Request a new Catalyst Center token. |

These controls do not persist after the program exits.

## Generated files

| Path | Content | Git behavior |
|---|---|---|
| `all_devices.json` | Catalyst Center device inventory | Ignored |
| `command_runner_outputs/command_output_*.txt` | Combined raw command output for each device | Ignored |
| `excel_reports/*.xlsx` | Excel reports | Ignored |
| `excel_reports/*.csv` | CSV exports | Not ignored |
| `drawio_exports/*.drawio` | Topology diagrams | Tracked by default |
| `token.env` | Last successful authentication token | Ignored |

> [!CAUTION]
> `token.env` contains a live access token.
> Do not copy this file to a shared system.
> Delete the file when you no longer require the token.

CSV exports can contain network and client data.
The Git ignore rules do not exclude CSV files.
Review each CSV file before you add files to a commit.

## Graphviz setup

The CDP topology export uses the Graphviz `dot` command.
Install Graphviz separately from the Python packages.

Debian or Ubuntu:

```bash
sudo apt install graphviz
```

RHEL or Fedora:

```bash
sudo dnf install graphviz
```

macOS:

```bash
brew install graphviz
```

Windows:

```powershell
winget install Graphviz.Graphviz
```

Add the Graphviz `bin` directory to `PATH` when the installer does not add it.
CHEAT skips the CDP diagram when it cannot find `dot`.
Other reports continue normally.

## Security notes

- CHEAT sends credentials only to the configured Catalyst Center or ISE host.
- CHEAT sends the Catalyst Center token in the `X-Auth-Token` header.
- CHEAT uses read-only network commands.
- CHEAT stores raw command output on the local computer.
- CHEAT disables Transport Layer Security certificate verification by default.

> [!WARNING]
> Disabled certificate verification can expose the connection to interception.
> Use CHEAT only on a trusted management network until certificate verification is enabled.

## Test the project

Run the offline automated tests:

```bash
pytest -q --ignore=test_dnac.py --ignore=test_mock_dnac.py --ignore=test_sandbox.py
```

Run the mock end-to-end harness:

```bash
python test_mock_dnac.py
```

Run `test_dnac.py` only against an authorized Catalyst Center system.
The script requests credentials interactively.

Run `test_sandbox.py` only when you want to use the Cisco DevNet sandbox.

## Project structure

| Area | Main files | Purpose |
|---|---|---|
| User interface | `main.py`, `main_cli.py` | Manage credentials, device selection, and report actions. |
| API access | `dnac_client.py`, `ise_client.py` | Access Catalyst Center and ISE. |
| Command execution | `cheat_core.py`, `cheat_constants.py` | Batch, run, poll, and save command jobs. |
| Port parsing | `interface_parser.py`, `port_utilisation.py` | Parse interfaces and calculate port use. |
| Client correlation | `mac_table.py`, `mac_by_port.py`, `device_tracking.py`, `ip_mac_report.py`, `palantir_report.py` | Correlate ports, MAC addresses, IP addresses, and VLANs. |
| Excel export | `excel_generator.py`, `consolidate_report.py` | Create formatted workbooks and CSV files. |
| Topology export | `cdp_detail.py`, `cdp_topology.py`, `topology_dot.py`, `drawio_generator.py` | Build CDP and site topology diagrams. |
| Access point monitoring | `ap_monitor.py` | Detect access point movement. |
| Tests | `test_*.py`, `fixtures/` | Verify parsing, correlation, export, and API behavior. |

## Operational defaults

| Operation | Default |
|---|---:|
| Authentication timeout | 10 seconds |
| Device-list timeout | 30 seconds |
| Command-submission timeout | 10 seconds |
| Commands in each Command Runner request | 5 |
| Task-poll interval | 1 second |
| Task-poll limit | 30 attempts |
| Concurrent device jobs | 2 |
| Maximum concurrent device jobs | 5 |
| HTTP retry count | 3 |

Slow mode changes the submission timeout to 20 seconds.
Slow mode changes the poll interval to 3 seconds.
Slow mode changes the poll limit to 60 attempts.

## Troubleshooting

### Authentication returns HTTP 401

Confirm the username and password.
Confirm that the account has Catalyst Center API access.
Confirm that the configured host is correct.
Use Menu 5 option `r` to request a new token.

An expired API token does not authenticate the refresh request.
The refresh request uses the stored username and password.

### A report contains no client IP addresses

Open the latest file in `command_runner_outputs/`.
Find the output from `show device-tracking database` or `show ip device tracking all`.
Confirm that the switch returns IP, MAC, VLAN, and interface data.
The exact output format can vary between switch software releases.

### Palantir Mode fails during command submission

Confirm that the runtime environment contains commit `580574a` or a later commit.
That commit adds the five-command batching requirement.

### The topology diagram is missing

Run `dot -V`.
Install Graphviz when the command is not available.

## Change history

See [CHANGELOG.md](CHANGELOG.md) for the project history.
