# Wiki conventions (shared)

These rules apply to every LLM wiki. The wiki's own CLAUDE.md adds project facts and may override formatting details.

## Never guess: escalation order
1. **Wiki first.** If the answer is in the wiki, use it.
2. **Sources second.** If the wiki doesn't cover it, go to the sources (`raw/` and the wiki's sources in `.claude/sources/`, read as their contracts say).
3. **Web last.** If the sources don't cover it either, research the web and say clearly that the answer comes from general research, not project documents. Mark forum posts and review sites as anecdotal.

Verify sub-agent claims against the source before putting them in a page or report.

## Ask for context, don't guess
- When the meaning of something is unclear, ask the user instead of guessing. Typical cases: who a person is, which of two offers or versions is meant, an unstated VAT or tax basis where amounts matter, whether a decision still stands, how a new kind of material fits the wiki.
- Record the answer as a source: `"User statement (YYYY-MM-DD)"`, in `sources:` and inline next to the claim.
- A pointer from the user ("the new contract is on Proton") is a pointer, not a fact about the document. Record facts about a file (signed or not, which version, its date) only after reading it; until then write "the user says X is in Y".
- In a non-interactive (headless) run nobody can answer: list the open questions in the final report instead of guessing.

## Verbatim figures (anti-drift)
- Every amount, date, percentage, deadline or contract term is quoted **exactly as in the source**, with its source, in the source type's **Cite** format (its `SOURCE.md`), e.g.:
  - a file: path and page, `(Proton: offers/offer-2026-08.pdf, p. 2)`, or `(raw/offer.pdf, p. 2)` for `raw/` (older pages write `raw: offer.pdf`; both mean the same, new citations use `raw/<path>`)
  - a manual key (no source file, e.g. `web`): `(web: example.com, buyer's guide)`, or the URL
  - an email: thread subject and message date, `(Gmail: "Re: offer", 10.08.2026)`
- Don't round, convert or paraphrase a figure. If you compute something (a sum, a difference), label it as computed and show the inputs.
- Questions about exact figures are answered by re-reading the source, not from the wiki page.
- When two sources disagree, record both with their sources and flag the conflict for the user; don't pick one silently.

## Git
- Commit locally with clear messages. **Never push**; the user pushes.
- Stage only explicitly named paths. Never `git add -A`, `git add .` or `git add -u`.
- If there are untracked files you didn't create, list them for the user instead of adding them.
- Paths under `.claude/` (settings, `.claude/sources/`) are protected by guard hooks; you never write them. Hand them to the user as in **Protected files** below.
- The guard reads whole command lines. A commit message (or any other command) that names `.claude/sources`, the wiki-tools plugin folders or a source's CLI (its guard words, e.g. `proton-drive`) is blocked, so write "instance files", "Proton" and the like instead.
- Run wiki-tools scripts (`${CLAUDE_PLUGIN_ROOT}/scripts/*.sh`, source wrappers) one per call, with no `;`, `&&`, pipes, `echo` around them or redirection; the guard blocks anything else. Don't `ls` or `cat` the plugin folders either: `sources.sh catalog` and `sources.sh contract <type>` show the source types.

## Protected files
`.claude/settings.json` and everything under `.claude/sources/` are written by the user, never by you, not even as a draft in a Bash heredoc (the guard blocks any command that names `.claude/sources`).
- **Source files, one at a time.** Show one file's full content in a fenced block, and above it the command the user runs in a terminal outside Claude, from the wiki:
  `bash ${CLAUDE_PLUGIN_ROOT}/scripts/install-source-file.sh instances/<key>.md` (or `types/<type>/<file>`).
  The user pastes the content, ends with Ctrl-D, reviews the diff and answers `y`. The script checks the file before writing it and prints any settings rules still missing. Show the next file only after the user says it's installed. If the script refuses, fix the draft from its message and show the whole file again.
- **Order:** a local type's `SOURCE.md`, then its scripts, then the instances that use it.
- **Settings:** show only the lines to add and where they go (`permissions.allow`, `permissions.deny`); the user edits `.claude/settings.json` by hand. A new wiki's first settings file is shown in full.
- **Commit:** at the end, give one line naming each installed file, e.g. `git add -- .claude/sources/instances/gmail.md .claude/settings.json && git commit -m "Add source files"`, with `git rm -q <file>` first for a file to delete. The user runs it: their commands may name protected paths, yours may not.

## Naming
- Filenames: kebab-case (`jane-doe.md`).
- Cross-references: `[[wikilink]]`.
