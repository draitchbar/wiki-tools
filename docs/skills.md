# Skills

The `wiki` plugin's skills, run in a wiki session. You start the ones marked *you*; Claude can't start them itself (`disable-model-invocation`). Claude may start the others when they fit.

| Skill | What it does | Started by |
|---|---|---|
| `/wiki:init <what the wiki is for>` | Sets up a wiki: **new** (empty folder), **adopt** (existing notes and files move into the layout), or **check** (reports what's missing; Claude can run its check, `wiki-check.sh`, itself). See `docs/setup.md`. | you |
| `/wiki:add-source <type> [key]` | Adds a source to the wiki and drafts its files for you to install. See `docs/sources.md`. | you |
| `/wiki:bind-reader <key>` | Binds a tool-neutral source (`access: tools`: `jira`, `onenote`, `proton-files`) to the reader on this machine. Has you deny the reader's write tools, tests each operation with one small read-only call, and drafts the instance file's `## Reader` section and the settings lines for you to install. An ingest's Check starts it when the binding is missing or broken, and the ingest stops until you've installed the file. | you or Claude |
| `/wiki:ingest <key>` | Brings new material from one source into the wiki's pages. The first ingest of a source checks it, asks for a starting point and reviews the data model. | you |
| `/wiki:sync-status` | Shows how long ago each source was last checked (and when `raw/` has nothing new since) and suggests what to ingest next. Also runs at every session start. | you or Claude |
| `/wiki:research <key> "<question>" [--critique] [--worktree]` | Researches a question in a research source (e.g. a codebase) with parallel agents and merges the findings into pages. See `docs/sources.md`. | you or Claude |
| `/wiki:lint` | Health-checks the wiki; details below. | you |
| `/wiki:audit <page>` | Fact-checks one page against its sources; details below. | you |
| `/wiki:commit-themes` | Commits the wiki's changes as one commit per theme. Never pushes. | you |

## Lint and audit

`/wiki:lint` and `/wiki:audit` reimplement ideas from [kfchou/wiki-skills](https://github.com/kfchou/wiki-skills) (MIT) on our own schema. That plugin isn't installed: it requires its own wiki layout, and its optional cross-model audit sends wiki content to OpenAI or Google. See `docs/kfchou-security-review.md`.

- **`/wiki:lint`:** `lint.sh` runs the structural checks (frontmatter, broken links, orphans, index coverage and index dates, dates, stale pages, `status_as_of`). Then one subagent per `wiki/` folder checks for contradictions, VAT ambiguities, superseded statements and missing cross-references. The report goes to `outputs/lint-YYYY-MM-DD.md` (`-2`, `-3`, … for a later run the same day), and fixes are only offered. Findings the user declined, deferred or judged fine (recorded as lines in the `lint-fix` log entry, written even when every fix is declined) are listed under "Already decided" in later reports and not offered again.
- **`/wiki:audit <page>`:** extracts every checkable claim, then runs one subagent per cited source (each read as its type's **Resolve citation** says; local files; URLs) to verify it against the source wording. The report goes to `outputs/audit-<slug>-YYYY-MM-DD.md`, and fixes are only offered.
