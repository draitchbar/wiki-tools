# wiki-tools

Shared tooling for the LLM wikis: a local-directory plugin marketplace with one plugin, `wiki`, which also carries the shared schema it loads into every wiki session.

This repo is maintained in a Claude session opened here, where the `wiki` plugin is **not** enabled. The guard hooks are active only inside the wikis. See README.md for the full design.

## Rules for editing this repo
- Scripts are POSIX bash that must run under Linux bash and Git Bash on Windows. No `jq`, no Python, no GNU-only flags beyond what Git Bash ships (`sed`, `grep -E`, `date -d` are fine).
- Keep LF line endings (`.gitattributes` enforces this). Never introduce CRLF.
- Any change to `plugins/wiki/scripts/`, `plugins/wiki/hooks/` or a wrapper in `plugins/wiki/sources/` needs a matching fixture or test (`tests/fixtures/`, `tests/run-tests.sh`) and a green `bash tests/run-tests.sh` before committing. Tests never call a real source CLI or account; they use fakes (`tests/sources/<type>/`).
- The guards are a guardrail, not a security boundary. Don't weaken one without saying so in the commit message.
- No fixed clone path. Skills, the schema and contract bodies name plugin files as `${CLAUDE_PLUGIN_ROOT}/...` (filled in by Claude Code for skills, by `schema.sh` and `sources.sh` for the rest); scripts find their own folder; contract `read_tools` use `Bash(bash */sources/<type>/<script>.sh *)`. Everything the wikis need lives under `plugins/wiki/`, since Claude Code may run an installed copy of only that folder.
- Sources: the wiki skills are source-neutral. Anything specific to one source belongs in its type's `plugins/wiki/sources/<type>/SOURCE.md`, never in a skill. New standard types: `/new-source-type`.
- Remote is the private GitHub repo `draitchbar/wiki-tools`.

## Open plans
- `docs/sources-design.md`: source redesign, on main. Both wikis migrated 2026-10-25, transition code removed 2026-10-31; remaining: a bookmarks local type in one wiki.
- `docs/codebase-design.md`: `codebase` research type, `/wiki:research`, plugin agents, agent_only guard. Built 2026-10-31, tested in ai-wiki on Windows 2026-11-01 (agent_id split confirmed); remaining: the graphify/SCIP decision after ~10 real runs.
- `docs/tier2-plan.md`: Tier 2 (pruned, Tier 3 folded in). Not started.
- `docs/proton-drive-plan.md`: decided 2026-11-01 to keep the `proton-drive` CLI behind `read.sh` (no `access: tools`, no MCP server; research record inside). Remaining: harden `read.sh` (exit code 0 on failed items, `database is locked` retries, list order); a faster `new` decided with the Python port. Not started.
- Speed and Python (decided 2026-11-01: a Python requirement is acceptable; the "no Python" rule above stands until the port starts). The test suite takes over 10 minutes on Windows, mostly in process starts under Git Bash. Step 1: time one guard call, one `sources.sh show` and each `run-tests.sh` section. Step 2, if the guard and contract parsing dominate as expected: port `guard.sh` and `lib-source.sh`'s parsing to Python, with every guard fixture run against both versions until they agree, a robust launcher on Windows (`python`/`python3`/`py`, not the Store alias) and a check in `/wiki:init`. Wrappers that mostly wait on `git`/`gh` stay bash. Not started.
- Clone-anywhere layout (plugin-loaded schema, path-free rules): both wikis switched and checked on Linux 2026-10-31 (README, Open checks). Still to check: Windows (Git Bash), and plugin loading in a fresh clone of a wiki without a project-scope install.
