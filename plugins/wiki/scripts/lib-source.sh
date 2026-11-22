# lib-source.sh: read source instances, for the source wrappers.
# Source this file; it defines functions only. No jq, no YAML library: the
# frontmatter of SOURCE.md and instance files is flat `key: value` lines and
# `- item` lists (see templates/source-type/SOURCE.md).
#
# Layout:
#   standard types   <plugin>/sources/<type>/SOURCE.md
#   local types      <wiki>/.claude/sources/types/<type>/SOURCE.md
#   instances        <wiki>/.claude/sources/instances/<key>.md
#
# Functions print errors to stderr and return non-zero; callers decide
# whether that is fatal.
#
# What stays in bash (docs/adr.md, 4):
# what the wrappers (codebase/git.sh, gh.sh, local-folder/read.sh,
# decode-download.sh) and the wikis' local types use.
# /wiki:add-source names src_values, src_expand, src_match_root and
# src_has_dots for local type scripts and models them on read.sh, so keep
# all of these. The frontmatter parsers stay the bash reference for
# contract.py (tests: contract-parity). Everything else is in sourcelib.py.

# Builtins where it's cheap: every process start costs ~25 ms in Git Bash.
SRC_PLUGIN=${BASH_SOURCE[0]%/*}
[ "$SRC_PLUGIN" != "${BASH_SOURCE[0]}" ] || SRC_PLUGIN=.
SRC_PLUGIN=$(cd "$SRC_PLUGIN/.." && pwd)
SRC_SCRIPTS=$SRC_PLUGIN/scripts
SRC_NAME_RE='^[a-z0-9][a-z0-9-]*$'

# The bridge: src_validate_instance and
# src_codebase_instance run in sourcelib.py, one Python start each instead
# of hundreds of processes.
# Their edge cases are checked in the tests (lib-source-edge). py-run.sh is
# sourced here, at the first bridged call, not at the top: scripts that never
# call one pay nothing. --plugin always, since callers (the tests) may set
# SRC_PLUGIN after sourcing this file.
_src_py() {
  declare -F _pr_call >/dev/null || . "$SRC_SCRIPTS/py-run.sh"
  _pr_call sourcelib --plugin "$SRC_PLUGIN" "$@"
}

# src_fm FILE: the frontmatter lines, CRs stripped. Nothing if there is none.
src_fm() {
  awk '{ sub(/\r$/, "") }
       NR == 1 { if ($0 ~ /^---[[:space:]]*$/) { fm = 1; next } else exit }
       fm && /^---[[:space:]]*$/ { exit }
       fm { print }' "$1" 2>/dev/null
}

# src_has_fm FILE: true if FILE opens and closes a frontmatter block.
src_has_fm() {
  awk '{ sub(/\r$/, "") }
       NR == 1 { if ($0 !~ /^---[[:space:]]*$/) exit 1; next }
       /^---[[:space:]]*$/ { found = 1; exit }
       END { exit !found }' "$1" 2>/dev/null
}

# src_field FILE KEY: a scalar value ("" when empty or absent).
src_field() {
  case "$2" in *[!a-z_]*|'') return 1 ;; esac
  src_fm "$1" | sed -n "s/^$2:[[:space:]]*//p" | head -n 1 | sed 's/[[:space:]]*$//'
}

# src_list FILE KEY: the `- item` lines under KEY, one per line.
src_list() {
  src_fm "$1" | awk -v k="$2" '
    /^[A-Za-z_]+:/ { cur = $0; sub(/:.*/, "", cur); next }
    cur == k && /^[[:space:]]+-/ {
      s = $0; sub(/^[[:space:]]+-[[:space:]]*/, "", s); sub(/[[:space:]]+$/, "", s)
      if (s != "") print s
    }'
}

# src_values FILE KEY: a scalar value, or else the list items.
src_values() {
  local v
  v=$(src_field "$1" "$2")
  if [ -n "$v" ]; then printf '%s\n' "$v"; else src_list "$1" "$2"; fi
}

# src_wiki_root [DIR]: the git toplevel of DIR (default $PWD).
src_wiki_root() { git -C "${1:-$PWD}" rev-parse --show-toplevel 2>/dev/null; }

src_instance_dir() { printf '%s/.claude/sources/instances' "$1"; }

# src_expand PATH: "~/x" -> "$HOME/x"; backslashes -> slashes; repeated
# slashes folded; no trailing "/".
src_expand() {
  local p=${1//\\//}
  case "$p" in "~/"*) p="$HOME/${p#\~/}" ;; esac
  while [[ $p == *//* ]]; do p=${p//\/\///}; done
  [ "${#p}" -le 1 ] || p=${p%/}
  printf '%s' "$p"
}

# src_is_abs PATH: "/x", "~/x" or "C:/x".
src_is_abs() {
  case "$1" in /*|"~/"*) return 0 ;; esac
  printf '%s' "$1" | grep -Eq '^[A-Za-z]:[/\\]'
}

# src_has_dots PATH: true if a path segment is "." or "..".
src_has_dots() {
  case "/${1//\\//}/" in */./*|*/../*) return 0 ;; esac
  return 1
}

# src_match_root PATH: print the first root (stdin, one per line) that is
# PATH or a parent of it. PATH must already be expanded and normalised.
src_match_root() {
  local r
  while IFS= read -r r || [ -n "$r" ]; do
    r=${r%$'\r'}
    case "$r" in ''|\#*) continue ;; esac
    r=$(src_expand "$r")
    if [ "$1" = "$r" ] || case "$1" in "$r"/*) true ;; *) false ;; esac; then
      printf '%s\n' "$r"; return 0
    fi
  done
  return 1
}

# src_validate_instance ROOT KEY: check an instance file and its contract.
src_validate_instance() { _src_py validate-instance "$1" "$2"; }

# src_codebase_instance ROOT KEY: six lines for the codebase wrappers: type,
# 1|0 (src_validate_instance passes, messages dropped), the number of roots,
# the first root as written, ref, gh_user. One Python start for all of it.
src_codebase_instance() { _src_py codebase-instance "$1" "$2"; }
