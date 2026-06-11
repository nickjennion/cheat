# CHEAT Product Family

**Cisco Homogeneous Environmental Awareness Tool**

A suite of Python utilities for managing large-scale Cisco network infrastructure changes, including device discovery, inventory management, and safe decommissioning workflows.

## Family Overview

### CHEAT UNPLUGGED (Current Release)

**Purpose**: Discover unused network ports in DNAC inventory and prepare for safe unplugging during fleet upgrades.

**Workflow**:
1. Authenticate with DNAC
2. Query device inventory
3. Filter by hostname
4. Select device(s) for inspection
5. Execute diagnostic commands via Command Runner
6. Auto-parse outputs
7. Generate Excel "unpatching list" with interface details and traffic indicators

**Output**: `unpatching_list_<timestamp>.xlsx` — one sheet per device with interface inventory, uptime tracking, and problem highlighting.

**Key Technology**: DNAC REST API + Command Runner

---

### CHEAT LINK (Planned)

**Purpose**: Discover network devices via CDP (Cisco Discovery Protocol) that are not yet in DNAC inventory — identifying shadow infrastructure and devices missed by automated discovery.

**Anticipated Workflow**:
1. Query existing DNAC device inventory
2. Authenticate with known devices
3. Walk CDP neighbor tables
4. Compare discovered devices against DNAC
5. Report on devices found via CDP but missing from DNAC
6. Generate audit report

**Key Technology**: CDP neighbor discovery + DNAC API

---

## Design Philosophy

- **Modular family**: Each CHEAT tool solves a specific problem but works together
- **Complementary workflows**: LINK discovers everything, UNPLUGGED safely manages known inventory
- **Enterprise-focused**: Designed for large organizations with complex upgrade/decommission projects
- **No credential storage**: All authentication is session-based, interactive
- **Audit trails**: Raw outputs and structured reports for compliance/troubleshooting

## Use Cases

### Pre-Upgrade Assessment
```
1. Run CHEAT LINK to identify all Cisco devices (including unknowns)
2. Ensure DNAC inventory matches reality
3. Remediate missing/shadow devices
```

### Safe Cable Unplugging
```
1. Run CHEAT UNPLUGGED on devices to be decommissioned
2. Review "unpatching list" for interface dependencies
3. Identify high-traffic ports (marked in gold)
4. Safely unplug with confidence
```

### Compliance & Audit
```
1. Run CHEAT UNPLUGGED on all managed devices
2. Collect baseline "unpatching lists"
3. Track changes over time
4. Audit decommissioning activity
```

## Directory Structure

```
flights2/
├── main.py                  # CHEAT UNPLUGGED application
├── dnac_client.py          # DNAC API client (shared)
├── requirements.txt        # Python dependencies
├── DNAC_README.md          # CHEAT UNPLUGGED detailed docs
├── CHEAT_FAMILY.md         # This file — product family overview
├── all_devices.json        # Device inventory (generated)
├── command_output_*.txt    # Raw command outputs (generated)
└── unpatching_list_*.xlsx  # Excel reports (generated)
```

## Future Tools in CHEAT Family

Potential additions:
- **CHEAT AUDIT** — Continuous compliance monitoring
- **CHEAT SYNC** — DNAC inventory reconciliation
- **CHEAT PLAN** — Safe change planning and dependency analysis

---

## Getting Started

See [DNAC_README.md](DNAC_README.md) for detailed setup and usage of CHEAT UNPLUGGED.

For CHEAT LINK, check back soon.
