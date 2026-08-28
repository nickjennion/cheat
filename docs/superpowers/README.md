# Design specs and implementation plans (archive)

Historical records of completed feature work — the spec and plan for each change
as it was designed and executed. They are not maintained as live documentation;
read them for intent and rationale, not as a current map of the codebase.

## Entry-point renames (2026-08-28)

File references in these documents were updated to the current names. The
mapping, for anyone comparing against a commit from before that date:

| Then | Now |
|------|-----|
| `main_latest.py` | `main.py` — interactive menu launcher, the primary entry point |
| `main.py` | `main_cli.py` — argparse, non-interactive |
| `main_debug.py` | **removed** — no successor |
| `test_main_latest_concurrency.py` | `test_main_concurrency.py` |

`main_debug.py` was a drifted duplicate of the old `main.py`, deleted rather
than renamed, so references to it here have been left as written. Steps that
say to apply a change to it no longer have anything to apply it to. The file is
still in git history if you need to read it.

Line numbers cited in these documents refer to the files as they were at the
time of writing and have not been rebased.
