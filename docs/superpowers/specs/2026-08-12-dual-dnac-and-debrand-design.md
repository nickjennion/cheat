# Design: Dual DNAC Credentials + Splash De-brand

**Date:** 2026-08-12
**Scope:** `main_latest.py`, `splash_rich.py`, `splash_generic.py`, `splash_preview.py`, tests

---

## Problem

Two unrelated changes to the launcher, both confined to the UI layer:

1. **Two controllers, one credential file.** The tool reads exactly one credential
   file, `dnac.env`. Sites migrating from an older DNA Center to a newer one need
   both sets of credentials on hand and currently have to hand-edit `dnac.env`
   between runs. Menu 1 offers no way to pick a controller.
2. **Sandbox co-brand wording.** The Rich splash co-brands with a fictional
   "Hamburger University" theme. The word should read "Generic" instead —
   including the `SPLASH_DESIGN` preference value `burger`, which is displayed
   on screen at Options → `J`.

---

## Part 1 — Dual DNAC credential files

### Menu 1 shape

```
  Menu 1 · Credentials

  1) Use Legacy DNAC
  2) Use New DNAC
  3) Enter manually   · remember
  4) Enter manually   · forget
  5) View credential files
  6) Options

  Select [1-6]:
```

Option 1 keeps today's behaviour exactly, relabelled. Option 2 is new. Options
3–6 are the current 2–5, renumbered.

### Credential file format

`dnac2.env` uses the **same three keys** as `dnac.env`:

```
DNAC_HOST=...
DNAC_USERNAME=...
DNAC_PASSWORD=...
```

The file is a literal copy of `dnac.env` with different values, so the existing
line parser is unchanged. `*.env` is already in `.gitignore`, so `dnac2.env`
is excluded from git with no ignore-file change.

### Behaviour per option

| Option | Behaviour |
|---|---|
| `1) Use Legacy DNAC` | `load_credentials_from_env(ENV_FILE)` — identical to today. On success prints `✓ Loaded from dnac.env` plus host/user. On failure names `dnac.env` and offers the `sample_dnac.env` hint. |
| `2) Use New DNAC` | Same code path against `ENV_FILE_NEW`. Messages name `dnac2.env`. **No fallback:** a missing `dnac2.env` reports the miss and returns to the menu — it must never quietly load legacy credentials, which would point the session at the wrong controller. |
| `3) Enter manually · remember` | Collects credentials as today, then prompts `Save to [1] dnac.env (legacy) or [2] dnac2.env (new):`. **Blank input = legacy (1)**, preserving existing muscle memory. Any other input re-prompts. Writes only the chosen file. |
| `4) Enter manually · forget` | Unchanged. Session-only, no file written. |
| `5) View credential files` | Prints one block per file that exists (`--- dnac.env ---`, `--- dnac2.env ---`), `DNAC_PASSWORD` masked as `********` exactly as today. If neither exists, prints the current not-found message plus the `sample_dnac.env` hint. |
| `6) Options` | Unchanged — calls `menu_options()`. |

### Code changes

All in `main_latest.py`:

| Change | Location |
|---|---|
| Add `ENV_FILE_NEW = Path("dnac2.env")` beside the existing `ENV_FILE` | line 35 |
| `load_credentials_from_env(env_file: Path = ENV_FILE)` — take the path as a defaulted parameter; message text derives from `env_file.name` | line 196 |
| `save_credentials_to_env(host, username, password, env_file: Path = ENV_FILE)` — same treatment | line 219 |
| Extract `_print_env_file(path: Path) -> bool` from option 4's inline masking loop; returns whether the file existed so option 5 can decide about the hint | new, near line 246 |
| Add `_prompt_save_target() -> Path` for option 3's file choice | new, near line 246 |
| Rewrite the `menu_1` option list and branch bodies; prompt becomes `Select [1-6]` | lines 262–326 |

Both existing functions keep a default argument, so no call site outside
`menu_1` needs touching.

### Out of scope for Part 1

`main.py` and `main_debug.py` each carry their own independent
`load_credentials_from_env()` reading `dnac.env` directly, and have no menu.
They stay legacy-only and are not modified.

---

## Part 2 — Splash de-brand

### Visible strings

| Location | Now | After |
|---|---|---|
| `splash_rich.py:197` | `CISCO · DNA CENTER     ×  Hamburger University` | `... ×  Generic University` |
| `splash_rich.py:93` (lockup wordmark) | `HAMBURGER` / `UNIVERSITY` | `GENERIC` / `UNIVERSITY` |
| `splash_rich.py:101` (stacked wordmark) | `HAMBURGER` / `UNIVERSITY` | `GENERIC` / `UNIVERSITY` |

Both wordmark rows are centred into a fixed `field` width, and `GENERIC`
(7 chars) is shorter than `HAMBURGER` (9), so it centres inside the existing
field-10 and field-17 grids without any geometry change.

### `SPLASH_DESIGN` value rename: `burger` → `mark`

`generic` is already a distinct design meaning "Cisco bars only, no co-brand",
so the co-brand mark cannot take that name. It becomes `mark` — the same
register as its siblings `lockup` / `stacked` / `generic`, and descriptive: the
mark alone, beside the bars.

| Location | Change |
|---|---|
| `splash_rich.py:145` | `_DESIGN_WIDTH` key `burger` → `mark`; width 87 unchanged |
| `splash_rich.py:154` | `_fit_design` unknown-design default → `_DESIGN_WIDTH["mark"]` |
| `splash_rich.py:162–176` | `_logo` docstring and the fall-through comment |
| `splash_rich.py:179–183` | `render(..., design="mark")` default arg and docstring |
| `splash_rich.py:80–81` | `_BURGER_COUNTS_LARGE/SMALL` → `_MARK_COUNTS_LARGE/SMALL` |
| `splash_rich.py:84–102` | `_hu_burger_rows` → `_mark_rows`, `_hu_lockup_rows` → `_lockup_rows`, `_hu_stacked_rows` → `_stacked_rows` |
| `splash_rich.py:70–144, 192` | comments referring to "Hamburger University" / "HU mark" / "burger" de-branded |
| `main_latest.py:108` | `_show_splash_rich(..., design="mark")` |
| `main_latest.py:141` | `prefs.get("SPLASH_DESIGN", "mark")` |
| `main_latest.py:351` | `DEFAULT_PREFS["SPLASH_DESIGN"] = "mark"`; comment lists `mark \| lockup \| stacked \| generic` |
| `main_latest.py:447–449` | J-cycle becomes `mark → lockup → stacked → generic → mark`; `.get` default `"mark"` |
| `splash_generic.py` | frozen pre-co-brand snapshot — comments only, no visible strings to change |

The Options → `J) Co-brand logo` row therefore displays `[mark]` by default.

### Prefs migration

`load_prefs()` merges `prefs.env` over `DEFAULT_PREFS`, so an existing
`prefs.env` containing `SPLASH_DESIGN=burger` would survive the rename and
display a stale `[burger]` at Options → J. Rendering would still be correct
(`_logo` falls through to the mark for any unrecognised name, and `_fit_design`
defaults unknown names to the mark's width), but the label would be wrong.

`load_prefs()` gains a one-line migration: after merging, if
`SPLASH_DESIGN == "burger"`, set it to `"mark"`. The value is rewritten to disk
on the next `save_prefs()` like any other change.

### Not changing

- **The halftone silhouette itself.** The dot-count sequences still draw a
  burger (bun crown → bun edge → filling stack → tapered base). Renaming the
  words leaves the picture as it is; redrawing it is deliberately out of scope.
- **`Hu` / `hu` elsewhere in the codebase.** These are the Cisco `HundredGigE`
  interface abbreviation (`interface_parser.py:68, 79, 131`, `cdp_detail.py:16`)
  and site codes in test fixtures. Unrelated to the branding.

---

## Splash preview stubs

`splash_rich.py:241`, `splash_generic.py:123`, and `splash_preview.py:20` each
hardcode the five old Menu 1 labels inside their `if __name__ == "__main__"`
preview blocks. No test asserts on them, but they would render a stale menu
when previewing a design (`python3 splash_rich.py`). All three are updated to
the new six-option list. `splash_rich.py:248` also drops `"burger"` from its
design-cycling list in favour of `"mark"`.

---

## Testing

### New — `test_credential_files.py`

| Test | Asserts |
|---|---|
| load from an explicit path | a populated file returns `(host, user, pass)` |
| load, file missing | returns `None` |
| load, file incomplete | a file missing `DNAC_PASSWORD` returns `None` |
| load, path defaults to legacy | calling with no argument reads `dnac.env` |
| save targets the named file | saving to `dnac2.env` writes it and leaves an existing `dnac.env` byte-identical |
| save, path defaults to legacy | calling with no `env_file` writes `dnac.env` |
| `_print_env_file` masks the password | output contains `DNAC_PASSWORD=********` and never the real value |
| `_print_env_file` on a missing file | returns `False` and prints nothing |
| signatures | both functions accept `env_file`, defaulting to `ENV_FILE` |

Tests use `tmp_path` + `monkeypatch.chdir` and monkeypatch the module-level
`ENV_FILE` / `ENV_FILE_NEW` paths, matching the pattern in
`test_cdp_topology.py`. Interactive branches inside `menu_1` are not driven
through `input()`; coverage is at the function level plus the wiring assertions
below, following the existing `test_av_mac_export_wiring.py` style.

### Updated

| File | Change |
|---|---|
| `test_splash_rich.py:12, 15, 43, 45, 48–49, 52–54, 58, 65, 70, 75–77, 85–89` | `"burger"` → `"mark"`, `"Hamburger University"` → `"Generic University"`; rename `test_invalid_design_falls_back_to_burger` → `..._to_mark` and `test_generic_has_no_burger_dots` → `..._no_mark_dots`; `test_cobrand_designs_render_the_hu_burger` → `..._render_the_mark` |
| `test_main_latest_concurrency.py:19–28` | `test_load_prefs_supplies_splash_design_default_for_old_prefs` expects `"mark"` |

### New prefs assertions — `test_main_latest_concurrency.py`

This file already owns the prefs default/migration tests, so the rename's prefs
behaviour is tested alongside them rather than in the credentials file:

- `DEFAULT_PREFS["SPLASH_DESIGN"] == "mark"`.
- `load_prefs()` migrates a `prefs.env` containing `SPLASH_DESIGN=burger` to
  `mark`, while leaving other values untouched.
- The Options → J cycle maps `mark → lockup → stacked → generic → mark`.

### Pre-existing failures — explicitly untouched

The suite currently reports `158 passed, 1 failed, 3 errors` before this work:

- `test_cdp_topology.py::test_generate_cdp_topology_stencil_icons` fails because
  `drawio_generator._node_style` ignores its `icons` argument, making the
  `DEVICE_ICONS` preference a no-op.
- `test_mock_dnac.py` raises 3 collection errors — helper functions take a
  `records` argument that pytest tries to resolve as a fixture.

Neither is caused by, nor fixed by, this work. The expected state after this
change is the same 1 failure and 3 errors, with the new tests passing and the
updated splash assertions still green.

---

## Files changed

| File | Change |
|---|---|
| `main_latest.py` | `ENV_FILE_NEW`; path parameters on the loader/saver; `_print_env_file`; `_prompt_save_target`; `menu_1` rewrite; `SPLASH_DESIGN` rename + migration in `load_prefs()`; J-cycle |
| `splash_rich.py` | de-branded visible strings, helper/constant renames, `mark` design key, preview stub |
| `splash_generic.py` | comment de-brand; preview stub menu labels |
| `splash_preview.py` | preview stub menu labels |
| `test_credential_files.py` | new |
| `test_splash_rich.py` | assertions updated for `mark` / "Generic University" |
| `test_main_latest_concurrency.py` | `SPLASH_DESIGN` default expectation, plus new `burger → mark` migration and J-cycle assertions |

No changes to `cheat_core.py`, `dnac_client.py`, any parser, or any emitter.
`.gitignore` needs no change.

---

## Decisions on record

- **No fallback from `dnac2.env` to `dnac.env`.** Silently loading legacy
  credentials when the new file is absent would connect the session to the wrong
  controller — a wrong-target risk worse than an error message.
- **Blank = legacy on the save-target prompt.** Preserves the muscle memory of
  the current option 2, which always wrote `dnac.env`.
- **`mark`, not `generic`, for the renamed design.** `generic` already names the
  no-co-brand design; reusing it would collide with a different meaning.
- **The silhouette stays burger-shaped.** The request was about wording; the
  geometry is a separate piece of work.
