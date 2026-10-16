#!/usr/bin/env bash
# PreToolUse(Bash) and PreToolUse(Write|Edit|MultiEdit): keep Proton Drive
# read-only and keep Claude away from the guard machinery.
#
# Bash: blocks commands that mention the proton-drive binary or any protected
# path/keyword. The only exception is a plain invocation of one of the
# plugin's own scripts (pd-read.sh, ocr.sh, sync-status.sh) with no chaining,
# redirection or substitution.
#
# Write/Edit: blocks writes to protected paths, and blocks non-Markdown
# content that contains "proton-drive" (a helper script around the wrapper).
#
# This is a guardrail, not a security boundary: an obfuscated command can
# still get through.

. "$(dirname "$0")/lib-hookjson.sh"

[ "$HOOK_PARSE_OK" = 1 ] || block "could not parse hook input; refusing (fail closed)."

# Substrings (lowercase, forward slashes) of protected paths.
PROTECTED_PATHS='wiki-tools/plugins/wiki/scripts
wiki-tools/plugins/wiki/hooks
.claude/proton-roots
.claude/settings
.claude/plugins/'

# Extra Bash-only keywords.
PROTECTED_WORDS='proton-drive
hooks.json
proton-roots
claude plugin
disableallhooks'

contains_any() { # TEXT LIST
  printf '%s\n' "$2" | while IFS= read -r needle; do
    [ -n "$needle" ] || continue
    case "$1" in *"$needle"*) echo "$needle"; break ;; esac
  done
}

case "$HOOK_TOOL" in
  Bash)
    [ -n "$HOOK_COMMAND" ] || block "Bash call without a command; refusing (fail closed)."
    cmd=$(norm "$HOOK_COMMAND")
    # Allowed: bash [quoted] <path>/src/wiki-tools/plugins/wiki/scripts/<script>.sh [args]
    # with no ; & | < > ` $ anywhere.
    if printf '%s' "$cmd" | grep -Eq '^[[:space:]]*bash[[:space:]]+"?[^[:space:]";&|<>`$]*/src/wiki-tools/plugins/wiki/scripts/(pd-read|ocr|sync-status)\.sh"?([[:space:]][^;&|<>`$]*)?$'; then
      exit 0
    fi
    hit=$(contains_any "$cmd" "$PROTECTED_PATHS
$PROTECTED_WORDS")
    [ -z "$hit" ] || block "command touches protected '$hit'. Proton Drive is read-only via pd-read.sh; guard files are edited by the user in a ~/src/wiki-tools session."
    exit 0
    ;;
  Write|Edit|MultiEdit)
    [ -n "$HOOK_FILE" ] || block "$HOOK_TOOL call without file_path; refusing (fail closed)."
    path=$(norm "$HOOK_FILE")
    hit=$(contains_any "$path" "$PROTECTED_PATHS")
    [ -z "$hit" ] || block "'$HOOK_FILE' is protected ('$hit'). The user edits it themselves."
    case "$path" in
      *.md) ;;
      *)
        case "$(norm "$HOOK_CONTENT")" in
          *proton-drive*) block "non-Markdown content calling proton-drive is not allowed; use pd-read.sh." ;;
        esac
        ;;
    esac
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
