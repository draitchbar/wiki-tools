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
- `docs/sources-design.md`: source redesign, on main. Both wikis migrated 2026-10-25; remaining: a bookmarks local type in one wiki, then removing the transition code.
- `docs/tier2-plan.md`: Tier 2 (pruned, Tier 3 folded in). Not started.
