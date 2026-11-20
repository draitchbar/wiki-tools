# Plan: unattended ingest with deferred questions, `/wiki:clarify`

Status: designed 2026-11-20 from the roadmap item (grilled 2026-11-19) and reviewed the same day (one round; its findings are folded in). It lets an ingest run without the user, the precondition for the parked **Headless or `/loop` ingest** (`docs/roadmap.md`), which stays parked: this plan does not schedule anything or test `claude -p`/`/loop`.

## Intent (settled in the roadmap)

- `/wiki:ingest <key> --unattended` and `/wiki:ingest all --unattended`. Without the flag an ingest still asks as today; the one change for attended runs is that they also close open questions their material or the user's answers settle (3).
- An unattended run never asks and never guesses: what it would ask becomes a **deferred question** in `open-questions.md` at the wiki root, and the page carries a marker where the fact would be.
- `/wiki:clarify` (manual-only) walks the open questions with the user.
- Reminders: sync-status (count, oldest) at session start and after `/clear`; lint (old questions, markers and questions that don't match, a malformed file).

## Design

### 1. The flag (ingest skill)

- `--unattended` may stand anywhere among the arguments; it is removed before the key and filter are parsed. `argument-hint` and `description` name it.
- **Clean start:** an unattended run first runs `git status` and refuses (the whole run) if `wiki/`, `raw/sync-log.md` or `open-questions.md` has uncommitted changes, naming the paths: a commit would sweep them in, and an earlier stopped run must be looked at by the user first.
- Where the skill or a contract would stop and ask, an unattended run does this instead:

| Situation | Attended (today) | Unattended |
|---|---|---|
| No key | stop and ask | the run fails: `no source key` |
| `all` with a filter; a `mode: research` key | stop | the same (the run fails, with today's message) |
| Key at `never` (first ingest) | First-ingest steps | refused: `first ingest needs the user: /wiki:ingest <key>` |
| **Check needed** | run Check, maybe propose an instance file | refused: `Check needed: run /wiki:ingest <key> without --unattended` |
| `show` or wrapper refusal; the reader's tool missing or failing during List new or Fetch | stop, show the message | that source fails with the message; `all` goes on as **Ingest all** step 5 says |
| A contract says to ask, to have the user approve, or to let the user choose (an attachment to fetch, a borderline page, items to skip) | ask | take the choice that fetches and writes nothing extra, and list it in the report |
| A contract can't go on without an answer (a new scope's starting point, a renamed field value, a sender that finds nothing) | ask | that source fails with what it needs |
| Unclear fact (step 7) | ask | `unclear` question, fact left out |
| Conflicting figure | keep both, flag to the user | keep both, `conflict` question |
| Material fits no page type (data-model review) | propose a model change | filed under the closest existing type, `filing` question; a model change is only proposed in the question's suggestion |
| Suspicious content, untracked files, privacy skips | told to the user | in the final report; suspicious content also as a line `Suspicious: <citation>, not acted on` in the ingest's `wiki/log.md` entry, naming the item by its citation only, never quoting it |

  The contract rows are a generic rule in the skill, so no contract changes (AGENTS.md keeps source specifics in `SOURCE.md`; this rule is source-neutral).
- `all --unattended` puts the `due` list in the report instead of showing it first; `due` already skips `never`, **Check needed**, research and unavailable sources.
- The final report is the run's last message (what `claude -p` prints and a cron job logs). It names the questions raised, added to and closed, by ID.
- Commits and never pushing are unchanged. `open-questions.md` is staged with the ingest commit of the source that raised, changed or closed a question.

### 2. Markers on pages

- **ID:** `q-YYYY-MM-DD-<slug>`, the date the question was raised; the slug is `[a-z0-9-]`, 1 to 40 characters, words from the question transliterated to ASCII (`æ` → `ae`, `ø` → `oe`, `å` → `aa`), never a source's key, guard word or CLI name (a commit message naming one is a guard refusal); `-2`, `-3` if taken. Regex: `q-[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]{1,40}`.
- **Marker:** `^[open: <id>]` (an Obsidian inline footnote). Regex for lint and clarify: `\^\[open: (<id regex>)\]`.
- `unclear`: one italic span saying what is missing, then the marker, where the fact would go: `*VAT basis of the quote not stated* ^[open: q-…]`. The fact itself is never written. Clarify replaces or removes exactly that span and the marker.
- `conflict`: both figures, each with its citation, then the marker.
- `filing`: `*Filed here until the question is settled* ^[open: q-…]` as the first body line after the frontmatter.
- A page may carry several markers; one question may have markers on several pages (`pages`). Markers go in page bodies only, never in frontmatter or `wiki/log.md`.

### 3. `open-questions.md`

At the wiki root, created by the first run that raises a question (not by `/wiki:init`). Header `# Open questions` and one line saying what the file is and that `/wiki:clarify` answers it. Then the blocks, newest first:

```markdown
### q-2026-11-20-offer-vat-basis
- kind: unclear
- raised: 2026-11-20, gmail
- items: Gmail: "Re: offer", 10.08.2026
- pages: [[supplier-x]], [[budget]]
- question: Is the 45,000 DKK in the quote incl. or excl. VAT?
- context: The quote states no VAT basis; the budget compares it with figures incl. VAT.
- suggestion: Excl. VAT, as the supplier's earlier quote (Gmail: "Offer", 01.07.2026).
```

- Fields, one bullet each, in this order: `kind` (`unclear`, `conflict`, `filing`), `raised` (`YYYY-MM-DD, <key>`), `items` (one or more, `; `-separated, in the contract's **Cite** form), `pages` (`[[links]]`), `question`, `context`, `suggestion`; optional `related: <id>` and `answer:` (typed by the user, below). `context` and `suggestion` describe; they never quote source text that reads as instructions.
- A later run **adds to** a question it matches (same fact, same pages): it appends to `items` and `pages` and may add to `context`; `raised` keeps the first date. It may **merge** two questions it finds are the same: the older ID stays, the other's markers are rewritten to it, its block removed, its fields folded in. When unsure, it raises a new question with `related:`.
- **Closing:** an ingest (attended or not) whose material settles a question writes the fact with its citation in place of the marker, removes the block and writes a `clarify` entry (5). An attended ingest whose user answers something an open question asks closes it as `answered` the same way. A block with an `answer:` line is never closed or merged by an ingest, only named in the report.
- Before raising a question, a run reads the `clarify` entries in `wiki/log.md` and does not re-raise one that was **dismissed** (same fact and pages); it leaves the fact out without a marker and says so in the report.
- A merge conflict in the file keeps both blocks (as for `wiki/log.md`); a duplicate ID is fixed by renaming the newer one and its markers. Lint reports both (7).
- `answer:`: the user may type an answer into the file in Obsidian (`- answer: …`). Only `/wiki:clarify` applies it, after confirming with the user.

### 4. `/wiki:clarify` (new skill, manual-only)

`disable-model-invocation: true`; allowed tools: `git add/commit/status/mv`, `sources.sh show` (to re-read a cited item's contract when the user asks to check). Arguments: none, or one question ID.

1. Read `open-questions.md` (missing, or no blocks: say so and stop) and the wiki's CLAUDE.md. Show the list: ID, kind, raised, question.
2. Walk the questions oldest first (or only the named one). For each: find its markers by searching `wiki/` for the ID (not only in `pages`), show the block, the marked lines, any `answer:` as the proposed answer, and the suggestion. The user **answers** or **dismisses**; there is no "later". Stopping the walk leaves the rest untouched.
3. **Answer:** write the fact in place of every marker (and its italic span), cited inline and in `sources:` as `"User statement (YYYY-MM-DD)"` (today); for `conflict` the chosen figure stays and the other is dropped (wiki-conventions' rule for a directed resolution); for `filing` the user says where it belongs: a move (`git mv`, links rewritten) or a data-model change, which follows the ingest skill's **Data-model review** steps 3 and 4 (its own `schema` commit first).
4. **Dismiss:** `unclear`: span and marker removed, the fact stays out; `conflict`: the figure with the newer source date stays, the older is dropped with its citation, marker removed; if the dates are equal or a source has none (`raw/` files), dismissing isn't offered: the user answers; `filing`: the page stands, span and marker removed.
5. Then update `updated:` on each changed page and its index row, remove the block, prepend the log entry, and commit the named paths: `Clarify <id>: answered` or `dismissed`. One commit per question. Never push.

### 5. Bookkeeping: the `clarify` log op

`## YYYY-MM-DD | clarify | <id>: answered|dismissed|closed by <key>`, then the lines `Question: …`, `Answer: …` (or `Dismissed.`, or `Closed by: <citation>`), `Pages: [[…]]`, and for a dropped figure `Dropped: <figure> (<citation>)`. One entry per question. The schema's op list gains `clarify`.

### 6. Reminder: sync-status

- `sync_status.py`, in a wiki with `raw/sync-log.md` (as today, nothing without one), adds after the source lines, when `open-questions.md` has blocks: `Open questions (open-questions.md): N, oldest <id> (raised YYYY-MM-DD, D days ago). Answer them with /wiki:clarify.` Blocks without a readable `raised` date count, but don't compete for oldest; with none readable the line ends after N. The plugin Note stays first.
- The parser lives in `sourcelib.py` (`open_questions(text)` and a reader for the root's file): per `### ` heading, the ID, whether it matches the ID regex, `kind`, `raised` date or None, the `pages` link targets; plus whether the text has conflict lines (`<<<<<<<`, `=======`, `>>>>>>>` at a line start). CR stripped, a last line without a newline read. No new module.
- `hooks.json`: the sync-status SessionStart matcher becomes `startup|clear`. `docs/plans/copilot-wiki-support.md` step 4 item 3 later drops the matcher; it notes this change.
- The sync-status skill puts the line under its table and suggests `/wiki:clarify` when questions are open.

### 7. Lint

`lint.py`, with the parser above (dates against `WIKI_LINT_TODAY` like the rest). Three new WARN sections after "possibly stale" and before the INFO sections, printed only when non-empty, so existing recorded outputs don't change:
- **WARN: open questions older than 30 days**: `- \`<id>\` raised YYYY-MM-DD (N days ago)` (31 days or more).
- **WARN: open question markers that don't match**: a marker in any file below `wiki/` but `log.md` (pages and `index.md`) whose ID has no block: `- \`<page>\`: marker <id> has no question in open-questions.md`; a block whose ID no file below `wiki/` marks: `- \`<id>\`: no page carries its marker`.
- **WARN: open-questions.md malformed**: a heading that isn't a valid ID, a duplicate ID, an unknown or missing `kind`, a missing or unreadable `raised`, a `pages` link to no page, conflict lines.
- Nothing when the wiki has neither the file nor markers. The lint skill's Phase 5 offers: `/wiki:clarify` for old questions; for a marker without a question, re-raise it or remove the marker (showing the line); for a question without a marker, put the marker back or let `/wiki:clarify` dismiss it; for a malformed file, the fix shown line by line. Renaming a page (wiki-conventions) also rewrites its links in `open-questions.md`.

### 8. Other files

- `wiki_check.py`: `open-questions.md` at the root is part of the layout (not "Markdown outside the layout").
- Schema (each file within the 9,000-byte test budget; `wiki-conventions.md` has about 1,000 bytes left): `wiki-layout.md` gets `open-questions.md`, the marker and the `clarify` op; `wiki-conventions.md`'s "Ask for context", two-sources and headless lines point at deferred questions for unattended runs, and the rename rule names `open-questions.md`.
- `AGENTS.md`: `clarify` joins the list of manual-only skills.
- Docs: `docs/skills.md` (clarify row, the flag in the ingest row), `docs/layout.md` (clarify in the skills list), `README.md` if it lists skills. When done: an ADR entry (14), the roadmap item removed and the parked headless row updated, this file deleted.

## Tests

- `test_lib_source.py` (sourcelib's parser): fields in any order, missing bullets, no final newline, CRLF, a duplicate ID, a non-`q-` heading, conflict lines.
- `test_sync_status.py`: no file / no blocks → no line; N questions and the oldest; an unreadable `raised`; no line without a sync-log.
- `test_lint.py`: each of the three sections, in a small wiki built in the test; none when absent; the 30-day boundary (30: none, 31: warning); a marker in `log.md` ignored.
- `test_wiki_check.py`: `open-questions.md` not reported as outside the layout.
- `test_guard.py`, beside `test_hooks_json_matcher`: the sync-status hook's matcher is `startup|clear`.
- Recorded outputs unchanged, `bash tests/run-tests.sh` and `--e2e` green, ruff and shellcheck clean.
- The skills (the flag, clarify) are prose; no automated test. The user's live check in a wiki (both skills are manual-only): an unattended ingest that raises each kind, `/wiki:clarify` answering and dismissing, and how `^[open: …]` renders in Obsidian's Live Preview and reading view, also in a table cell.

## Out of scope

Scheduling (cron, `/loop`, `claude -p` permissions), two runs at once in the same wiki, and notifications other than sync-status: the parked **Headless or `/loop` ingest** item.
