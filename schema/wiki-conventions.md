# Wiki conventions (shared)

These rules apply to every LLM wiki. The wiki's own CLAUDE.md adds project facts and may override formatting details.

## Never guess: escalation order
1. **Wiki first.** If the answer is in the wiki, use it.
2. **Sources second.** If the wiki doesn't cover it, go to the raw sources (documents, Gmail, Proton Drive).
3. **Web last.** If the sources don't cover it either, research the web and say clearly that the answer comes from general research, not project documents. Mark forum posts and review sites as anecdotal.

Verify sub-agent claims against the source before putting them in a page or report.

## Verbatim figures (anti-drift)
- Every amount, date, percentage, deadline or contract term is quoted **exactly as in the source**, with its source:
  - files: path and page, e.g. `(Proton: tilbud/tilbud kløvervej 8.pdf, p. 2)`
  - Gmail: thread subject and message date, e.g. `(Gmail: "Vedr. Kløvervej, Tisvildeleje", 10.08.2026)`
- Don't round, convert or paraphrase a figure. If you compute something (a sum, a difference), label it as computed and show the inputs.
- Questions about exact figures are answered by re-reading the source, not from the wiki page.
- When two sources disagree, record both with their sources and flag the conflict for the user; don't pick one silently.

## Git
- Commit locally with clear messages. **Never push**; the user pushes.
- Stage only explicitly named paths. Never `git add -A`, `git add .` or `git add -u`.
- If there are untracked files you didn't create, list them for the user instead of adding them.
- Paths under `.claude/` (settings, proton-roots) are protected by guard hooks; ask the user to commit those themselves.

## Naming
- Filenames: kebab-case (`pierre-devriel.md`).
- Cross-references: `[[wikilink]]`.
