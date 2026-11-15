#!/usr/bin/env bash
# wiki-check.sh: read-only setup check for a raw/wiki-layout wiki.
#
#   bash <plugin>/scripts/wiki-check.sh
#
# Run from inside a wiki (any directory of its git repo). Used by /wiki:init
# in check mode. Prints a Markdown pass/fail list with a fix for each failure
# and writes nothing. Makes no calls to any source; sources are
# checked at their first ingest.
#
# Exit 0 when every check passes, 1 when any check fails.
#
# Environment (for tests): WIKI_CHECK_TEMPLATE overrides the settings
# template path; CLAUDE_CONFIG_DIR (as in Claude Code) moves ~/.claude.
#
# The work is in wiki_check.py (docs/adr.md, 4); this launcher only
# runs it. Without Python it prints the launcher's message (no Python 3.9 or
# later found, and the fix) instead of a report, and exits 1. The plugin
# folder goes over as bash spells it, for the messages (one subshell).

d=${BASH_SOURCE[0]%/*}
[ "$d" != "${BASH_SOURCE[0]}" ] || d=.
. "$d/py-run.sh"
_pr_label=wiki-check _pr_call wiki_check --plugin "$(cd "$d/.." && pwd)" "$@"
exit $?
