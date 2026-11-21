# Setup

Installing wiki-tools on a machine, setting up a wiki, and the known limits.

## Per machine

Two ways to install. **From GitHub** (`claude plugin marketplace add draitchbar/wiki-tools`): Claude Code keeps its own copy of the plugin. To update it, run `claude plugin marketplace update wiki-tools` (refreshes the marketplace's listing), then `claude plugin update wiki@wiki-tools --scope project` in each wiki, and restart `claude` there; `git pull` doesn't apply. Automatic updates are off by default for a marketplace like this one; `/plugin`, tab Marketplaces, turns them on. **From a clone**, for changing the plugin: the rest of this section. Clone wherever you like; nothing depends on the path, and no environment variable is needed. The examples use `~/src/wiki-tools`.

| | Linux | Windows |
|---|---|---|
| Prerequisites | git, bash, Python 3.9 or later (`python3`; standard library only) | Git for Windows (Git Bash), Claude Code runs hooks in Git Bash; Python 3.9 or later from python.org, with the `python3` App execution alias turned off in Settings |
| OCR | `sudo apt install ocrmypdf` plus the Tesseract language packs your documents need (e.g. `tesseract-ocr-dan`); `/wiki:ingest` passes the languages from the wiki's CLAUDE.md | none; scans are read as page images |
| Sources | whatever the wikis' source types need, listed in each type's Caveats; e.g. codebase: a git clone of the repository, and `gh auth login` for the account in `gh_user`; Proton Drive: a Proton Drive reader, e.g. the `proton` plugin from `aitchbar-ai-tools` loaded from a local clone, with the CLI and its sign-in as its README says, and its rule in your user settings; Jira: a Jira reader, e.g. the claude.ai "Atlassian MCP" connector connected, its read tools allowed and its write tools denied in your settings; OneNote: a OneNote reader (CLI, skill or MCP server) signed in with Graph `Notes.Read` or `Notes.Read.All`, its read operations allowed in your settings | the same |

```bash
git clone https://github.com/draitchbar/wiki-tools.git ~/src/wiki-tools
bash ~/src/wiki-tools/tests/run-tests.sh          # optional: needs pytest (docs/development.md)
claude plugin marketplace add ~/src/wiki-tools     # registers the marketplace only
```

Don't install or enable the plugin at user scope. Each wiki enables it in its own committed `.claude/settings.json` (see `plugins/wiki/templates/project-settings.json`).

The marketplace is this local folder, so Claude Code runs the plugin straight from this working tree, as long as the wiki only enables it and doesn't install it (Setting up a wiki, step 2). `claude plugin install` (and `plugin update`) also writes a copy to `~/.claude/plugins/cache/`, and a session can start from that stale copy: seen 2026-11-20 on Windows in a wiki with a project-scope install, until `/reload-plugins` switched it to the folder. On 2026-11-03 (Linux, Claude Code 2.1.317), the copy was not used. Without an install, the plugin loads from `plugins/wiki/` (Open checks). So **uncommitted edits here are live in every wiki at once**, guard included, and a running wiki session mixes skills read at its start with scripts read at each call. The session-start status in a wiki says so when `plugins/wiki/` has uncommitted changes. After changing or pulling the plugin, restart `claude` in each wiki (or run `/reload-plugins` there); `claude plugin update` isn't needed.

**Wikis set up from a clone with `claude plugin install`** (the earlier step 2) need no change in the wiki itself: its `.claude/settings.json` already enables the plugin. The install lives on each machine. Either keep it and run `/reload-plugins` (or restart `claude`) in each wiki after every pull, or remove it, on each machine, in each wiki:

1. Check `~/.claude/plugins/installed_plugins.json` for a `wiki@wiki-tools` entry for this wiki's folder, with an `installPath` under `plugins/cache/`. If there is none, you're done.
2. In the wiki folder, in a terminal: `claude plugin uninstall wiki@wiki-tools --scope project`.
3. `git diff .claude/settings.json`. If the uninstall removed `"wiki@wiki-tools": true` from `enabledPlugins`, restore it: `git checkout -- .claude/settings.json`.
4. Start `claude` and check that the plugin root in the session-start schema text is your clone (`…/plugins/wiki`), not a path under `.claude/plugins/cache/`.
5. Once every wiki on the machine is done, you may delete `~/.claude/plugins/cache/wiki-tools/`.

Steps 2 and 3 are untested; try them on one wiki first.

## Setting up a wiki

1. Create the folder (e.g. `mkdir ~/wikis/<name>`) and `cd` into it.
2. Enable the plugin for this folder only, in `.claude/settings.json`:
   - **Installed from GitHub:** `claude plugin install wiki@wiki-tools --scope project`.
   - **From a clone:** don't install it, since that also writes a copy to the cache that a session may run instead of your clone (Per machine). Enable it instead:
     ```bash
     mkdir -p .claude && printf '{\n  "enabledPlugins": {\n    "wiki@wiki-tools": true\n  }\n}\n' > .claude/settings.json
     ```
     `/wiki:init` later replaces this file with the full settings, which enable the plugin too.
3. Start `claude` and run `/wiki:init <what the wiki is for>`.

`/wiki:init` works in three modes:
- **New** (empty folder): grills you on scope, researches the domain, shows the full plan (CLAUDE.md, page types and templates, sources) and creates the raw/wiki layout after your go.
- **Adopt** (folder with content): the same, plus a move table that brings existing notes into `wiki/` (with `git mv` and frontmatter) and source files into `raw/`.
- **Check** (already set up): runs `scripts/wiki-check.sh` and reports what's missing; it also lists Markdown files outside the layout (INFO, not a failure). Run outside a git repo in a folder whose settings enable the plugin, it says the wiki isn't initialised yet and points to `/wiki:init`.

In new and adopt mode, before asking or writing anything, `/wiki:init` checks that git has a commit identity (`git config user.name`, `user.email`) and stops with the fix if not, since setup ends with a commit. Check mode skips this.

Only you can start `/wiki:init` (`disable-model-invocation`). Claude can run its check itself: `bash ${CLAUDE_PLUGIN_ROOT}/scripts/wiki-check.sh` (read-only; the guard allows it). A test plan sent to a wiki session therefore uses `wiki-check.sh`, or marks `/wiki:init` as a step the user runs.

`raw/` is the only built-in source. Every other source is chosen during init with the same flow as `/wiki:add-source`.

It ends with a guide for the steps only you can do, because the guard blocks Claude from them: pasting `.claude/settings.json` (from `plugins/wiki/templates/project-settings.json` plus the sources' rules) and the files under `.claude/sources/`, committing them and restarting `claude`. Setting up the git remote and pushing is also yours.

Sources start at `last_checked_<key>: never`. The first `/wiki:ingest <key>` of each source checks it, asks for a starting point and reviews the data model (folders, page types, templates) against the wiki's purpose.

The shared starting template for people and organisations is `plugins/wiki/templates/pages/entity.md`; every other page type is designed per wiki by `/wiki:init`.

## Known issues

- **No OCR on Windows (deliberately out of scope for now).** `ocr.sh` needs `ocrmypdf` and Tesseract's language data, which are installed on Linux only.
  - **Normal case:** OCR scanned PDFs on Linux. The text is committed as `raw/ocr/<file>.txt`, so Windows reads it after `git pull`.
  - **A new scan ingested first on Windows:** `ocr.sh` exits with "ocrmypdf not installed", and `/wiki:ingest` falls back to Claude reading the PDF pages as images. That uses more tokens and leaves no `raw/ocr/` text. Re-run the ingest of that file on Linux to produce it.
  - **If Windows OCR is needed later:**
    - *Native:* Tesseract (UB Mannheim installer, with the language data your documents need), Ghostscript and `pip install ocrmypdf`, all on PATH. `ocr.sh` should then work unchanged from Git Bash. Untested.
    - *WSL:* `apt install ocrmypdf` and the language packs inside WSL, but `ocr.sh` would need to call `wsl ocrmypdf …`.

## Open checks

- **Plugin loading (checked 31.10.2026 on Linux, both wikis):** with the marketplace registered at user scope and a project-scope install in the wiki (`claude plugin install … --scope project`), `enabledPlugins` in the wiki's settings loads the plugin, its skills and its hooks. **Without that install (checked 20.11.2026 on Windows, a fresh clone of a wiki at a new path, headless session):** `enabledPlugins` alone loads it, from `plugins/wiki/` of the marketplace folder: the model-invocable `wiki:` skills, both schema files and the sync status. The clone's `permissions.allow` rules are ignored until the folder is trusted (start `claude` there once and accept the trust dialog). The guard was not exercised in that run.
- **Skill injections (checked 31.10.2026 on Linux, both wikis):** `${CLAUDE_PLUGIN_ROOT}` is filled in inside `` !`…` `` injections, and they pass the guard without a permission prompt (`/wiki:sync-status`).
- **Schema hook and wrapper rules (checked 31.10.2026 on Linux, both wikis):** the SessionStart hooks load both schema files on start and resume, with `${CLAUDE_PLUGIN_ROOT}` filled in. A wiki's settings rule `Bash(bash */sources/<type>/<script>.sh *)` matched the wrapper's absolute path without a prompt. **Windows (Git Bash), 20.11.2026:** the schema hooks load both files with the plugin root filled in (as `/c/...` in the schema text, `C:/...` in skill bodies); the wrapper rule is unchecked, since it needs an interactive session outside auto mode that runs a wrapper the wiki's settings allow by such a rule.
- **Plugin variables (checked 27.10.2026 in the skills, hooks and plugins-reference docs):** `${CLAUDE_PLUGIN_ROOT}` is substituted in a plugin skill's body and in Bash rules in its `allowed-tools`, and set for hooks. It is not available to commands Claude runs through the Bash tool, so scripts find their own folder. Project settings and CLAUDE.md imports expand no variables.
- **Bash rule wildcards (checked 24.10.2026 in the permissions docs):** a `*` may stand anywhere in a Bash rule and matches any text, slashes and spaces included, so `Bash(bash ${CLAUDE_PLUGIN_ROOT}/sources/*/*.sh *)` in the skills' `allowed-tools` and `Bash(bash */sources/<type>/read.sh *)` in a wiki's settings work; the guard rejects `..` and lookalikes.
- **Hook environment (checked 24.10.2026 in the hooks docs):** hooks get `CLAUDE_PROJECT_DIR` (where the session started) and the input JSON has `cwd`; the guard uses the former and falls back to the git root of the latter.
