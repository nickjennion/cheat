# CHEAT UNPLUGGED

Network port discovery and inventory tool for Cisco DNA Center (DNAC).

## Quick Start

```bash
python main.py
```

## What is CHEAT UNPLUGGED?

Query Cisco DNAC for devices, execute diagnostic commands, and generate Excel reports identifying unused/problematic network ports.

**Perfect for:**
- Pre-upgrade assessments
- Cable management planning
- Identifying unused ports before unplugging
- Creating audit trails for decommissioning

## Features

✓ Interactive DNAC authentication (no stored credentials)  
✓ Wildcard device filtering  
✓ Single and batch device selection with range support (1-5,7,9-12)  
✓ Automated command execution via DNAC Command Runner  
✓ Intelligent output parsing  
✓ Excel reports with color-coded interface analysis  
✓ CDP neighbor discovery  
✓ Support for stacked switches  

## Requirements

- Python 3.8+
- `requests` (HTTP client)
- `openpyxl` (Excel generation)

Install:
```bash
pip install --user -r requirements.txt
```

## Credentials

Create `dnac.env` in the project directory (optional):
```
DNAC_HOST=dnac.example.com
DNAC_USERNAME=admin
DNAC_PASSWORD=yourpassword
```

If not present, you'll be prompted for credentials interactively.

## Documentation

See [DNAC_README.md](DNAC_README.md) for detailed usage and API reference.

## File Structure

```
.
├── main.py                    # Production application
├── main_debug.py              # Debug version with detailed logging
├── dnac_client.py            # DNAC API client
├── interface_parser.py        # CLI output parsing
├── excel_generator.py         # Report generation
├── requirements.txt           # Dependencies
├── README.md                  # This file
│
├── all_devices.json          # Device inventory (generated)
├── command_output_*.txt      # Raw outputs (generated)
└── unpatching_list_*.xlsx    # Excel reports (generated)
```

## Security

- Credentials are never stored by the tool
- SSL verification disabled for lab DNAC instances
- Tokens expire at session end
- If using dnac.env, add it to `.gitignore`

