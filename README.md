# CHEAT — Cisco Homogeneous Environmental Awareness Tool

A suite of network management utilities for large-scale Cisco infrastructure changes.

## Quick Links

- **[CHEAT UNPLUGGED](DNAC_README.md)** — Current tool for discovering unused ports and planning cable unplugging workflows
- **[CHEAT Product Family](CHEAT_FAMILY.md)** — Overview of the CHEAT suite, roadmap, and architecture
- **[CHEAT LINK](CHEAT_FAMILY.md#cheat-link-planned)** — Planned tool for CDP-based shadow device discovery

## What is CHEAT?

CHEAT is a family of Python CLI tools designed to help large organizations safely manage network infrastructure during major upgrades or decommissioning projects.

**Current Release:**

### CHEAT UNPLUGGED

Query Cisco DNAC for devices, run standardized diagnostics, and generate Excel reports identifying unused/problematic network ports.

**Perfect for:**
- Pre-upgrade assessments
- Cable management planning
- Identifying unused ports before unplugging
- Creating audit trails for decommissioning

**Quick start:**
```bash
python main.py
```

See [DNAC_README.md](DNAC_README.md) for full documentation.

---

## Requirements

- Python 3.8+
- `requests` (HTTP client)
- `openpyxl` (Excel generation)

Install:
```bash
pip install --user -r requirements.txt
```

## Key Features

✓ Interactive DNAC authentication (no stored credentials)  
✓ Device filtering and batch operations  
✓ Automated command execution via DNAC Command Runner  
✓ Intelligent output parsing  
✓ Excel reports with color-coded interface analysis  
✓ Support for stacked switches  

## File Structure

```
.
├── main.py                    # CHEAT UNPLUGGED application
├── dnac_client.py            # DNAC API client library
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── DNAC_README.md            # CHEAT UNPLUGGED detailed docs
├── CHEAT_FAMILY.md           # Product family overview & roadmap
│
├── all_devices.json          # Device inventory (generated)
├── command_output_*.txt      # Raw command outputs (generated)
└── unpatching_list_*.xlsx    # Excel reports (generated)
```

## Security Notes

- Credentials are entered interactively and never stored
- SSL verification disabled by default (typical for lab DNAC instances with self-signed certs)
- Command outputs are saved to files — manage file permissions accordingly
- Tokens expire at session end

## Roadmap

**CHEAT LINK** (coming soon)
- CDP-based device discovery
- Shadow inventory detection
- Identify devices in network but not in DNAC

**CHEAT AUDIT** (planned)
- Continuous compliance monitoring
- Track unplugging activity over time

---

For detailed CHEAT UNPLUGGED usage, see [DNAC_README.md](DNAC_README.md).

For product family context, see [CHEAT_FAMILY.md](CHEAT_FAMILY.md).
