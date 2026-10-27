#!/usr/bin/env bash
# PreToolUse(Bash|PowerShell): block any git push. The user pushes themselves.
# Known false positive: a command mentioning both "git" and the word "push",
# e.g. a commit message containing "push". Rephrase the message.

. "$(dirname "$0")/lib-hookjson.sh"

[ "$HOOK_PARSE_OK" = 1 ] || block "could not parse hook input; refusing (fail closed)."
case "$HOOK_TOOL" in Bash|PowerShell) ;; *) exit 0 ;; esac
[ -n "$HOOK_COMMAND" ] || block "$HOOK_TOOL call without a command; refusing (fail closed)."

cmd=$(norm "$HOOK_COMMAND")
if printf '%s' "$cmd" | grep -Eq '\bgit\b.*\bpush\b'; then
  block "git push is not allowed in wiki sessions. Commit locally; the user pushes."
fi
exit 0
