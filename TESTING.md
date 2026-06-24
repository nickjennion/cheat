# CHEAT UNPLUGGED — Testing Guide

## Quick Start: Test Against DevNet Sandbox

### 1. Access Cisco DevNet Sandbox

1. Go to: https://developer.cisco.com/sandbox
2. Search for "Catalyst Center" or "DNA Center"
3. Click **"Always On"** or **"Reserve"**
   - Always On: Available immediately, no reservation needed
   - Reserve: Full admin access, requires ~10 min setup

### 2. Get Credentials

When you access the sandbox, you'll get:
- **Hostname/IP**: (e.g., `sandboxdnacenter.cisco.com`)
- **Username**: (usually `admin`)
- **Password**: (provided in sandbox details)

### 3. Run Test Suite

```bash
python test_dnac.py
```

Then enter the sandbox credentials when prompted.

---

## What Gets Tested

The test script validates all components:

| Test | What It Does | Expected Result |
|------|------|--------|
| **1. Authentication** | Logs into DNAC, gets token | ✓ Token received |
| **2. Device Discovery** | Queries all managed devices | ✓ Devices list returned |
| **3. Command Execution** | Runs 4 show commands via Command Runner | ✓ Output received |
| **4. Output Parsing** | Extracts interfaces, uptime, traffic data | ✓ Interface records created |
| **5. Excel Generation** | Creates formatted report with color coding | ✓ .xlsx file written |

---

## Test Output Example

```
======================================================================
  TEST 1: Authentication
======================================================================
Testing connection to: sandboxdnacenter.cisco.com
Username: admin
✓ PASSED: Authentication successful
  Token: JIUzI1NiIs...

======================================================================
  TEST 2: Device Discovery
======================================================================
Querying all devices from DNAC...
✓ PASSED: Found 5 devices

  First device:
    Hostname: cat9k-1
    IP: 10.10.20.175
    Model: Cisco Catalyst 9300
    Serial: ABC1234567
    UUID: a1b2c3d4-e5f6-47g8-h9i0...
...
```

---

## Troubleshooting

### "Authentication failed"
- Check credentials (DevNet passwords are case-sensitive)
- Verify network connectivity to sandbox
- Try "Always On" instead of "Reserve"

### "No devices found"
- Sandbox may be warming up (takes 1-2 min after reservation)
- Check that devices are actually added to DNAC
- Some Always On instances have 0 devices pre-configured

### "Command execution timed out"
- Sandbox may be slow during peak hours
- Command Runner takes ~30-60s to complete
- Try again in a few minutes

### "No interfaces parsed"
- Device may not support all 4 commands
- Different IOS versions output different formats
- Check raw output: `command_output_*.txt`

### "Excel generation failed"
- Check openpyxl is installed: `pip install --user openpyxl`
- Verify disk space and file permissions
- Check filename isn't too long (sheet names limited to 31 chars)

---

## Files Generated During Testing

```
test_report_<hostname>_<timestamp>.xlsx    # Excel report
command_output_<hostname>.txt              # Raw command output (if saved)
```

---

## Testing Checklist

Run through this before declaring tests complete:

- [ ] Authentication succeeds with DevNet credentials
- [ ] Device discovery returns at least 1 device
- [ ] Command execution completes within 60 seconds
- [ ] Parsing finds at least 1 interface
- [ ] Excel file is created and readable
- [ ] Excel has correct sheet name (device hostname)
- [ ] Color coding is visible (green, yellow, red, gold)
- [ ] No error messages in output

---

## Expected Behavior on Different Device Types

### Cisco Catalyst 9300/9500 (Modern)
- ✓ All 4 commands work
- ✓ Stack support (if stacked)
- ✓ Full interface inventory

### Older Catalyst 3850/3650
- ✓ All 4 commands work
- ✓ Stack support
- ✓ Full interface inventory

### Virtual/Lab Devices
- ⚠ May have limited interfaces
- ⚠ Some output formats may vary
- Parser should still work but may find fewer interfaces

---

## Next Steps After Testing

1. **If tests pass**: Ready for production use
2. **If parsing issues**: Review raw `command_output_*.txt` and refine regex patterns
3. **If command failures**: Check DNAC Command Runner permissions
4. **If Excel issues**: Verify openpyxl version and file permissions

---

## Support

For DevNet sandbox issues, see: https://developer.cisco.com/docs/sandbox/

For CHEAT UNPLUGGED issues, check the main README.md
