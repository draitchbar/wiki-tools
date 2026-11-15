# Plan: Copilot CLI as a second development agent

Roadmap item in `docs/roadmap.md` ("Planned, not started"). Intent settled with the owner and plan reviewed 2026-11-15.

Goal: wiki-tools can be developed with GitHub Copilot CLI as well as Claude Code, under the same rules and restrictions, with every rule and skill defined once (DRY). Main audience: invited collaborators who use Copilot (the repo goes public, `docs/roadmap.md`); also the owner.

Scope: development of this repo only. The `wiki` plugin (guard, `${CLAUDE_PLUGIN_ROOT}`, contracts with Claude Code permission rules, and a wiki's own `CLAUDE.md`) keeps running under Claude Code only. Copilot surfaces other than the CLI are parked.

## Research (2026-11-15; Claude Code docs, Copilot CLI 1.0.112 docs and changelog)

| | Claude Code | Copilot CLI |
|---|---|---|
| Reads `AGENTS.md` | only if no `CLAUDE.md` (2.1.277+); docs recommend `@AGENTS.md` in `CLAUDE.md`, and no symlink on Windows | yes, and also `CLAUDE.md`; concatenates; dedupes only identical files |
| `@path` imports | yes | yes, in `AGENTS.md`/`CLAUDE.md`, inside the repo only |
| Skill locations | `.claude/skills/` only | `.github/skills`, `.claude/skills`, `.agents/skills` |
| `disable-model-invocation`, `argument-hint` | yes | per the changelog; not on the skills docs page (verify, step 0) |
| `$ARGUMENTS` | yes | undocumented (verify, step 0) |
| Repo hooks | `.claude/settings.json` | own files, and also reads `.claude/settings.json` (Claude-format input; output format undocumented) |
| Repo-committed tool permissions | yes | not in the user-overridable keys; `.github/copilot/settings.json` exists (contents to verify) |
| Co-author trailer | yes | yes (`includeCoAuthoredBy`); email undocumented |

Prior art: symlinks (apache/airflow, vercel/next.js), AGENTS.md only (home-assistant/core), pointer files (microsoft/vscode, pydantic/pydantic). Symlinks break on Windows with `core.symlinks=false`.

## Design

0. Done 2026-11-15, Copilot CLI 1.0.112: the trailer is `Co-authored-by: Copilot` with a GitHub noreply address and passes the check, so `pii_check.py` is unchanged; `$ARGUMENTS` is substituted; `argument-hint` isn't shown; `disable-model-invocation` is ignored, even for a prompt that doesn't name the skill (hence the guard line, step 3); the built-in GitHub MCP server is read-only by default (`/delegate` and write tools not tested, since a test would push; forbidden instead). Was: before PR 2 (owner, in Copilot CLI, a throwaway branch never pushed): one commit by Copilot; run `scripts/pii-check.sh` on it to see whether its trailer email passes (a GitHub noreply address for the Copilot bot passes; a plain `github.com` address fails). Also check `$ARGUMENTS`, `disable-model-invocation`, and whether `/delegate` or GitHub MCP write tools push without the local hook. Outcome decides: allow the address in `scripts/pii_check.py` (with a test, `docs/development.md` "Personal data"), or require `includeCoAuthoredBy: false`.
1. Each rule lives once, in the file of its primary audience; humans reach the other file by link, agents by `@` import. Chain: `CLAUDE.md` → `@AGENTS.md` → `@CONTRIBUTING.md`.
   - `CONTRIBUTING.md` (humans; the full description): who may contribute; branch, PR, squash; CI and review; personal data; `core.hooksPath`; never `--no-verify`; noreply identity; trust in workflows; every change must work in Claude Code and Copilot CLI. Links to `AGENTS.md` for how to change the code and to `docs/` for detail.
   - `AGENTS.md` (agents): starts with `@CONTRIBUTING.md`; then the code rules from today's `CLAUDE.md` (POSIX bash, Python allow-list, tests, lint, LF, no fixed clone path, sources, test plans for wiki sessions, plans), made agent-neutral ("an agent session (Claude Code or Copilot CLI)"); then agent-only behaviour: stop and report when a hook, guard or push is blocked and never get around it; run the `core.hooksPath` line in cloud sessions too; no `/delegate` or GitHub MCP write tools to push or open PRs; `Co-Authored-By` trailers only with addresses the PII check allows, no session-link trailers; for instruction and skill files, use only features both agents support and mark anything one agent can't do, with the alternative for the other.
   - The policy lines now duplicated between `CLAUDE.md` and `CONTRIBUTING.md` are removed from the agent file.
2. `CLAUDE.md` is exactly `@AGENTS.md\n`. Kept (not deleted, though Claude Code 2.1.277+ reads `AGENTS.md` natively) because older or telemetry-off sessions read only `CLAUDE.md`, and `claude-review.yml` names it. Copilot loads the text twice (~4 KB, identical, no conflict): accepted.
3. The skill `.claude/skills/new-source-type/SKILL.md` stays where it is (both agents find it), and is made agent-neutral:
   - line 12, "Repo rules (CLAUDE.md): ... no jq or Python" (stale) becomes "Repo rules: `AGENTS.md`";
   - section 5 describes the old `run-tests.sh` (per-type sections, `contract/<type>-valid` loop); rewrite for the pytest suite;
   - Claude-only terms (`run_in_background`, "the Edit tool", "scratchpad", "a Claude Bash call", "this session" in the MCP step) become neutral or are marked "Claude Code:" with the Copilot alternative;
   - the H1 and body read correctly if `$ARGUMENTS` is not substituted (per step 0).
4. Enforcement stays in git and CI (pre-push PII hook, `pii.yml`, lint, tests): identical for both agents. No agent hooks or committed permissions now.
5. Files only one agent reads stay out for instructions and skills: no `.github/copilot-instructions.md`, `.github/instructions/`, `.github/skills/`, `.agents/`, `GEMINI.md`, `.claude/CLAUDE.md`, no symlinks. (Claude-only files with other jobs stay: `.claude/settings.json`, `.claude-plugin/`, `claude-review.yml`.)
6. Structural test `tests/test_agent_files.py` (picked up by `run-tests.sh` and CI as is):
   - `CLAUDE.md` is the bytes `@AGENTS.md\n`; `AGENTS.md` exists, imports `@CONTRIBUTING.md` on a line of its own, and with it is under 8 KB;
   - a few policy key phrases (e.g. `core.hooksPath`, `noreply`) occur in `CONTRIBUTING.md` and not in `AGENTS.md`;
   - none of the paths in step 5 exist; `git ls-files -s` has no mode 120000;
   - every `.claude/skills/*/SKILL.md` has `name` and `description` in its frontmatter.
7. Docs that mean this repo's `CLAUDE.md` and change to `AGENTS.md`: `CONTRIBUTING.md:7`, `docs/roadmap.md:15` and `:23`, `SKILL.md:12` (step 3). Off limits: every other mention (in `plugins/`, `tests/`, `docs/setup.md`, `docs/sources.md`, `docs/adr.md`) means a wiki's or a researched repo's `CLAUDE.md`; `claude-review.yml` stays (decided). `docs/development.md:7` ("Edit this repo in a Claude session") becomes an "Agents" section: both agents supported; Copilot: trust the folder, avoid `--allow-all`/`--yolo`; `core.hooksPath` before the first push; no `/delegate`.
7a. Dual-agent rule: stated once, in `CONTRIBUTING.md` ("every change must work in both Claude Code and Copilot CLI"), and so reaches every agent session through the import; the agent-facing how (common features only, mark one-agent steps, no one-agent instruction or skill files, step 5) is in `AGENTS.md` (step 1). The research table goes in the ADR, not in a maintained doc table.
8. Acceptance test (owner, Copilot CLI, after PR 2): `/instructions` lists `AGENTS.md` and `CLAUDE.md`; it states the Python and push rules, and the noreply rule (only in `CONTRIBUTING.md`, so this proves the nested import works in Copilot); `/skills list` shows `new-source-type` and it is not auto-invoked; `/new-source-type foo` gets the argument. Also check that PR 2's Claude review still cites the rules through the pointer. Note: without a local denylist the PII check runs general patterns only.
9. Parked, with triggers: VS Code agent mode (a collaborator asks); Copilot coding agent and `/delegate` (only when the PII check no longer depends on the local hook); Copilot code review; shared guard hooks in `.claude/settings.json` (an agent bypasses the hook).

## Delivery
- PR 1 (plans rule, done with this file): one file per detailed plan in `docs/plans/<slug>.md`, indexed in `docs/roadmap.md` (items may be one line; plan file deleted when done, decision to `docs/adr.md`). Update every statement of the old rule: `CLAUDE.md:20`, `docs/roadmap.md:3`, `docs/development.md:3`, and `docs/layout.md` (the `docs/` listing). Add this plan and its index line.
- Step 0, by the owner.
- PR 2 (done): steps 1-7a, ADR in `docs/adr.md` (with the research table and why `CLAUDE.md` is kept), green tests (`--e2e`) and lint. Then step 8.
