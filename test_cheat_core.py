import time as _time

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


class _OrderStub:
    """Completes later-selected devices first, to exercise result reordering.

    task_id == device_id; get_task_result sleeps `delays[device_id]` so a
    device selected earlier finishes later. get_file_output is per-device.
    """

    def __init__(self, delays):
        self._delays = delays

    def execute_commands(self, device_id, commands, timeout=10):
        return device_id

    def get_task_result(self, task_id):
        _time.sleep(self._delays.get(task_id, 0))
        return {"endTime": 1, "progress": '{"fileId": "%s"}' % task_id}

    def get_file_output(self, file_id):
        return f"OUT-{file_id}"


class _FailOneStub(_StubClient):
    """execute_commands returns None (submit failure) for one device id."""

    def __init__(self, fail_id):
        super().__init__()
        self._fail_id = fail_id

    def execute_commands(self, device_id, commands, timeout=10):
        return None if device_id == self._fail_id else "T1"


class _RaiseOneStub:
    """get_task_result raises for one device id, to exercise the future guard."""

    def __init__(self, raise_id):
        self._raise_id = raise_id

    def execute_commands(self, device_id, commands, timeout=10):
        return device_id

    def get_task_result(self, task_id):
        if task_id == self._raise_id:
            raise RuntimeError("boom")
        return {"endTime": 1, "progress": '{"fileId": "%s"}' % task_id}

    def get_file_output(self, file_id):
        return f"OUT-{file_id}"


_THREE = [
    {"hostname": "sw-1", "id": "D1"},
    {"hostname": "sw-2", "id": "D2"},
    {"hostname": "sw-3", "id": "D3"},
]


def test_run_commands_concurrency_1_all_outputs(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.setattr(cheat_core, "COMMAND_RUNNER_DIR", str(tmp_path / "out"))
    outputs = cheat_core.run_commands(
        _THREE, _StubClient(), ["show clock"], poll_interval=0, concurrency=1,
    )
    assert outputs == {"sw-1": "OUTPUT TEXT", "sw-2": "OUTPUT TEXT", "sw-3": "OUTPUT TEXT"}


def test_run_commands_concurrency_5_all_outputs(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.setattr(cheat_core, "COMMAND_RUNNER_DIR", str(tmp_path / "out"))
    outputs = cheat_core.run_commands(
        _THREE, _StubClient(), ["show clock"], poll_interval=0, concurrency=5,
    )
    assert list(outputs) == ["sw-1", "sw-2", "sw-3"]


def test_run_commands_preserves_selection_order(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.setattr(cheat_core, "COMMAND_RUNNER_DIR", str(tmp_path / "out"))
    # sw-1 finishes last, sw-3 first — completion order is the reverse of selection.
    stub = _OrderStub({"D1": 0.06, "D2": 0.03, "D3": 0.0})
    outputs = cheat_core.run_commands(
        _THREE, stub, ["show clock"], poll_interval=0, concurrency=3,
    )
    assert list(outputs.keys()) == ["sw-1", "sw-2", "sw-3"]
    assert outputs["sw-1"] == "OUT-D1"
    assert outputs["sw-3"] == "OUT-D3"


def test_run_commands_one_failure_others_succeed(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.setattr(cheat_core, "COMMAND_RUNNER_DIR", str(tmp_path / "out"))
    outputs = cheat_core.run_commands(
        _THREE, _FailOneStub("D2"), ["show clock"], poll_interval=0, concurrency=3,
    )
    assert set(outputs) == {"sw-1", "sw-3"}
    assert None not in outputs.values()


def test_run_commands_worker_exception_does_not_abort(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.setattr(cheat_core, "COMMAND_RUNNER_DIR", str(tmp_path / "out"))
    outputs = cheat_core.run_commands(
        _THREE, _RaiseOneStub("D2"), ["show clock"], poll_interval=0, concurrency=3,
    )
    # sw-2's worker raised; the run still returns the other two.
    assert set(outputs) == {"sw-1", "sw-3"}


def test_run_device_commands_unwraps_envelope(tmp_path):
    import json
    from cheat_core import _run_device_commands
    envelope = json.dumps([{"commandResponses": {"SUCCESS": {
        "show clock": "12:00:00", "show ver": "IOS-XE",
    }}}])
    host, out, msgs = _run_device_commands(
        {"hostname": "sw-a", "id": "D1"}, _StubClient(file_output=envelope),
        ["show clock"], tmp_path, "TS", poll_timeout=3, poll_interval=0, submit_timeout=1,
    )
    assert "12:00:00" in out and "IOS-XE" in out
    assert "commandResponses" not in out


class _BatchStub:
    def __init__(self):
        self.submissions = []
        self.task_batches = {}

    def execute_commands(self, device_id, commands, timeout=10):
        task_id = f"T{len(self.submissions) + 1}"
        batch = list(commands)
        self.submissions.append(batch)
        self.task_batches[task_id] = batch
        return task_id

    def get_task_result(self, task_id):
        return {"endTime": 1, "progress": '{"fileId": "%s"}' % task_id}

    def get_file_output(self, file_id):
        import json
        batch = self.task_batches[file_id]
        return json.dumps([{"commandResponses": {"SUCCESS": {
            command: f"OUTPUT {command}" for command in batch
        }}}])


def test_run_device_commands_batches_more_than_five_commands(tmp_path):
    from cheat_core import _run_device_commands
    commands = [f"show item {i}" for i in range(1, 8)]
    stub = _BatchStub()

    host, out, msgs = _run_device_commands(
        {"hostname": "sw-a", "id": "D1"}, stub, commands,
        tmp_path, "TS", poll_timeout=3, poll_interval=0, submit_timeout=1,
    )

    assert host == "sw-a"
    assert stub.submissions == [commands[:5], commands[5:]]
    assert all(len(batch) <= 5 for batch in stub.submissions)
    assert [out.index(f"OUTPUT {command}") for command in commands] == sorted(
        out.index(f"OUTPUT {command}") for command in commands
    )
    assert "2 batches" in " ".join(msgs)
    assert (tmp_path / "command_output_sw-a_TS.txt").read_text() == out


def test_command_batches_handles_exact_boundary_and_empty_input():
    from cheat_core import _command_batches
    commands = [f"cmd-{i}" for i in range(10)]
    assert _command_batches(commands) == [commands[:5], commands[5:]]
    assert _command_batches([]) == []


def test_later_batch_failure_discards_partial_device_output(tmp_path):
    from cheat_core import _run_device_commands

    class _FailSecondBatch(_BatchStub):
        def execute_commands(self, device_id, commands, timeout=10):
            if self.submissions:
                self.submissions.append(list(commands))
                return None
            return super().execute_commands(device_id, commands, timeout)

    commands = [f"show item {i}" for i in range(1, 8)]
    stub = _FailSecondBatch()
    host, out, msgs = _run_device_commands(
        {"hostname": "sw-a", "id": "D1"}, stub, commands,
        tmp_path, "TS", poll_timeout=3, poll_interval=0, submit_timeout=1,
    )

    assert host == "sw-a"
    assert out is None
    assert "batch 2/2" in " ".join(msgs)
    assert not (tmp_path / "command_output_sw-a_TS.txt").exists()


def test_dnac_commands_use_cdp_detail():
    from cheat_core import DNAC_COMMANDS
    assert "show cdp neighbors detail" in DNAC_COMMANDS
    assert "show cdp neighbors" not in DNAC_COMMANDS  # brief form replaced
    assert len(DNAC_COMMANDS) == 5                    # count unchanged
