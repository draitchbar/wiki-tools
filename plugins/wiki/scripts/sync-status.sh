#!/usr/bin/env bash
# Print how long ago each source in raw/sync-log.md was last checked.
# Runs as a SessionStart hook (stdout becomes session context) and from the
# /wiki:sync-status skill. Prints nothing when the wiki has no sync-log.
# A value of "never" (set by /wiki:init and /wiki:add-source) means the
# source was never ingested. Instances in .claude/sources/instances/ that
# have no line yet are listed too, and keys with no instance file are
# marked as manual once the wiki has instances.
# Read-only.

if [ -n "$CLAUDE_PROJECT_DIR" ] && [ -d "$CLAUDE_PROJECT_DIR" ]; then
  root=$CLAUDE_PROJECT_DIR
else
  root=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null) || exit 0
fi

log="$root/raw/sync-log.md"
[ -f "$log" ] || exit 0

. "$(dirname "$0")/lib-source.sh"

# Keys with a line but no instance file, once the wiki has instances: they
# are kept by hand and can't be ingested.
manual=""
[ -z "$(src_instances "$root")" ] || manual=" $(src_manual_keys "$root" | tr '\n' ' ')"

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
  case "$manual" in *" $key "*) note=" (manual key: enters via raw/ or user statements)" ;; *) note="" ;; esac
  val=$(printf '%s' "${line#*:}" | tr -d '[:space:]')
  if [ "$val" = never ] && [ -n "$note" ]; then
    out="$out
- $key: never checked$note"
  elif [ "$val" = never ]; then
    out="$out
- $key: never checked (first ingest asks for a starting point)"
  elif when=$(date -d "$val" +%s 2>/dev/null); then
    days=$(( (today - when) / 86400 ))
    out="$out
- $key: last checked $val ($days days ago)$note"
  else
    out="$out
- $key: unreadable date '$val'"
  fi
done < "$log"

for k in $(src_instances "$root"); do
  grep -q "^last_checked_$k:" "$log" || out="$out
- $k: no last_checked_$k line yet (treated as never checked)"
done

[ -n "$out" ] || exit 0
printf 'Wiki sync status (raw/sync-log.md):%s\n' "$out"
