---
key: tracker
type: jira
site: example.atlassian.net
scopes:
  - help-search | under: ABC-100
state:
  - last_checked
  - cursor
  - scopes
reader:
  - site access: mcp__claude_ai_Atlassian_MCP__getAccessibleAtlassianResources
  - find project: mcp__claude_ai_Atlassian_MCP__executeRead name=listJiraProjects
  - search: mcp__claude_ai_Atlassian_MCP__searchJiraIssuesUsingJql
  - read issue: mcp__claude_ai_Atlassian_MCP__getJiraIssue
  - list comments: mcp__claude_ai_Atlassian_MCP__listJiraIssueComments
  - list remote links: mcp__claude_ai_Atlassian_MCP__executeRead name=listJiraIssueRemoteIssueLinks
reader_deny:
  - mcp__claude_ai_Atlassian_MCP__executeWrite
  - mcp__claude_ai_Atlassian_MCP__executeDestructive
---

## Reader
The claude.ai "Atlassian MCP" connector, bound 2026-11-19. Fixed arguments: compact view, the fields each step names.
