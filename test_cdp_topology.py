SW1_CDP = "\n".join([
    "show cdp neighbors detail",
    "-------------------------",
    "Device ID: sw2",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet1/0/3,  Port ID (outgoing port): GigabitEthernet1/0/2",
    "-------------------------",
    "Device ID: sw3",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/2",
    "-------------------------",
    "Device ID: sw4",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet0/0,  Port ID (outgoing port): GigabitEthernet0/0",
    "-------------------------",
    "Device ID: deskphone",
    "Platform: Cisco IP Phone 6901,  Capabilities: Host Phone",
    "Interface: GigabitEthernet1/0/9,  Port ID (outgoing port): Port 1",
    "Total cdp entries displayed : 4",
])
# sw2 sees sw1 back on the reciprocal ports (tests bidirectional dedup).
SW2_CDP = "\n".join([
    "show cdp neighbors detail",
    "-------------------------",
    "Device ID: sw1",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): GigabitEthernet1/0/3",
    "Total cdp entries displayed : 1",
])


def _raw():
    return {"sw1": SW1_CDP, "sw2": SW2_CDP, "sw3": ""}


def test_build_topology_nodes_and_rogue_flag():
    from cdp_topology import build_topology
    topo = build_topology(_raw(), ["sw1", "sw2", "sw3"])
    by_name = {n.name: n for n in topo.nodes}
    assert set(by_name) == {"sw1", "sw2", "sw3", "sw4"}
    assert by_name["sw4"].is_rogue is True
    assert by_name["sw4"].platform == "C9KV-UADP"
    assert by_name["sw1"].is_rogue is False
    assert "deskphone" not in by_name  # phone (Capability H P) excluded


def test_build_topology_dedups_bidirectional_link():
    from cdp_topology import build_topology
    topo = build_topology(_raw(), ["sw1", "sw2", "sw3"])
    # sw1<->sw2 seen from both ends must collapse to ONE edge.
    sw1_sw2 = [e for e in topo.edges
               if {e.a, e.b} == {"sw1", "sw2"}]
    assert len(sw1_sw2) == 1
    e = sw1_sw2[0]
    assert {e.a_port, e.b_port} == {"Gi1/0/3", "Gi1/0/2"}
    # Three switch links total: sw1-sw2, sw1-sw3, sw1-sw4.
    assert len(topo.edges) == 3
    rogue_edge = [e for e in topo.edges if "sw4" in (e.a, e.b)]
    assert len(rogue_edge) == 1


def test_generate_cdp_topology_writes_multipage(tmp_path, monkeypatch):
    import shutil
    if shutil.which("dot") is None:
        import pytest
        pytest.skip("graphviz 'dot' not installed")
    import cheat_core, xml.etree.ElementTree as ET
    monkeypatch.chdir(tmp_path)
    ok, msg = cheat_core.generate_cdp_topology(_raw(), _raw().keys(), "topo")
    assert ok is True
    path = msg.split("CDP topology: ")[1].split(" (")[0]
    from pathlib import Path
    assert Path(path).is_file() and path.endswith("-cdp-topology.drawio")
    root = ET.fromstring(Path(path).read_text(encoding="utf-8").split("?>", 1)[1])
    assert root.tag == "mxfile" and root.findall("diagram")   # >= 1 page


def test_find_dot_env_override(tmp_path, monkeypatch):
    import cheat_core
    fake = tmp_path / "mydot"
    fake.write_text("")
    monkeypatch.delenv("GRAPHVIZ_DOT", raising=False)
    monkeypatch.setenv("DOT", str(fake))
    assert cheat_core._find_dot() == str(fake)


def test_find_dot_graphviz_dot_env_override(tmp_path, monkeypatch):
    import cheat_core
    fake = tmp_path / "mydot"
    fake.write_text("")
    monkeypatch.delenv("DOT", raising=False)
    monkeypatch.setenv("GRAPHVIZ_DOT", str(fake))
    assert cheat_core._find_dot() == str(fake)


def test_find_dot_bad_env_falls_through_to_path(monkeypatch):
    import cheat_core
    # A stale/invalid env override must NOT be returned — fall through to PATH.
    monkeypatch.setenv("DOT", "/nonexistent/dot_does_not_exist")
    monkeypatch.delenv("GRAPHVIZ_DOT", raising=False)
    monkeypatch.setattr(cheat_core.shutil, "which", lambda name: "/usr/bin/dot")
    assert cheat_core._find_dot() == "/usr/bin/dot"


def test_find_dot_uses_path(monkeypatch):
    import cheat_core
    monkeypatch.delenv("DOT", raising=False)
    monkeypatch.delenv("GRAPHVIZ_DOT", raising=False)
    monkeypatch.setattr(cheat_core.shutil, "which", lambda name: "/usr/bin/dot")
    assert cheat_core._find_dot() == "/usr/bin/dot"


def test_find_dot_windows_fallback(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.delenv("DOT", raising=False)
    monkeypatch.delenv("GRAPHVIZ_DOT", raising=False)
    monkeypatch.setattr(cheat_core.shutil, "which", lambda name: None)
    fake = tmp_path / "dot.exe"
    fake.write_text("")
    monkeypatch.setattr(cheat_core, "_DOT_CANDIDATES", [str(fake)])
    assert cheat_core._find_dot() == str(fake)


def test_find_dot_none(monkeypatch):
    import cheat_core
    monkeypatch.delenv("DOT", raising=False)
    monkeypatch.delenv("GRAPHVIZ_DOT", raising=False)
    monkeypatch.setattr(cheat_core.shutil, "which", lambda name: None)
    monkeypatch.setattr(cheat_core, "_DOT_CANDIDATES", [])
    assert cheat_core._find_dot() is None


def test_generate_cdp_topology_falls_back_when_primary_fails(tmp_path, monkeypatch):
    import shutil
    if shutil.which("dot") is None:
        import pytest
        pytest.skip("graphviz 'dot' not installed")
    import cheat_core, glob, xml.etree.ElementTree as ET
    monkeypatch.chdir(tmp_path)
    real_run_dot = cheat_core._run_dot

    def flaky(dot_str, dot_exe):
        # simulate the primary (spline) layout failing; ortho fallback still works
        if "splines=spline" in dot_str:
            return None
        return real_run_dot(dot_str, dot_exe)

    monkeypatch.setattr(cheat_core, "_run_dot", flaky)
    ok, _ = cheat_core.generate_cdp_topology(_raw(), _raw().keys(), "fb")
    assert ok is True   # page still rendered via the spline/ortho fallback
    root = ET.fromstring(
        open(glob.glob("drawio_exports/*.drawio")[0], encoding="utf-8").read().split("?>", 1)[1])
    assert any(d.get("name") == "Overview" for d in root.findall("diagram"))


def test_generate_cdp_topology_skips_without_dot(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cheat_core, "_find_dot", lambda: None)
    ok, msg = cheat_core.generate_cdp_topology(_raw(), _raw().keys(), "topo")
    assert ok is False
    assert "Graphviz" in msg
    from pathlib import Path
    assert not list(Path(tmp_path).glob("**/*.drawio"))


def test_generate_cdp_topology_skips_when_no_scanned(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.chdir(tmp_path)
    ok, msg = cheat_core.generate_cdp_topology({}, [], "topo")
    assert ok is False
    from pathlib import Path
    assert not list(Path(tmp_path).glob("**/*.drawio"))


def test_build_topology_rogue_carries_feeding_description():
    from cdp_topology import build_topology
    raw = {"sw1": "\n".join([
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: rogue1",
        "Platform: cisco WS-C3560C,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/0/5,  Port ID (outgoing port): GigabitEthernet0/1",
        "Total cdp entries displayed : 1",
    ])}
    descriptions = {("sw1", "Gi1/0/5"): "Link to comms cab"}
    topo = build_topology(raw, ["sw1"], descriptions)
    r = {n.name: n for n in topo.nodes}["rogue1"]
    assert r.is_rogue is True
    assert r.description == "Link to comms cab"


def test_build_topology_rogue_without_description_omits_blank_label_line():
    from cdp_topology import build_topology
    from topology_dot import node_label
    raw = {"sw1": "\n".join([
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: rogue1",
        "Platform: cisco WS-C3560C,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/0/5,  Port ID (outgoing port): GigabitEthernet0/1",
        "Total cdp entries displayed : 1",
    ])}
    # descriptions present but with no entry for the rogue's feeding port.
    descriptions = {("sw1", "Gi1/0/9"): "Unrelated port"}
    topo = build_topology(raw, ["sw1"], descriptions)
    r = {n.name: n for n in topo.nodes}["rogue1"]
    assert r.description == ""
    label = node_label(r)
    assert "" not in label.split("\n"), f"blank line in label: {label!r}"
    assert label == "rogue1\nWS-C3560C\n(unscanned)"


def test_generate_cdp_topology_rogue_label_has_description(tmp_path, monkeypatch):
    import shutil
    if shutil.which("dot") is None:
        import pytest
        pytest.skip("graphviz 'dot' not installed")
    import cheat_core
    monkeypatch.chdir(tmp_path)
    raw = {"sw1": "\n".join([
        "show interfaces",
        "GigabitEthernet1/0/5 is up, line protocol is up (connected)",
        "  Description: UPLINK TO ROGUE CAB",
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: rogueX",
        "Platform: cisco WS-C3560C,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/0/5,  Port ID (outgoing port): GigabitEthernet0/1",
        "Total cdp entries displayed : 1",
    ])}
    ok, _ = cheat_core.generate_cdp_topology(raw, list(raw.keys()), "d")
    assert ok is True
    import glob
    xml = open(glob.glob("drawio_exports/*.drawio")[0], encoding="utf-8").read()
    assert "UPLINK TO ROGUE CAB" in xml


def test_build_topology_rogue_carries_mgmt_ip():
    from cdp_topology import build_topology
    # sw1 sees rogue sw4 with a management IP in its CDP detail block.
    raw = {"sw1": "\n".join([
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: sw4",
        "Entry address(es):",
        "  IP address: 10.1.2.3",
        "Platform: cisco WS-C3560CX-8PC-S,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet0/1,  Port ID (outgoing port): GigabitEthernet0/0",
        "Total cdp entries displayed : 1",
    ])}
    topo = build_topology(raw, ["sw1"])
    sw4 = {n.name: n for n in topo.nodes}["sw4"]
    assert sw4.is_rogue is True
    assert sw4.mgmt_ip == "10.1.2.3"
    assert sw4.platform == "WS-C3560CX-8PC-S"
