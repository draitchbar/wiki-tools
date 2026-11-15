#!/usr/bin/env bash
# sync-status.sh: how long ago each source in raw/sync-log.md was checked.
#
#   bash <plugin>/scripts/sync-status.sh
#
# Runs as a SessionStart hook (stdout becomes session context) and from the
# /wiki:sync-status skill. Prints nothing when the wiki has no sync-log.
# Read-only. The work is in sync_status.py (docs/adr.md, 4); this
# launcher only runs it.
#
# A hook: it exits 0 on every path. Without Python it says so on stdout
# (session context), not as a hook error on stderr.

d=${BASH_SOURCE[0]%/*}
[ "$d" != "${BASH_SOURCE[0]}" ] || d=.
. "$d/py-run.sh"
if ! _pr_find; then
  printf 'sync-status: %s\n' "$_pr_nopy"
  exit 0
fi
_pr_found=1 _pr_call sync_status "$@"
exit 0
