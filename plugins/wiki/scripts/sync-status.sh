#!/usr/bin/env bash
# Print how long ago each source in raw/sync-log.md was last checked.
# Runs as a SessionStart hook (stdout becomes session context) and from the
# /wiki:sync-status skill. Prints nothing when the wiki has no sync-log.
# A value of "never" (set by /wiki:init and /wiki:add-source) means the
# source was never ingested. Instances in .claude/sources/instances/ that
# have no line yet are listed too, and keys with no instance file are
# marked as manual once the wiki has instances.
# Read-only.

# A plugin from a local-directory marketplace runs from the wiki-tools working
# tree, not from a copy pinned to a commit: uncommitted edits there are live
# in every wiki, and skills (read at session start) can differ from scripts
# (read at each call). Say so when that tree has uncommitted plugin changes.
plugin_note() {
  local p top dirty
  p=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd) || return 0
  top=$(git -C "$p" rev-parse --show-toplevel 2>/dev/null) || return 0
  dirty=$(git -C "$p" status --porcelain -- . 2>/dev/null | head -n 5)
  [ -n "$dirty" ] || return 0
  printf 'Note: the wiki plugin runs from the working tree %s (commit %s), which has uncommitted changes in the plugin:\n%s\nSkills were read when this session started, scripts are read at each call, so they may not match. Commit the changes and run /reload-plugins (or restart).\n' \
    "$top" "$(git -C "$p" rev-parse --short HEAD 2>/dev/null)" "$dirty"
}
plugin_note

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

# Research instances (mode: research) aren't ingested, so their age isn't a
# reason to ingest; they are left out.
research=" "
for k in $(src_instances "$root"); do
  t=$(src_field "$(src_instance_dir "$root")/$k.md" type)
  c=$(src_contract "$root" "$t" 2>/dev/null) || continue
  [ "$(src_mode "$c")" = research ] && research="$research$k "
done

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
  case "$research" in *" $key "*) continue ;; esac
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
  case "$research" in *" $k "*) continue ;; esac
  grep -q "^last_checked_$k:" "$log" || out="$out
- $k: no last_checked_$k line yet (treated as never checked)"
done

[ -n "$out" ] || exit 0
printf 'Wiki sync status (raw/sync-log.md):%s\n' "$out"
