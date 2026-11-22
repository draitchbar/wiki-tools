#!/usr/bin/env bash
# file-snapshot.sh: compare a folder walk with the previous one, and keep
# it for the next run. For a tool-neutral source (access: tools) whose
# reader lists a folder without modified times, this is how new and
# changed files are found; a reader that gives modified times doesn't
# need it.
#
#   bash <plugin>/scripts/file-snapshot.sh <key> compare
#   bash <plugin>/scripts/file-snapshot.sh <key> save
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
# - <key> is an instance in <wiki>/.claude/sources/instances/ whose type
#   (standard or local) is access: tools.
# - Nothing outside that cache folder is read or written; the reader is
#   never called.
#
# Run it from inside a wiki (any directory of its git repo).

set -u
#
# The work is in file_snapshot.py (docs/adr.md, 4); this launcher only
# runs it.

d=${BASH_SOURCE[0]%/*}
[ "$d" != "${BASH_SOURCE[0]}" ] || d=.
. "$d/py-run.sh"
_pr_label=file-snapshot _pr_call file_snapshot "$@"
exit $?
