#!/usr/bin/env bash
# snapshot.sh: compare a SharePoint folder walk with the previous one, and
# keep it for the next run. SharePoint folder listings carry no dates, so
# the ms-teams type finds new and changed files this way.
#
#   bash <plugin>/sources/ms-teams/snapshot.sh <key> compare
#   bash <plugin>/sources/ms-teams/snapshot.sh <key> save
#
# Files, in ~/.cache/wiki-sources/<wiki>/<key>/:
#   walk.tsv   this run's walk, written by Claude: one line per file,
#              URI <TAB> <folder label>/<path> <TAB> size in bytes
#   files.tsv  the snapshot of the last saved walk, same format
#
# compare  prints one line per file that differs, keyed on the URI:
#            new<TAB><path><TAB><size>
#            changed<TAB><path><TAB><size> (was <old size>)
#            moved<TAB><path><TAB>from <old path>
#            removed<TAB><old path><TAB><old size>
#          then a summary line. It changes nothing.
# save     replaces files.tsv with walk.tsv and removes walk.tsv.
#
# Rules:
# - <key> is an ms-teams instance in <wiki>/.claude/sources/instances/.
# - Nothing outside that cache folder is read or written; the connector is
#   never called.
#
# Run it from inside a wiki (any directory of its git repo).

set -u
#
# The work is in snapshot.py (docs/adr.md, 4); this launcher only
# runs it.

d=${BASH_SOURCE[0]%/*}
[ "$d" != "${BASH_SOURCE[0]}" ] || d=.
. "$d/../../scripts/py-run.sh"
_pr_dir=$d _pr_label="ms-teams snapshot" _pr_call snapshot "$@"
exit $?
