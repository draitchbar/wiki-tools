# Plan: type checking for the plugin's Python

Status: planned 2026-11-21 and reviewed the same day (one round, folded in). Roadmap item: "Type checking for the plugin's Python" (`docs/roadmap.md`). Owner's decisions: the checker is **mypy**, the most used one; the annotations use the standard library's `typing` (nothing to install); the Python floor may rise, 3.9 is not a goal.

## Intent

- Catch wrong shapes before they ship: `None` reaching a string method, a `bytes | str` return used as `str`, an attribute set that a class doesn't declare. The roadmap's example: the `git()` helpers (`sourcelib.git`, `sourcelib.git_out`, `scripts/pii_check.git`) return different shapes.
- **Scope:** every Python module behind a launcher (`docs/adr.md`, 4): the 11 in `plugins/wiki/scripts/`, `plugins/wiki/sources/ms-teams/snapshot.py` and the repo's `scripts/pii_check.py`. Not `tests/` (can follow later, parked).
- **mypy is a dev tool**, like pytest and ruff: CI and contributors install it; the plugin never imports or runs it, and the wikis never need it.
- **End state:** every module in scope passes `mypy --strict`, and ruff's `ANN` rules keep new functions annotated. `ANN` alone only checks that annotations exist; mypy checks that they are right.

## Findings so far (2026-11-21, Linux, Python 3.13; checked in review)

1. **mypy 2.x refuses `--python-version 3.9`** ("must be 3.10 or higher"); 1.20.x is the last line that targets 3.9. mypy drops a target after its end of life, and 3.10 reached its end of life in October 2026, so a 3.10 floor would likely need raising again soon. **The floor rises to 3.11:** it is supported until October 2027, and its `typing` has `NotRequired`, `Required`, `Self` and `assert_never`, which typed hook JSON (`TypedDict`) wants without `typing_extensions`. The cost: Ubuntu 22.04's system Python is 3.10; Debian 12, Ubuntu 24.04 and python.org installs are 3.11 or later. mypy is pinned to a major (`mypy>=2,<3`) in CI.
2. **Baseline, unannotated:** default options, 3 errors (`_cache` and `_shown` need annotations; `sources.py:499` assigns to the name an `except` bound). With `check_untyped_defs`, **66 errors in 9 files**; about 25 are `HookCall` and other `__slots__` classes whose attributes aren't declared at class level, `sourcelib.Question.raised_date` is the same pattern. `--strict`: 1,083 errors in 12 files, nearly all "missing annotation", so strict comes module by module.
3. **pyright, as a probe** (not the chosen tool): 32 errors at its basic level, mostly `Optional` misuse (`guard.py:530`, `:550`, `install_source.py:156`, `lint.py:173`, `:500`, `:514`, `sourcelib.py:652`, `:853`, `sources.py:503`–`537`), `wiki_check.py:331` (`hist` possibly unbound), `contract.py:265` (`None` default for a `str` field) and 12 in `pii_check.py`, all from `git()` returning `bytes | str`. Each is a real bug or a missing annotation.
4. **The interpreter cache doesn't check the version.** `py-launch.sh` and `py-run.sh` cache the found interpreter's path in `$CLAUDE_PLUGIN_DATA/python` and trust it later without probing (`_pl_ok`, `_pr_ok` check only for an absolute path to an executable `python*`). A machine that cached a 3.9 or 3.10 keeps running on it after the floor rises; the first 3.11-only code evaluated at run time fails, and the guard fails closed with only "guard.py failed (exit 1)": **every tool call blocked**, with no hint why. The floor must rise, cache included, before any annotation lands.
5. **Imports cost start time.** `import typing` adds about 2–3 ms per start (3.10 and 3.13, Linux) against the guard's ~28 ms, more on Windows; `hookjson.py` already avoids `dataclasses` for that reason. With `from __future__ import annotations`, annotations are never evaluated, and `TYPE_CHECKING = False` / `if TYPE_CHECKING: from typing import ...` keeps `typing` out of the guard's run-time imports.
6. **Sibling imports resolve.** With the files listed, mypy resolves the bare sibling imports (`import contract`, also from `snapshot.py`) without `mypy_path`, and the generic names (`lint`, `guard`, `sources`) don't clash.
7. **Platform branches.** The code branches on `os.name == "nt"`, which mypy doesn't narrow, so a Linux run checks both sides; no Windows mypy job.

## Pull requests and tasks

One commit per task. Three pull requests or more, each green and shippable on its own:

- **PR 1, the ground:** tasks 1–3 (spike, floor, mypy in CI at the baseline level).
- **PR 2:** task 4 (the guard's parser to strict). **PR 3:** task 5 (`sourcelib.py`). **PR 4:** task 6 (`guard.py`). **PR 5:** tasks 7–8. **PR 6:** task 9 (`scripts/pii*`, owner review, `CONTRIBUTING.md`, "Trust") and closing.

Each task: `bash tests/run-tests.sh` green, plus `--e2e` where a launcher or another `.sh` changes; `ruff check .`; `shellcheck -S warning`; from task 3 on, `mypy` green.

### 1. Spike (time-boxed: half a day)

Answer, with evidence in "Spike results" below; no production code:

- **Config:** `mypy.ini` at the root (no `pyproject.toml` here; ruff has `ruff.toml`), `files`, `python_version = 3.11`; confirm finding 6.
- **Gradual strictness:** per-module sections that turn strict on (some flags, like `warn_unused_ignores`, are global only), or `strict = True` globally with per-module relaxations that shrink task by task. Pick one and show it working on two modules.
- **The baseline at `check_untyped_defs`** (finding 2): sort the 66 into real bugs, class-attribute declarations and noise; which task fixes which.
- **Start-time cost** (finding 5): the guard's start before and after a trial annotation of `contract.py`, with and without `from __future__ import annotations` and the `TYPE_CHECKING` guard; choose the rule for the guard's modules (`guard.py`, `contract.py`, `hookjson.py`) and for the rest. Keep the trial's branch for task 4.
- **ruff `ANN`:** which rules (whether `ANN401`, no `Any`, is wanted), and per-file ignores that shrink as modules are done.
- **The cache fix** (finding 4): confirm the stale-cache failure with a fake old `python`. Default fix: a cache file named after the floor (`$CLAUDE_PLUGIN_DATA/python-3.11`), so older caches are never read: no parsing, no extra process start, repeatable at the next raise. Check the guard's protected paths and `py-run.sh`'s lookups cover the new name. Plus a first-line version check in `guard.py` (and the scripts' entry) that says "Python 3.11 or later is needed" instead of a bare exit 1.
- **CI:** mypy in the `lint` job and its time; a test job on the floor (Linux, plain, Python 3.11).
- **Review the task list** and revise it.

### 2. Raise the Python floor to 3.11

- `py-launch.sh` and `py-run.sh`: the floor as one constant per launcher, `>= (3, 11)`, "no Python 3.11 or later found", the cache fix from the spike, and the version check. Tests: the existing "no Python" messages, and new tests for a cache from before the raise and for an interpreter older than the floor (a fake `python`). `--e2e` green.
- Every other mention, with `grep -rn "3\.9\|(3, 9)\|py39"` as the checklist: `ruff.toml` (`target-version = "py311"` and its comment), the launchers' and `wiki-check.sh`'s header comments, `README.md`, `docs/setup.md`, `docs/adr.md` 4, `AGENTS.md`, `claude-review.yml`'s prompt, `py_version.py`, the `init` skill, `docs/plans/wiki-venv.md`, `docs/plans/dev-venv.md` (a note: its 3.9 job becomes 3.11), and the message assertions in `tests/`.
- CI: a test job on Python 3.11 (Linux, plain), so the suite runs on the floor. **A new required check: the owner adds it to `main`'s ruleset.**
- The commit message says users on Python older than 3.11 must upgrade: the guard blocks until they do.

### 3. mypy in CI, at the baseline level

- `mypy.ini` from the spike, every module in scope, `check_untyped_defs = True`. Fix what it reports: the `__slots__` classes get class-level attribute declarations (`HookCall` and others in the guard's parser, `Question`), so `hookjson.py` is fixed here; a module whose fixes belong to its own task gets a per-module relaxation naming that task.
- A fix that changes behaviour (a real `None` case, an unbound name) gets a test that fails without it.
- **`AGENTS.md`'s test rule, amended:** a change under `plugins/wiki/scripts/` that only adds or changes type annotations (no run-time behaviour) is covered by mypy and the existing suite; every behaviour change still needs its fixture or test.
- CI `lint` job: install `"mypy>=2,<3"`, run `mypy`. `AGENTS.md`'s lint rule and `docs/development.md`: `mypy` clean before committing, how to install it. `docs/adr.md` 4: mypy as a dev-only tool, never imported by the plugin.

### 4. `contract.py`, `hookjson.py`, `py_version.py` to strict

The guard's parser and its helpers first: the code that blocks or allows. Strict in mypy, `ANN` in ruff for these files. Starts from the spike's trial branch.

### 5. `sourcelib.py` to strict

874 lines, one sub-agent session. Includes `git()`/`git_out()` and `Question`.

### 6. `guard.py` to strict

934 lines, one sub-agent session. The two `Optional` accesses (`guard.py:530`, `:550`) get a test each if they are real.

### 7. `sources.py`, `sync_status.py`, `install_source.py` to strict

### 8. `lint.py`, `wiki_check.py`, `decode_download.py`, `sources/ms-teams/snapshot.py` to strict

### 9. `scripts/pii_check.py` to strict, and close

- `git()` returns `bytes` or `str` by argument: overloads, or two functions.
- `strict = True` with no relaxations left; ruff `ANN` for every module in scope, no per-file ignores.
- Close: a new decision in `docs/adr.md` (mypy strict, why mypy, the 3.11 floor, `tests/` out of scope); drop the roadmap item (park "Type checking for `tests/`" if wanted); delete this plan.

## Risks

- **Users on Python older than 3.11** (Ubuntu 22.04's system Python) lose the guard (it blocks, with a message saying what to install) until they upgrade.
- **A refactor hidden in an annotation task.** Annotation commits change no behaviour; anything that does gets its own test and its own line in the commit message.
- **`Any` creep.** `--strict` doesn't forbid an explicit `Any`; JSON from hooks is the natural place for it. Use `TypedDict` or `object` and narrow; keep `Any` to the JSON boundary and say where.
- **Slower guard.** Run-time `typing` imports in the guard's modules; the spike sets the rule (finding 5).

## Spike results

(Filled in by task 1.)
