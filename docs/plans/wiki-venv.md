# Proposal: third-party Python for the wikis, and a plugin-managed venv

Status: proposal, 2026-11-16, reviewed the same day (one round, folded in). Parked: not for building until its trigger. Companion to `docs/plans/dev-venv.md`, which is planned.

## What a wiki needs today

Nothing from PyPI. The guard and every script are Python 3.9+ standard library (`docs/adr.md`, 4). The optional tools a wiki can use are:

| Tool | Used by | Today |
|---|---|---|
| `ocrmypdf` + Tesseract languages + Ghostscript | `ocr.sh` (scanned PDFs) | Linux: `apt`. Windows: none; pages read as images (`docs/setup.md`, "Known issues"). |
| `proton-drive` CLI | `proton-files` | Installed by the user. |
| `drawio` | `.drawio` rendering | A snap. |
| Gmail, Drive, Jira, Teams, OneNote | their source types | MCP connectors; nothing local. |

A venv would solve nothing today. Even Windows OCR, the nearest case, still needs native Tesseract and Ghostscript installers beside a pip-installed `ocrmypdf`.

**Trigger:** the first source type or skill whose need the standard library can't meet. Then walk the ladder below with that package named.

## The ladder: how a future need is met, cheapest first

1. **Standard library.** Many apparent needs aren't: `.docx`/`.xlsx`/`.pptx` text is `zipfile` + `xml.etree`; HTML to text is `html.parser`. Default answer.
2. **Vendored pure-Python package** in `plugins/wiki/vendor/<pkg>/`. Works under `py-launch.sh`'s and `py-run.sh`'s `-I -S` with the `sys.path` insert scripts already use for siblings; versioned and shipped with the plugin (also in a copy installed from GitHub); guard-protected like the rest of the plugin; no install step for the user. Costs: licence review (MIT-compatible, licence file kept), updates by hand, pure Python only, and an ADR 4 amendment ("standard library, plus vendored pure-Python packages listed in `vendor/README.md`").
3. **A CLI the user installs** (apt, pipx, `uv tool`), reported by `wiki-check.sh` with the install line, and the script falls back without it. This is how `ocrmypdf`, `proton-drive` and `drawio` already work. No venv of ours.
4. **V0: a plugin-managed venv for CLI tools.** As 3, but `setup-venv.sh` installs the tool from a hashed lock into a venv in the plugin's data folder, and scripts call it by absolute path. Worth it only when 3 is painful on some platform.
5. **V1: per-script opt-in to the venv's interpreter**, for a *compiled* package a script must import (not possible with 2). See below.
6. **V2: the venv as the plugin's interpreter, guard included. Rejected.**

## The owner's idea: the venv as the plugin's interpreter

The owner asked for this to be weighed seriously. The review's findings:

- **V2 is rejected.** The guard fails closed, so a half-built venv, or one whose base Python was upgraded or removed, would refuse every Bash, Write and Edit call until fixed outside Claude. On Windows a venv's `python.exe` is a redirector that starts the base Python, so every hook would pay a second process start: the cost ADR 4 exists to avoid.
- **V1 can't be "`py-run.sh` prefers the venv".** The launchers run Python with `-I -S`, and `-S` skips `site`, so nothing in the venv's site-packages is importable. Dropping `-S` for every script would run every installed `.pth` file on every call.
- **If V1 is built, it is per script.** A script that needs a package declares it (a list in `py-run.sh`, or a marker its launcher passes). That one script runs on the venv interpreter without `-S`. Everything else, and every hook, stays on the system Python with `-I -S`. Each such script must still fail cleanly without the venv, because the venv is optional per machine. The cost is two code paths to test on two platforms, and a decision recorded in ADR 4.
- **On balance:** the interpreter idea is sound only in V1's per-script form, and only once rungs 1–4 fail for a named need. Vendoring (2) delivers most of what the idea promises (third-party code in plugin scripts) without a venv, an install step or a second interpreter.

## If a venv is built (V0, or V1's)

These choices were settled with the owner, and the review confirms them:

- **Location:** one per machine, in the plugin's data folder (`${CLAUDE_CONFIG_DIR:-~/.claude}/plugins/data/wiki-wiki-tools/`). The folder survives plugin updates and is deleted on uninstall.
- **Hand-over at init:**
  - `wiki-check.sh`, and so `/wiki:init`'s check mode, reports whether the venv is absent, current, stale or broken.
  - When a wiki uses a tool that needs the venv, `/wiki:init` gives the user `bash <plugin>/scripts/setup-venv.sh` to run in a separate terminal.
  - `setup-venv.sh` behaves like `install-source-file.sh`: it refuses to run under Claude, lists the packages and versions, and asks y/n.
  - The session never runs a package manager, and nothing is installed silently.

The review added these:

- **Version skew.** After a plugin update, the old version's folder stays for 14 days, and running sessions keep the old plugin root. So two plugin versions with different locks can share one data folder. The fix is to name the venv after its lock, `venv-<first 12 hex of the lock's hash>/`. Each plugin version then finds its own venv, and `setup-venv.sh --prune` deletes the ones no installed version names. The venv is never invalidated automatically.
- **The guard is weaker than the first draft claimed:**
  - `guard.py` protects `.claude/plugins` as a path segment of the command or path. A `cd ~/.claude && …` followed by relative paths (`plugins/data/…`) doesn't contain it.
  - A data folder moved by `CLAUDE_CONFIG_DIR` or `CLAUDE_CODE_PLUGIN_CACHE_DIR` isn't covered either.
  - Today one cached path sits behind that match. A venv would put a tree of executable code there.
  - Before any venv ships, the guard needs to protect the resolved data folder (`$CLAUDE_PLUGIN_DATA`, as the hook sees it), with fixtures for the `cd` form and a relocated config directory. That gap exists today for the interpreter cache too, so it is worth a GitHub issue on its own.
- **Trust:** a hash-pinned lock means that what runs is what the plugin release named. The exposure is the same as any CLI the user installs, and smaller than an MCP server's.
- **Windows:** tools are called as `Scripts/<tool>.exe`, and a V1 interpreter as `Scripts/python.exe`. The redirector cost applies to each V1 script call.

## Open, for when the trigger fires

- Which rung the named need lands on. Make that decision then, not now.
- For vendoring: the update process (a script that copies a pinned wheel's sources and checks the licence?) and how `ruff` excludes `vendor/`.
- For V1: how a script declares that it needs the venv, and what its fallback looks like without one.
