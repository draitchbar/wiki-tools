# Plan: a repository-local venv for the dev tools

Status: designed 2026-11-16 and reviewed the same day (one review round; changes from it are folded in, see "Review"). Intent grilled with the owner. Companion proposal for the wikis: `docs/plans/wiki-venv.md`.

## Intent (settled)

- **Scope:** this repo only. The plugin stays standard library only (`docs/adr.md`, 4); nothing here changes what a wiki runs.
- **Why:** reproducibility (the same tool versions locally, in CI and in agent sessions) and isolation (nothing installed into the user's or the system's Python; no `pip install --user`, no `--break-system-packages` under PEP 668).
- **What goes in:** the dev tools CI installs today: `pytest`, `pytest-xdist`, `ruff`, `shellcheck-py`.
- **Pinning:** every package, transitive ones included, pinned exactly, with hashes. This reverses "unpinned" in `docs/adr.md`, 7 and in the xdist decision (today a second "10", see "Housekeeping"); both are amended when the work is done.
- **Python range:** one lock that installs on every supported Python, 3.9 up, on Linux and Windows. CI gains a Linux job on 3.9, the first run of the suite on the plugin's stated floor.
- **No silent installs:** Python (and `uv`, if used) are prerequisites the user installs. Scripts check for them and stop with a message; packages are installed only into `.venv`, only by a script someone runs on purpose.
- **One path everywhere:** laptops, CI and cloud agent sessions run the same setup script.
- **Agents:** a rule in `AGENTS.md`, no SessionStart hook.

## Research findings that shape the design

1. **`pip freeze` can't produce this lock.** A freeze records one machine's resolution, without environment markers. pytest needs `colorama` only on Windows and `exceptiongroup`/`tomli` only below 3.11. A lock valid on Linux + Windows × 3.9–3.14 needs a *universal* resolver that writes markers. (Confirmed in review: the compiled lock carries `colorama ; sys_platform == 'win32'` and `… ; python_full_version < '3.11'` lines.)
2. **The lock forks by Python version.** Some packages are pinned differently below and above 3.10 (in review: `pluggy` 1.6.0 vs 1.7.0, `iniconfig` 2.1.0 vs 2.3.1). "The same versions everywhere" means the same versions *per Python version*, which is what reproducibility needs.
3. **Universal resolvers today:** `uv pip compile --universal --python-version 3.9 --generate-hashes` writes a plain `requirements.txt` with markers and hashes that ordinary pip installs (review: `pip install --no-deps --require-hashes -r` resolved it on 3.14 with pip 25.1 and on 3.9 with pip 23.0; recompiling was byte-identical; 146 lines). pip's own `pip lock` (25.1) and `pip install -r pylock.toml` (26.1, April 2026) are experimental and resolve for the current environment only; pip-tools' `pip-compile` is not universal.
4. **pytest 9.0 (2025-11) dropped Python 3.9;** 8.4.x is the last line on 3.9 and installs through 3.14. pytest-xdist 3.8 still declares `>=3.9`. Python 3.9 reached end of life in October 2025.
5. **Dependabot:** the `uv` ecosystem's updater in dependabot-core re-runs `uv pip compile` on compiled requirements files and keeps `--universal` and `--generate-hashes` from the file's header (review read `uv/lib/dependabot/uv/file_updater/compile_file_updater.rb`); GitHub's docs still mention only `uv.lock`. The `pip` ecosystem edits line by line and would break a file with marker-split duplicate pins.

## Design

### Files

| File | What |
|---|---|
| `requirements-dev.in` | The four top-level tools; `pytest<9` while the floor is 3.9. The only file people edit. |
| `requirements-dev.txt` | Generated: `uv pip compile --universal --python-version 3.9 --generate-hashes requirements-dev.in -o requirements-dev.txt`, with the uv version named in the header. Committed. |
| `scripts/dev-setup.sh` | Creates and syncs `.venv`. Safe to re-run. |
| `scripts/lint.sh` | ruff, shellcheck, the CRLF check: the three steps CI's lint job runs today, from the venv (the tools live in `.venv/bin` or `.venv/Scripts`, off PATH). |
| `scripts/dev-env.sh` (sourced) | Finds the venv's Python and checks it is current; shared by `run-tests.sh` and `lint.sh`. |
| `.gitignore` | `.venv/`. |
| `.github/dependabot.yml` | `package-ecosystem: "uv"`, monthly, for `requirements-dev.txt`. |

### Q5: which tool (settled after review)

**`uv` generates the lock; `uv` or stdlib `venv` + pip installs it.** This is the owner's "uv when present, else venv", placed where the difference is safe.

- **Creating the lock** needs a universal resolver (finding 1), so whoever changes `requirements-dev.in` needs `uv`, at the version the header names. That is rare; Dependabot does the routine bumps.
- **Installing** works with either tool, because the output is a plain hashed requirements file. `dev-setup.sh`: with `uv` on PATH, `uv venv --python <found Python> .venv` (only when `.venv` is absent; newer uv refuses an existing one without `--clear`), then `uv pip sync --python .venv/<bin>/python --require-hashes requirements-dev.txt`. Without uv: `python -m venv .venv`, then `.venv/<bin>/python -m pip install --no-deps --require-hashes -r requirements-dev.txt`. Both paths run in CI.
- **Never `uv run`, `uv sync` or uv-managed Python downloads** (`UV_PYTHON_DOWNLOADS=never`, `--python` always given). uv never fetches an interpreter or installs on its own (the `uv run` concern in `docs/kfchou-security-review.md`).
- **Rejected: `pyproject.toml` + `uv.lock`** (with `[tool.uv] package = false` and dependency groups it needn't look like a package). pip can't read `uv.lock`, so the pip path would need a second, exported file that Dependabot doesn't regenerate.
- **Rejected for now: `pylock.toml`** (PEP 751): pip's support is experimental. Revisit when it isn't.
- **Hashes: yes.** No cost at run time; supply-chain safety is part of the point of pinning.
- **uv is pinned** in CI (`astral-sh/setup-uv` with `version:`, the action itself pinned to a commit SHA) so `lock-check` doesn't churn. Dependabot's own uv version can still drift from ours; if `lock-check` starts failing on Dependabot PRs for that reason alone, drop `lock-check` rather than fight it.

### Q6: script shape (settled after review)

`run-tests.sh` and `lint.sh` use the venv without activation (activation differs between bash and Git Bash and is lost between an agent's Bash calls). Through `dev-env.sh`:

1. `.venv` current → use it.
2. `.venv` **stale or missing → fail** with `run-tests: .venv is missing or out of date with requirements-dev.txt: run bash scripts/dev-setup.sh`. A warning above hundreds of pytest lines goes unseen, by agents especially, and a stale venv gives "green locally, red in CI".
3. **One override** for offline work or a deliberate system pytest: `WIKI_TOOLS_DEV_VENV=off` skips the venv and uses today's probe and pytest from wherever, with a one-line note that the run is outside the lock. There is no silent fallback: two supported modes would otherwise live on indefinitely.

**Staleness stamp:** after a successful install, `dev-setup.sh` writes `.venv/wiki-tools-stamp`: a copy of `requirements-dev.txt` plus a last line with the venv Python's `major.minor`. Current means: `.venv/<bin>/python` runs, prints the same `major.minor`, and the rest matches `requirements-dev.txt` (`cmp` on the two, no hashing tool needed). The Python check catches a distro upgrade (3.12 → 3.13) that leaves `.venv/bin/python` running while its `lib/python3.12/site-packages` has become invisible.

`py-run.sh` and `py-launch.sh` are not touched: the plugin never sees this venv. A venv Python started with `-I -S` imports the standard library fine and keeps `sys.executable` as the venv path, which `_pr_ok` accepts (checked in review on 3.14 and 3.9, Linux).

**Windows cost to measure:** `tests/conftest.py` hands the plugin under test `sys.executable`. In a Windows venv that is `Scripts/python.exe`, a redirector that starts the base Python, so every launcher call in the e2e suite would pay one more process start, on the job the xdist work just sped up. Step 1 of the work measures it; if it shows, the fixture uses `sys._base_executable` (the plugin is stdlib only, so it needs nothing from the venv; pytest itself still runs in it).

Considered and not chosen: `nox`/`tox` (another tool with its own venvs), a `Makefile`/`justfile` (not in Git Bash by default), direnv (per-user shell setup, invisible to agents).

### `dev-setup.sh`

```
bash scripts/dev-setup.sh            # create .venv if missing, sync it to requirements-dev.txt
bash scripts/dev-setup.sh --clean    # delete and rebuild .venv
bash scripts/dev-setup.sh --pip      # use venv + pip even when uv is present (CI's Windows jobs)
```

- **Finding Python:** `$WIKI_TOOLS_DEV_PYTHON` if set (CI's 3.9 job), else the probe `python`, `python3`, `py -3` (≥ 3.9, not the Store alias). Not `py-run.sh`'s `_pr_find`: it reads the wiki plugin's interpreter cache first, so the dev venv's base would follow whatever the wiki plugin cached. No Python → stop with the install hint per platform. Never installs Python or uv.
- **Debian/Ubuntu without `python3-venv`** (no `ensurepip`): detect the failure of `python -m venv` and print the `apt install python3-venv` (or `python3.X-venv`) line.
- **Root:** a warning, not a refusal (container CI and cloud agent sandboxes run as root).
- **Never deletes what it didn't make:** refuses if `.venv` exists without `pyvenv.cfg`; `--clean` deletes only a `.venv` that has one.
- Prints what it does (`creating .venv with /usr/bin/python3.12 (uv)`, `installing 9 packages from requirements-dev.txt`). Network is needed only for installs.
- Calls native programs with ordinary Git Bash path conversion; it doesn't reuse `py-run.sh`'s `_pr_call` (its `MSYS2_ARG_CONV_EXCL` is for the plugin's scripts).

### CI (`.github/workflows/ci.yml`, owner review)

- Every job: `bash scripts/dev-setup.sh`, then `bash scripts/lint.sh` or `bash tests/run-tests.sh [--e2e]`.
- uv on the Linux jobs (`setup-uv`, version and SHA pinned), `--pip` on the Windows jobs, so both install paths run on every PR.
- New job `test (ubuntu-latest, 3.9, plain)`: `setup-python` 3.9, `WIKI_TOOLS_DEV_PYTHON=python3.9`. A required check. When `setup-python` drops 3.9 from ubuntu-latest, the floor moves: a decision, not a silent drop.
- `lock-check` in lint: recompile with the pinned uv into a temp file and `cmp` it with `requirements-dev.txt`, so a hand-edited lock fails. uv keeps existing pins when `-o` names the current file, so a new PyPI release doesn't fail it.
- Cache: uv's and pip's caches keyed on `requirements-dev.txt`.

### Docs

- `docs/development.md`: workflow step 0 gains `bash scripts/dev-setup.sh`; step 2 and the lint block use `run-tests.sh` and `lint.sh`; the `pip install --user` lines go. New subsection "Dev environment": the venv, the override, how to change `requirements-dev.in` (needs uv at the named version), what Dependabot does.
- `docs/setup.md`: the optional test line points to `dev-setup.sh`.
- `tests/run-tests.sh` header comment: the install advice changes.
- `AGENTS.md`: "Once per clone, and whenever a script says the venv is missing or out of date, run `bash scripts/dev-setup.sh`. Run tests and lint only through `tests/run-tests.sh` and `scripts/lint.sh`." The Python rules line names `requirements-dev.*` as the only third-party Python, dev only.
- `docs/layout.md`: the new files.
- When done: amend ADR 7 and the xdist decision (pinned, from the lock), and add a decision for the venv and the lock tool.

### Tests

New `tests/test_dev_env.py` (end to end through bash): staleness (current, stale lock, stale Python minor, missing, venv with a vanished base Python), the override, the venv path per platform, `dev-setup.sh` refusals (not a venv, no Python), the root warning, `--pip`. The package install itself isn't run in the suite (network); CI's own setup covers it. `shellcheck` on the new scripts.

## Order of work

1. `requirements-dev.in` + generated lock; check it installs on 3.9 and 3.13, Linux and Windows; measure the Windows e2e time with a venv Python (`sys.executable` vs `sys._base_executable`).
2. `dev-env.sh`, `dev-setup.sh`, `lint.sh`, `run-tests.sh` changes, tests.
3. CI and Dependabot (owner review).
4. Docs, AGENTS.md, ADRs.

## Housekeeping (separate, small)

`docs/adr.md` has two sections numbered 10 ("Two coding agents" and "Parallel tests"). Renumber the second to 11 in its own small PR before this work amends it.

## Review (2026-11-16, one round)

Changed after review: fail instead of warn on a stale or missing venv, with one override, and no silent fallback; Python minor version in the stamp; root a warning, not a refusal; Dependabot's `uv` ecosystem; uv pinned in CI; the lock forks by Python version; the real reason against `uv.lock`; `python3-venv` detection; no `_pr_find` for the dev venv; explicit `--python` and no `uv venv` over an existing `.venv`; the Windows redirector cost measured before choosing `sys._base_executable`; the duplicate ADR number. Kept: the three-script shape, both install paths in CI, `lock-check` (with a pinned uv), hashes. Owner's settled 3.9 floor: the review calls its cost small (pytest 8.4); a later `pytest<9 ; python_version < '3.10'` / `pytest>=9` split in the `.in` file would give 3.10+ the newer pytest without moving the floor.
