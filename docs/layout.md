# Repository layout

What lives where in this repository. Everything the wikis need is under `plugins/wiki/`.

## Files

```
.claude-plugin/marketplace.json   marketplace "wiki-tools"
LICENSE, CONTRIBUTING.md          MIT; how collaborators work (by invitation)
AGENTS.md, CLAUDE.md              rules for coding agents; CLAUDE.md only imports AGENTS.md, which imports CONTRIBUTING.md
.claude/skills/new-source-type/   repo-local skill (Claude Code and Copilot CLI): add or promote a standard source type
.claude/skills/fix-issues-ai/     repo-local skill (both agents): triage issues, fix each in its own pull request, follow it until ready to merge
plugins/wiki/
  schema/                         shared wiki schema, loaded at session start by schema.sh
  templates/project-settings.json core of a wiki's .claude/settings.json (source rules come from the types)
  templates/source-type/SOURCE.md the source contract template
  templates/pages/entity.md       shared page template for people and organisations
  skills/{init,add-source,bind-reader,ingest,clarify,research,sync-status,commit-themes,lint,audit}/SKILL.md
  agents/{source-researcher,critic}.md  subagents /wiki:research dispatches (read-only research; independent critic)
  skills/ingest/reading-files.md  core rules for reading fetched files (pdftotext, LibreOffice, OCR)
  hooks/hooks.json                PreToolUse guard + SessionStart schema and status
  sources/                        standard source types
    gmail/SOURCE.md               Gmail via the claude.ai connector (MCP)
    google-drive/SOURCE.md        Google Drive folders via the claude.ai connector (MCP)
    ms-teams/{SOURCE.md,snapshot.sh,snapshot.py}  Teams channels, chats and SharePoint folders via the claude.ai Microsoft 365 connector (MCP)
    jira/SOURCE.md                Jira issues selected by named scopes (team, component, epic/initiative, project, JQL) through whatever Jira reader the machine supplies (tool-neutral)
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
    schema.sh                     prints one schema file (SessionStart, every start, resume, /clear, compaction)
    sync-status.sh                staleness report from raw/sync-log.md, and the open questions' count; a launcher for sync_status.py
    sync_status.py                the work of sync-status.sh
    ocr.sh                        ocrmypdf wrapper (Linux)
    lint.sh                       deterministic wiki checks for /wiki:lint (read-only); a launcher for lint.py
    lint.py                       the work of lint.sh
    wiki-check.sh                 setup check for /wiki:init check mode (read-only); also lists Markdown outside the layout and checks the guard hook and the scripts find Python; a launcher for wiki_check.py
    wiki_check.py                 the work of wiki-check.sh, lint in-process
scripts/pii-check.sh, pii_check.py  repo tooling, not the plugin: the personal-data check (docs/development.md, "Personal data")
.githooks/pre-push                runs the personal-data check on every push (switched on per clone)
.github/workflows/                ci.yml (lint, tests), pii.yml (personal-data check), claude-review.yml
tests/                            run-tests.sh (runs pytest), conftest.py and test_*.py, codebase_story.py (the codebase modules' shared setup), fixtures and fixture wikis, fakes
docs/                             these pages, the ADR, the roadmap, a security review
docs/plans/                       one file per detailed plan, indexed in the roadmap
```
