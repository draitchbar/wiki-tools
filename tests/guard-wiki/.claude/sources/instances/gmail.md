---
key: gmail
type: gmail
labels: Receipts
state:
  - last_checked
reader:
  - search threads: mcp__claude_ai_Gmail__search_threads
  - read thread: mcp__claude_ai_Gmail__get_thread
  - list labels: mcp__claude_ai_Gmail__list_labels
  - read message: mcp__claude_ai_Gmail__get_message
  - download attachment: mcp__claude_ai_Gmail__download_gmail_attachment
reader_deny:
  - mcp__claude_ai_Gmail__send_message
  - mcp__claude_ai_Gmail__reply
  - mcp__claude_ai_Gmail__forward
  - mcp__claude_ai_Gmail__create_draft
  - mcp__claude_ai_Gmail__update_draft
  - mcp__claude_ai_Gmail__delete_draft
  - mcp__claude_ai_Gmail__trash_message
  - mcp__claude_ai_Gmail__trash_thread
  - mcp__claude_ai_Gmail__untrash_message
  - mcp__claude_ai_Gmail__untrash_thread
  - mcp__claude_ai_Gmail__mark_message_spam
  - mcp__claude_ai_Gmail__mark_thread_spam
  - mcp__claude_ai_Gmail__unmark_message_spam
  - mcp__claude_ai_Gmail__unmark_thread_spam
  - mcp__claude_ai_Gmail__create_label
  - mcp__claude_ai_Gmail__delete_label
  - mcp__claude_ai_Gmail__update_label
  - mcp__claude_ai_Gmail__label_message
  - mcp__claude_ai_Gmail__label_thread
  - mcp__claude_ai_Gmail__unlabel_message
  - mcp__claude_ai_Gmail__unlabel_thread
  - mcp__claude_ai_Gmail__update_message_labels
  - mcp__claude_ai_Gmail__apply_sensitive_message_label
  - mcp__claude_ai_Gmail__apply_sensitive_thread_label
  - mcp__claude_ai_Gmail__list_drafts
  - mcp__claude_ai_Gmail__get_draft
---

## Reader
The claude.ai Gmail connector, bound 2026-11-23. search threads: `query`, `pageSize: 50`, `view: THREAD_VIEW_SUMMARY`, following the next page token as `pageToken`; read thread: `threadId`; read message: `messageId`.
