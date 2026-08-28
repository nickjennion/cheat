# PEER REVIEW — Implementation Plan

**Branch:** `improve/retry-unify-dryrun-portutil`
**Date:** 2026-06-24
**Prepared by:** opencode
**Status:** Pending peer review before execution

---

## Scope

Implement four improvements to the CHEAT UNPLUGGED codebase:

| # | Item | Impact |
|---|------|--------|
| 5 | Retry/backoff on all DNAC API calls | Reliability |
| 7 | Unify `uptime_days()` and `parse_last_input_days()` | Maintainability |
| 8 | Add `--dry-run` flag with argparse | Usability |
| 9 | Wire `port_utilisation.py` into the main workflow | Feature integration |

Changes target **five files** and introduce **one new file**. All existing interfaces are preserved.

---

## Future Compatibility Note

The codebase is slated for an interactive step-by-step refactor (Step 1: login → Step 2: filter → Step 3: command selection → Step 4: parse → Step 5: port analysis). This plan structures each stage as a discrete, independently-callable function to minimise rework during that refactor.

---

## Detailed Plan

### Item 5 — Retry/Backoff on API Calls

**File:** `dnac_client.py`

**Rationale:** All six HTTP call sites in `DNACClient` fail immediately on any network error despite the target being a DNAC appliance that may be under load, behind a flaky WAN link, or temporarily unresponsive during maintenance windows.

**Changes:**

1. Add `import urllib3` and `from requests.adapters import HTTPAdapter` at the top of the file.

2. In `__init__()`, replace the bare `self.token` / `self.base_url` setup with a `requests.Session`:

   ```python
   def __init__(self, host, username, password, verify_ssl=False,
                retry_total=3, retry_backoff=1):
       self.host = host
       self.username = username
       self.password = password
       self.verify_ssl = verify_ssl
       self.token = None
       self.base_url = f"https://{host}"
       self.session = requests.Session()
       self.session.verify = verify_ssl
       retry_strategy = urllib3.Retry(
           total=retry_total,
           backoff_factor=retry_backoff,
           status_forcelist=[500, 502, 503, 504],
           allowed_methods=["GET", "POST"]
       )
       adapter = HTTPAdapter(max_retries=retry_strategy)
       self.session.mount("https://", adapter)
   ```

3. Replace all six `requests.get(...)` and `requests.post(...)` calls with `self.session.get(...)` / `self.session.post(...)`. Remove the per-call `verify=self.verify_ssl` argument (the session handles it).

4. Retry only on transient errors: 5xx status codes, `ConnectionError`, `Timeout`, `TooManyRedirects`. 4xx errors (bad credentials, forbidden) are NOT retried and fail immediately as they do now.

5. Existing `try/except requests.exceptions.RequestException` blocks remain — retry happens inside the session/adapter, and if all retries are exhausted the original exception propagates to the existing handler.

**Affected call sites (6):**

| Method | Line | Verb | Timeout |
|--------|------|------|---------|
| `authenticate()` | 22 | POST | 10s |
| `get_devices()` | 63 | GET | 30s |
| `query_devices_by_hostname()` | 106 | GET | 30s |
| `execute_commands()` | 145 | POST | 10s |
| `get_task_result()` | 168 | GET | 10s |
| `get_file_output()` | 189 | GET | 10s |

**Sandbox test:** Inject a deliberately unavailable hostname for one API call, confirm retry with exponential backoff, confirm 401 on bad password is NOT retried, confirm normal flow works end-to-end.

---

### Item 7 — Unify Time Parsing

**New file:** `time_utils.py`
**Modified files:** `interface_parser.py`, `port_utilisation.py`, `excel_generator.py`

**Rationale:** Two functions in two modules independently parse time-duration strings into fractional days using different regex patterns and different input format assumptions. They are never imported between modules. Any bugfix or format addition requires changes in two places.

**Changes:**

1. **New file `time_utils.py`** — single public function:

   ```python
   def parse_duration_days(value: str) -> Optional[float]:
       """Parse a duration string into fractional days.
       
       Handles colon format ("00:00:13", "01:30:00"),
       prose format ("45 weeks, 3 days, 2 hours"),
       and compact format ("2d3h", "5w", "222h").
       Returns None for empty/"never" or unparseable input.
       """
   ```

   Implementation order (first match wins):
   - Return `None` if value is empty, whitespace, or `"never"` (case-insensitive)
   - Try `HH:MM:SS` / `MM:SS` colon format → convert to fractional days
   - Try prose regex `r'(\d+)\s*(week|day|hour|minute|second)'` with full unit weights
   - Try compact regex `r'(\d+)\s*([a-z]+)'` with full unit weights (w/d/h/m/s)
   - Return `total` if > 0, else `None`

2. **`interface_parser.py`** — body of `uptime_days()` becomes:

   ```python
   from time_utils import parse_duration_days
   
   def uptime_days(uptime_str: str) -> Optional[float]:
       return parse_duration_days(uptime_str)
   ```

   Kept as a thin wrapper for backward compatibility. Only one caller (`excel_generator.py:105`) — but this avoids touching the interface.

3. **`port_utilisation.py`** — body of `parse_last_input_days()` becomes:

   ```python
   from time_utils import parse_duration_days
   
   def parse_last_input_days(last_input_str: str) -> Optional[float]:
       return parse_duration_days(str(last_input_str).strip())
   ```

   Also kept as a thin wrapper. Only caller is `port_utilisation.py:149`.

4. **`excel_generator.py`** — no change needed. It imports `uptime_days` from `interface_parser`, which still exists as a wrapper.

**Import graph after change:**

```
time_utils.py          ←  new, no internal imports
interface_parser.py    ←  imports time_utils
port_utilisation.py    ←  imports time_utils
excel_generator.py     ←  imports interface_parser (unchanged)
```

**Sandbox test:** Run the full flow against sandbox. Verify Excel report shows identical uptime values and highlighting to the pre-change output. Feed edge-case strings (`"never"`, `"00:00:00"`, `"2d3h"`, `"45 weeks 3 days"`) through `parse_duration_days()` directly and assert expected float outputs.

---

### Item 8 — `--dry-run` Flag

**File:** `main_cli.py`

**Rationale:** Currently there is no way to preview what the tool will do without actually executing commands on devices. A dry-run mode allows safe discovery and planning.

**Changes:**

1. Add `import argparse` and a `parse_args()` function:

   ```python
   def parse_args():
       parser = argparse.ArgumentParser(
           description="CHEAT UNPLUGGED — Network port discovery and inventory"
       )
       parser.add_argument("--host", help="DNAC server hostname/IP")
       parser.add_argument("--username", help="DNAC username")
       parser.add_argument("--password", help="DNAC password (omit value for interactive prompt)")
       parser.add_argument("--filter", help="Hostname filter pattern (e.g. 'switch-*')")
       parser.add_argument("--batch", help="Device numbers to select (e.g. '1,3-5')")
       parser.add_argument("--dry-run", action="store_true",
                           help="Authenticate and preview, skip command execution")
       parser.add_argument("--output-dir", default="output",
                           help="Output directory (default: output/)")
       parser.add_argument("--port-util", action="store_true", default=None,
                           help="Run port utilisation analysis after Excel generation")
       parser.add_argument("--no-port-util", action="store_false", dest="port_util",
                           help="Skip port utilisation analysis")
       parser.add_argument("--port-util-threshold", type=int, default=42,
                           help="Port utilisation threshold in days (default: 42)")
       return parser.parse_args()
   ```

2. Modify `get_credentials()` to accept `args` — CLI values take precedence over `dnac.env`, which takes precedence over interactive prompts. Password from `--password` is only used if a value is provided; `--password` with no value triggers `getpass`.

3. In `main()`, after device selection succeeds and before command execution:

   ```python
   if args.dry_run:
       print_summary_of_what_would_happen(selected, DNAC_COMMANDS, session_timestamp)
       if args.filter and args.batch:
           return   # one-shot CLI mode
       continue     # loop back to filter prompt for another iteration
   ```

   `print_summary_of_what_would_happen()` prints:
   - Which devices selected (hostname, IP, model)
   - Which commands would run (list)
   - Where output files would be saved
   - Estimated Excel report filename

4. In `main()`: `OUTPUT_DIR` is read from `args.output_dir` instead of the hardcoded constant.

5. `main_debug.py` — identical argparse additions. In a future refactor this should be merged into `main_cli.py` with `--debug`, but for now keep parity.

**Behaviour matrix:**

| Scenario | Authenticate? | Fetch devices? | Execute commands? | Generate Excel? |
|----------|:---:|:---:|:---:|:---:|
| Normal interactive | Yes | Yes | Yes | Yes |
| `--dry-run` | Yes | Yes | No | No |
| `--dry-run` + `--filter X` | Yes | Yes | No | No |
| Bad credentials | Fails | — | — | — |
| `--filter` no match | Yes | Yes | — | — |

**Sandbox test:**
```bash
python main_cli.py --host sandboxdnacenter.cisco.com --username admin --dry-run
```
Expected: authenticates, fetches devices, enters interactive filter/select loop, on selection prints "Would execute..." block, loops back. No files created in `output/`. No Command Runner API calls made.

---

### Item 9 — Wire Port Utilisation into Main Workflow

**Files:** `main_cli.py` (modify), `port_utilisation.py` (no changes)

**Rationale:** Port utilisation analysis currently requires a separate manual invocation of `python port_utilisation.py <report.xlsx>`. The main workflow generates the Excel report and knows its exact path — it can offer this analysis as a natural final step.

**Changes in `main_cli.py`:**

1. Add imports:

   ```python
   from port_utilisation import analyse_workbook, print_summary, write_summary_excel
   ```

2. After `parse_and_generate_excel()` succeeds, add a post-processing block:

   ```python
   if success and excel_path:
       do_port_util = args.port_util
       if do_port_util is None:
           # Not specified on CLI — prompt interactively
           choice = input("\nRun port utilisation analysis? [Y/n]: ").strip().lower()
           do_port_util = choice in ('', 'y', 'yes')
       
       if do_port_util:
           threshold = args.port_util_threshold
           ok, msg, results = analyse_workbook(excel_path, threshold)
           print(msg)
           if ok and results:
               print_summary(results, threshold)
               ok2, msg2 = write_summary_excel(results, threshold)
               print(msg2)
   ```

3. `parse_and_generate_excel()` is modified to **return** the output file path alongside its success boolean. Current signature:

   ```python
   def parse_and_generate_excel(outputs, session_timestamp) -> bool
   ```
   New signature:
   ```python
   def parse_and_generate_excel(outputs, session_timestamp) -> tuple[bool, Optional[str]]
   ```

   The Excel path is already computed on line 422 — it just needs to be returned.

**Changes in `port_utilisation.py`:** None. All three functions (`analyse_workbook`, `print_summary`, `write_summary_excel`) are already public with clean signatures and exist solely for this kind of integration.

**Flow after the change:**

```
[Stage 4: Parse + Excel]
    parse_and_generate_excel() → (True, "output/port-information-2026-06-24-14-30.xlsx")
    │
    └─ [Stage 5: Port Utilisation (optional)]
         if --port-util or user says yes:
             analyse_workbook(excel_path, 42) → (True, "Analysed 48 copper ports", {...})
             print_summary({...})              → stdout table
             write_summary_excel({...})        → "port_utilisation_summary_2026-06-24-14-30.xlsx"
```

**Sandbox test:**
```bash
python main_cli.py --host sandboxdnacenter.cisco.com --username admin --filter cat9k --batch 1 --port-util
```
Expected: full end-to-end flow, Excel generated, port utilisation summary printed, summary Excel written. Verify copper port counts match manual inspection of the generated report.

---

## Execution Order

| Step | Item | Depends On | Files Affected |
|------|------|-----------|----------------|
| 1 | Retry/backoff | None | `dnac_client.py` |
| 2 | Unify time parsing | None | `time_utils.py` (new), `interface_parser.py`, `port_utilisation.py` |
| 3 | `--dry-run` + argparse | Step 1 | `main_cli.py`, `main_debug.py` |
| 4 | Wire port utilisation | Step 3 | `main_cli.py` |

Steps 1 and 2 are independent and can be developed in parallel. Steps 3 and 4 are sequential (4 needs the argparse infrastructure from 3).

---

## Files NOT Modified

| File | Reason |
|------|--------|
| `test_dnac.py` | Uses `DNACClient` interface, which is unchanged; retry is transparent |
| `test_mock_dnac.py` | No network calls, no time parsing, no CLI args |
| `consolidate_report.py` | Copies values verbatim; no time parsing logic to update |
| `excel_generator.py` | Imports `uptime_days` wrapper from `interface_parser` (unchanged interface) |
| `requirements.txt` | `urllib3` is a transitive dependency of `requests` (already present) |

---

## Regression Risk Assessment

| Risk | Likelihood | Mitigation |
|------|:---:|------------|
| Retry adapter changes error-handling behaviour | Low | Retry only on 5xx/connection; 4xx and other exceptions propagate identically |
| Unified time parser produces different results | Low | Same tests fed through both old and new functions with assertion comparison |
| argparse breaks interactive prompts when no flags given | Low | All argparse arguments are optional with `default=None`; no behaviour change when omitted |
| Port utilisation calls fail on non-standard Excel layouts | Low | `analyse_workbook()` already handles missing columns and empty sheets gracefully |
| `main_debug.py` drifts from `main_cli.py` | Medium | Apply identical argparse changes to both; document need for future merge |

---

## Sandbox Integration Test (End-to-End)

After all four items are implemented:

```bash
# Test 1: Dry-run with CLI args
python main_cli.py \
  --host sandboxdnacenter.cisco.com \
  --username admin \
  --filter cat9k \
  --dry-run

# Expected: authenticates, fetches devices, prints "Would execute" block, exits.
# Verify: no output/ files created, no Command Runner API calls in Wireshark/logs.

# Test 2: Full run with port utilisation
python main_cli.py \
  --host sandboxdnacenter.cisco.com \
  --username admin \
  --filter cat9k \
  --batch 1 \
  --port-util

# Expected: authenticates, runs commands, generates Excel, runs port analysis.
# Verify: Excel report opens correctly, time highlighting matches expectations,
#         port utilisation counts are accurate, summary Excel is generated.

# Test 3: Retry behaviour
# (Temporarily patch dnac_client.py to use an invalid host for one call,
#  or run against a flaky proxy — confirm retry with backoff in logs.)

# Test 4: Time parsing edge cases
python -c "
from time_utils import parse_duration_days
assert parse_duration_days('never') is None
assert parse_duration_days('') is None
assert parse_duration_days('2d3h') == 2.125
assert parse_duration_days('5w') == 35
assert parse_duration_days('45 weeks, 3 days') == 318
assert parse_duration_days('00:00:13') == 13 / 86400
print('All assertions passed')
"
```

---

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | opencode | 2026-06-24 | — |
| Reviewer | | | |
| Approver | | | |
