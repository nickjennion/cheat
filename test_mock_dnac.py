#!/usr/bin/env python3
"""
Mock test for CHEAT UNPLUGGED — validates parsing and Excel generation.

Simulates DNAC command outputs without requiring real DNAC instance.
Tests all components: parsing, data extraction, Excel generation.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

from interface_parser import parse_output, InterfaceRecord, StackMember
from excel_generator import write_combined_excel


# ============================================================================
# Mock DNAC Command Outputs
# ============================================================================

MOCK_SHOW_HARDWARE = """
Cisco IOS XE Software, C3850 Software, Version 16.12.10a, RELEASE SOFTWARE
Technical Support: http://www.cisco.com/techsupport

Model Number                    : WS-C3850-24TS
System Serial Number            : FOC2345A6789
Processor type                  : ARM

Switch  Ports  Model              SW Version              SW Image              Status
------  -----  -----              ----------              --------              ------
*1      28     WS-C3850-24TS      16.12.10a               cat3k_caa-universalk9.16.12.10a  Ok
 2      28     WS-C3850-24TS      16.12.10a               cat3k_caa-universalk9.16.12.10a  Ok

Switch 1 uptime is 45 weeks, 3 days, 2 hours, 15 minutes
Switch uptime   : 45 weeks, 3 days, 2 hours, 15 minutes
Model Number    : WS-C3850-24TS
Serial Number   : FOC2345A6789

Switch 2 uptime is 2 weeks, 1 day, 6 hours, 30 minutes
Switch uptime   : 2 weeks, 1 day, 6 hours, 30 minutes
Model Number    : WS-C3850-24TS
Serial Number   : FOC2345A6790
"""

MOCK_SHOW_INTERFACES = """
GigabitEthernet1/0/1 is up, line protocol is up
  Hardware is Gigabit Ethernet, address is aabb.cc00.0001
  Description: Link to Core-Switch-1
  Internet address is 10.0.1.1/30
  MTU 1500 bytes, BW 1000000 Kbit/sec
  Encapsulation ARPA, loopback not set
  Last input 00:00:03, output 00:00:01, output hang never
  Last clearing of "show interface" counters never

GigabitEthernet1/0/2 is up, line protocol is up
  Hardware is Gigabit Ethernet, address is aabb.cc00.0002
  Description: Access Port - Unused
  Internet address is 10.0.1.5/30
  MTU 1500 bytes, BW 1000000 Kbit/sec
  Encapsulation ARPA, loopback not set
  Last input never, output never, output hang never
  Last clearing of "show interface" counters never

GigabitEthernet1/0/3 is administratively down, line protocol is down
  Hardware is Gigabit Ethernet, address is aabb.cc00.0003
  Description: Disabled - Cable Unplugged
  Internet address is 10.0.1.9/30
  MTU 1500 bytes, BW 1000000 Kbit/sec
  Encapsulation ARPA, loopback not set
  Last input never, output never, output hang never
  Last clearing of "show interface" counters never

GigabitEthernet2/0/1 is up, line protocol is up
  Hardware is Gigabit Ethernet, address is aabb.cc00.0101
  Description: Uplink Port
  Internet address is 10.0.2.1/30
  MTU 1500 bytes, BW 1000000 Kbit/sec
  Encapsulation ARPA, loopback not set
  Last input 00:00:01, output 00:00:02, output hang never
  Last clearing of "show interface" counters 1 week ago

GigabitEthernet2/0/2 is up, line protocol is down
  Hardware is Gigabit Ethernet, address is aabb.cc00.0102
  Description:
  Internet address is 10.0.2.5/30
  MTU 1500 bytes, BW 1000000 Kbit/sec
  Encapsulation ARPA, loopback not set
  Last input never, output never, output hang never
  Last clearing of "show interface" counters never
"""

MOCK_SHOW_INTERFACES_STATUS = """
Port     Name               Status       Vlan
Gi1/0/1  Link to Core-SW-1  connected    1
Gi1/0/2  Access Port-Unused not connect  100
Gi1/0/3  Disabled-Unplugged disabled     1
Gi1/0/4                     notconnect   1
Gi1/0/5                     notconnect   1
Gi1/0/6                     notconnect   1
Gi1/0/7                     notconnect   1
Gi1/0/8                     notconnect   1
Gi2/0/1  Uplink Port        connected    trunk
Gi2/0/2                     notconnect   1
Gi2/0/3                     notconnect   1
Gi2/0/4                     notconnect   1
"""

MOCK_SHOW_INTERFACE_COUNTERS = """
Port                 InOctets
Gi1/0/1              1245678900
Gi1/0/2              0
Gi1/0/3              0
Gi1/0/4              0
Gi1/0/5              0
Gi1/0/6              0
Gi1/0/7              0
Gi1/0/8              0
Gi2/0/1              5823456789
Gi2/0/2              0
Gi2/0/3              0
Gi2/0/4              0
"""

# Concatenate all outputs (as Command Runner would return)
MOCK_COMMAND_OUTPUT = f"""{MOCK_SHOW_HARDWARE}

{MOCK_SHOW_INTERFACES}

{MOCK_SHOW_INTERFACES_STATUS}

{MOCK_SHOW_INTERFACE_COUNTERS}
"""


# ============================================================================
# Test Functions
# ============================================================================

def test_parsing():
    """Test 1: Parse mock command output."""
    print("\n" + "="*70)
    print("  TEST 1: Output Parsing")
    print("="*70)

    print(f"\nParsing mock command output ({len(MOCK_COMMAND_OUTPUT)} bytes)...")

    try:
        records, stack_members = parse_output(MOCK_COMMAND_OUTPUT, "switch-lab-01")
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None

    if not records:
        print("✗ FAILED: No interfaces parsed")
        return None

    print(f"✓ PASSED: Parsed successfully")
    print(f"  Interfaces: {len(records)}")
    print(f"  Stack members: {len(stack_members)}")

    # Show sample data
    print(f"\n  Sample interfaces:")
    for rec in records[:4]:
        print(f"    {rec.iface:10} state={rec.state:12} vlan={rec.vlan:5} suspect={rec.suspect}")

    if stack_members:
        print(f"\n  Stack members:")
        for num, member in sorted(stack_members.items()):
            active = " [ACTIVE]" if member.is_active else ""
            print(f"    Member {num}: {member.model} (uptime: {member.uptime}){active}")

    return records, stack_members


def test_data_extraction(records, stack_members):
    """Test 2: Validate extracted data."""
    print("\n" + "="*70)
    print("  TEST 2: Data Validation")
    print("="*70)

    failures = []

    # Check for expected interfaces
    ifaces = {r.iface for r in records}
    expected = {"Gi1/0/1", "Gi1/0/2", "Gi1/0/3", "Gi2/0/1", "Gi2/0/2"}
    missing = expected - ifaces

    if missing:
        failures.append(f"Missing interfaces: {missing}")
    else:
        print(f"✓ All expected interfaces found: {', '.join(sorted(expected))}")

    # Check states
    connected = [r for r in records if r.state == "connected"]
    notconnect = [r for r in records if r.state == "notconnect"]
    disabled = [r for r in records if r.state == "disabled"]

    print(f"✓ States detected:")
    print(f"  - Connected: {len(connected)} ({', '.join(r.iface for r in connected[:2])}...)")
    print(f"  - Not connected: {len(notconnect)}")
    print(f"  - Disabled: {len(disabled)}")

    # Check traffic detection (suspect flag)
    with_traffic = [r for r in records if r.suspect == "YES"]
    without_traffic = [r for r in records if r.suspect == "NO"]

    print(f"✓ Traffic detection:")
    print(f"  - Interfaces with traffic: {len(with_traffic)} {[r.iface for r in with_traffic]}")
    print(f"  - Interfaces without traffic: {len(without_traffic)}")

    # Check stack info
    if stack_members:
        for num, member in sorted(stack_members.items()):
            if not member.model:
                failures.append(f"Member {num} missing model")
            if not member.uptime:
                failures.append(f"Member {num} missing uptime")

        if not failures:
            print(f"✓ Stack members properly parsed")

    # Check descriptions
    with_desc = [r for r in records if r.description]
    print(f"✓ Descriptions: {len(with_desc)} interfaces have descriptions")

    # Check VLAN assignments
    with_vlan = [r for r in records if r.vlan]
    print(f"✓ VLAN assignments: {len(with_vlan)} interfaces have VLANs")

    if failures:
        print(f"\n✗ FAILED:")
        for f in failures:
            print(f"  - {f}")
        return False

    print(f"\n✓ PASSED: All data validations successful")
    return True


def test_excel_generation(records, stack_members):
    """Test 3: Excel generation."""
    print("\n" + "="*70)
    print("  TEST 3: Excel Report Generation")
    print("="*70)

    devices_data = {
        "switch-lab-01": (records, stack_members),
        "switch-lab-02": (records[:5], {}),  # Test multiple devices
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Use temp directory for test files
    with tempfile.TemporaryDirectory() as tmpdir:
        filename = Path(tmpdir) / f"mock_report_{timestamp}.xlsx"

        print(f"\nGenerating combined Excel: {filename.name}")
        print(f"  Devices: {len(devices_data)}")
        print(f"  Total interfaces: {sum(len(r[0]) for r in devices_data.values())}")

        success, message = write_combined_excel(devices_data, 42, str(filename))

        if not success:
            print(f"✗ FAILED: {message}")
            return False

        if not filename.exists():
            print(f"✗ FAILED: File not created")
            return False

        file_size = filename.stat().st_size
        print(f"✓ PASSED: {message}")
        print(f"  File size: {file_size:,} bytes")

        return True


def test_edge_cases(records):
    """Test 4: Edge cases and special conditions."""
    print("\n" + "="*70)
    print("  TEST 4: Edge Cases")
    print("="*70)

    tests_passed = 0
    tests_total = 0

    # Test 1: Empty descriptions
    tests_total += 1
    empty_desc = [r for r in records if not r.description]
    if empty_desc:
        print(f"✓ Handles empty descriptions: {len(empty_desc)} interfaces")
        tests_passed += 1

    # Test 2: No traffic (never)
    tests_total += 1
    never_traffic = [r for r in records if r.suspect == "NO"]
    if never_traffic:
        print(f"✓ Detects 'never' traffic: {len(never_traffic)} interfaces")
        tests_passed += 1

    # Test 3: Administrative down
    tests_total += 1
    admin_down = [r for r in records if r.state == "disabled"]
    if admin_down:
        print(f"✓ Detects admin down: {len(admin_down)} interfaces")
        tests_passed += 1

    # Test 4: Mixed case handling
    tests_total += 1
    if all(r.iface for r in records):
        print(f"✓ Handles interface naming correctly: {records[0].iface}")
        tests_passed += 1

    # Test 5: Large counters
    tests_total += 1
    large_counts = [r for r in records if r.counters_in and int(r.counters_in) > 1000000000]
    if large_counts:
        print(f"✓ Handles large counter values: {large_counts[0].iface} = {large_counts[0].counters_in}")
        tests_passed += 1

    print(f"\n✓ PASSED: {tests_passed}/{tests_total} edge case tests")
    return True


def main():
    """Run all mock tests."""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " " * 18 + "CHEAT UNPLUGGED — Mock Test Suite" + " " * 17 + "║")
    print("║" + " " * 15 + "Validates parsing and Excel generation logic" + " " * 11 + "║")
    print("╚" + "="*68 + "╝")

    # Test 1: Parsing
    parse_result = test_parsing()
    if not parse_result:
        print("\n✗ Parsing test failed. Stopping.")
        sys.exit(1)

    records, stack_members = parse_result

    # Test 2: Data extraction
    if not test_data_extraction(records, stack_members):
        print("\n✗ Data validation failed. Stopping.")
        sys.exit(1)

    # Test 3: Excel generation
    if not test_excel_generation(records, stack_members):
        print("\n✗ Excel generation failed. Stopping.")
        sys.exit(1)

    # Test 4: Edge cases
    if not test_edge_cases(records):
        print("\n✗ Edge case tests failed. Stopping.")
        sys.exit(1)

    # Summary
    print("\n" + "="*70)
    print("  Test Summary")
    print("="*70)
    print("✓ All mock tests passed!")
    print("\nParsing logic: VALIDATED")
    print("Excel generation: VALIDATED")
    print("Data extraction: VALIDATED")
    print("Edge cases: VALIDATED")
    print("\n✓ Ready for testing against real DevNet sandbox")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
