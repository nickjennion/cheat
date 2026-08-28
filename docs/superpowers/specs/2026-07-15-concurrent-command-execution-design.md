# Concurrent Command Execution — Design

**Date:** 2026-07-15
**Status:** Approved

## Problem

`run_commands` executes commands device-by-device sequentially: submit → poll
(up to 30–60s) → fetch → next device. Total wall-clock ≈ the sum over all
selected devices, so a multi-stack site scan takes a long time. We want to run
several devices at once.

## Goal

Run up to N devices concurrently, default **2×**, user-selectable **1–5×** from
the same Menu 5 screen where slow mode lives — via a cycle key `c` (each press
cycles 1→2→3→4→5→1).

## Constraints & context

- DNAC Command Runner has a server-side cap on concurrent sessions (~5), which
  is why the maximum is 5 and the default is a conservative 2.
- Concurrency (parallelism) and slow mode (timeouts/backoff) are orthogonal and
  independently set.
- Applies to every `run_commands` path: reports (Menu 5 options 1–3) and custom
  commands (option 4). The MAC/IP Assurance lookups (options 5–7) do not use
  `run_commands` and are unaffected.

## Components

### `cheat_core.py`

New module constants:

```python
DEFAULT_CONCURRENCY = 2
MAX_CONCURRENCY = 5
```

Two pure helpers (small, testable, reused by the menu):

```python
def clamp_concurrency(n: int) -> int:
    """Clamp n into [1, MAX_CONCURRENCY]: n < 1 -> 1, n > MAX -> MAX."""
    return max(1, min(int(n), MAX_CONCURRENCY))

def next_concurrency(n: int) -> int:
    """Cycle 1->2->3->4->5->1 for the menu toggle (precondition: n in 1..MAX)."""
    return clamp_concurrency(n) % MAX_CONCURRENCY + 1
```

`next_concurrency` clamps first so a stray value never escapes the cycle
(`clamp_concurrency(0) % 5 + 1 == 2`, `next_concurrency(5) == 1`).

`run_commands` gains a trailing parameter `concurrency: int = DEFAULT_CONCURRENCY`:

- Clamp with `clamp_concurrency` at entry.
- Replace the sequential `for device in selected_devices` loop with a
  `concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)`: submit
  `_run_device_commands(device, client, commands, cmd_dir, timestamp,
  poll_timeout, poll_interval, submit_timeout)` for each device, then iterate
  `concurrent.futures.as_completed(...)`.
- **All Rich progress updates and per-device ✓/✗ prints happen on the main
  thread**, inside the `as_completed` loop — worker threads only perform network
  and file IO and return their `(hostname, output_text, msgs)` tuple. Nothing
  touches the `Progress`/`Console` from a worker thread.
- Progress stays a single overall bar (`SpinnerColumn`, description,
  `BarColumn`, `MofNCompleteColumn`, `TimeElapsedColumn`) with
  `total=len(selected_devices)`, advanced once per completed future. The
  description is set **once** at task creation to the exact string
  `f"Running {len(commands)} command(s) ×{concurrency}"` and is **not** updated
  per-device (the current sequential code updates it to the hostname per device;
  that per-device update is dropped, since it would be racy/noisy with several
  devices in flight).
- **Worker exceptions never abort the run.** `_run_device_commands` catches
  anticipated failures and returns `(host, None, msgs)`, but a client method can
  still raise an unanticipated exception (e.g. a JSON/parse error), which a
  `Future` re-raises at `future.result()`. Wrap the `future.result()` call in
  `try/except Exception`: on exception, treat that device as failed (append its
  hostname to `failed`, print one red message) and continue consuming the
  remaining futures. One device's crash must not abort the others.
- **Deterministic result order:** futures complete out of order, so build the
  returned dict by iterating `selected_devices` and emitting only the hosts that
  succeeded — never inserting `None`:
  `{d["hostname"]: outputs[d["hostname"]] for d in selected_devices if d["hostname"] in outputs}`.
  This keeps Excel per-device tab order stable and guarantees downstream
  `parse_outputs` never receives a `None` value. (Duplicate hostnames in the
  selection already collapse to one entry today; behaviour is unchanged.)
- The `failed` list and its trailing "Failed on: ..." summary behave exactly as
  today — a device that returns `output_text is None` (or whose future raised)
  is recorded as failed and does not affect the others.
- `poll_timeout` keeps its per-device meaning (max poll iterations per device);
  under concurrency the wall-clock ceiling stays ≈ one device's poll window, not
  a per-batch multiple. Do not scale `poll_timeout` by `concurrency`.

### `main.py`

- Import `next_concurrency` (and `DEFAULT_CONCURRENCY`) from `cheat_core`.
- In the Menu 5 loop, add state `concurrency = DEFAULT_CONCURRENCY` alongside
  `slow_mode` / `copper_only` / `link_state`.
- Header line gains `Concurrency: {concurrency}×`.
- Add menu line `c) Concurrency (1-5)`; update the input prompt to include `c`.
- Handler: `elif choice == "c": concurrency = next_concurrency(concurrency)`.
- Thread `concurrency` through:
  - `_exec_and_report(..., concurrency=concurrency)` for options 1–3.
  - the option-4 custom-commands `run_commands(..., concurrency=concurrency)`.

### `_exec_and_report` (in `main.py`)

- New parameter `concurrency: int = DEFAULT_CONCURRENCY`.
- Pass `concurrency=concurrency` to `run_commands` in **both** the slow-mode and
  normal branches.

## Data flow

```
Menu 5: c cycles concurrency (1..5, default 2)
   └─ option 1-3 -> _exec_and_report(..., concurrency)
   │                    └─ run_commands(..., concurrency)
   └─ option 4   -> run_commands(..., concurrency)
                         └─ ThreadPoolExecutor(max_workers=concurrency)
                                └─ _run_device_commands (per device, in worker)
                         main thread: as_completed -> print msgs, advance bar,
                                      collect outputs -> reorder to selection
```

## Thread-safety

- The shared `DNACClient` issues independent HTTP requests per call via its
  `requests.Session`. Each call passes its own local `headers` dict (it does not
  mutate `session.headers`), and urllib3's connection pool is itself
  thread-safe, so concurrent `get`/`post` from ≤5 workers is safe. Note
  `requests.Session` is not *officially* guaranteed thread-safe for shared use;
  at this bounded concurrency it is safe in practice, and this is an accepted
  limitation rather than a per-thread-client design.
- **Ordering boundary (must hold):** `client.enable_slow_mode()` replaces the
  session's HTTPAdapter (`session.mount(...)`, an unlocked write to
  `session.adapters`). It is called once in `_exec_and_report` **before**
  `run_commands` creates the pool, so it completes before any worker starts.
  `run_commands` must **not** call `enable_slow_mode()` from inside the pool, and
  workers must not call it.
- `DNACClient.authenticate()` / `_save_token()` (which rewrites `token.env`) are
  **not** thread-safe and are **not** called from `_run_device_commands`, so the
  auth token is read-only during a run. This is a boundary to preserve: if a
  future change adds token-refresh-during-run, it must add a lock around
  `authenticate()`/`_save_token()`. Out of scope here.
- Each `_run_device_commands` writes a uniquely named per-device output file
  (`command_output_{hostname}_{timestamp}` with a single run-level timestamp), so
  there are no file-write collisions.
- The `Progress`/`Console` object is only touched from the main thread (inside
  the `as_completed` loop); workers only perform network + file IO.

## Error handling

- Per-device failures are unchanged: `_run_device_commands` returns
  `(host, None, msgs)`, the host is appended to `failed`, and the run continues.
  One device's failure never affects the others.
- `concurrency` values outside 1–5 (e.g. a stale/garbage value) are clamped, not
  rejected.

## Testing

- `clamp_concurrency`: `0 -> 1`, `1 -> 1`, `3 -> 3`, `5 -> 5`, `99 -> 5`.
- `next_concurrency`: `1 -> 2`, `2 -> 3`, `4 -> 5`, `5 -> 1`.
- `run_commands` with a stub `DNACClient` (canned `execute_commands` →
  `get_task_result` with `endTime` + `progress` as a JSON **string** containing
  `fileId` → `get_file_output`) over three devices:
  - returns `{hostname: output}` for all three;
  - **the returned dict order matches `selected_devices` order** even though
    completion order differs — the stub must make a later-selected device finish
    first (e.g. return a decreasing fake elapsed / flip the poll so device 3
    completes before device 1) so the reorder is genuinely exercised, not
    trivially true;
  - works at `concurrency=1` and `concurrency=5`;
  - a device that fails (its `execute_commands` returns `None`) lands in the
    failure path while the other two still return; the returned dict contains no
    `None` values;
  - a worker that raises (a stub method throwing) is caught and that device is
    marked failed without aborting the run.
  - Follow the existing `test_cheat_core.py` convention:
    `monkeypatch.setattr(cheat_core, "COMMAND_RUNNER_DIR", str(tmp_path / "out"))`
    (not `chdir`) and `poll_interval=0` for a fast, hermetic test. Passing a
    quiet `rich` console (or accepting the captured progress output) keeps test
    output clean.
- `_run_device_commands` JSON-envelope unwrap: a stub `get_file_output`
  returning the `[{"commandResponses": {"SUCCESS": {...}}}]` envelope yields the
  joined command outputs (the wrap path in `_run_device_commands` is otherwise
  untested).
- `clamp_concurrency`: `0 -> 1`, `1 -> 1`, `3 -> 3`, `5 -> 5`, `99 -> 5`.
- `next_concurrency`: `1 -> 2`, `2 -> 3`, `3 -> 4`, `4 -> 5`, `5 -> 1`.

## Out of scope (YAGNI)

- Batching multiple device UUIDs into one Command Runner request (the earlier
  "Option B").
- Per-device concurrent progress rows (multiple live bars).
- Persisting the concurrency choice across runs.
