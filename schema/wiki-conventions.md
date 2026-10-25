# Wiki conventions (shared)

These rules apply to every LLM wiki. The wiki's own CLAUDE.md adds project facts and may override formatting details.

## Never guess: escalation order
1. **Wiki first.** If the answer is in the wiki, use it.
2. **Sources second.** If the wiki doesn't cover it, go to the sources (`raw/` and the wiki's sources in `.claude/sources/`, read as their contracts say).
3. **Web last.** If the sources don't cover it either, research the web and say clearly that the answer comes from general research, not project documents. Mark forum posts and review sites as anecdotal.

Verify sub-agent claims against the source before putting them in a page or report.

## Ask for context, don't guess
- When the meaning of something is unclear, ask the user instead of guessing. Typical cases: who a person is, which of two offers or versions is meant, an unstated VAT basis, whether a decision still stands, how a new kind of material fits the wiki.
- Record the answer as a source: `"User statement (YYYY-MM-DD)"`, in `sources:` and inline next to the claim.
- In a non-interactive (headless) run nobody can answer: list the open questions in the final report instead of guessing.

## Verbatim figures (anti-drift)
- Every amount, date, percentage, deadline or contract term is quoted **exactly as in the source**, with its source, in the source type's **Cite** format (its `SOURCE.md`), e.g.:
  - a file: path and page, `(Proton: tilbud/tilbud kløvervej 8.pdf, p. 2)`, or `(raw/tilbud.pdf, p. 2)` for `raw/` (older pages write `raw: tilbud.pdf`; both mean the same, new citations use `raw/<path>`)
  - a manual key (no source file, e.g. `web`): `(web: fdm.dk, leasing guide)`, or the URL
  - an email: thread subject and message date, `(Gmail: "Vedr. Kløvervej, Tisvildeleje", 10.08.2026)`
- Don't round, convert or paraphrase a figure. If you compute something (a sum, a difference), label it as computed and show the inputs.
- Questions about exact figures are answered by re-reading the source, not from the wiki page.
- When two sources disagree, record both with their sources and flag the conflict for the user; don't pick one silently.

## Git
- Commit locally with clear messages. **Never push**; the user pushes.
- Stage only explicitly named paths. Never `git add -A`, `git add .` or `git add -u`.
- If there are untracked files you didn't create, list them for the user instead of adding them.
- Paths under `.claude/` (settings, `.claude/sources/`) are protected by guard hooks; draft their content and ask the user to save and commit them.
- The guard reads whole command lines. A commit message (or any other command) that names `.claude/sources`, the wiki-tools plugin folders or a source's CLI (its guard words, e.g. `proton-drive`) is blocked, so write "instance files", "Proton" and the like instead.
- Run wiki-tools scripts (`~/src/wiki-tools/plugins/wiki/scripts/*.sh`, source wrappers) one per call, with no `;`, `&&`, pipes, `echo` around them or redirection; the guard blocks anything else. Don't `ls` or `cat` the plugin folders either: `sources.sh catalog` and `sources.sh contract <type>` show the source types.

## Naming
- Filenames: kebab-case (`pierre-devriel.md`).
- Cross-references: `[[wikilink]]`.
