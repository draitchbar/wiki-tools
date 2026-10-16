---
name: sync-status
description: Show how long ago each source of the current wiki (Gmail, Proton Drive, OneNote, bookmarks...) was last ingested, and suggest what to ingest next. Use when the user asks what's new, what's stale, or where to start a wiki session.
allowed-tools:
  - Bash(bash ~/src/wiki-tools/plugins/wiki/scripts/sync-status.sh)
---

# Sync status

!`bash ~/src/wiki-tools/plugins/wiki/scripts/sync-status.sh`

If nothing is printed above, this wiki has no `raw/sync-log.md`; say so and stop.

Otherwise:
1. Show the list above as a short table: source, last checked, days ago.
2. Suggest which source to ingest first: the stalest source that is still active for the project (check the wiki's CLAUDE.md for which sources are in use). Sources with a manual step, such as a OneNote or bookmarks export, should say what the user needs to do first.
3. Give the exact command to run, e.g. `/wiki:ingest gmail` or `/wiki:ingest proton`.

Don't ingest anything yourself; ingesting is the user's call.
