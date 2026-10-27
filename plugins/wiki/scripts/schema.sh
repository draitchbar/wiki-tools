#!/usr/bin/env bash
# Print one file of the shared wiki schema (schema/<name>.md of this
# plugin), with ${CLAUDE_PLUGIN_ROOT} filled in.
#
#   bash <plugin>/scripts/schema.sh wiki-conventions|wiki-layout
#
# Runs as SessionStart hooks, one per file, on every start, resume, /clear
# and compaction (stdout becomes session context), so a wiki needs no
# CLAUDE.md import and no fixed clone path. Claude Code caps each hook's
# context at 10,000 characters; tests/run-tests.sh keeps each file's output
# under 9,000 bytes, with a long plugin path filled in.
# Read-only.
#
# Environment (for tests only): WIKI_SCHEMA_ROOT replaces the plugin path
# that is filled in.

case "${1:-}" in
  wiki-conventions|wiki-layout) ;;
  *) printf 'schema: usage: schema.sh wiki-conventions|wiki-layout\n' >&2; exit 1 ;;
esac
here=$(cd "$(dirname "$0")/.." && pwd)
root=${WIKI_SCHEMA_ROOT:-$here}
printf '# Shared wiki schema: %s (loaded by the wiki plugin)\n\n' "$1"
tr -d '\r' < "$here/schema/$1.md" | sed "s#\${CLAUDE_PLUGIN_ROOT}#$root#g"
