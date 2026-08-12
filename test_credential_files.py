"""Dual-DNAC credential files — Menu 1 options 1/2/3/5.

Legacy credentials live in dnac.env, the new controller's in dnac2.env, both
using the same three DNAC_* keys. ENV_FILE / ENV_FILE_NEW are relative paths,
so monkeypatch.chdir(tmp_path) is enough to isolate every test (same approach
as test_cdp_topology.py).
"""

import inspect
from pathlib import Path


LEGACY_TEXT = (
    "DNAC_HOST=legacy.example.net\n"
    "DNAC_USERNAME=legacy-user\n"
    "DNAC_PASSWORD=legacy-secret\n"
)
LEGACY_CREDS = ("legacy.example.net", "legacy-user", "legacy-secret")

NEW_TEXT = (
    "DNAC_HOST=new.example.net\n"
    "DNAC_USERNAME=new-user\n"
    "DNAC_PASSWORD=new-secret\n"
)
NEW_CREDS = ("new.example.net", "new-user", "new-secret")


# ---------------------------------------------------------------- file paths

def test_env_file_new_points_at_dnac2():
    import main_latest
    assert main_latest.ENV_FILE_NEW == Path("dnac2.env")
    assert main_latest.ENV_FILE == Path("dnac.env")


# ------------------------------------------------------------------- loading

def test_load_reads_the_named_file(tmp_path, monkeypatch):
    import main_latest
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dnac2.env").write_text(NEW_TEXT)
    assert main_latest.load_credentials_from_env(main_latest.ENV_FILE_NEW) == NEW_CREDS


def test_load_defaults_to_the_legacy_file(tmp_path, monkeypatch):
    import main_latest
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dnac.env").write_text(LEGACY_TEXT)
    assert main_latest.load_credentials_from_env() == LEGACY_CREDS


def test_load_new_never_falls_back_to_legacy(tmp_path, monkeypatch):
    """A missing dnac2.env must not silently hand back legacy credentials —
    that would point the session at the wrong controller."""
    import main_latest
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dnac.env").write_text(LEGACY_TEXT)
    assert main_latest.load_credentials_from_env(main_latest.ENV_FILE_NEW) is None


def test_load_returns_none_when_a_key_is_missing(tmp_path, monkeypatch):
    import main_latest
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dnac2.env").write_text(
        "DNAC_HOST=new.example.net\nDNAC_USERNAME=new-user\n"
    )
    assert main_latest.load_credentials_from_env(main_latest.ENV_FILE_NEW) is None


# -------------------------------------------------------------------- saving

def test_save_writes_only_the_named_file(tmp_path, monkeypatch):
    import main_latest
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "dnac.env"
    legacy.write_text(LEGACY_TEXT)

    assert main_latest.save_credentials_to_env(
        *NEW_CREDS, env_file=main_latest.ENV_FILE_NEW) is True

    assert main_latest.load_credentials_from_env(main_latest.ENV_FILE_NEW) == NEW_CREDS
    assert legacy.read_text() == LEGACY_TEXT      # legacy left untouched


def test_save_defaults_to_the_legacy_file(tmp_path, monkeypatch):
    import main_latest
    monkeypatch.chdir(tmp_path)
    assert main_latest.save_credentials_to_env(*LEGACY_CREDS) is True
    assert (tmp_path / "dnac.env").exists()
    assert not (tmp_path / "dnac2.env").exists()


# ------------------------------------------------------------------- viewing

def test_print_env_file_masks_the_password(tmp_path, monkeypatch, capsys):
    import main_latest
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dnac2.env").write_text(NEW_TEXT)

    assert main_latest._print_env_file(main_latest.ENV_FILE_NEW) is True

    out = capsys.readouterr().out
    assert "dnac2.env" in out
    assert "DNAC_PASSWORD=********" in out
    assert "new-secret" not in out
    assert "DNAC_HOST=new.example.net" in out


def test_print_env_file_reports_a_missing_file(tmp_path, monkeypatch, capsys):
    import main_latest
    monkeypatch.chdir(tmp_path)
    assert main_latest._print_env_file(main_latest.ENV_FILE_NEW) is False
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------- save-target prompt

def test_prompt_save_target_blank_means_legacy(monkeypatch):
    import main_latest
    monkeypatch.setattr("builtins.input", lambda *a: "")
    assert main_latest._prompt_save_target() == main_latest.ENV_FILE


def test_prompt_save_target_one_means_legacy(monkeypatch):
    import main_latest
    monkeypatch.setattr("builtins.input", lambda *a: "1")
    assert main_latest._prompt_save_target() == main_latest.ENV_FILE


def test_prompt_save_target_two_means_new(monkeypatch):
    import main_latest
    monkeypatch.setattr("builtins.input", lambda *a: "2")
    assert main_latest._prompt_save_target() == main_latest.ENV_FILE_NEW


def test_prompt_save_target_reprompts_until_valid(monkeypatch):
    import main_latest
    answers = iter(["9", "banana", "2"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert main_latest._prompt_save_target() == main_latest.ENV_FILE_NEW


# ------------------------------------------------------------------ signatures

def test_loader_and_saver_take_an_env_file_parameter():
    import main_latest
    load_sig = inspect.signature(main_latest.load_credentials_from_env)
    assert load_sig.parameters["env_file"].default == main_latest.ENV_FILE

    save_sig = inspect.signature(main_latest.save_credentials_to_env)
    assert list(save_sig.parameters) == ["host", "username", "password", "env_file"]
    assert save_sig.parameters["env_file"].default == main_latest.ENV_FILE


# ---------------------------------------------------------------- menu wiring

def test_menu_1_offers_both_controllers():
    import main_latest
    src = inspect.getsource(main_latest.menu_1)
    assert "1) Use Legacy DNAC" in src
    assert "2) Use New DNAC" in src
    assert "3) Enter manually   · remember" in src
    assert "4) Enter manually   · forget" in src
    assert "5) View credential files" in src
    assert "6) Options" in src
    assert "Select [1-6]" in src
    assert "1) Use dnac.env" not in src
