"""Menu wiring for the ISE endpoint-inventory action."""

import inspect


def test_action_ise_endpoints_signature():
    import main_latest
    assert callable(main_latest.action_ise_endpoints)
    sig = inspect.signature(main_latest.action_ise_endpoints)
    assert list(sig.parameters) == ["host", "username", "password", "ise_host", "ise_version"]
    assert sig.parameters["ise_host"].default == ""
    assert sig.parameters["ise_version"].default == ""


def test_ise_default_version_constant():
    import main_latest
    assert main_latest.ISE_DEFAULT_VERSION == "3.3_patch_1"


def test_menu_2_offers_ise_endpoint_inventory():
    import main_latest
    src = inspect.getsource(main_latest.menu_2)
    assert "5) ISE — Endpoint Inventory" in src
    assert "action_ise_endpoints" in src
    assert "Select [0-5]" in src


def test_menu_1_returns_five_tuple_with_ise_settings():
    import main_latest
    src = inspect.getsource(main_latest.menu_1)
    assert "ise_host, ise_version = load_ise_settings_from_env" in src
    assert "Select [1-6]" in src


def test_ise_exports_imported():
    import main_latest
    assert callable(main_latest.write_ise_endpoint_excel)
    assert callable(main_latest.write_ise_endpoint_csv)
