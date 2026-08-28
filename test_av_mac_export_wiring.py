import inspect


def test_av_mac_commands_defined():
    import cheat_core
    assert cheat_core.AV_MAC_COMMANDS == ["show mac address-table", "show cdp neighbors detail"]


def test_action_av_mac_export_exists_with_expected_signature():
    import main
    assert callable(main.action_av_mac_export)
    sig = inspect.signature(main.action_av_mac_export)
    assert list(sig.parameters) == ["selected_devices", "client", "concurrency"]
    assert sig.parameters["concurrency"].default == main.DEFAULT_CONCURRENCY


def test_action_mac_by_port_export_exists_with_expected_signature():
    import main
    assert callable(main.action_mac_by_port_export)
    sig = inspect.signature(main.action_mac_by_port_export)
    assert list(sig.parameters) == ["selected_devices", "client", "concurrency"]
    assert sig.parameters["concurrency"].default == main.DEFAULT_CONCURRENCY
