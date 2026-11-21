# wiki-tools

Shared tooling for the LLM wikis: a local-directory plugin marketplace with one plugin, `wiki`, which also carries the shared schema it loads into every wiki session.

This repo is developed in an agent session opened here, Claude Code or GitHub Copilot CLI (`docs/development.md`, "Agents"). The wikis themselves run only in Claude Code, with the `wiki` plugin; it is **not** enabled here, and its guard hooks are active only inside the wikis. README.md is the quick start; the details are in `docs/` (setup, skills, sources, guard, development, layout) and the decisions in `docs/adr.md`.

The contribution rules, for people and agents alike:

@CONTRIBUTING.md

## Rules for editing this repo
- Scripts are POSIX bash that must run under Linux bash and Git Bash on Windows. No `jq`, no GNU-only flags beyond what Git Bash ships (`sed`, `grep -E`, `date -d` are fine). Python (`docs/adr.md`, 4): the guard (`guard.py`, `hookjson.py`, `contract.py`, `py_version.py`), run only through `py-launch.sh`, which fails closed; and the scripts' work behind their `.sh` launchers (`sourcelib.py`, `sources.py`, `lint.py`, `wiki_check.py`, `sync_status.py`, `install_source.py`, `decode_download.py`, `sources/ms-teams/snapshot.py`), run only through `py-run.sh`; and the repo's own `scripts/pii_check.py` behind `scripts/pii-check.sh`. Standard library only, Python 3.11 or later. No other Python without a decision recorded in `docs/adr.md`.
- Keep LF line endings (`.gitattributes` enforces this). Never introduce CRLF.
- Any change to `plugins/wiki/scripts/`, `plugins/wiki/hooks/` or a wrapper in `plugins/wiki/sources/` needs a matching fixture or test (`tests/fixtures/`, `tests/test_*.py`) and a green `bash tests/run-tests.sh` before committing; a change to a launcher or another `.sh` file also a green `bash tests/run-tests.sh --e2e`. The tests are pytest (unpinned, the test runner's only dependency, never the plugin's; pytest-xdist optional, for parallel runs, `docs/adr.md`, 15). Tests never call a real source CLI or account; they use fakes (`tests/sources/<type>/`).
- The guards are a guardrail, not a security boundary. Don't weaken one without saying so in the commit message.
- No fixed clone path. Skills, the schema and contract bodies name plugin files as `${CLAUDE_PLUGIN_ROOT}/...` (filled in by Claude Code for skills, by `schema.sh` and `sources.sh` for the rest); scripts find their own folder; contract `read_tools` use `Bash(bash */sources/<type>/<script>.sh *)`. Everything the wikis need lives under `plugins/wiki/`, since Claude Code may run an installed copy of only that folder.
- Sources: the wiki skills are source-neutral. Anything specific to one source belongs in its type's `plugins/wiki/sources/<type>/SOURCE.md`, never in a skill. New standard types: `/new-source-type`.
- Test plans sent to a wiki session: Claude can't start a skill with `disable-model-invocation` (`init`, `add-source`, `ingest`, `clarify`, `lint`, `audit`, `commit-themes`): mark such a step as the user's; for `/wiki:init`'s check mode, Claude can run `wiki-check.sh` (`docs/skills.md`, `/wiki:init`).
- Lint must be clean before committing: `ruff check .` (`ruff.toml`) and `shellcheck -S warning` on every `*.sh` (`.shellcheckrc`).

## Agents
- If the push hook, a guard or the push itself is blocked or fails, stop and report it; never get around it (another remote URL, `git -c`, the GitHub API or web UI). The hook must be switched on in every clone before its first push, cloud sessions included.
- Change GitHub only through `git push` and `gh` (PRs, issues, comments). Never Copilot's `/delegate` or a GitHub MCP tool that writes files, commits or branches, or merges: they change the repo on GitHub, past the push hook. Without `gh` (a Claude Code cloud session), MCP tools may open PRs, comment and close issues, nothing more (`docs/adr.md`, 16).
- Issues to pull requests: `/fix-issues-ai <numbers or titles>`.
- Files for agents (this file, `CLAUDE.md`, skills in `.claude/skills/`) use only what both Claude Code and Copilot CLI support (`docs/development.md`, "Agents"); a step only one agent can do says so and gives the other's way. No instruction, skill or config files that only one agent reads (`.github/copilot-instructions.md`, `.github/instructions/`, `.github/skills/`, `.github/agents/`, `.github/mcp.json`, `.github/copilot/settings.json`, `.agents/`, `GEMINI.md`, `.claude/CLAUDE.md`) and no symlinks. `tests/test_agent_files.py` checks this.
- Copilot CLI refuses a manual-only skill (`disable-model-invocation`) at its `skill` tool, but a model can still read the skill file and follow it by hand, so a manual-only skill starts its body with: Run only when the user typed `/<name>`; if you loaded this skill yourself, stop and ask whether to start it.

## Plans
`docs/roadmap.md` lists every plan: what is in progress, planned and parked (with triggers); an item may be one line. A plan worked out in detail gets its own file, `docs/plans/<slug>.md`, linked from its roadmap item, and is deleted when the work is done. `docs/adr.md` records the decisions behind what is built; a new decision goes there when its work is done. Small fixes go to GitHub issues; an issue that needs a plan stays open and gets a roadmap item that refers to it.
