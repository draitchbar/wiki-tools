# Plan: size and complexity limits for the Python

Status: proposal, 2026-11-27, reviewed the same day (one round, folded in); sizes, names and ADR numbers brought up to date 2026-11-28 (after #118 and #120). Not started. The draft decision is at the end: ADR 21 goes into `docs/adr.md` with phase 1, covering the limits only, and is amended when phase 4 lands. This file is deleted when the last phase is done.

## Why

Some modules have grown past what one reader holds in mind: `sourcelib.py` (1229 lines) mixes six concerns, and a few functions do a whole script's work in one body (`wiki_check.py`'s `Check.run`, 263 lines). Nothing in the lint stops either from growing further. The goal is single responsibility, separation of concerns and no repeated code, enforced where a tool can do it and left to review where it can't.

## What the guidance says

- **No official numbers.** PEP 8 sets no length limit; every figure below is a convention.
- **Google's Python style guide:** no hard limit; a function over about 40 lines is a prompt to consider splitting it.
- **pylint's defaults** (ruff implements most): per function 50 statements, 12 branches, 6 returns, 5 arguments, 15 locals; per class 20 public methods, 7 attributes; per module 1000 lines.
- **Cyclomatic complexity** (McCabe): 10 is the usual ceiling, 15 with a stated reason (NIST SP 500-235). ruff's `C901` defaults to 10. Branching predicts defects better than line count.
- **Small versus deep.** *Clean Code* argues for functions of a few lines; Ousterhout (*A Philosophy of Software Design*) argues for deep modules with simple interfaces, and against splitting to meet a number, which leaves pieces that only make sense read together. This repo's style (`docs/adr.md`, 16: loops where they read better) is closer to Ousterhout.
- **Single responsibility is cohesion, not size:** a unit should do one job, nameable without "and", and change for one reason. Size is the cheap signal of where to look.
- **DRY:** share on the third copy, and only what changes for the same reason; a wrong shared abstraction costs more than a copy.

## What the code looks like (2026-11-27, sizes 2026-11-28)

Python under `plugins/` and `scripts/`, tests excluded: 322 functions, median 9.5 lines; 17 over 50 lines, 8 over 80. ruff 0.17.6's `C901`, `PLR0911`, `PLR0912`, `PLR0913` and `PLR0915` at their defaults flag 62 findings in 30 functions, 25 of them over complexity 10 (and 14 more in `tests/`).

| Unit | Size | What it mixes |
|---|---|---|
| `wiki_check.py` `Check.run` | 263 lines, complexity 57 | Numbered checks (`# 1. Layout.` …) inline, one after another. |
| `lint.py` `report` | 183 lines, complexity 38 | Several reports in one body. |
| `sourcelib.py` `settings_rules` | 124 lines, complexity 37 | A parser; some branching is inherent (`_ParseState` exists already). |
| `sourcelib.py` `validate_contract` | 81 lines, complexity 34 | Ordered checks, each extractable. |
| `sources.py` `op_settings`, `op_check_settings` | 89 and 97 lines | Subcommand handlers. |
| `sourcelib.py` (module) | 1229 lines, 60 top-level definitions | Paths, output and git; deferred questions; connector names (17); contract and instance validation; permission rules; the settings.json parser; a CLI for `lib-source.sh`. |
| `save.py` (module) | 919 lines | Cohesive (one feature); `run` at complexity 22. |
| `guard.py` (module) | 1193 lines; `Context` 331 lines, 21 methods | One file on purpose: a hook pays for every import. |

**Repeated code.** Five scripts define an empty `class Die(Exception)`. Their `main`s follow one pattern (run `_main`, map errors to exit codes, print with the script's prefix, flush) with differences:
- `lint`, `install_source`, `wiki_check`: identical: `Die` → 1, `GitBashPath` → 3, anything else → 3 with "internal error".
- `sources`: as those, and `BindingMixError` → 1.
- `sourcelib`: no `Die`; `BindingMixError` → 1; flushes `stdout` but not `stdout.buffer`.
- `file_snapshot`: no `GitBashPath` clause, so a Git Bash path prints `file-snapshot: internal error: GitBashPath: …` (exit 3).
- `sync_status` (a hook that never fails the session start), `save` and `decode_download` (their own exit codes) differ on purpose and stay out.

**Not repeated code, left alone:** `save.Git` beside `sourcelib.git` (a cleaned environment and an empty hooks folder, `docs/adr.md`, 18); the two `wiki_root()` (different messages, tested in `test_shared_helpers.py`); `native()` in `guard.py` and `sourcelib.py` (the guard stays off `sourcelib`, checked by `test_no_copies`).

## Phases

Each phase is its own pull request and changes no behaviour unless it says so; the existing tests pass, and the edits each phase needs to them are listed with it.

### 1. The limits (ruff and one test)

- `ruff.toml`: add `C901`, `PLR0911`, `PLR0912`, `PLR0913`, `PLR0915` to `select`, at the defaults (`max-complexity = 10`; pylint's 6 returns, 12 branches, 5 arguments, 50 statements). `tests/**` is exempt from all five. Add `RUF100` (unused `noqa`) too, so a refactor that brings a function under the limits must remove its `noqa`; enabling it also flags 32 `# noqa: E402` that ruff no longer needs (imports after `sys.path.insert`), 6 of them in `guard.py`, which this phase removes (comments only).
- The 30 functions over a limit today each get `# noqa: <codes>  # docs/adr.md, 21` on their `def` line, not a per-file ignore, so new code in the same file is checked. The `noqa` must be on the `def` line, also for a signature over several lines (after the opening `(`: `lint.report`, `lint.questions`); one on the closing `):` doesn't apply. The guard's modules get theirs too and keep them: they are never rewritten for size alone (16), but new guard code meets the limits.
- `tests/test_code_size.py`: every `.py` under `plugins/` and `scripts/` is at most 600 lines. Over-limit files are listed with their ceiling, at today's size: `sourcelib.py` 1229, `guard.py` 1193, `save.py` 919, `sources.py` 710 (2026-11-28; phase 1 re-measures). The test fails when a file is over its ceiling, and also when it is more than 20 lines under it or back under 600, so a ceiling follows the file down and growth back is seen. A pull request may raise a ceiling only when it says why. `guard.py`'s ceiling makes its growth visible without forcing a split.
- Not added: ruff has no module-length rule (pylint's `C0302` isn't implemented), hence the test. No class-size rule: the classes are few, and module size plus complexity cover them. The preview rules `PLR0917` (positional arguments) and `PLR0914` (15 locals) flag only functions already among the 30, so they add nothing today.
- `AGENTS.md`: one line beside the Python style rule naming the limits and ADR 21.
- Tests: the new test; the `noqa` changes are comments only and need none (as for annotations only, AGENTS.md).

### 2. One `main` for the scripts

- `sourcelib.run_main(prog, fn, argv, *, refusals=())`: the shared wrapper, with `Die` defined once beside it. It maps `Die` and each of `refusals` to 1, `GitBashPath` to 3, anything else to 3 with "internal error", and flushes `stdout` and `stdout.buffer`. Each script binds the shared `Die` (`from sourcelib import Die`), so the tests' `lint.Die`, `install_source.Die` and the others still resolve; `wiki_check` catches `lint.Die` only around lint's own calls, which a shared class doesn't change. `sources.py` and `sourcelib` pass `BindingMixError` as a refusal.
- `Die` and `run_main` stay in `sourcelib.py` through phase 4 (the helpers don't move), so these imports are written once.
- The one output change, deliberate: `file_snapshot` reports a Git Bash path as `file-snapshot: <message>` (exit 3, as before) instead of an internal error. A test covers it. The extra `stdout.buffer` flush in `sourcelib` writes nothing new.
- Tests: a unit test of `run_main` (each exit code, the prefix, the flushes); `test_no_copies` adds `run_main` and `Die` to the shared names.

### 3. The long functions outside `sourcelib.py`

In this order, one pull request each or a few together:
1. `wiki_check.py` `Check.run`: one method per numbered step; `run` calls them in order. The numbering stays in the method names or their docstrings.
2. `lint.py` `report`: one function per report section.
3. `sources.py` `op_settings`, `op_check_settings`; `install_source.py` `check`; `save.py` `run`; `file_snapshot.py` `run`.

`lint.py` (583 lines) and `wiki_check.py` (527) may cross 600 when their long functions become several with their own signatures and docstrings. Then the cohesive part moves into a module of its own (in `lint.py`, say, the question reports beside `questions`), not a ceiling: a ceiling is for code that predates the limits.

A function in a guard module isn't on this list. Where a split reads worse than the whole (an ordered validation that must stop at the first failure, say), the `noqa` stays, with a one-line reason after the ADR reference.

### 4. Splitting `sourcelib.py`

First a pure move, reviewed as one: names move, bodies don't. Then, in their own pull requests, the splits of `validate_contract`, `validate_instance` and `settings_rules` (`settings_rules` last: a parser can stay one state machine, with its `noqa` and a comment saying so, if splitting it reads worse).

**By responsibility, function by function,** not along the file's comment sections: those depend on each other in a cycle (connector names call permission rules, which call validation, which calls connector names). The shared helpers stay in `sourcelib.py`, and everything else moves out. The scripts import those helpers at about 90 call sites (`out` 17, `err` 16, `words` 12, `quietly` 12, `toplevel` 10, `native` 9, `git` and `git_out` 9), against about 25 for validation. The other way round, keeping validation and the CLI in `sourcelib.py`, would rewrite the 90 and leave the helpers in a module named after what it no longer holds; this way `lib-source.sh`'s one `_pr_call sourcelib` line changes, which needs a green `--e2e`.

| Module | Holds | About |
|---|---|---|
| `sourcelib.py` | The helpers: `native`, `show`, `_shown`, `out`, `err`, `_sink`, `_b`, `quietly`, `words`, `names`, `_IFS`, `_NAME_CUT`, `_grep_file`, `read_text`, `git`, `git_out`, `toplevel`, `GitBashPath`; `run_main`, `Die` (2) | 150 lines |
| `questions.py` | Deferred questions: `Question`, `QID`, `QUESTIONS`, `KINDS`, `MARKER`, `MARKER_ANY`, the `_Q_*` patterns, `_q_date`, `open_questions`, `read_questions` | 90 |
| `settings_json.py` | The settings.json parser: `_ParseState`, `settings_rules`, `settings_key_typos`, `SETTINGS_KEYS`, `PERMISSION_KEYS` | 170 |
| `connectors.py` | The pair table (17): `CONNECTORS`, `_PAIR`, `_SERVER`, `_SERVERS_KEY`, `_pairs`, `TABLE_ERR`, `CLOUD_NOTE`, `SETTINGS_CLOUD`, `ConnectorsError`, `BindingMixError`, `connector_pairs`, `server_of`, `cloud_name`, `is_cloud`, `_quoted`, `_unquoted`, `binding_rules`, `_has_mcp`, `_both_forms`, `tools_instances`, `wiki_pairs` | 150 |
| `permissions.py` | Permission rules: `_PATH_RULE`, `_SOURCE_SCRIPT`, `reader_rules`, `type_rules`, `narrow_rules`, `needed_rules`, `user_rules`, `rules_check`, `stale_rules`, `covers`, `_fields`, `_by_list`, `missing_rules`, `blocked_rules`, `settings_check`, `_free_of`, `free_cloud`, `wiki_binding_error`, `cloud_setup`, `cloud_missing` | 300 |
| `validation.py` | Contract and instance validation: `PLACEHOLDER_RE`, `SECTIONS`, `_CACHE_RULE`, `_SCRIPT`, `_OP`, `validate_contract`, `validate_instance`, `reader_errors`, `has_body_section` (with `from questions import _Q_FENCE`), `instance_fields`, `FIELD_ARG_RE`, `manual_keys`; the CLI `lib-source.sh` calls (`_main`, `main`) | 320 |

Every top-level name in `sourcelib.py` is in the table (checked 2026-11-28; `TYPE_CHECKING` is the import idiom each module has its own of); the phase's first step regenerates this list from the file and fails on any name left out. Imports go one way, checked with an AST pass over the current file: `sourcelib` ← `questions`, `settings_json`, `connectors` ← `permissions` ← `validation`. Callers and tests import from the new modules directly; no re-exports. The names were checked against the reviewer's own AST pass; `rules` and `shared` were rejected as too generic.

**Edits beyond import paths:**
- `tests/test_source_neutral.py`: `ALLOWED["sourcelib.py"]` splits by where each allowed word lands: `claude_ai_`, the docstring example of a pair, goes with `connectors.py`; re-check the rest against the file at phase 4 (`codebase_instance` became `instance_fields` in #118).
- `tests/test_sync_status.py`: `SS_FILES`, the files of its minimal plugin, adds the modules `sync_status.py` now reaches (`questions.py`, `validation.py` for `manual_keys` and `instance_fields`, and what they import).
- `tests/conftest.py`: the reset of module state moves with it: `sourcelib._shown` and `_sink` stay, `_pairs` becomes `connectors._pairs`. A reset left on the old module would do nothing, silently.
- `test_no_copies`: the guard's ban on importing `sourcelib` extends to every new module.
- A test of the import direction (an AST pass, like `test_no_copies`).
- Docs that name `sourcelib.py` for what moves: `plugins/wiki/sources/connectors.md` (line 17) and `docs/layout.md` (lines 30, 40, 42); ADR 17 (only `sourcelib.py` reads the table: now `connectors.py`) and ADR 12 (`sourcelib.open_questions`: now `questions.open_questions`), through ADR 21's amendment.
- `mypy.ini`'s `files` and AGENTS.md's list of Python modules.

Measure a script's start before and after on Windows (Git Bash): five more imports should cost little, but ADR 4 exists because process time there matters.

Open: whether `connectors.py` and `permissions.py` are one module (connector names exist for the rules) or two (ADR 17's table changes for other reasons than the rules). Two is proposed; the grouping works either way.

### Not planned

- `guard.py`: no split, no refactor for size (3, 16). Its `noqa`s are permanent; its ceiling only shows growth.
- `save.py` stays one module: one feature, and 919 lines with a ceiling. Phase 3 shortens `run`; a split is for when it grows.
- Tests: no limits. `test_save.py` (1191 lines) mirrors `save.py`; it splits if `save.py` does.

## Draft: ADR 21

Added to `docs/adr.md` with phase 1 as `## 21.` (shown one level down here); the paragraph marked *phase 4* is added by the amendment when phase 4 lands.

### 21. Size and complexity limits
**Decision.** In the Python under `plugins/` and `scripts/`, ruff enforces pylint's and McCabe's defaults per function: complexity 10 (`C901`), 6 returns, 12 branches, 5 arguments, 50 statements (`PLR0911`, `PLR0912`, `PLR0913`, `PLR0915`), and `RUF100` flags a `noqa` no longer needed. A test (`tests/test_code_size.py`) caps a module at 600 lines. A function over a limit carries a `noqa` on its `def` line naming this decision, with a reason where it is kept for good; a module over the cap has a ceiling in the test, at its size within 20 lines, raised only by a pull request that says why. The guard's modules meet the limits in new code only: their existing `noqa`s stay, and `guard.py`'s ceiling shows growth without forcing a split, since it is one file by design. `tests/` is exempt. The scripts share one `main` wrapper (`sourcelib.run_main`) and one `Die`, defined once (`test_no_copies`); code that only looks alike and changes for different reasons stays separate.

**Why.** By 2026-11-27 one module, `sourcelib.py`, held six concerns in 1215 lines (1229 by 2026-11-28), and 30 functions were over a default limit, the largest at 263 lines and complexity 57; nothing in the lint stopped either from growing. The numbers are conventions (PEP 8 sets none): pylint's and McCabe's defaults are the ones most Python tools ship and readers know, and complexity predicts defects better than length. Per-function `noqa`s rather than per-file ignores, so a file with one old offender still checks its new code; ceilings that follow a file down, so the backlog can shrink but not grow back unseen. The guard keeps its shape for the reasons in 3 and 16. Splitting for a number alone was rejected: where a whole reads better than its pieces, the `noqa` stays with its reason. The plan and its measurements: `docs/plans/code-size.md` (deleted when done).

**Consequences.** Extends 16 from style to size. A new function over a limit fails the lint; the author splits it or writes the reason. A module that passes 600 is split by responsibility, not given a ceiling. Which split reads better stays a judgement for the author and the reviewer, as in 16.

*Phase 4:* Amends 12 and 17: `sourcelib.py` keeps the scripts' shared helpers; `questions.py`, `settings_json.py`, `connectors.py`, `permissions.py` and `validation.py` take its other concerns, each in `mypy.ini` and AGENTS.md's list, imports going one way (checked by a test). `connectors.py` is now the only reader of the pair table (17), `questions.py` parses the deferred questions (12), and `lib-source.sh` calls `validation.py`.
