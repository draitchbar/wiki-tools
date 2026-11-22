# Plan: type checking for the plugin's Python

Status: planned 2026-11-21 and reviewed the same day (one round, folded in); task 1 (spike) done the same day, tasks 2–9 revised from it; tasks 2 and 3 done the same day (PR 1, merged as #64); 2026-11-22: three PRs instead of six, and the run-time rule narrowed (owner); next task 4. Roadmap item: "Type checking for the plugin's Python" (`docs/roadmap.md`). Owner's decisions: the checker is **mypy**, the most used one; the annotations use the standard library's `typing` (nothing to install); the Python floor may rise, 3.9 is not a goal.

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

One commit per task, one sub-agent session per task. Three pull requests, each green and shippable on its own (the owner's choice after PR 1, 2026-11-22):

- **PR 1, the ground:** tasks 1–3 (spike, floor, mypy in CI at the baseline level). Merged as #64.
- **PR 2, the guard path:** tasks 4–6 (`contract`, `hookjson`, `py_version`, `sourcelib`, `guard`): the code that blocks or allows, reviewed as one. Task 4 also narrows the run-time rule (below).
- **PR 3, the scripts:** tasks 7–9 (`sources`, `sync_status`, `install_source`, `lint`, `wiki_check`, `decode_download`, `snapshot`, `pii_check`; `scripts/pii*` needs the owner's review, `CONTRIBUTING.md`, "Trust") and closing.
- **When PR 3 is up: a full review** that every function and method in scope is annotated (parameters and return), by reading the code, not only by trusting mypy and ruff: a relaxation or `# type: ignore` / `# noqa: ANN` left behind would hide one.

**The run-time rule, narrowed (owner, 2026-11-22):** `from __future__ import annotations` in every module; `typing` only under `TYPE_CHECKING = False` / `if TYPE_CHECKING:` in the guard's modules (`guard.py`, `contract.py`, `hookjson.py`), where a hook pays about 3 ms per import; elsewhere a plain `from typing import ...` (`cast`, `@overload`, a `TypedDict` base). Supersedes "Spike results", 3's rule for the other modules. `AGENTS.md` and `docs/development.md` say so.

Each task: `bash tests/run-tests.sh` green (the tools from `.venv`, `uv sync --locked`; `bash scripts/dev-lint.sh` runs the lint), plus `--e2e` where a launcher or another `.sh` changes; `ruff check .`; `shellcheck -S warning`; from task 3 on, `mypy` green.

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

- `py-launch.sh` and `py-run.sh`: the floor as one constant per launcher, `>= (3, 11)`, "no Python 3.11 or later found", the cache fix and the guard's version check as specified in "Spike results", 5. Tests: the existing "no Python" messages, and new tests for a cache from before the raise (an old `python` file pointing at a fake interpreter: never read), for an interpreter older than the floor (a fake `python`), and for the guard's version check. `--e2e` green.
- The cache's new name everywhere it is read: both launchers, `wiki_check.py:368` (its "cached" line), `tests/test_py_launch.py`, `tests/test_py_run.py:97`, `tests/test_wiki_check.py:80`.
- Every other mention, with `grep -rn "3\.9\|(3, 9)\|py39"` as the checklist: `ruff.toml` (`target-version = "py311"` and its comment; it brings two `B905` findings, `zip()` in `tests/test_contract_parity.py:69` and `tests/test_reader_binding.py:73`: both already check the lengths, so `strict=True`), the launchers' and `wiki-check.sh`'s header comments, `README.md`, `docs/setup.md`, `docs/adr.md` 4, `AGENTS.md`, `claude-review.yml`'s prompt, `py_version.py`, the `init` skill, `docs/plans/wiki-venv.md`, `docs/plans/dev-venv.md` (a note: its 3.9 job becomes 3.11, and its `pytest<9` pin loses its reason), and the message assertions in `tests/`.
- CI: a test job on Python 3.11 (Linux, plain), YAML in "Spike results", 6; the header comment of `ci.yml` lists it. **A new required check, "test (ubuntu-latest, plain, 3.11)": the owner adds it to `main`'s ruleset.**
- The commit message says users on Python older than 3.11 must upgrade: the guard blocks until they do.

Left out of PR 1: `claude-review.yml`'s prompt still says "Python 3.9+". The review action doesn't run on a PR that changes that file, so the one-line change to "3.11+" goes in a PR of its own.

### 3. mypy in CI, at the baseline level

- `mypy.ini` from "Spike results", 1: `strict = True` with every module in a relaxed section, which leaves `check_untyped_defs` and strict's other checks of unannotated code. Fix the 66 as "Spike results", 2, assigns them; `sourcelib.py`'s `settings_rules` state waits for task 5 behind a `disable_error_code` line naming it.
- ruff: `ANN` selected, with every module in scope in the per-file ignores and `tests/**` for good ("Spike results", 4), so a new module is checked from its first line.
- A fix that changes behaviour (a real `None` case, an unbound name) gets a test that fails without it. The spike found none at this level.
- **`AGENTS.md`'s test rule, amended:** a change under `plugins/wiki/scripts/` that only adds or changes type annotations (no run-time behaviour) is covered by mypy and the existing suite; every behaviour change still needs its fixture or test.
- **`AGENTS.md`, the run-time rule** ("Spike results", 3): `from __future__ import annotations`; `typing` only under `if TYPE_CHECKING:`; `guard.py` parseable by an old Python up to its version check.
- CI `lint` job: install `"mypy>=2,<3"`, run `mypy` ("Spike results", 6). `AGENTS.md`'s lint rule and `docs/development.md`: `mypy` clean before committing, how to install it. `docs/adr.md` 4: mypy as a dev-only tool, never imported by the plugin.

Every strict task (4–9): its modules leave the relaxed section of `mypy.ini` and ruff's per-file ignores; it fixes what its new types surface in the relaxed modules that call it (with the trial `contract.py`, `sourcelib.py:313`: `p` reused for a tuple, then a list).

### 4. `contract.py`, `hookjson.py`, `py_version.py` to strict

The guard's parser and its helpers first: the code that blocks or allows. Strict in mypy, `ANN` in ruff for these files. `contract.py` starts from the spike's trial ("Spike results", 3). A test that importing `guard` leaves `typing` out of `sys.modules`. `TypedDict`s for the hook JSON, if any, live under `TYPE_CHECKING`.

### 5. `sourcelib.py` to strict

874 lines, one sub-agent session. Includes `git()`/`git_out()`, `Question` and `settings_rules`' mixed-type state (`st`, 22 errors; its `disable_error_code` line goes).

### 6. `guard.py` to strict

934 lines, one sub-agent session. The two `Optional` accesses (`guard.py:530`, `:550`) are not bugs: both run only after `allowed_script()` returned a value, so `script_path()` is not `None` there. A restructure that mypy can follow (e.g. `allowed_script()` returning the script path too), no test.

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

2026-11-21, Linux, mypy 2.3.1 (2.4.1, the current release, gives the same 66), the guard version check tried on a copy of `guard.py`, ruff 0.16.9, Pythons 3.11 and 3.13. Experiments ran on copies outside the repo.

### 1. Config and gradual strictness

`mypy.ini` at the root, as task 3 adds it:

```ini
# mypy (CI and local: `mypy`): a dev tool, never imported by the plugin.
# Strict everywhere; the modules in the sections below are relaxed until
# their task in docs/plans/type-checking.md makes them strict.
[mypy]
python_version = 3.11
files =
    plugins/wiki/scripts/contract.py,
    plugins/wiki/scripts/decode_download.py,
    plugins/wiki/scripts/guard.py,
    plugins/wiki/scripts/hookjson.py,
    plugins/wiki/scripts/install_source.py,
    plugins/wiki/scripts/lint.py,
    plugins/wiki/scripts/py_version.py,
    plugins/wiki/scripts/sourcelib.py,
    plugins/wiki/scripts/sources.py,
    plugins/wiki/scripts/sync_status.py,
    plugins/wiki/scripts/wiki_check.py,
    plugins/wiki/sources/ms-teams/snapshot.py,
    scripts/pii_check.py
strict = True

# Not annotated yet: strict's checks of unannotated code only.
[mypy-contract,hookjson,py_version,guard,sources,sync_status,install_source,lint,wiki_check,decode_download,snapshot,pii_check]
disallow_untyped_defs = False
disallow_incomplete_defs = False
disallow_untyped_calls = False
disallow_any_generics = False
warn_return_any = False

# The same, and settings_rules' state dict until task 5. (A module named in
# two sections takes the options of one only.)
[mypy-sourcelib]
disallow_untyped_defs = False
disallow_incomplete_defs = False
disallow_untyped_calls = False
disallow_any_generics = False
warn_return_any = False
disable_error_code = operator, call-overload
```

- **Chosen: `strict = True` globally, with one relaxed section** that shrinks task by task; a new module is strict from the start. With every module relaxed it reports exactly the 66 of `--check-untyped-defs`; with this file, the 44 left after the 22 that wait for task 5. A module in two sections lost the first one's relaxations (sourcelib, with `disable_error_code` in a section of its own, went fully strict: 253 errors), hence the repeated lines. Demonstrated with the trial `contract.py` taken out of the relaxed list: removing `is_abs`'s annotations gives `contract.py:201: Function is missing a type annotation [no-untyped-def]` (and `[no-untyped-call]` at its call); `hookjson.py`, relaxed, has unannotated functions (`_clean`, `_opt`) and gets no such error.
- **Rejected: per-module `strict = True`.** mypy 2.3.1 applies it to every module, silently: a `[mypy-contract]` section, or one naming no module at all, gave `hookjson.py` 37 strict errors.
- Finding 6 confirmed: the module names are the bare file names, siblings resolve (also `snapshot.py`'s `import contract`), no `mypy_path`.
- Strict modules may call only typed functions (`disallow_untyped_calls`). The task order follows the imports: `contract`, `hookjson`, `py_version` and `pii_check` import no sibling; `sourcelib` imports `contract`; `guard` `contract` and `hookjson`; the rest `contract` and `sourcelib`, plus `sources` → `sync_status` and `wiki_check` → `lint`, each pair in one task.

### 2. The baseline: 66 errors at `check_untyped_defs`

| Group | Errors | Where | Task |
|---|---|---|---|
| Class-level attribute declarations | 23 | `hookjson.py:123`–`169`, all `HookCall` (`__slots__`, set outside `__init__`). guard's `Context` and `Sources` and `sourcelib.Question` set theirs in `__init__`: no error | 3 |
| Empty container needs a type | 16 | `var-annotated`: `contract.py:54`; `sourcelib.py:74`, `:124`, `:410` (2), `:594`, `:637`; `decode_download.py:60`; `guard.py:336`; `lint.py:349`, `:394`, `:414`, `:465`; `install_source.py:217`; `sources.py:513`, `:526` | 3 |
| One dict for ints and strings | 22 | `sourcelib.py:710`–`815`, `settings_rules`' `st` | 5 |
| Narrowing mypy can't follow | 5 | `sourcelib.py:128` (`_sink`: a list or `None`); `lint.py:173` (the caller's `_KEY` match guarantees the `:`); `lint.py:514` (`age` is `None` only when `raised_date` is); `wiki_check.py:324` (`n = None`); `sources.py:499` (`e` reused after its `except`) | 3 |

**No real bugs at this level.** pyright's `Optional` findings (finding 3) need annotated signatures, so mypy reports them in tasks 4–9. Two checked: `guard.py:530` and `:550` are not bugs (task 6); `contract.py:265` is the trial's `_field` (3).

### 3. Start-time cost

`guard.py` run directly (`-I -S -X utf8`), a Bash call `cat wiki/index.md` on a copy of `tests/guard-wiki` (loads `contract.py` and the source files), allowed. Median of 300 interleaved runs each, ms:

| `contract.py` | 3.11 | 3.13 |
|---|---|---|
| Today, unannotated | 21.6 | 24.8 |
| Annotated, `from __future__ import annotations` | 21.4 | 24.8 |
| Annotated, without it (evaluated, works on 3.11) | 21.4 | 24.9 |
| + `from typing import Final` at run time | 24.7 | 27.8 |
| + the same under `if TYPE_CHECKING:` | 21.7 | 25.1 |

Annotations cost nothing measurable; importing `typing` costs about 3 ms (12–14 %; `-X importtime`: 2.4–3.3 ms), `__future__` 0.1 ms. Windows not measured; process and import costs are higher there.

**The rule,** for every module in scope: `from __future__ import annotations` first; `typing` imported only as `TYPE_CHECKING = False` / `if TYPE_CHECKING: from typing import ...` (mypy takes any name `TYPE_CHECKING` as true; `from typing import TYPE_CHECKING` would import `typing`). So nothing from `typing` runs: no `cast()`, no run-time `@overload`, `NamedTuple` or `TypedDict` base; builtin generics and `X | None` need no import. In the guard's modules a test enforces it (task 4); elsewhere a run-time `typing` import is allowed with a comment saying why. `guard.py` itself stays parseable by old Pythons up to its version check (no `match`, no `except*`): a syntax error stops it before any line runs.

**The trial `contract.py`** (task 4 starts from it, or redoes it from this description): every function, `_cache`, and the locals `out`, `cur`, `plugin` annotated, `from __future__ import annotations`, no `typing` import. `field(path, key, default="") -> str` now returns `default` when a new `_field(path, key) -> str | None` returns `None`; `_cli` calls `_field` where it called `field(..., None)` (pyright's `contract.py:265`). `mypy --strict` and ruff `ANN` clean; the whole suite passes with it (contract-parity included).

### 4. ruff `ANN`

All of `ANN`, `ANN401` included: no `Any` in a signature; the JSON boundary takes `object` and narrows, and a needed `Any` gets `# noqa: ANN401` with the reason. Task 3's `ruff.toml` (task 2 has already raised the target):

```toml
[lint]
select = ["E", "F", "W", "B", "ANN"]
ignore = ["E501"]

[lint.per-file-ignores]
# Not annotated yet: each leaves the list when its task in
# docs/plans/type-checking.md makes it strict.
"plugins/wiki/scripts/{contract,decode_download,guard,hookjson,install_source,lint,py_version,sourcelib,sources,sync_status,wiki_check}.py" = ["ANN"]
"plugins/wiki/sources/ms-teams/snapshot.py" = ["ANN"]
"scripts/pii_check.py" = ["ANN"]
# The tests are out of scope.
"tests/**" = ["ANN"]
```

Confirmed with `ruff check .` on a copy (`contract` out of the list, trial file): clean except `B905` twice, from `target-version = "py311"` (task 2); `is_abs` without annotations gives `ANN201`.

### 5. The interpreter cache

**Reproduced:** `$CLAUDE_PLUGIN_DATA/python` pointing at a fake `python3.9` that logs its arguments and fails as 3.9 would on 3.11 code. The hook command ran it without a probe (only the `guard.py` call was logged) and printed its error, then `wiki guard: guard.py failed (exit 1); refusing (fail closed).`; `py-run.sh py_version` ran it too, exit 1.

**The cache name is read** in `py-launch.sh` (header, line 49), `py-run.sh` (header, lines 44–45), `wiki_check.py:368`, `tests/test_py_launch.py`, `tests/test_py_run.py:97`, `tests/test_wiki_check.py:80`. The guard names no cache file: it protects every path with the `.claude/plugins` segment (`_SEGMENTS`, `guard.py:122`), which covers a new name beside the old one.

**The fix:**
- The cache file is `python-3.11`: `$CLAUDE_PLUGIN_DATA/python-3.11` in `py-launch.sh`; in `py-run.sh` that, then `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/data/wiki-wiki-tools/python-3.11`; the same in `wiki_check.py`. Each launcher has one constant, `_pl_floor=3.11` / `_pr_floor=3.11`, for the cache name, the probe (`>= (3, 11)`) and the message; the test that compares the launchers' candidates compares the floors too. The old `python` file stays, never read (removing it costs a process start in Git Bash).
- Message, both launchers: `no Python 3.11 or later found (tried python, python3, py -3). Install it (Windows: from python.org, and turn off the python3 App execution alias), then start Claude again`.
- `guard.py`, after `from __future__ import annotations` and `import sys`, before the sibling imports:

  ```python
  if sys.version_info < (3, 11):
      sys.stderr.write("wiki guard: Python 3.11 or later is needed, %s is %d.%d. Install it (Windows: "
                       "from python.org), then start Claude again; refusing (fail closed).\n"
                       % (sys.executable, sys.version_info[0], sys.version_info[1]))
      sys.exit(2)
  ```

  Exit 2, so `py-launch.sh` passes the message on. Test: `python -I -S -c "import runpy, sys; sys.version_info = (3, 10, 0, 'final', 0); runpy.run_path(<guard.py>, run_name='__main__')"` (assigning `sys.version_info` works, checked on 3.11).
- **No check at the scripts' entry** (a change to the plan): with the version-named cache and the probe, a script reaches an old Python only if the cached path itself is replaced by an older one, and then it fails with its own traceback on that one call. The guard's check is there because its failure blocks every call with no hint.

### 6. CI

mypy on the 13 files: about 1.1 s without a cache, 0.1 s with one; `pip install` about 3 s. Not run on GitHub here.

`lint` job:

```yaml
      - run: python -m pip install ruff shellcheck-py "mypy>=2,<3"
      - name: mypy (Python types)
        run: mypy
```

`test` job, the floor added (task 2):

```yaml
  test:
    name: test (${{ matrix.os }}, ${{ matrix.mode }}${{ matrix.python != '3.13' && format(', {0}', matrix.python) || '' }})
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]   # windows: Git Bash
        mode: [plain, e2e]
        python: ["3.13"]
        include:
          - {os: ubuntu-latest, mode: plain, python: "3.11"}   # the floor
    ...
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
```

The explicit `name` keeps the four required checks' names (a matrix key would otherwise be added to each) and adds "test (ubuntu-latest, plain, 3.11)". The `include` entry gives `python` a new value, so it adds a job; a new key would instead merge into the existing Linux plain job.

### 7. Changes to the task list

- Task 2: the cache's readers listed (`wiki_check.py`, three test files); the two `B905` fixes; the YAML; the version check in `guard.py` only.
- Task 3: the 66 assigned; `ANN` in ruff from here, with per-file ignores; the run-time rule into `AGENTS.md`. Finding 2's "other `__slots__` classes" and `Question` don't show at this level: only `HookCall`.
- Tasks 4–9: each fixes what its types surface in relaxed callers; task 4 gets the `typing` test; task 5 the `st` dict; task 6's `Optional` accesses need no test.
