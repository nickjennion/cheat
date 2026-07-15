import inspect


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
