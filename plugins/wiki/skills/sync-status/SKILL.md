---
name: sync-status
description: Show how long ago each source of the current wiki was last ingested, and suggest what to ingest next. Use when the user asks what's new, what's stale, or where to start a wiki session.
allowed-tools:
  - Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/sync-status.sh)
  - Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/sources.sh *)
---

# Sync status

!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/sync-status.sh`

!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/sources.sh list`

If the sync-status block above has no source lines (it is empty, or holds only a Note), this wiki has no `raw/sync-log.md`: show the Note if there is one, say so and stop.

Otherwise:
1. First show any Note or error text from either block word for word. Then show **one** short table that merges the two blocks: one row per key in either block, with source, last checked, days ago, and a note. Build each row on its own, one key at a time: its note takes only the qualifiers on the lines that name that key in either block, never another key's, and lists them comma-separated in this order: type (e.g. `gmail (standard)`), manual key, INVALID, UNKNOWN TYPE, not available here, unreadable date, nothing new in raw/, then any other qualifier word for word; `-` if there are none. Write the finished table only: no corrections or second thoughts inside a cell. Research sources (`research …; not ingested` in the list) get no row: name them in one line under the table. Don't print the blocks as they are, and don't repeat a sync-status list from the start of the session: this table replaces it.
2. Suggest which source to ingest first: the stalest source that is still active for the project (check the wiki's CLAUDE.md for which sources are in use). Skip `raw` when its line says `nothing new in raw/`: it has nothing to ingest. `/wiki:ingest` takes `raw` or any source key in the list above that is valid and available here. A key with a `last_checked_<key>` line but no source (a manual key), or one marked INVALID, UNKNOWN TYPE or not available here, can't be ingested: say what the user needs to save into `raw/` first and suggest `/wiki:ingest raw`, or `/wiki:add-source` to set it up.
3. If the sync-status block ends with an `Open questions` line, show it under the table as it is, and suggest `/wiki:clarify` before the next ingest when the oldest is more than a few days old.
4. Give the exact command to run, e.g. `/wiki:ingest <key>`. When two or more sources can be ingested and are stale, also offer `/wiki:ingest all`, which ingests every source last checked before today in turn (oldest first; it skips first ingests and sources with **Check needed**).

Don't ingest anything yourself; ingesting is the user's call.
