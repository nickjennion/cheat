# Concurrent Command Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run device command execution concurrently (default 2×, selectable 1–5× via a `c` cycle key on Menu 5) instead of sequentially.

**Architecture:** `cheat_core.run_commands` fans `_run_device_commands` out across a bounded `ThreadPoolExecutor`, printing progress and collecting results on the main thread via `as_completed`, then returns results reordered to the device-selection order. Two pure helpers (`clamp_concurrency`, `next_concurrency`) back a Menu 5 cycle key that threads a `concurrency` value into every `run_commands` call site.

**Tech Stack:** Python 3.9+, `concurrent.futures`, Rich (progress bar), pytest.

## Global Constraints

- Python 3.9+ (`X | None`, `list[...]` hints used in this codebase).
- Default concurrency **2**, min **1**, max **5** (`DEFAULT_CONCURRENCY = 2`, `MAX_CONCURRENCY = 5`).
- Concurrency and slow mode are independent controls.
- `clamp_concurrency(n)`: `n < 1 -> 1`, `n > MAX -> MAX`. `next_concurrency(n)`: cycles `1→2→3→4→5→1` (`clamp_concurrency(n) % MAX_CONCURRENCY + 1`).
- All Rich `Progress`/`Console` calls stay on the main thread (inside the `as_completed` loop); worker threads only do network + file IO.
- Progress description is set **once** at task creation to `f"Running {len(commands)} command(s) ×{concurrency}"`; no per-device description updates.
- A worker that raises must be caught at `future.result()`, marked failed, and must not abort the run.
- The returned dict is built by iterating `selected_devices`, emitting only succeeded hosts — **never `None` values**; order matches selection.
- `enable_slow_mode()` is only ever called before the pool starts (it already is, in `_exec_and_report`); `run_commands` must not call it. Do not call `authenticate()` from workers.
- Run tests with `python3 -m pytest` from the repo root. Pre-existing collection errors in `test_mock_dnac.py` / `test_dnac.py` / `test_sandbox.py` (fixture-arg / live-integration) are unrelated — ignore them.

---

### Task 1: Concurrency constants + helpers

**Files:**
- Modify: `cheat_core.py` (add constants near `COMMAND_POLLING_INTERVAL_SECONDS`; add two helpers)
- Test: `test_cheat_core.py`

**Interfaces:**
- Produces: `DEFAULT_CONCURRENCY = 2`, `MAX_CONCURRENCY = 5`, `clamp_concurrency(n: int) -> int`, `next_concurrency(n: int) -> int`.

- [ ] **Step 1: Write the failing test**

Append to `test_cheat_core.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_cheat_core.py -k "clamp or next_concurrency" -q`
Expected: FAIL with `ImportError: cannot import name 'clamp_concurrency'`

- [ ] **Step 3: Write minimal implementation**

In `cheat_core.py`, add after the line `COMMAND_POLLING_INTERVAL_SECONDS = 1`:

```python
DEFAULT_CONCURRENCY = 2
MAX_CONCURRENCY = 5


def clamp_concurrency(n: int) -> int:
    """Clamp n into [1, MAX_CONCURRENCY]: n < 1 -> 1, n > MAX -> MAX."""
    return max(1, min(int(n), MAX_CONCURRENCY))


def next_concurrency(n: int) -> int:
    """Cycle 1->2->3->4->5->1 for the menu toggle."""
    return clamp_concurrency(n) % MAX_CONCURRENCY + 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_cheat_core.py -k "clamp or next_concurrency" -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add cheat_core.py test_cheat_core.py
git commit -m "feat: concurrency constants and clamp/cycle helpers"
```

---

### Task 2: Concurrent `run_commands`

**Files:**
- Modify: `cheat_core.py` (add a `concurrent.futures` import; rewrite `run_commands`)
- Test: `test_cheat_core.py`

**Interfaces:**
- Consumes: `clamp_concurrency` (Task 1), existing `_run_device_commands`.
- Produces: `run_commands(selected_devices, client, commands, poll_timeout=..., poll_interval=..., submit_timeout=10, concurrency: int = DEFAULT_CONCURRENCY) -> dict` — returns `{hostname: output_text}` for succeeded devices, in `selected_devices` order.

- [ ] **Step 1: Write the failing test**

Append to `test_cheat_core.py` (the module already defines `_StubClient`):

```python
import time as _time


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
    assert set(outputs) == {"sw-1", "sw-2", "sw-3"}


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_cheat_core.py -k run_commands -q`
Expected: FAIL — `run_commands` has no `concurrency` parameter (`TypeError: run_commands() got an unexpected keyword argument 'concurrency'`).

- [ ] **Step 3: Write minimal implementation**

In `cheat_core.py`, add to the imports near the top (after `import time`):

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

Replace the entire `run_commands` function (from `def run_commands(` through its `return outputs`) with:

```python
def run_commands(
    selected_devices: list,
    client,
    commands: list,
    poll_timeout: int = COMMAND_POLLING_TIMEOUT_SECONDS,
    poll_interval: int = COMMAND_POLLING_INTERVAL_SECONDS,
    submit_timeout: int = 10,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> dict:
    """Execute commands on devices via an authenticated DNACClient.

    Runs up to `concurrency` devices at once (clamped to 1..MAX_CONCURRENCY) on a
    thread pool. A live Rich progress bar advances as each device completes; all
    progress/print calls happen on this (main) thread. Saves raw output to
    COMMAND_RUNNER_DIR/command_output_<hostname>_<timestamp>.txt and returns
    {hostname: output_text} for every device that succeeded, in the same order as
    `selected_devices`.
    """
    concurrency = clamp_concurrency(concurrency)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    cmd_dir = Path(COMMAND_RUNNER_DIR).resolve()
    cmd_dir.mkdir(exist_ok=True)
    outputs = {}
    failed = []

    console = Console()
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Running {len(commands)} command(s) ×{concurrency}",
            total=len(selected_devices),
        )
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_host = {
                executor.submit(
                    _run_device_commands,
                    device, client, commands, cmd_dir, timestamp,
                    poll_timeout, poll_interval, submit_timeout,
                ): device.get("hostname", "unknown")
                for device in selected_devices
            }
            for future in as_completed(future_to_host):
                submitted_host = future_to_host[future]
                try:
                    host, output_text, msgs = future.result()
                except Exception as e:  # worker crashed unexpectedly
                    host, output_text = submitted_host, None
                    msgs = [f"✗ {submitted_host}: unexpected error: {e}"]
                for msg in msgs:
                    colour = "green" if msg.startswith("✓") else "red"
                    progress.console.print(f"  [{colour}]{msg}[/{colour}]", highlight=False)
                if output_text is not None:
                    outputs[host] = output_text
                else:
                    failed.append(host)
                progress.advance(task)

    if failed:
        console.print(f"\n  [yellow]⚠ Failed on: {', '.join(failed)}[/yellow]")

    # Return in selection order, omitting failures (never a None value).
    return {
        h: outputs[h]
        for h in (d.get("hostname", "unknown") for d in selected_devices)
        if h in outputs
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_cheat_core.py -q`
Expected: PASS (all `test_cheat_core.py` tests, including the pre-existing `_run_device_commands` and `build_command_list` ones).

- [ ] **Step 5: Commit**

```bash
git add cheat_core.py test_cheat_core.py
git commit -m "feat: run device commands concurrently with bounded pool"
```

---

### Task 3: Menu 5 control + wiring

**Files:**
- Modify: `main_latest.py` (cheat_core import block; `_exec_and_report`; the Menu 5 loop)
- Test: `test_main_latest_concurrency.py`

**Interfaces:**
- Consumes: `run_commands(..., concurrency=...)` (Task 2), `next_concurrency`, `DEFAULT_CONCURRENCY` (Task 1).
- Produces: `_exec_and_report(..., concurrency: int = DEFAULT_CONCURRENCY)`; a Menu 5 `c` cycle key.

- [ ] **Step 1: Write the failing test**

Create `test_main_latest_concurrency.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_main_latest_concurrency.py -q`
Expected: FAIL — `AttributeError: module 'main_latest' has no attribute 'DEFAULT_CONCURRENCY'` (and `_exec_and_report` lacks the param).

- [ ] **Step 3: Write minimal implementation**

**(a)** In `main_latest.py`, extend the `from cheat_core import (...)` block to add two names:

```python
from cheat_core import (
    EXCEL_DIR,
    COMMAND_RUNNER_DIR,
    build_command_list,
    run_commands,
    parse_outputs,
    generate_excel,
    generate_cdp_topology,
    next_concurrency,
    DEFAULT_CONCURRENCY,
)
```

**(b)** Change the `_exec_and_report` signature to add a trailing `concurrency` parameter:

```python
def _exec_and_report(selected_devices, client, commands, mode, filename, threshold=42, slow_mode=False, copper_only=False, concurrency=DEFAULT_CONCURRENCY):
```

And pass `concurrency=concurrency` in **both** its `run_commands` calls. Replace:

```python
        outputs = run_commands(selected_devices, client, commands,
                               poll_timeout=60, poll_interval=3, submit_timeout=20)
    else:
        outputs = run_commands(selected_devices, client, commands)
```

with:

```python
        outputs = run_commands(selected_devices, client, commands,
                               poll_timeout=60, poll_interval=3, submit_timeout=20,
                               concurrency=concurrency)
    else:
        outputs = run_commands(selected_devices, client, commands,
                               concurrency=concurrency)
```

**(c)** In the Menu 5 loop, add the concurrency state variable. Replace:

```python
    slow_mode = False
    copper_only = False
    link_state = False
```

with:

```python
    slow_mode = False
    copper_only = False
    link_state = False
    concurrency = DEFAULT_CONCURRENCY
```

**(d)** Add the concurrency indicator to the header. Replace:

```python
        print(f"  Host: {host}  |  User: {username}  |  Selected: {len(selected_devices)} device(s)  |  Slow mode: {slow_label}  |  Copper only: {copper_label}  |  Link-state: {link_label}\n")
```

with:

```python
        print(f"  Host: {host}  |  User: {username}  |  Selected: {len(selected_devices)} device(s)  |  Slow mode: {slow_label}  |  Copper only: {copper_label}  |  Link-state: {link_label}  |  Concurrency: {concurrency}×\n")
```

**(e)** Add the menu line and update the prompt. Replace:

```python
        print("  s) Toggle slow mode")
        print("  p) Toggle copper only")
        print("  l) Toggle link-state column")
        print("  8) Back")
        print()
        choice = input("  Select [1-8 / s / p / l]: ").strip().lower()
```

with:

```python
        print("  s) Toggle slow mode")
        print("  p) Toggle copper only")
        print("  l) Toggle link-state column")
        print("  c) Concurrency (1-5)")
        print("  8) Back")
        print()
        choice = input("  Select [1-8 / s / p / l / c]: ").strip().lower()
```

**(f)** Add the `c` handler. Replace:

```python
        elif choice == "l":
            link_state = not link_state
```

with:

```python
        elif choice == "l":
            link_state = not link_state

        elif choice == "c":
            concurrency = next_concurrency(concurrency)
```

**(g)** Thread `concurrency` into the three report call sites. Replace the two `_exec_and_report(...)` calls (options 1–2 and option 3):

```python
            _exec_and_report(selected_devices, client, build_command_list(link_state), int(choice), filename,
                             slow_mode=slow_mode, copper_only=copper_only)
```

with:

```python
            _exec_and_report(selected_devices, client, build_command_list(link_state), int(choice), filename,
                             slow_mode=slow_mode, copper_only=copper_only, concurrency=concurrency)
```

and:

```python
            _exec_and_report(selected_devices, client, build_command_list(link_state), 3, filename, threshold,
                             slow_mode=slow_mode, copper_only=copper_only)
```

with:

```python
            _exec_and_report(selected_devices, client, build_command_list(link_state), 3, filename, threshold,
                             slow_mode=slow_mode, copper_only=copper_only, concurrency=concurrency)
```

And the option-4 custom-commands call. Replace:

```python
            outputs = run_commands(selected_devices, client, commands)
```

with:

```python
            outputs = run_commands(selected_devices, client, commands, concurrency=concurrency)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_main_latest_concurrency.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: feature and existing suites pass; only the pre-existing `test_mock_dnac.py` / `test_dnac.py` / `test_sandbox.py` collection errors remain.

- [ ] **Step 6: Commit**

```bash
git add main_latest.py test_main_latest_concurrency.py
git commit -m "feat: Menu 5 concurrency control (1-5, default 2) wired through run paths"
```

---

## Self-Review

**Spec coverage:**
- Constants + `clamp_concurrency`/`next_concurrency` → Task 1.
- `run_commands` concurrency, ThreadPoolExecutor + `as_completed`, worker-exception guard, description-once, deterministic reorder omitting `None` → Task 2 (tests: order under out-of-order completion, concurrency 1/5, one-failure, worker-raise, envelope unwrap).
- Menu 5 `c` cycle key, header, prompt, `_exec_and_report` param, all three `run_commands` call sites threaded → Task 3.
- Thread-safety boundaries (enable_slow_mode before pool; no auth from workers) → respected: `run_commands` never calls `enable_slow_mode`; `_exec_and_report` still calls it before `run_commands` as today. No code change needed there.
- Out-of-scope items (batching, per-device bars, persistence) → correctly absent.

**Placeholder scan:** No TBD/TODO/vague steps — every code step is complete, with exact old→new snippets for the `main_latest.py` edits.

**Type consistency:** `concurrency` is an `int` everywhere; `DEFAULT_CONCURRENCY`/`MAX_CONCURRENCY`/`clamp_concurrency`/`next_concurrency` names match across tasks; `run_commands(..., concurrency=DEFAULT_CONCURRENCY)` and `_exec_and_report(..., concurrency=DEFAULT_CONCURRENCY)` defaults agree; the returned `dict` shape (`{hostname: output_text}`) is unchanged from today, so `parse_outputs` consumers are unaffected.
