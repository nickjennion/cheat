"""Menu 5 wiring for the IP/MAC per VLAN export, plus the helpers it shares with m)."""

import inspect
from pathlib import Path


def test_device_tracking_command_defined():
    import cheat_core
    assert cheat_core.DEVICE_TRACKING_COMMANDS == ["show device-tracking database"]


def test_action_exists_with_expected_signature():
    import main
    assert callable(main.action_ip_mac_export)
    sig = inspect.signature(main.action_ip_mac_export)
    assert list(sig.parameters) == ["selected_devices", "client", "concurrency"]
    assert sig.parameters["concurrency"].default == main.DEFAULT_CONCURRENCY


def test_av_export_signature_unchanged_by_the_helper_extraction():
    import main
    sig = inspect.signature(main.action_av_mac_export)
    assert list(sig.parameters) == ["selected_devices", "client", "concurrency"]
    assert sig.parameters["concurrency"].default == main.DEFAULT_CONCURRENCY


def test_menu_5_offers_the_new_export():
    import main
    src = inspect.getsource(main.menu_5)
    assert "d) IP/MAC per VLAN export (device tracking)" in src
    assert "m) MAC/port export (for AV)" in src          # m) still there
    assert "/ d /" in src                                 # prompt advertises the key


# ------------------------------------------------------------------ _prompt_vlans

def test_prompt_vlans_accepts_space_separated(monkeypatch):
    import main
    monkeypatch.setattr("builtins.input", lambda *a: "900 905")
    assert main._prompt_vlans() == ["900", "905"]


def test_prompt_vlans_accepts_comma_separated(monkeypatch):
    import main
    monkeypatch.setattr("builtins.input", lambda *a: "900,905")
    assert main._prompt_vlans() == ["900", "905"]


def test_prompt_vlans_rejects_non_numeric(monkeypatch):
    import main
    monkeypatch.setattr("builtins.input", lambda *a: "900 voice")
    assert main._prompt_vlans() == []


def test_prompt_vlans_blank_cancels(monkeypatch):
    import main
    monkeypatch.setattr("builtins.input", lambda *a: "   ")
    assert main._prompt_vlans() == []


# ------------------------------------------------------- _timestamped_excel_path

def test_timestamped_excel_path_lands_in_the_report_dir(tmp_path, monkeypatch):
    import main
    monkeypatch.chdir(tmp_path)
    out = Path(main._timestamped_excel_path("av-export.xlsx"))
    assert out.parent == (tmp_path / "excel_reports").resolve()
    assert out.parent.is_dir()          # created for us
    assert out.name.startswith("av-export-")
    assert out.suffix == ".xlsx"


def test_timestamped_excel_path_strips_any_given_extension(tmp_path, monkeypatch):
    import main
    monkeypatch.chdir(tmp_path)
    out = Path(main._timestamped_excel_path("report.xlsx"))
    assert ".xlsx-" not in out.name
    assert out.name.count(".xlsx") == 1
