from cheat_core import build_command_list, DNAC_COMMANDS


class _StubClient:
    """Minimal DNACClient stand-in for run_commands tests (no network)."""

    def __init__(self, *, task_id="T1", result=None, file_output="OUTPUT TEXT"):
        self._task_id = task_id
        # A completed task carries endTime and a progress JSON with a fileId.
        self._result = result if result is not None else {
            "endTime": 1, "progress": '{"fileId": "F1"}',
        }
        self._file_output = file_output

    def execute_commands(self, device_id, commands, timeout=10):
        return self._task_id

    def get_task_result(self, task_id):
        return self._result

    def get_file_output(self, file_id):
        return self._file_output


def test_run_device_commands_success(tmp_path):
    from cheat_core import _run_device_commands
    host, out, msgs = _run_device_commands(
        {"hostname": "sw-a", "id": "D1"}, _StubClient(), ["show clock"],
        tmp_path, "TS", poll_timeout=3, poll_interval=0, submit_timeout=1,
    )
    assert host == "sw-a"
    assert out == "OUTPUT TEXT"
    assert (tmp_path / "command_output_sw-a_TS.txt").read_text() == "OUTPUT TEXT"
    assert any("saved" in m for m in msgs)


def test_run_device_commands_timeout(tmp_path):
    from cheat_core import _run_device_commands
    # result without endTime never completes -> timeout.
    host, out, msgs = _run_device_commands(
        {"hostname": "sw-b", "id": "D2"}, _StubClient(result={}), ["show clock"],
        tmp_path, "TS", poll_timeout=2, poll_interval=0, submit_timeout=1,
    )
    assert host == "sw-b"
    assert out is None
    assert any("timed out" in m for m in msgs)


def test_run_device_commands_submit_failure(tmp_path):
    from cheat_core import _run_device_commands
    host, out, msgs = _run_device_commands(
        {"hostname": "sw-c", "id": "D3"}, _StubClient(task_id=None), ["show clock"],
        tmp_path, "TS", poll_timeout=2, poll_interval=0, submit_timeout=1,
    )
    assert out is None
    assert any("failed to start" in m for m in msgs)


def test_run_commands_returns_outputs(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.setattr(cheat_core, "COMMAND_RUNNER_DIR", str(tmp_path / "out"))
    outputs = cheat_core.run_commands(
        [{"hostname": "sw-a", "id": "D1"}], _StubClient(), ["show clock"],
        poll_timeout=3, poll_interval=0,
    )
    assert outputs == {"sw-a": "OUTPUT TEXT"}


def test_build_command_list_off_is_base():
    assert build_command_list(False) == DNAC_COMMANDS
    assert "show logging" not in build_command_list(False)


def test_build_command_list_on_adds_logging_and_clock():
    cmds = build_command_list(True)
    assert cmds[: len(DNAC_COMMANDS)] == DNAC_COMMANDS
    assert cmds[-2:] == ["show logging", "show clock"]


def test_clamp_concurrency_bounds():
    from cheat_core import clamp_concurrency
    assert clamp_concurrency(0) == 1
    assert clamp_concurrency(1) == 1
    assert clamp_concurrency(3) == 3
    assert clamp_concurrency(5) == 5
    assert clamp_concurrency(99) == 5


def test_next_concurrency_cycles():
    from cheat_core import next_concurrency
    assert next_concurrency(1) == 2
    assert next_concurrency(2) == 3
    assert next_concurrency(3) == 4
    assert next_concurrency(4) == 5
    assert next_concurrency(5) == 1
    # A stray out-of-range value is clamped before cycling.
    assert next_concurrency(0) == 2
    assert next_concurrency(99) == 1
