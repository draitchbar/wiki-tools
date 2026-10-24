---
name: sync-status
description: Show how long ago each source of the current wiki was last ingested, and suggest what to ingest next. Use when the user asks what's new, what's stale, or where to start a wiki session.
allowed-tools:
  - Bash(bash ~/src/wiki-tools/plugins/wiki/scripts/sync-status.sh)
  - Bash(bash ~/src/wiki-tools/plugins/wiki/scripts/sources.sh *)
---

# Sync status

!`bash ~/src/wiki-tools/plugins/wiki/scripts/sync-status.sh`

!`bash ~/src/wiki-tools/plugins/wiki/scripts/sources.sh list`

If the sync-status block above is empty, this wiki has no `raw/sync-log.md`; say so and stop.

Otherwise:
1. Show the list above as a short table: source, last checked, days ago.
2. Suggest which source to ingest first: the stalest source that is still active for the project (check the wiki's CLAUDE.md for which sources are in use). `/wiki:ingest` takes `raw` or any source key in the list above that is valid and available here. A key with a `last_checked_<key>` line but no source (a manual key), or one marked INVALID or not available here, can't be ingested: say what the user needs to save into `raw/` first and suggest `/wiki:ingest raw`, or `/wiki:add-source` to set it up. If the list says **Old layout**, suggest `/wiki:init` (check mode) first.
3. Give the exact command to run, e.g. `/wiki:ingest <key>`.

Don't ingest anything yourself; ingesting is the user's call.
