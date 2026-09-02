from vlan_report import build_vlan_report


def test_build_vlan_report_extracts_vlan_svi_and_arp_clients():
    raw = {
        "sw-a": "\n".join([
            "show vlan brief",
            "VLAN Name                             Status    Ports",
            "101  Voice                            active    Gi1/0/1",
            "501  AV                               active    Gi1/0/2",
            "show interfaces vlan",
            "Vlan501 is administratively down, line protocol is down , Autostate Enabled",
            "  Description: AV SVI",
            "  Internet address is 192.0.2.126/26",
            "show mac address-table",
            " 501    aaaa.bbbb.cccc    DYNAMIC     Gi1/0/2",
            "show ip arp",
            "Internet 192.0.2.10 0 aaaa.bbbb.cccc ARPA Gi1/0/2",
        ])
    }

    rows = build_vlan_report(raw)
    vlan = next(row for row in rows if row.vlan == "501")
    assert vlan.name == "AV"
    assert vlan.description == "AV SVI"
    assert vlan.subnet == "192.0.2.64/26"
    assert vlan.gateway == "192.0.2.126"
    assert vlan.client_count == 1
    assert "192.0.2.10" in vlan.clients
