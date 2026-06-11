# CHEAT UNPLUGGED

**Part of the CHEAT Product Family**

A Python CLI tool for discovering and managing unused network ports in Cisco DNA Center (DNAC). Executes diagnostic commands, parses interface inventory, and generates Excel reports to support enterprise cable unplugging and fleet upgrade workflows.

## About CHEAT

**CHEAT** (Cisco Homogeneous Environmental Awareness Tool) is a family of network management utilities for large-scale infrastructure changes. Current tools:

- **CHEAT UNPLUGGED** (this tool) - Discovers unused ports in DNAC, prepares for safe decommissioning
- **CHEAT LINK** (planned) - Discovers devices via CDP not yet in DNAC (shadow inventory detection)

## Features

- **Device Discovery**: Query DNAC for network devices by hostname, display full inventory (model, IP, serial, UUID)
- **Batch Operations**: Select single or multiple devices for command execution
- **Standardized Diagnostics**: Automatically runs four diagnostic commands:
  - `show hardware` (stack/module info, uptime)
  - `show interfaces` (port state, protocols, descriptions)
  - `show interfaces status` (VLAN assignments)
  - `show interface counters` (traffic activity)
- **Command Runner Integration**: Executes commands via DNAC Command Runner with 30-second polling
- **Automatic Parsing**: Parses raw outputs into structured data
- **Excel Reporting**: Generates "unpatching list" with:
  - One sheet per device
  - Interface state, description, VLAN, traffic indicators
  - Stack member uptime tracking
  - Color-coded highlights: green (connected), yellow (not connected), red (error-disabled), gold (active traffic), orange (short uptime)
- **Persistent Inventory**: Saves device list and raw command outputs for audit/reference

## Requirements

- Python 3.8+
- `requests` library (HTTP client)
- `openpyxl` library (Excel generation)

## Installation (Windows Store Python)

1. Open PowerShell or Command Prompt
2. Navigate to the project directory
3. Install dependencies:
   ```powershell
   pip install --user -r requirements.txt
   ```

> **Note**: On Windows, use `pip install --user` instead of `sudo pip` to avoid UAC elevation requirements.

## Usage

### Quick Start

Run CHEAT UNPLUGGED:
```powershell
python main.py
```

Or with explicit Python:
```powershell
python.exe main.py
```

### Full Workflow Example

```
============================================================
Cisco DNAC Device Query Tool
============================================================

Enter DNAC server hostname/IP: dnac.example.com
Enter username: admin
Enter password: ••••••••
Authenticating...
✓ Authentication successful

Fetching devices...
✓ Found 42 devices
✓ Saved 42 devices to all_devices.json

============================================================
Enter hostname filter (or 'quit'): switch
Found 8 device(s):

#  Hostname                 Model               IP Address      Serial
1  switch-core-01           WS-C3850-12X48U     10.0.1.1        ABC123456
2  switch-core-02           WS-C3850-12X48U     10.0.1.2        ABC123457
3  switch-access-01         WS-C3650-24TS       10.0.2.1        XYZ789001
...

Options:
  's' - Select single device
  'b' - Select batch of devices
  'f' - Filter and try again
  'q' - Quit

Choice: s
Enter device number: 1

============================================================
Executing commands on: switch-core-01
============================================================
Task ID: abc-def-123-456
Polling for results (30s timeout)...
  [1/30] Waiting...
  [2/30] Waiting...
  ...
✓ Output saved to command_output_switch-core-01_20260611_143022.txt

============================================================
Parsing command outputs and generating Excel...
============================================================

Parsing switch-core-01... ✓ 48 interfaces found

✓ Saved: unpatching_list_20260611_143022.xlsx
```

### Commands Executed

The tool automatically runs these four commands on selected devices:

1. `show hardware` - Stack member info, models, uptime, software versions
2. `show interfaces` - Interface states, protocols, descriptions, last input time
3. `show interfaces status` - Port status, VLAN assignments
4. `show interface counters` - Ingress octets (traffic activity)

## Output Files

### Automatic Outputs

- **all_devices.json**: Complete device inventory from DNAC (created after first successful authentication)
- **command_output_<hostname>_<timestamp>.txt**: Raw command output from Command Runner for each device
- **unpatching_list_<timestamp>.xlsx**: Parsed Excel report with one sheet per device

### Excel Report Contents

**Interfaces Sheet (per device):**
- Switch hostname
- Stack member number
- Hardware model
- Software version
- Member uptime (in days, highlighted if < 42 days)
- Interface name
- Description
- State (connected/disabled/err-disabled/notconnect)
- Protocol status
- VLAN assignment
- Input traffic (octets)
- Last input time
- "Suspect" flag (YES = has had traffic recently, highlighted in gold)

**Color Coding:**
- **Green**: Connected interfaces
- **Yellow**: Not connected interfaces
- **Gray**: Disabled interfaces
- **Red**: Error-disabled interfaces
- **Gold**: Interfaces with recent traffic
- **Orange**: Stack members with < 42 days uptime

## Security Notes

- Credentials are NOT stored anywhere
- They are only used for the current session
- SSL certificate verification is disabled by default (common for lab DNAC instances)
- The token expires with each session
- Command outputs are saved to files but not securely deleted; manage accordingly

## Troubleshooting

### Authentication Failed
- Verify DNAC server hostname/IP is correct and accessible
- Check username and password are correct
- Ensure DNAC is running and accessible from your network

### SSL Certificate Errors
- DNAC typically uses self-signed certificates
- SSL verification is disabled by default in this tool

### No Devices Found
- Verify your DNAC instance has discovered and added devices
- Check user permissions allow device viewing

## API Reference

The tool uses the following DNAC REST API endpoints:

- `POST /dna/system/api/v1/auth/token` - Authentication
- `GET /dna/intent/api/v1/network-device` - List all devices
- `GET /dna/intent/api/v1/network-device?hostname={hostname}` - Query by hostname

For more information, refer to the Cisco DNAC API documentation.
