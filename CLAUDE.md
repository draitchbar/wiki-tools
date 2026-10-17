# wiki-tools

Shared tooling for the LLM wikis (udbygning, carleasing): a local-directory plugin marketplace with one plugin, `wiki`, plus the shared schema that each wiki's CLAUDE.md imports.

This repo is maintained in a Claude session opened here, where the `wiki` plugin is **not** enabled. The guard hooks are active only inside the wikis. See README.md for the full design.

## Rules for editing this repo
- Scripts are POSIX bash that must run under Linux bash and Git Bash on Windows. No `jq`, no Python, no GNU-only flags beyond what Git Bash ships (`sed`, `grep -E`, `date -d` are fine).
- Keep LF line endings (`.gitattributes` enforces this). Never introduce CRLF.
- Any change to `plugins/wiki/scripts/` or `plugins/wiki/hooks/` needs a matching fixture in `tests/fixtures/` and a green `bash tests/run-tests.sh` before committing.
- The guards are a guardrail, not a security boundary. Don't weaken one without saying so in the commit message.
- The script paths `~/src/wiki-tools/plugins/wiki/scripts/*.sh` are literal in the skills, the guard exception and the wikis' `allowed-tools`. If the clone path ever changes, update all three.
- Remote is the private GitHub repo `draitchbar/wiki-tools`.

## Open plans
- `docs/tier2-plan.md`: Tier 2 (pruned, Tier 3 folded in). Not started.
