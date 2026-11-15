#!/usr/bin/env bash
# lint.sh: deterministic health checks for a raw/wiki-layout wiki.
#
#   bash <plugin>/scripts/lint.sh
#
# Run from inside a wiki (any directory of its git repo). Read-only: prints a
# Markdown findings report to stdout and writes nothing. No LLM involved; the
# /wiki:lint skill adds the judgement checks (contradictions, missing
# cross-references) on top of this output. The checks are listed in lint.py.
#
# Environment (for tests): WIKI_LINT_TODAY=YYYY-MM-DD overrides today's date.
#
# The work is in lint.py (docs/adr.md, 4); this launcher only runs
# it. No program starts but Python.

d=${BASH_SOURCE[0]%/*}
[ "$d" != "${BASH_SOURCE[0]}" ] || d=.
. "$d/py-run.sh"
_pr_call lint "$@"
exit $?
