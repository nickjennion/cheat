# Cisco DNAC Device Query Tool

A lightweight Python CLI tool for querying Cisco DNA Center (DNAC) devices with interactive authentication and hostname-based filtering.

## Features

- **Interactive Authentication**: Prompts for DNAC server, username, and password (credentials are not saved)
- **Token-Based Access**: Uses DNAC REST API with session tokens
- **Device Enumeration**: Fetches and displays all reachable devices
- **Persistent Storage**: Saves device inventory to `all_devices.json` for offline reference
- **Interactive Filtering**: Query devices by hostname with substring matching
- **Formatted Output**: Clean tabular display of device information

## Requirements

- Python 3.8+
- `requests` library

## Installation (Windows Store Python)

1. Open PowerShell or Command Prompt
2. Navigate to the project directory
3. Install dependencies:
   ```powershell
   pip install --user -r requirements.txt
   ```

> **Note**: On Windows, use `pip install --user` instead of `sudo pip` to avoid UAC elevation requirements.

## Usage

Run the tool:
```powershell
python main.py
```

Or with explicit Python:
```powershell
python.exe main.py
```

### Interactive Prompts

1. **DNAC Server**: Enter the hostname or IP address of your DNAC instance
2. **Username**: Enter your DNAC username
3. **Password**: Enter your password (input is hidden)
4. **Hostname Filter**: Search for devices by hostname substring (case-insensitive)

Example:
```
Enter DNAC server hostname/IP: dnac.example.com
Enter username: admin
Enter password: ••••••••
Authenticating...
✓ Authentication successful

Fetching devices...
✓ Found 42 devices
✓ Saved 42 devices to all_devices.json

============================================================
Enter hostname filter (or 'quit' to exit): switch
Found 8 device(s) matching 'switch':

Hostname                   IP Address      Type                Status
---------------------------------------------------------------------------
switch-core-01             10.0.1.1        Switches and Hubs   Reachable
switch-core-02             10.0.1.2        Switches and Hubs   Reachable
switch-access-01           10.0.2.1        Switches and Hubs   Reachable
...
```

## Output Files

- **all_devices.json**: Complete device inventory from DNAC (created after first successful authentication)

## Security Notes

- Credentials are NOT stored anywhere
- They are only used for the current session
- SSL certificate verification is disabled by default (common for lab DNAC instances)
- The token expires with each session

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
