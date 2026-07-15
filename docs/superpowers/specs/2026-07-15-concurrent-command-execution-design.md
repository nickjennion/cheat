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
    """Clamp to the supported 1..MAX_CONCURRENCY range."""

def next_concurrency(n: int) -> int:
    """Cycle 1->2->3->4->5->1 for the menu toggle."""
    # returns n % MAX_CONCURRENCY + 1
```

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
  description reflects the level, e.g. `Running 5 command(s) ×2`.
- **Deterministic result order:** futures complete out of order, so after
  collection reorder `outputs` to match `selected_devices` order before
  returning. This keeps Excel per-device tab order stable regardless of which
  device finishes first.
- The `failed` list and its trailing "Failed on: ..." summary behave exactly as
  today — a device that returns `output_text is None` is recorded as failed and
  does not affect the others.

### `main_latest.py`

- Import `next_concurrency` (and `DEFAULT_CONCURRENCY`) from `cheat_core`.
- In the Menu 5 loop, add state `concurrency = DEFAULT_CONCURRENCY` alongside
  `slow_mode` / `copper_only` / `link_state`.
- Header line gains `Concurrency: {concurrency}×`.
- Add menu line `c) Concurrency (1-5)`; update the input prompt to include `c`.
- Handler: `elif choice == "c": concurrency = next_concurrency(concurrency)`.
- Thread `concurrency` through:
  - `_exec_and_report(..., concurrency=concurrency)` for options 1–3.
  - the option-4 custom-commands `run_commands(..., concurrency=concurrency)`.

### `_exec_and_report` (in `main_latest.py`)

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
  `requests.Session`; the underlying urllib3 connection pool serves concurrent
  connections. With ≤5 workers this is safe in practice.
- `client.enable_slow_mode()` (called once in `_exec_and_report` before
  `run_commands`) mutates the client before any threads start.
- The auth token is read-only during a run.
- Each `_run_device_commands` writes a uniquely named per-device output file, so
  there are no file-write collisions.
- The `Progress`/`Console` object is only touched from the main thread.

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
  `get_task_result` with `endTime` + `progress` JSON `fileId` →
  `get_file_output`) over three devices:
  - returns `{hostname: output}` for all three;
  - the returned dict order matches `selected_devices` order (deterministic),
    even though completion order may differ;
  - works at `concurrency=1` and `concurrency=5`;
  - a stub whose device fails (returns no task id) lands that host in the
    failure path and still returns the others.
  - Uses `poll_interval=0` for speed and `monkeypatch.chdir(tmp_path)` so output
    files land in a temp dir.

## Out of scope (YAGNI)

- Batching multiple device UUIDs into one Command Runner request (the earlier
  "Option B").
- Per-device concurrent progress rows (multiple live bars).
- Persisting the concurrency choice across runs.
