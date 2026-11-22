# Plan: a repository-local venv for the dev tools

Status: rewritten 2026-11-22 to follow the standard Python layout (`pyproject.toml` dependency groups and a committed `uv.lock`), and the same day checked against the repo and made ready to implement (claims checked, the setup tried on a copy of the repo with uv 0.13.7 on Linux, Pythons 3.11, 3.12 and 3.13). It replaces the 2026-11-16 design (a hashed `requirements-dev.txt` compiled by `uv pip compile`, installable by pip or uv); what changed and why is under "Why the standard layout". Reviewed 2026-11-22; the findings are folded in ("Review"). Companion proposal for the wikis: `docs/plans/wiki-venv.md`.

## Intent (settled 2026-11-16, still holds)

- **Scope:** this repo only. The plugin stays standard library only (`docs/adr.md`, 4); nothing here changes what a wiki runs, and `py-run.sh` and `py-launch.sh` are not touched.
- **Why:** reproducibility (the same tool versions locally, in CI and in agent sessions) and isolation (nothing installed into the user's or the system's Python; no `pip install --user`, no `--break-system-packages` under PEP 668).
- **What goes in:** the dev tools CI installs today: `pytest`, `pytest-xdist`, `ruff`, `mypy` (`>=2,<3`), `shellcheck-py`.
- **Pinning:** every package, transitive ones included, pinned exactly, with hashes. This reverses "unpinned" in `docs/adr.md`, 7 and 15; both are amended when the work is done.
- **Python range:** one lock that installs on every supported Python, 3.11 up (the floor since #64), on Linux and Windows.
- **No silent installs:** Python and `uv` are prerequisites the user installs. Scripts check for them and stop with a message; packages go only into `.venv`, only when someone runs the setup on purpose.
- **One path everywhere:** laptops, CI and agent sessions (Claude Code and Copilot CLI locally, Claude Code in the cloud, worktrees included) run the same setup. (Copilot's cloud agent isn't used here: `AGENTS.md` rules out `/delegate`.)

## Why the standard layout (research, 2026-11-22)

- **What projects do.** Of eleven well-known Python repos checked on 2026-11-22 (flask, fastapi, httpx, pytest, pip, mypy, black, attrs, pydantic, django, click), eight declare their dev tools in `[dependency-groups]` in `pyproject.toml`, and six commit a `uv.lock` (flask, fastapi, pytest, attrs, pydantic, click). One keeps a top-level `requirements.txt`; none keeps a hashed `requirements-dev.txt`.
- **The standards.** PEP 735 (accepted) puts tools that only a project's developers need in `[dependency-groups]`; uv, pip (`pip install --group`, 25.1), PDM and Hatch read it. PEP 751's `pylock.toml` is the coming standard lock file, but pip's install support is still experimental (26.1, April 2026). uv's own advice is one lock, `uv.lock`, committed, with no parallel `requirements.txt`; it can export `requirements.txt` or `pylock.toml` if a tool ever needs one.
- **The old reasons against `uv.lock` no longer hold.**
  - *pip can't read `uv.lock`, so the Windows jobs would need a second file.* uv runs on Windows and in `astral-sh/setup-uv`, so every job installs with uv from the one lock. A pip install path is dropped.
  - *Never `uv sync` (the 2026-11-16 draft's rule, citing `docs/kfchou-security-review.md`, finding 3).* The review never said that: its concern was kfchou's git hook that ran `uv run` on every commit, which installs whatever a changed script declares. An explicit `uv sync --locked`, run by a person or a setup step from a committed lock, doesn't do that. The rule becomes narrower: no `uv run` in scripts, hooks or docs, and no uv-managed Python downloads.

## Checked 2026-11-22 (uv 0.13.7, Linux, a copy of the repo outside it)

- A `pyproject.toml` with only `[dependency-groups]` locks, but can't state a Python floor: uv defaulted to `requires-python = ">=3.13"` (the newest Python it found). So a minimal `[project]` table is needed, with `[tool.uv] package = false` so the repo itself is never built or installed.
- The file under "Files" locked 16 packages plus the project itself (uv reports "17"): pytest 9.2.0, pytest-xdist 3.8.0, ruff 0.17.6, mypy 2.4.1, shellcheck-py 0.11.0.1 and their dependencies, `requires-python = ">=3.11"`, Windows-only `colorama` marked, hashes for every artifact (cp311 wheels for Linux and Windows among them). `uv.lock` is about 85 KB, LF line endings.
- `uv sync --locked` installs the `dev` group by default (no `--group` needed) and built `.venv` in well under a second from uv's cache. A uv-made `.venv` carries its own `.gitignore` (`*`).
- With that `.venv`, on today's tree: the full suite green, plain and `--e2e`, on 3.13 (1074 passed, 1 skipped, 10 s, xdist) and on 3.11 (8 s plain, 17 s `--e2e`); `ruff check .`, `mypy` and `shellcheck -S warning` clean. pytest still takes `tests/pytest.ini` (rootdir `tests/`); `ruff.toml` and `mypy.ini` stay in charge (the new file has no `[tool.ruff]`, `[tool.mypy]` or `[tool.pytest]`), and ruff skips `.venv` by default.
- `uv sync --locked --check -q`, about 60 ms, needs no network (`UV_OFFLINE=1` gives the same answers), prints nothing and exits 0 on a current `.venv`; exits 1 with uv's own message when `.venv` is missing or a package was removed ("The environment is outdated; run `uv sync`"), and when `pyproject.toml` changed without `uv lock` ("The lockfile at `uv.lock` needs to be updated ... hint: run `uv lock`"); exits 2 when `required-version` doesn't match the running uv or no interpreter is found. It accepts a `.venv` on any Python ≥ 3.11 (made with `--python 3.11` or 3.12, checked without `--python`: 0). It replaces the old design's stamp file. `uv sync --locked` itself fails with the same lockfile message, so CI needs no separate `uv lock --check` step.
- `[tool.uv] python-downloads = "never"` in `pyproject.toml` works: `--python 3.11` with no 3.11 installed fails ("No interpreter found ... downloads are set to 'never'", exit 2) instead of downloading. But `UV_PYTHON_DOWNLOADS` in the environment overrides it, and even `--check` then downloads (review: `UV_PYTHON_DOWNLOADS=automatic uv sync --locked --check --python 3.10` fetched CPython 3.10). So `dev-env.sh` and CI also set `UV_PYTHON_DOWNLOADS=never` ("Scripts", "CI").
- `[tool.uv] no-build = true` (review): the lock has an sdist beside the wheels for all 16 packages, and without it uv would build one (run its build backend) where no wheel fits. Wheels cover CPython 3.11 to 3.15 on Linux and Windows for every compiled package (mypy, librt, ast_serialize); `uv sync --locked` with `no-build` works on 3.11 and 3.13, and the lock is unchanged by it.
- `uv.lock` passes `pii-check.sh text` (general patterns): its only hosts are `pypi.org` and `files.pythonhosted.org`.
- uv prefers a uv-managed Python it already has over the system one (here a managed 3.13 over the system 3.12). Downloads stay off; a managed Python someone installed on purpose is fine.
- A `--python` path works (`uv sync --locked --python /path/to/python3.11`); switching Python recreates `.venv`.
- A venv Python started with `-I -S` has only the standard library on `sys.path` and keeps `sys.executable` as the venv path, which `_pr_ok` accepts. So the plugin under test still sees no third-party package.
- `uv sync` on a `.venv` made by `python -m venv` reuses it and leaves `pip` in it.

The repo as it is (checked the same day):
- `tests/run-tests.sh` (mode 100644, run with `bash`) finds Python with `py-run.sh`'s `_pr_find` (the `$CLAUDE_PLUGIN_DATA/python-3.11` cache, the hooks' cache, then `python`, `python3`, `py -3`) and runs `"$_pr_py" -X utf8 -m pytest tests/ [-n auto --dist loadfile] ARGS`; no `-I`.
- `tests/conftest.py`'s `pydata` fixture writes `sys.executable`, the Python running pytest, into the `python-3.11` cache in a temporary `CLAUDE_PLUGIN_DATA`, so the launchers under test run that same Python. With pytest in `.venv`, **the plugin under test runs the venv's Python**, not the one `_pr_find` would pick (the draft said otherwise). That is what makes CI's floor job test 3.11: its `.venv` is made on 3.11.
- CI (`.github/workflows/ci.yml`): job `lint` (ubuntu, `setup-python` 3.13, `pip install ruff shellcheck-py "mypy>=2,<3"`, four steps: `ruff check --output-format=github .`, `mypy`, `git ls-files -z '*.sh' | xargs -0 shellcheck -S warning`, the CRLF check); job `test`, matrix `os` ubuntu-latest and windows-latest × `mode` plain and e2e on 3.13, plus `{ubuntu-latest, plain, 3.11}`, `shell: bash`, `pip install pytest pytest-xdist`, a git identity, `bash tests/run-tests.sh [--e2e]`. Required checks: `lint` and the five `test (...)` names; the job names must not change. First-party actions are referenced by tag (`actions/checkout@v4`, `actions/setup-python@v5`); the one third-party action, in `claude-review.yml`, by commit SHA.
- `.gitignore` has no `.venv/` (this clone excludes it in `.git/info/exclude` only). `.gitattributes` names `*.sh`, `*.json`, `*.py`, `*.md`, but not `*.toml` or `uv.lock`.
- `AGENTS.md` plus `CONTRIBUTING.md` is 7856 bytes; `tests/test_agent_files.py` fails at 8192. About 330 bytes to spare; the edits under "Docs", as worded there, make 7938 (measured in review).
- `.github/workflows/claude-review.yml` and `pii.yml` install nothing and run no tests; the review's tools are read-only.
- `docs/setup.md` has no test or pytest line (the draft named one).
- `.claude/skills/fix-issues-ai/SKILL.md` names `ruff check .` and `shellcheck -S warning` in its brief, and its subagents work in fresh worktrees, which have no `.venv`.
- The plugin has its own `plugins/wiki/scripts/lint.sh` (wiki lint, named in the guard's tests and the skills), so the repo's lint script gets another name: `scripts/dev-lint.sh`.
- This clone has a `.venv` made by hand on 2026-11-22 (`python3 -m venv`, Python 3.12, pip, no `uv.lock` behind it) with a `plugin-data/` folder whose `python` and `python-3.11` files point at `.venv/bin/python`: a `CLAUDE_PLUGIN_DATA` workaround to make `run-tests.sh` use it. Left in place by this check; deleted in step 0.

## Design

### Files

| File | What |
|---|---|
| `pyproject.toml` | As below. The only file people edit to change a tool. |
| `uv.lock` | Generated by `uv lock`; committed; never edited by hand. |
| `scripts/dev-env.sh` (sourced, mode 100644) | Finds `uv`, checks `.venv` is current, finds the venv's Python and tool folder. Shared by `run-tests.sh` and `dev-lint.sh`. |
| `scripts/dev-lint.sh` (mode 100644, run with `bash`) | ruff, mypy, shellcheck, the CRLF check: the four steps CI's lint job runs today, from `.venv`. |
| `tests/run-tests.sh` | Runs pytest from `.venv` through `dev-env.sh`. |
| `tests/test_dev_env.py` | The tests ("Tests"). |
| `tests/conftest.py` | `WIKI_TOOLS_DEV_VENV`, `UV_PROJECT_ENVIRONMENT` and `UV_PYTHON_DOWNLOADS` join `_DROP`. |
| `.gitignore` | `.venv/` (uv's own `.venv/.gitignore` doesn't cover a hand-made one). |
| `.gitattributes` | `*.toml text eol=lf`, `uv.lock text eol=lf`. |
| `.github/workflows/ci.yml` | uv in every job ("CI"). |

```toml
# The dev tools for this repo (tests and lint), locked in uv.lock and
# installed into .venv by `uv sync --locked` (docs/development.md,
# "Dev environment"). The plugin never reads this file: it is standard
# library only (docs/adr.md, 4).
[project]
name = "wiki-tools-dev"
version = "0"
requires-python = ">=3.11"

[dependency-groups]
dev = ["pytest", "pytest-xdist", "ruff", "mypy>=2,<3", "shellcheck-py"]

[tool.uv]
package = false
python-downloads = "never"
no-build = true
required-version = ">=0.13.7"
```

No `[build-system]`. `no-build`: wheels only, never a package's build code; a Python with no wheel for some package fails at `uv sync` with uv's message. `required-version` is the uv the lock was made with (update it with the CI pin when a newer uv rewrites the lock). `ruff.toml` and `mypy.ini` stay as they are; moving their settings into `pyproject.toml` is not part of this work.

### Setup: `uv sync`

There is no `dev-setup.sh`: the setup is the standard command, documented once.

```
uv sync --locked                          # create .venv if missing, make it match uv.lock
uv sync --locked --python 3.11            # the same on a given Python
```

- Downloads off through `pyproject.toml`; no Python ≥ 3.11 found → uv's own error; the docs give the install hint per platform, and say not to set `UV_PYTHON_DOWNLOADS` (it overrides the file) or `UV_PROJECT_ENVIRONMENT` (the scripts use `.venv`).
- `--locked` always: it fails if `uv.lock` doesn't match `pyproject.toml`, instead of quietly re-resolving.
- Once per clone and per worktree (a worktree has no `.venv`; uv fills it from its cache, offline once cached).
- Changing a tool: edit `pyproject.toml` (or `uv add --dev <tool>`), run `uv lock`, commit both files. A version bump: `uv lock --upgrade` (or `--upgrade-package <name>`), run the tests and lint, commit `uv.lock`.

### Scripts: use the venv, fail when it is stale

`run-tests.sh` and `dev-lint.sh` use `.venv` without activation (activation differs between bash and Git Bash and is lost between an agent's Bash calls).

`scripts/dev-env.sh`, sourced; like `py-run.sh` it only defines things, never exits, is safe under `set -u`, and uses builtins plus `uv`:
- `_de_root`: the repo root, from its own path (`$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)`; not `${BASH_SOURCE[0]%/*}`, which breaks on a path without a slash). `dev-lint.sh` finds `dev-env.sh` the same way, as `run-tests.sh` finds its folder.
- `_de_venv LABEL`: returns 0 and sets `_de_py` (the venv's Python) and `_de_bin` (its tool folder), 1 with a message on stderr, or 2 under the override.
  1. `WIKI_TOOLS_DEV_VENV` unset or empty → the venv; `off` → print `LABEL: WIKI_TOOLS_DEV_VENV=off: tools from PATH, outside uv.lock` and return 2; any other value → `LABEL: WIKI_TOOLS_DEV_VENV must be off or unset`, return 1.
  2. `UV_PROJECT_ENVIRONMENT` set and not empty → `LABEL: UV_PROJECT_ENVIRONMENT is set; these scripts use .venv. Unset it.`, return 1 (uv would check, and `uv sync` fill, another folder, so the advice in 4 would loop).
  3. No `uv` (`command -v uv`) → `LABEL: uv not found. Install uv 0.13.7 or later (https://docs.astral.sh/uv/getting-started/installation/; a distribution's package may be older), then run: uv sync --locked`, return 1.
  4. `(cd "$_de_root" && UV_PYTHON_DOWNLOADS=never uv sync --locked --check -q)` (a subshell `cd`, so no path argument goes through Git Bash's conversion; the variable because a user's own `UV_PYTHON_DOWNLOADS` would override `pyproject.toml`, and `--check` downloads too); uv's stderr passes through. Exit 1 → `LABEL: .venv is missing or out of date with uv.lock. Run: uv sync --locked`, return 1. (A stale lock shows uv's own "run `uv lock`" hint above that line.) Any other non-zero (2: `required-version`, no interpreter) → `LABEL: uv could not check .venv (its message is above)`, return 1. A warning above hundreds of pytest lines goes unseen, by agents especially, and a stale venv gives "green locally, red in CI": so it fails.
  5. `_de_bin` is `$_de_root/.venv/bin` if it holds an executable `python`, else `.venv/Scripts` if it holds `python.exe` (Windows); `_de_py` the Python in it. Neither → the first message of 4, return 1.

`tests/run-tests.sh`:
- Sources `"$here/../scripts/dev-env.sh"`, then `_de_venv run-tests`: 0 → `py=$_de_py`; 1 → exit 1; 2 → today's path (`_pr_find`, the "pytest is not installed" check, its pip advice), `py=$_pr_py`.
- The rest as today with `$py`: the hooksPath note (not in CI), xdist when `"$py" -c 'import xdist'` works, `exec "$py" -X utf8 -m pytest "$here" "${par[@]}" "$@"`.
- Header comment: `uv sync --locked` once; the override; the pip lines kept only for the override.

`scripts/dev-lint.sh` (no arguments):
- `cd` to `_de_root`; `_de_venv dev-lint`: 0 → `PATH="$_de_bin:$PATH"`; 1 → exit 1; 2 → tools from PATH.
- Runs all four steps, each under a header line, even after one fails: `ruff check .` (with `--output-format=github` when `GITHUB_ACTIONS=true`), `mypy`, `git ls-files -z '*.sh' | xargs -0 shellcheck -S warning`, the CRLF check as CI has it (`::error::` only under `GITHUB_ACTIONS`). A tool not found fails its step ("not installed"), never passes. Ends with the failed steps' names and exit 1, or exit 0.

POSIX bash for Linux and Git Bash: no GNU-only flags, `$'\r'` and `xargs -0` as CI uses them today; shellcheck picks both new scripts up through `git ls-files '*.sh'`; LF endings.

Considered and not chosen: `uv run` in the scripts (it syncs implicitly, the review's concern); nox or tox (another tool with its own venvs, used by pip, black and django for multi-version matrices that CI already covers here); a Makefile or justfile (not in Git Bash by default); direnv (per-user shell setup, invisible to agents); a `dev-setup.sh` wrapper (the old design's; `uv sync --locked` is the standard command and needs no wrapper); a step argument for `dev-lint.sh` so CI keeps four named steps (one step's log shows the four headers; not worth the option); `UV_PYTHON_PREFERENCE=only-system` (would refuse a managed Python a user installed on purpose).

### CI (`.github/workflows/ci.yml`, owner review)

- Every job keeps `setup-python` for the interpreter (downloads are off, so uv needs a Python on the runner), with `id: py`; the `pip install` lines go. Then `astral-sh/setup-uv` pinned to a commit SHA with the version in a comment (as `claude-code-action` is), `version:` the uv pinned (0.13.7 or the newest at implementation, the same as `required-version`; a test checks they agree), the SHA that `gh api repos/astral-sh/setup-uv/git/ref/tags/<tag>` gives (dereferenced if the tag is annotated) for a release newer than that uv, so its built-in checksums cover the uv it downloads, `enable-cache: true`, and not its `python-version` input (it would let uv fetch one). Then `uv sync --locked` with `UV_PYTHON: ${{ steps.py.outputs.python-path }}` in the step's `env` (the exact interpreter, on Windows a `C:\...` path, without quoting it in bash).
- `lint`: `bash scripts/dev-lint.sh` replaces its four steps.
- `test`: `bash tests/run-tests.sh [--e2e]` as today; the git identity step stays. The 3.11 floor job stays a required check: its `.venv` is made on 3.11, so pytest and the plugin under test run on 3.11.
- No `uv lock --check` step: `uv sync --locked` already fails on a stale lock.
- Workflow-level `env: UV_PYTHON_DOWNLOADS: never`: belt and braces beside `pyproject.toml`, since a variable set by an action or the runner image would override the file.
- Job names and the matrix unchanged, so the required checks keep their names. The header comment says the tools come from `uv.lock`.
- The PII workflow and the Claude review are not touched.

```yaml
      - uses: actions/setup-python@v5
        id: py
        with:
          python-version: ${{ matrix.python }}   # lint: "3.13"
      - uses: astral-sh/setup-uv@<sha> # v<major.minor.patch>
        with:
          version: "0.13.7"
          enable-cache: true
      - run: uv sync --locked
        env:
          UV_PYTHON: ${{ steps.py.outputs.python-path }}
```

### Docs

- `docs/development.md`: workflow step 0 gains `uv sync --locked` (once per clone and worktree); step 2 and the lint block run `bash tests/run-tests.sh` and `bash scripts/dev-lint.sh`; the `pip install --user` lines go. New subsection "Dev environment": uv as a prerequisite (install hint per platform), `.venv`, what the scripts do when it is stale, the override, how to change or bump a tool (`pyproject.toml`, `uv lock`, `uv lock --upgrade`), downloads off, never `uv run`.
- `AGENTS.md` (Claude Code and Copilot CLI alike), within the ~330 bytes `test_agent_files.py` leaves: the test rule's "(unpinned, the test runner's only dependency, never the plugin's; pytest-xdist optional, ...)" becomes "(dev tools: `pyproject.toml`'s `dev` group, locked in `uv.lock`, never the plugin's)"; the lint rule becomes "`bash scripts/dev-lint.sh` (ruff, mypy, shellcheck, LF) must be clean before committing"; one new rule: "Once per clone or worktree, and whenever a script says `.venv` is missing or out of date: `uv sync --locked`. Never `uv run`." The Python rules line names the `dev` group as the only third-party Python, dev only.
- `.claude/skills/fix-issues-ai/SKILL.md`: the brief's checks become `uv sync --locked` in the worktree, then `bash tests/run-tests.sh` (and `--e2e`) and `bash scripts/dev-lint.sh`.
- `docs/layout.md`: `pyproject.toml`, `uv.lock`, `scripts/dev-env.sh`, `scripts/dev-lint.sh`.
- `docs/kfchou-security-review.md`: no edit; the new decision cites it for the narrowed rule.
- `docs/roadmap.md`: the item goes when done.
- Checklist for the rest: `git grep -n -E 'pip install|unpinned|python3-pytest|ruff check|shellcheck -S|mypy>=2|xdist optional' -- ':!docs/plans/'` (tracked files only: a `grep -r .` walks `.venv` and its thousands of `pip install` lines). Today it also names the comments in `ruff.toml` and `.shellcheckrc` (still true: `dev-lint.sh` runs those commands), `docs/setup.md`'s `pip install ocrmypdf` (unrelated) and `ci.yml`; `.claude/skills/new-source-type/SKILL.md` runs `run-tests.sh`, which now says when `.venv` is missing, so it needs no edit.
- When done: amend ADR 7 and 15 (pytest and xdist pinned, from `uv.lock`), ADR 4 (mypy's major pinned in `pyproject.toml`, not in CI) and ADR 8 (lint through `scripts/dev-lint.sh`), and add a decision: dev tools in `pyproject.toml`'s `dev` group, locked in `uv.lock`, installed only by an explicit `uv sync --locked`, never `uv run`; wheels only (`no-build`); uv-managed Python downloads off; why (this plan's research and checks).

### Tests

`tests/test_dev_env.py`, end to end through bash (`run` fixture), check names `dev-env/<case>`. Each test builds a copy in `tmp_path`: `scripts/dev-env.sh`, `scripts/dev-lint.sh`, `tests/run-tests.sh`, `plugins/wiki/scripts/py-run.sh`, and a fake `uv` in its own folder put first on `PATH`; it records its working folder and arguments to a log and answers with an exit code and stderr the test sets (e.g. `FAKE_UV_RC`, `FAKE_UV_ERR`). Fakes are bash scripts with a shebang, as `test_py_run.py`'s fake interpreters are, so they run from Git Bash too; venv fakes use the `.venv/bin` layout on both platforms. `CI=1` keeps the hooksPath note out. The real install isn't run in the suite (network); CI's own `uv sync --locked` covers it.

- **current:** uv 0 and a fake `.venv/bin/python` that records its arguments and answers 0 to everything (so `import xdist` works) → `run-tests.sh` runs it with `-X utf8 -m pytest <tests dir> -n auto --dist loadfile` and the given arguments; uv was called as `sync --locked --check -q`, in the repo root, also when `run-tests.sh` is started from another folder.
- **stale, lock stale:** uv 1 with each of uv's two messages → exit 1; uv's message and "out of date with uv.lock. Run: uv sync --locked" on stderr; the fake Python never ran.
- **missing:** uv 0 but no `.venv` → the same failure.
- **no uv:** `PATH` without `uv` → exit 1, the install hint. `PATH` is the fake's folder plus bash's own; skipped if `command -v uv` finds one in that same environment (asked through the `run` fixture first: on Windows Git's bash puts its own folders in front of `PATH`, `docs/adr.md`, 7, so `shutil.which` on bash's folder isn't enough).
- **uv env:** `UV_PROJECT_ENVIRONMENT=x` → exit 1, its message, uv never called. With `UV_PYTHON_DOWNLOADS=automatic` in the caller's environment, the fake uv records `never`. uv exit 2 → "could not check", not "out of date".
- **override:** `WIKI_TOOLS_DEV_VENV=off`, a `CLAUDE_PLUGIN_DATA` whose `python-3.11` file (`conftest.CACHE`) names a fake `python` (absolute, executable, named `python`, answering `-c 'import pytest'` with 0) → uv never called (empty log), the note on stderr, pytest run by that fake. A bad value (`WIKI_TOOLS_DEV_VENV=1`) → exit 1.
- **layout:** a driver that sources `dev-env.sh`, calls `_de_venv t` and prints `_de_bin`, `_de_py` and "still here": `.venv/bin/python` wins; with only `.venv/Scripts/python.exe` (an empty executable file, never run) that one; sourcing never exits.
- **lint:** fake `ruff`, `mypy`, `shellcheck` in `.venv/bin` (with a fake `python` there, so step 5 picks the folder) that record their arguments, in a git repo copy: all clean → exit 0, each tool run with today's arguments (`shellcheck -S warning` on the `*.sh` files `git ls-files` names); one tool failing → the other steps still run, exit 1, its name in the summary; `GITHUB_ACTIONS=true` adds `--output-format=github`; a committed file with CRLF fails the LF step and is named; under the override, a tool missing from `PATH` fails its step.

- **config** (Python, no bash): `pyproject.toml` read with `tomllib` (3.11's standard library): `requires-python` is `">=" + conftest.FLOOR` (so the next floor rise can't miss it, as `test_py_run.py` ties the launchers to `FLOOR`), and `uv.lock`'s `requires-python` the same; `[tool.uv]` has `package = false`, `python-downloads = "never"`, `no-build = true`; `required-version`'s version equals the `version:` under `setup-uv` in `ci.yml`, and that action is referenced by a 40-hex SHA; no tracked `*.sh`, workflow or `.githooks/` file contains `uv run`.

`bash tests/run-tests.sh` and `--e2e` green (the new module is bash-only, so both modes run it the same way), `dev-lint.sh` clean, no personal data in the fakes (made-up paths, `example.invalid`).

## Order of work

One pull request: once `run-tests.sh` requires `.venv`, CI must create it in the same change, and `AGENTS.md` must say so. Commits in this order.

0. Locally, before anything: delete the hand-made `.venv` (with its `plugin-data/`), then `uv sync --locked` once step 1's files exist. The `.git/info/exclude` line can stay.
1. `pyproject.toml` (above), `uv lock`, `.gitignore`, `.gitattributes`. Check: `uv sync --locked`; the suite plain and `--e2e` and the three linters through `.venv` (done on Linux 2026-11-22 for 3.11 and 3.13, on a copy).
2. `scripts/dev-env.sh`, `scripts/dev-lint.sh`, `tests/run-tests.sh`, `tests/conftest.py`'s `_DROP`, `tests/test_dev_env.py`. Check: `bash tests/run-tests.sh`, `--e2e`, `bash scripts/dev-lint.sh`.
3. `.github/workflows/ci.yml` (owner review: a workflow change, `CONTRIBUTING.md`, "Trust"), and the config test's `ci.yml` checks (`setup-uv`'s SHA and version), which need it. The pull request's own CI is the Windows check: every job green, and the Windows e2e job's time against main's last run ("Open"). Push the branch first after this step: from step 2 on, `run-tests.sh` needs a `.venv` that only step 3's CI makes, so an earlier push is red.
4. Docs, `AGENTS.md` (run `test_agent_files.py`: the size limit), `fix-issues-ai`, `docs/layout.md`, the ADRs, the roadmap item. Delete this plan.

## Open

- **Windows, the venv's `python.exe`:** `conftest.py` hands the plugin under test `sys.executable`; in a Windows venv that is `.venv/Scripts/python.exe`, a launcher that starts the base Python, so every launcher call in the tests may pay one more process start. Can't be measured here (no Windows). In step 3, compare the PR's Windows e2e and plain job times with main's last run. Default: keep `sys.executable`; if a job is more than about 10 % slower, `pydata` writes `getattr(sys, "_base_executable", sys.executable)` instead (the same Python, standard library only under `-I -S`) and a test checks the cache names an existing `python*`.
- **Windows, CI setup:** `setup-uv` under Git Bash and `UV_PYTHON` from `setup-python`'s `python-path`: seen only in the PR's CI. Default: as written; if uv doesn't take the path, `--python "$pythonLocation/python.exe"`.
- **Cloud sessions:** whether a Claude Code cloud environment has `uv`, and reaches PyPI for the first `uv sync`. Default: install it in the environment's setup (uv's installer) where the session can; otherwise `WIKI_TOOLS_DEV_VENV=off` with the tools installed as today, and the report says the run was outside the lock.
- **Automatic updates (owner):** the draft had Dependabot (`package-ecosystem: "uv"`) update `uv.lock` monthly. Left out by default: a Dependabot pull request gets no repository secrets, so `pii` (a required check, `--require-denylist`) fails unless `PII_DENYLIST` is also stored as a Dependabot secret, and the review lacks its token; and its description and commit carry upstream release notes and changelogs, with third parties' names, into a pull request description and, at the squash, into `main`'s history, which `CONTRIBUTING.md` rules out. Instead, bumps are a collaborator's pull request (`uv lock --upgrade`, "Setup"). If the owner wants Dependabot anyway: add `.github/dependabot.yml` and the Dependabot secret, and check on its first pull request that it updates a `package = false` project with only a dependency group. Either way (review): once `uv.lock` is committed, GitHub's repository setting "Dependabot security updates" opens such pull requests without any `dependabot.yml`; the owner checks it is off (alerts alone are fine).

## Review (2026-11-22)

Checked against the repo and tried with uv 0.13.7 on a copy; each finding is folded in above.

1. **High: `UV_PYTHON_DOWNLOADS` overrides `python-downloads = "never"`, and `--check` downloads too** (seen: it fetched CPython 3.10). → `dev-env.sh` runs the check with `UV_PYTHON_DOWNLOADS=never`; CI sets it workflow-wide; the docs say not to set it; a test.
2. **Medium: every package has an sdist in `uv.lock`;** where no wheel fits, uv would run its build code. → `no-build = true` (wheels cover 3.11 to 3.15 on Linux and Windows; tried on 3.11 and 3.13); in the ADR.
3. **Medium: nothing tests the policy in `pyproject.toml`.** Dropping `python-downloads` or `no-build`, a floor rise that skips `requires-python`, or `required-version` drifting from CI's uv would pass. → The `config` test.
4. **Medium: `UV_PROJECT_ENVIRONMENT`** makes uv check and sync another folder while the scripts use `.venv`; the advice "Run: uv sync --locked" would loop. → Refused with a message, step 2 of `_de_venv`.
5. **Medium: a push between steps 2 and 3 is red** (`run-tests.sh` needs `.venv`; CI makes none yet). → Push first after step 3; the config test's CI checks move to step 3.
6. **Low: uv's exit 2** (`required-version`, no interpreter) got the "out of date" advice. → Its own message.
7. **Low: the checklist's `grep -r .`** walks `.venv` and repeats `.github` and `.claude`. → `git grep`, with what it finds today.
8. **Low: `${BASH_SOURCE[0]%/*}`** breaks on a path without a slash. → `dirname`, as `run-tests.sh` does.
9. **Low: the "no uv" test's skip** used `shutil.which` on bash's folder; on Windows Git's bash puts its own folders first. → `command -v uv` through the `run` fixture.
10. **Low: unclear test setup:** the override fake is named in `CLAUDE_PLUGIN_DATA/python-3.11`, not the folder; the fake Python must answer `import xdist`; the lint fakes need a `.venv/bin/python`. → Spelled out.
11. **Low: the setup-uv pin** gave no way to get the SHA or check the uv download. → `gh api` on the official tag, a release whose checksums cover the pinned uv.
12. **Low: facts.** "Copilot cloud" sessions don't exist here (`/delegate` is ruled out); the security review never said "never `uv sync`" (the 2026-11-16 draft did); the install hint names the minimum uv (distribution packages can be older). → Corrected.
13. **Owner, open: "Dependabot security updates"** would open lock pull requests with no `dependabot.yml`. → Under "Automatic updates": check the setting is off.

Confirmed as written: the `AGENTS.md` edits fit (7938 of 8192 bytes); `uv.lock` passes the general PII patterns; uv's `--check` exit codes; one pull request is needed (CI and `run-tests.sh` must change together).
