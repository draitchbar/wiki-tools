#!/usr/bin/env bash
# Print how long ago each source in raw/sync-log.md was last checked.
# Runs as a SessionStart hook (stdout becomes session context) and from the
# /wiki:sync-status skill. Prints nothing when the wiki has no sync-log.
# A value of "never" (set by /wiki:init) means the source was never ingested.
# Read-only.

if [ -n "$CLAUDE_PROJECT_DIR" ] && [ -d "$CLAUDE_PROJECT_DIR" ]; then
  root=$CLAUDE_PROJECT_DIR
else
  root=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null) || exit 0
fi

log="$root/raw/sync-log.md"
[ -f "$log" ] || exit 0

today=$(date +%s)
out=""
while IFS= read -r line; do
  line=${line%$'\r'}
  case "$line" in
    last_checked_*:*) ;;
    *) continue ;;
  esac
  key=${line%%:*}
  key=${key#last_checked_}
  val=$(printf '%s' "${line#*:}" | tr -d '[:space:]')
  if [ "$val" = never ]; then
    out="$out
- $key: never checked (first ingest asks for a starting point)"
  elif when=$(date -d "$val" +%s 2>/dev/null); then
    days=$(( (today - when) / 86400 ))
    out="$out
- $key: last checked $val ($days days ago)"
  else
    out="$out
- $key: unreadable date '$val'"
  fi
done < "$log"

[ -n "$out" ] || exit 0
printf 'Wiki sync status (raw/sync-log.md):%s\n' "$out"
