#!/usr/bin/env bash
# save.sh: save the wiki's commits to its own remote, pinned in the
# committed .claude/settings.wiki.json.
#
#   bash <plugin>/scripts/save.sh                        integrate and push
#   bash <plugin>/scripts/save.sh --check                a dry run
#   bash <plugin>/scripts/save.sh --update               fetch and merge only
#   bash <plugin>/scripts/save.sh --unattended           push; paths that need
#                                                        permission go to a holding branch
#   bash <plugin>/scripts/save.sh --update --unattended  update, unless a holding branch waits
#   bash <plugin>/scripts/save.sh --allow <path>...      push with these permission paths
#
# Run from inside a wiki. Exit 0 done, 1 refused (`save: refused: ...` on
# stderr), 3 merge conflict left in progress (`conflict: <path>` lines).
#
# The work is in save.py (docs/adr.md, 4), which lists the checks; this
# launcher only runs it, with the plugin folder as bash spells it (for the
# --allow call it prints).

d=${BASH_SOURCE[0]%/*}
[ "$d" != "${BASH_SOURCE[0]}" ] || d=.
. "$d/py-run.sh"
_pr_label=save _pr_call save --plugin "$(cd "$d/.." && pwd)" "$@"
exit $?
