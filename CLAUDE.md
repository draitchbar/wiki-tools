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
- `docs/proton-drive-plan.md`: decided 2026-11-01 to keep the `proton-drive` CLI behind `read.sh` (no `access: tools`, no MCP server; research record inside). Remaining: harden `read.sh` (reproduce first; exit code 0 on failed downloads, `database is locked` retries, `list` as sorted lines instead of JSON); a faster `new` decided with the Python port. Not started.
- `docs/speed-plan.md`: faster guard and test suite (40 minutes on Windows, 112 s on Linux). Step 1 done: guard ~320 ms per call on Linux, ~7.8 s on Windows (every section ~21× Linux: process starts); 40% of the suite either way. Decided 2026-11-05: the guard and contract parsing go to Python (step 2b; the "no Python" rule above stands until it starts), bash work only in the test runner (step 2a). Not started.
- Clone-anywhere layout (plugin-loaded schema, path-free rules): both wikis switched and checked on Linux 2026-10-31 (README, Open checks). Still to check: Windows (Git Bash), and plugin loading in a fresh clone of a wiki without a project-scope install.
