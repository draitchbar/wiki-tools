#!/usr/bin/env bash
# sources.sh: read-only view of a wiki's sources for the wiki skills.
#
#   bash <plugin>/scripts/sources.sh list
#   bash <plugin>/scripts/sources.sh show <key>
#   bash <plugin>/scripts/sources.sh catalog
#   bash <plugin>/scripts/sources.sh contract <type>
#   bash <plugin>/scripts/sources.sh settings [<type>... [--key <key>]]
#   bash <plugin>/scripts/sources.sh check-settings
#
# list      the wiki's instances: key, type, standard/local, platform, state
# show      one instance: checks, its instance file and its type's contract
# catalog   every source type this wiki can use (standard and local)
# contract  one type's SOURCE.md
# settings  the permission rules (allow, deny) for the given types, or for
#           all instances. Cache rules (~/.cache/wiki-sources/...) are
#           narrowed to <wiki>/<key>/ per instance, or for --key <key>.
# check-settings  .claude/settings.json: well-formed JSON, the rules the
#           instances need, duplicates, rules in both allow and deny, and
#           broad cache rules. Exit 1 on a problem other than the last.
#
# Run it from inside a wiki (any directory of its git repo). Writes nothing.
#
# The work is in sources.py (docs/adr.md, 4); this launcher only
# runs it. The plugin folder goes over as bash spells it (/c/... in Git
# Bash), so messages and filled-in contracts read as before; Python opens
# files through its native form. No program starts but Python (the plugin
# folder costs one subshell).

d=${BASH_SOURCE[0]%/*}
[ "$d" != "${BASH_SOURCE[0]}" ] || d=.
. "$d/py-run.sh"
_pr_call sources --plugin "$(cd "$d/.." && pwd)" "$@"
exit $?
