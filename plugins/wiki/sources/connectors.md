---
servers:
  - local=claude_ai_Gmail cloud=Gmail
  - local=claude_ai_Microsoft_365 cloud=Microsoft_365
  - local=claude_ai_Atlassian_MCP cloud=Atlassian_MCP
---

# Connector names per surface

A claude.ai connector's tools have one name in a local Claude Code session, on Linux and Windows alike, and another in a Claude Code cloud session: `mcp__claude_ai_<Connector>__<tool>` locally, `mcp__<Connector>__<tool>` in the cloud. Each item above pairs the two server names (the part between `mcp__` and the next `__`) of one connector.

How it is used (`docs/adr.md`, 25):

- A reader binding (an instance's `reader` and `reader_deny`) is made locally, with the local names. `sources.sh settings` gives each of its rules under the cloud name too, so the wiki's committed `.claude/settings.json` serves both surfaces; a tool bound only with a limit is denied under its cloud name, where the limit can't hold. Cloud-name rules count only from the wiki's own `.claude/settings.json`: a cloud session reads no other settings file.
- The server name matches exactly, never as a prefix. The mapping goes one way, local to cloud; a binding written in cloud names is taken as it is, and serves only the cloud. A binding may not name one connector under both names.
- `sources.sh show <key>` prints each bound tool with its cloud name, and whether this session is local or cloud.
- Read by `scripts/sourcelib.py` only; the guard doesn't use it. This file is not a source type.

A pair is added by pull request to wiki-tools, only after the connector was seen live on both surfaces with the same short tool names, compared in both directions. The first three pairs were added before the local side of that comparison (live check 2 in `docs/plans/cloud-wikis.md`), on the cloud side's match and the documented local names; a mismatch found there is fixed by pull request. A connector not listed keeps one name, as bound.

## Sightings

- **Gmail:** local 2026-11-22 (Linux, Windows). Cloud 2026-11-22 (a wiki's `/wiki:ingest gmail` stopped at Check: the tools there are `mcp__Gmail__*`) and 2026-11-25: the cloud tool set equals the gmail contract's short names exactly, every read and every listed write and deny tool.
- **Microsoft 365:** cloud 2026-11-25 offers only read tools (no `teams_send_*`, no `outlook_create_event`), whose short names match the ms-teams contract.
- **Atlassian:** cloud 2026-11-25 offers, among them, `getJiraIssue`, `searchJiraIssuesUsingJql`, `listJiraIssueComments`, `executeRead`, `getAccessibleAtlassianResources`, and also `executeWrite`, `executeDestructive`, `showConfluenceEditor` (these three not offered 2026-11-24).
- **Not paired:** Google Drive (`mcp__claude_ai_Google_Drive__*` locally; its cloud name not seen yet: not attached in the 2026-11-25 cloud session). The Desktop app's `mcp__<uuid>__*` names differ per user and can't be paired.
- **Still open:** the local side of the comparison (each connector's local short tool names against the cloud lists above).
