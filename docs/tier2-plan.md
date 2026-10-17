# Tier 2 plan: wiki tooling (pruned, with Tier 3 folded in)

Status: **not started**, plan only (17.10.2026). Source: `~/reports/LLM wiki tooling for Claude Code.md` (Tier 2 #9–#14, Tier 3 #15–#22), pruned against what Tier 1 and `/wiki:init` already deliver. Grill the open choices before building.

## Keep

| # | Item | Why | Effort | Open choices to grill |
|---|---|---|---|---|
| A | **Personal subagents** `candidate-researcher` and `evaluator` in `~/.claude/agents/` (report #9) | Makes "find N candidates, then evaluate them" repeatable: udbygning (carpenter, anneks suppliers), carleasing (`research/*.md`). The researcher gets web tools and writes only to `outputs/`. The evaluator is read-only with a criteria rubric and `memory: user`. | ~1 h | Rubric contents; where the researcher may write; personal agents vs. the plugin (agents in plugins ignore their own hooks, so personal) |
| B | **Saved workflow** `/evaluate-candidates` (report #10) | Research → N evaluators → ranked summary, the same way every run. Build after A. | ~30 min | Number of evaluators; output file name and format |
| C | **Fidelity checks in `/wiki:audit` and `/wiki:lint`** (report #15 + #17) | Rules, no installs. (1) Every number, date and name on a page must appear in the cited source; grep the whole source (the Pulshuse 1,225,000 vs. 1,395,000 mix-up was this kind). (2) Claim tags `^[inferred]` / `^[ambiguous]` next to non-sourced statements, which lint counts and lists. Extends the "User statement (YYYY-MM-DD)" rule in `schema/wiki-conventions.md`. | ~1 h | Tag syntax; whether lint warns or errors on untagged unsourced claims |
| D | **Bookmarks helper script** (report #13, slimmed) | Reads Brave's `Bookmarks` JSON (Snap profile on Linux) and lists bookmarks in the configured folder added since `last_checked_bookmarks`. No page fetching; Claude reads the pages it needs. Needs a guard exception and fixtures like the other scripts. | ~1 h | Folder name per wiki (CLAUDE.md); Windows profile path later |

## Parked, with triggers

| Item | Trigger to pick it up |
|---|---|
| **qmd** local search (report #16) | Queries feel slow or keyword searches miss pages (synonyms), typically a few hundred pages. Test on udbygning first. |
| **Headless or `/loop` ingest** (report #20) | Ingests have become routine. Test `/loop` in a session first. Headless needs `--allowedTools` (incl. `Skill`) in untrusted folders; first ingests and data-model reviews need the user, so they can't run unattended. Unknown whether claude.ai connectors load under cron. |
| **Obsidian Bases** view of frontmatter (report #11, CLI part dropped) | You want a "stale pages" or status view inside Obsidian. User-side only; `index.md` stays Claude's entry point. |
| **Obsidian Importer for OneNote** (report #12) | New OneNote notes appear for a wiki (udbygning's OneNote was last read 24.05.2026). |

## Dropped
- Report #14, personal plugin: done (this repo).
- #18 claude-obsidian, #19 nvk/llm-wiki: covered by wiki-tools and `/wiki:init`.
- #21 Basic Memory and generic notes MCP servers: decided 17.10.2026. Claude Code's built-in tools already search and edit, and an MCP write tool would bypass the guard hooks.
- #22 Docling: LibreOffice handled the audits.
- Obsidian CLI (part of #11): needs the desktop app running and always exits 0.
- Markdown LSP plugins (marksman): overlap with `lint.sh`; no search speed-up.

## Order
C first (cheap, improves every audit), then A → B, then D. Parked items only when their trigger appears.
