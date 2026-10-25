# Wiki layout (raw + wiki pattern)

For wikis that follow the raw/wiki pattern. Each wiki's CLAUDE.md names its folders, page types and page templates.

## Structure
- `raw/`: immutable source material and derived extracts. Never edit source files here.
  - `raw/sync-log.md`: per source (`raw` and each instance key) a `last_checked_<key>: YYYY-MM-DD` line and any other state line its instance agreed (`<field>_<key>: <value>`), plus a history table. `never` means the source hasn't been ingested yet; its first ingest asks for a starting point.
  - `raw/ocr/<file>.txt`: OCR text layers of scanned PDFs (created by the ingest skill).
- `wiki/`: pages written and maintained by Claude.
  - `wiki/index.md`: master catalogue, a table per section.
  - `wiki/log.md`: append-only operations log, newest entry first, headed `## YYYY-MM-DD | <op> | <title>`, where `<op>` is `init`, `ingest`, `research`, `schema`, `lint`, `lint-fix`, `audit` or `audit-fix`. Entries are never edited; a later change gets its own entry.
- `outputs/`: reports: `lint-YYYY-MM-DD.md`, `audit-<slug>-YYYY-MM-DD.md`, `init-research-YYYY-MM-DD.md`.
- `templates/`: one `<type>.md` per page type that has a template; new pages start from it.
- `.claude/sources/`: the wiki's sources (guard-protected; the user installs each file with `~/src/wiki-tools/plugins/wiki/scripts/install-source-file.sh` and commits them):
  - `instances/<key>.md`: one per source instance: its type, parameters and agreed state fields. The key is the `/wiki:ingest <key>` argument and names its state lines in `raw/sync-log.md`.
  - `types/<type>/SOURCE.md`: wiki-local source types (contract plus optional wrapper scripts). Standard types live in `~/src/wiki-tools/plugins/wiki/sources/`.
- Fetched source files are cached outside the repo in `~/.cache/wiki-sources/<wiki>/<key>/`. Don't copy them into the repo.

## Page frontmatter
Every wiki page starts with YAML frontmatter:

```yaml
---
title: Page Title
type: <one of the types listed in this wiki's CLAUDE.md>
sources:
  - "<source citation>"   # in the source type's Cite format, e.g. "Gmail: subject (YYYY-MM-DD)"
related:
  - "[[related-page]]"
created: YYYY-MM-DD
updated: YYYY-MM-DD
status_as_of: YYYY-MM-DD   # decision and approval pages only
---
```

Decision and approval pages carry `status_as_of`, so a superseded decision doesn't read as current.

## Ingest workflow
Use `/wiki:ingest <key> [filter]` (`raw` or an instance key). Add sources with `/wiki:add-source <type>`. Ingest:
1. reads the instance and its type's contract, and `raw/sync-log.md` for its state;
2. lists and fetches what's new as the contract says;
3. creates or updates pages (templates as CLAUDE.md names them, verbatim-figures rule);
4. updates `wiki/index.md` and appends to `wiki/log.md`;
5. updates the instance's state lines and the history table in `raw/sync-log.md`;
6. makes **one commit per ingested source**, staging named paths only.

## Data model
The folders under `wiki/`, the page types, the templates and which types carry `status_as_of` form the wiki's data model, set by `/wiki:init` from the wiki's purpose. It isn't fixed: the first ingest of each source, and any ingest that brings material no page type fits, reviews the model against the purpose in CLAUDE.md and proposes changes. Changes are applied only after the user agrees, in a separate commit logged as `schema`.

## Query workflow
1. Read `wiki/index.md` to find the relevant pages.
2. Read those pages and answer, citing them with `[[wikilinks]]`.
3. For exact figures, confirm against the cited source.
4. Offer to save a valuable new synthesis as a page.

## Lint and audit
- `/wiki:lint` runs the structural checks and the contradiction checks. Run it about every 5 ingests; the report goes to `outputs/lint-YYYY-MM-DD.md`.
- `/wiki:audit <page>` re-reads a page's sources and checks every figure and claim against them. Use it on budget, decision and approval pages, and whenever lint reports a contradiction. The report goes to `outputs/audit-<slug>-YYYY-MM-DD.md`.
- Reports live in `outputs/` and are committed; wiki pages don't link to them.
