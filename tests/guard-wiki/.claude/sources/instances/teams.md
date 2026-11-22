---
key: teams
type: ms-teams
channels:
  - Team > General | 00000000-0000-0000-0000-000000000001 | 19:abc@thread.tacv2
folders:
  - Team files | file:///b!drive/
state:
  - last_checked
  - cursor
reader:
  - show scope: mcp__claude_ai_Microsoft_365__get_granted_scopes
  - list channels: mcp__claude_ai_Microsoft_365__teams_list_channels
  - list channel posts: mcp__claude_ai_Microsoft_365__teams_list_channel_messages
  - list replies: mcp__claude_ai_Microsoft_365__teams_list_channel_messages
  - read message: mcp__claude_ai_Microsoft_365__read_resource
  - list folder: mcp__claude_ai_Microsoft_365__read_resource
  - read file: mcp__claude_ai_Microsoft_365__read_resource
  - search files by name: mcp__claude_ai_Microsoft_365__sharepoint_search
reader_deny:
  - mcp__claude_ai_Microsoft_365__teams_send_channel_message
  - mcp__claude_ai_Microsoft_365__teams_reply_channel_message
  - mcp__claude_ai_Microsoft_365__teams_send_chat_message
  - mcp__claude_ai_Microsoft_365__teams_create_chat
  - mcp__claude_ai_Microsoft_365__outlook_create_event
  - mcp__claude_ai_Microsoft_365__outlook_email_search
  - mcp__claude_ai_Microsoft_365__outlook_calendar_search
  - mcp__claude_ai_Microsoft_365__outlook_find_available_time
  - mcp__claude_ai_Microsoft_365__find_meeting_availability
  - mcp__claude_ai_Microsoft_365__search_people
  - mcp__claude_ai_Microsoft_365__get_me
---

## Reader
The claude.ai Microsoft 365 connector, bound 2026-11-22. list channel posts: `limit: 50`, following `nextCursor`; list replies: `parentMessageId`; read message, list folder and read file: `read_resource` on the `teams:///` or `file:///` URI.
list folder: modified times no
