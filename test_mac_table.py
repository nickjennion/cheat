MAC_TABLE_OUTPUT = "\n".join([
    "show mac address-table",
    "          Mac Address Table",
    "-------------------------------------------",
    "",
    "Vlan    Mac Address       Type        Ports",
    "----    -----------       --------    -----",
    " All    0100.0ccc.cccc    STATIC      CPU",
    " All    0100.0ccc.cccd    STATIC      CPU",
    " 900    0011.2233.4455    DYNAMIC     Gi1/0/24",
    " 900    aabb.ccdd.eeff    DYNAMIC     Gi2/0/12",
    "Total Mac Addresses for this criterion: 4",
])


def test_parse_mac_address_table_extracts_vlan_rows():
    from mac_table import parse_mac_address_table
    entries = parse_mac_address_table(MAC_TABLE_OUTPUT)
    assert [(e.vlan, e.mac, e.type, e.interface) for e in entries] == [
        ("900", "0011.2233.4455", "DYNAMIC", "Gi1/0/24"),
        ("900", "aabb.ccdd.eeff", "DYNAMIC", "Gi2/0/12"),
    ]


def test_parse_mac_address_table_derives_stack_member():
    from mac_table import parse_mac_address_table
    entries = parse_mac_address_table(MAC_TABLE_OUTPUT)
    assert entries[0].stack_member == "1"
    assert entries[1].stack_member == "2"


def test_parse_mac_address_table_skips_all_vlan_and_cpu_rows():
    from mac_table import parse_mac_address_table
    entries = parse_mac_address_table(MAC_TABLE_OUTPUT)
    assert all(e.vlan != "All" for e in entries)
    assert all(e.interface != "CPU" for e in entries)


def test_parse_mac_address_table_lowercases_mac():
    from mac_table import parse_mac_address_table
    text = "\n".join([
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
        " 10     AABB.CCDD.EEFF    STATIC      Gi1/0/1",
    ])
    entries = parse_mac_address_table(text)
    assert entries[0].mac == "aabb.ccdd.eeff"


def test_parse_mac_address_table_empty_text_returns_empty_list():
    from mac_table import parse_mac_address_table
    assert parse_mac_address_table("") == []
