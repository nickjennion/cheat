import inspect
from pathlib import Path


def test_exec_and_report_has_concurrency_param():
    import main_latest
    sig = inspect.signature(main_latest._exec_and_report)
    assert "concurrency" in sig.parameters
    assert sig.parameters["concurrency"].default == main_latest.DEFAULT_CONCURRENCY


def test_concurrency_helpers_imported_in_main_latest():
    import main_latest
    assert main_latest.DEFAULT_CONCURRENCY == 2
    assert main_latest.next_concurrency(5) == 1
    assert main_latest.next_concurrency(2) == 3


def test_load_prefs_supplies_splash_design_default_for_old_prefs(tmp_path, monkeypatch):
    # An existing prefs.env written before SPLASH_DESIGN existed must merge over
    # DEFAULT_PREFS and yield the new default, not a missing key.
    import main_latest
    old = tmp_path / "prefs.env"
    old.write_text("SLOW_MODE=on\nCOLOURS=off\n")
    monkeypatch.setattr(main_latest, "PREFS_FILE", Path(old))
    prefs = main_latest.load_prefs()
    assert prefs["SPLASH_DESIGN"] == "mark"  # new key defaulted
    assert prefs["SLOW_MODE"] == "on"         # existing value preserved


def test_load_prefs_migrates_burger_to_mark(tmp_path, monkeypatch):
    # The co-brand design was renamed burger -> mark; a prefs.env written before
    # the rename must not leave a stale value on the Options -> J row.
    import main_latest
    old = tmp_path / "prefs.env"
    old.write_text("SPLASH_DESIGN=burger\nSLOW_MODE=on\n")
    monkeypatch.setattr(main_latest, "PREFS_FILE", Path(old))
    prefs = main_latest.load_prefs()
    assert prefs["SPLASH_DESIGN"] == "mark"
    assert prefs["SLOW_MODE"] == "on"   # untouched by the migration


def test_load_prefs_leaves_other_splash_designs_alone(tmp_path, monkeypatch):
    import main_latest
    old = tmp_path / "prefs.env"
    old.write_text("SPLASH_DESIGN=stacked\n")
    monkeypatch.setattr(main_latest, "PREFS_FILE", Path(old))
    assert main_latest.load_prefs()["SPLASH_DESIGN"] == "stacked"


def test_splash_design_cycle_starts_and_ends_at_mark():
    import main_latest
    assert main_latest.DEFAULT_PREFS["SPLASH_DESIGN"] == "mark"
    assert main_latest.next_splash_design("mark") == "lockup"
    assert main_latest.next_splash_design("lockup") == "stacked"
    assert main_latest.next_splash_design("stacked") == "generic"
    assert main_latest.next_splash_design("generic") == "mark"
    assert main_latest.next_splash_design("banana") == "mark"   # corrupt value
