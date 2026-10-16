# Security review: kfchou/wiki-skills

Reviewed 16.10.2026 at commit `d9267ec` (2026-07-03), MIT licence, 189 stars. Everything was read as untrusted data in a scratch clone; nothing was installed or executed.

**Scope:** all 7 SKILL.md files, the 4 helper scripts and the pre-commit hook under `skills/wiki-init/assets/bin/`, the plugin and marketplace manifests, the README, and `docs/` (design notes only). The Python tests were skimmed, not run.

**Verdict:** no malicious code, no hidden network calls, no credential access. There is one real data-exposure risk (strong-mode audit) and a few design weaknesses. We **did not install** the plugin. `/wiki:lint` and `/wiki:audit` in this repo reimplement its ideas without the risky parts.

## Findings

| # | Severity | Where | Issue | How wiki-tools handles it |
|---|---|---|---|---|
| 1 | **High** (privacy) | `wiki-audit` Phase C, "strong mode" | If `codex` or `gemini` is on PATH, the audit sends the full page, the cited source excerpts and every directly linked page to OpenAI or Google, with no consent step beyond typing `strong`. The payload is passed as a command-line argument (`codex exec "$(cat …)"`), so it's visible in the process list and left in `$TMPDIR` afterwards. `codex exec` is itself an agent that can run commands, so a prompt injection in a source could act through it. | Not adopted. `/wiki:audit` uses only Claude subagents. |
| 2 | Medium | `wiki-ingest`, `wiki-audit` | No rule that source content (URLs, documents, emails) is data, not instructions. The skills read untrusted text while holding write access to the wiki. | Our `/wiki:ingest`, `/wiki:audit` and `/wiki:lint` (subagent prompt) now say this explicitly. |
| 3 | Medium | `wiki-init` → `git config core.hooksPath bin/hooks` | A tracked, in-repo hook runs on every commit. Anything that can change `bin/hooks/pre-commit` or `bin/*.py` in the repo gets code execution at the next commit, e.g. a pulled change or an LLM write during ingest. The hook uses `uv run`, which would install any dependencies a modified script declares. | Not adopted. No git hooks. Our guard scripts live outside the wikis, and the Claude hooks block writes to them. |
| 4 | Low | `.claude-plugin/marketplace.json` | The plugin source is the repo URL with no pinned commit, so installs and updates take whatever is on `main`. | Not installed. |
| 5 | Low | all skills: "find `SCHEMA.md` … upward, or `~/wikis/`" | Wiki discovery falls back to `~/wikis/`, which is exactly where our wikis live. It could act on a different wiki than the one you're in. | Our scripts resolve the wiki strictly as the git toplevel of the current directory. |
| 6 | Low (data loss, not security) | `generate-index.py`, run automatically as lint Phase 0 | It overwrites `wiki/index.md` from frontmatter, so hand-maintained index tables would be lost. | Our lint only reads `index.md`. |
| 7 | Info | `wiki-audit`, `wiki-lint` | Reports and the `review:` frontmatter stamp are written without asking. That's harmless in itself, but it means the skills write on every run. | Ours also write reports without asking (only to `outputs/`), and change wiki pages only after confirmation. |

## What the helper scripts do (verified)

- `lint-mechanical.py`, `check-contradictions.py`, `render-log.py`, `generate-index.py`: standard library only. `subprocess` calls only `git -C <wiki root> …`, with an argument list and no shell. No network access. The only write is `wiki/index.md`, in `generate-index.py`.
- `bin/hooks/pre-commit`: runs two of those scripts via `uv run`, or blocks the commit. Bypassed with `--no-verify`.

## Ideas adopted (reimplemented, not copied)

- **Two-phase lint:** a deterministic script with no LLM, then judgement checks by subagents scoped to clusters. Page bodies stay out of the main context. Our clusters are folders, since udbygning has no tags.
- **Stale-claim heuristic:** not updated in N days, and the body still uses words like "pending" or "latest". We extended the word list with Danish.
- **Per-source audit:** one subagent per source file, in parallel, with a fixed verdict rubric that must quote what the source actually says.
- **Uncited-claim detection** as a separate step.
