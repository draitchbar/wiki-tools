# Repository layout

What lives where in this repository. Everything the wikis need is under `plugins/wiki/`.

## Files

```
.claude-plugin/marketplace.json   marketplace "wiki-tools"
LICENSE, CONTRIBUTING.md          MIT; how collaborators work (by invitation)
AGENTS.md, CLAUDE.md              rules for coding agents; CLAUDE.md only imports AGENTS.md, which imports CONTRIBUTING.md
.claude/skills/new-source-type/   repo-local skill (Claude Code and Copilot CLI): add or promote a standard source type
.claude/skills/fix-issues-ai/     repo-local skill (both agents): triage issues, fix each in its own pull request, follow it until ready to merge
.claude/skills/implement-feature-ai/  repo-local skill (both agents): a goal or roadmap item, its open choices settled (the user asked only what is unsure and hard to revert), designed or planned, built by subagents in one pull request
plugins/wiki/
  schema/                         shared wiki schema, loaded at session start by schema.sh
  templates/project-settings.json core of a wiki's .claude/settings.json (source rules come from the types)
  templates/source-type/SOURCE.md the source contract template
  templates/pages/entity.md       shared page template for people and organisations
  skills/{init,add-source,bind-reader,ingest,clarify,research,sync-status,save,commit-themes,lint,audit}/SKILL.md
  agents/{source-researcher,critic}.md  subagents /wiki:research dispatches (read-only research; independent critic)
  cloud/SETUP.md                  guided setup for a wiki in a Claude Code cloud session (environment setup script, CLAUDE_CODE_PLUGIN_DIRS, the plugin's self-update); what was checked, what is untested
  skills/ingest/reading-files.md  core rules for reading fetched files (pdftotext, LibreOffice, OCR)
  hooks/hooks.json                PreToolUse guard + SessionStart cloud update (first, startup only), schema and status
  git-hooks-off/                  an empty hooks folder (a README only): save.sh runs git with core.hooksPath set to it
  sources/                        standard source types
    gmail/SOURCE.md               Gmail threads by label, sender and recipient through whatever Gmail reader the machine supplies (tool-neutral, read-only; seen working: the claude.ai connector)
    google-drive/SOURCE.md        Google Drive folders through whatever Drive reader the machine supplies (tool-neutral; seen working: the claude.ai connector)
    ms-teams/SOURCE.md            Teams channels, chats and SharePoint folders through whatever Microsoft 365 reader the machine supplies (tool-neutral; seen working: the claude.ai connector)
    jira/SOURCE.md                Jira issues selected by named scopes (team, component, epic/initiative, project, JQL) through whatever Jira reader the machine supplies (tool-neutral)
    connectors.md                 local and cloud names of the claude.ai connectors (read by sourcelib.py; not a type)
    proton-files/SOURCE.md            Proton Drive through a reader (the proton plugin, aitchbar-ai-tools)
    local-folder/{SOURCE.md,read.sh}  folders outside the wiki, read-only
    codebase/{SOURCE.md,git.sh,gh.sh}  a git clone researched on demand by subagents (research type, agent_only); PR/issue context via gh
  scripts/
    guard.py                      the PreToolUse hook: source/guard protection and no git push (every tool; unknown tools refused), rules from the contracts
    hookjson.py                   hook-input parsing and tool classification for guard.py (fails closed)
    contract.py                   parsing of source contracts and instances for guard.py (the Python side of lib-source.sh)
    py-launch.sh                  runs a Python hook: cached interpreter, probe, fails closed
    py_version.py                 prints the interpreter the launcher finds (wiki-check)
    lib-source.sh                 jq-free instance reading for the source wrappers and the wikis' local types; validation runs in sourcelib.py
    py-run.sh                     runs a Python script (not a hook) with its arguments and exit code; sourced, the bridge lib-source.sh calls
    sourcelib.py                  validation, needed rules and settings parsing for the scripts and lib-source.sh
    sources.sh                    read-only view of a wiki's sources (list, show, due, catalog, contract, settings, check-settings); a launcher for sources.py
    sources.py                    the work of sources.sh
    install-source-file.sh        the user (never Claude) checks and installs one file into .claude/sources/; keeps the terminal (paste, diff, prompt)
    install_source.py             its checks and the writing
    decode-download.sh            base64 download (e.g. Google Drive) into the source cache; checks and paths, decoding in decode_download.py
    decode_download.py            finds the base64 (plain, or a saved tool result's "content") and decodes it
    file-snapshot.sh              folder-walk snapshot for readers without modified times (any access: tools type); work in file_snapshot.py
    schema.sh                     prints one schema file (SessionStart, every start, resume, /clear, compaction)
    cloud-update.sh               SessionStart (startup): in a cloud session, updates the setup script's plugin copy from its clone when it follows a branch (cloud/SETUP.md, "Keeping the plugin current")
    sync-status.sh                staleness report from raw/sync-log.md, and the open questions' count; a launcher for sync_status.py
    sync_status.py                the work of sync-status.sh
    ocr.sh                        ocrmypdf wrapper (Linux)
    lint.sh                       deterministic wiki checks for /wiki:lint (read-only); a launcher for lint.py
    lint.py                       the work of lint.sh
    wiki-check.sh                 setup check for /wiki:init check mode (read-only); also lists Markdown outside the layout and checks the guard hook and the scripts find Python; a launcher for wiki_check.py
    wiki_check.py                 the work of wiki-check.sh, lint in-process
    save.sh                       saves a wiki's commits to its own remote, at the URL and branch pinned in its committed .claude/settings.wiki.json (/wiki:save; the only push); a launcher for save.py
    save.py                       the work of save.sh: the pin and URL checks, the merge, the path tiers, the host's protection (gh api on GitHub), the push or the holding branch
scripts/pii-check.sh, pii_check.py  repo tooling, not the plugin: the personal-data check (docs/development.md, "Personal data")
scripts/dev-env.sh                repo tooling: finds uv and .venv, stops when .venv is out of date with uv.lock (sourced by run-tests.sh and dev-lint.sh)
scripts/dev-lint.sh               repo tooling: the lint CI runs (ruff, mypy, shellcheck, LF line endings), from .venv
pyproject.toml, uv.lock           the dev tools (the dev group) and their lock, installed into .venv by `uv sync --locked` (docs/development.md, "Dev environment"); never the plugin's
.githooks/pre-push                runs the personal-data check on every push (switched on per clone)
.github/workflows/                ci.yml (lint, tests), pii.yml (personal-data check), claude-review.yml
tests/                            run-tests.sh (runs pytest from .venv), conftest.py and test_*.py, codebase_story.py (the codebase modules' shared setup), fixtures and fixture wikis, fakes
docs/                             these pages, the ADR, the roadmap, a security review; agent-pr-flow.md, what /fix-issues-ai and /implement-feature-ai share
docs/plans/                       one file per detailed plan, indexed in the roadmap
```
