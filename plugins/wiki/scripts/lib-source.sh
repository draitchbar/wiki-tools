# lib-source.sh: read source-type contracts and source instances.
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

SRC_PLUGIN=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SRC_NAME_RE='^[a-z0-9][a-z0-9-]*$'

src_err() { printf '%s\n' "$1" >&2; }

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

# src_names: first word of each stdin line, up to a space, "(" or ":".
src_names() { sed -e 's/[[:space:](:].*//' | grep -v '^$'; }

src_platform() {
  case "$(uname -s)" in
    Linux*) echo linux ;;
    MINGW*|MSYS*|CYGWIN*) echo windows ;;
    Darwin*) echo macos ;;
    *) uname -s | tr '[:upper:]' '[:lower:]' ;;
  esac
}

# src_wiki_root [DIR]: the git toplevel of DIR (default $PWD).
src_wiki_root() { git -C "${1:-$PWD}" rev-parse --show-toplevel 2>/dev/null; }

src_instance_dir() { printf '%s/.claude/sources/instances' "$1"; }

# src_instances ROOT: the instance keys of a wiki, sorted.
src_instances() {
  local d f b
  d=$(src_instance_dir "$1")
  [ -d "$d" ] || return 0
  for f in "$d"/*.md; do
    [ -f "$f" ] || continue
    b=${f##*/}; printf '%s\n' "${b%.md}"
  done | LC_ALL=C sort
}

# src_contract ROOT TYPE: path of the type's SOURCE.md.
# A local type may not shadow a standard one.
src_contract() {
  local t=$2 std loc
  printf '%s' "$t" | grep -Eq "$SRC_NAME_RE" || { src_err "invalid source type name '$t'"; return 1; }
  std="$SRC_PLUGIN/sources/$t/SOURCE.md"
  loc="$1/.claude/sources/types/$t/SOURCE.md"
  if [ -f "$std" ] && [ -f "$loc" ]; then
    src_err "local type '$t' ($loc) shadows the standard type of the same name; rename it"
    return 1
  fi
  if [ -f "$std" ]; then printf '%s\n' "$std"
  elif [ -f "$loc" ]; then printf '%s\n' "$loc"
  else src_err "unknown source type '$t' (no standard type and no $loc)"; return 1
  fi
}

# src_catalog ROOT: "<type><TAB>standard|local<TAB><title>" for every type.
src_catalog() {
  local f t kind
  for f in "$SRC_PLUGIN"/sources/*/SOURCE.md "$1"/.claude/sources/types/*/SOURCE.md; do
    [ -f "$f" ] || continue
    t=${f%/SOURCE.md}; t=${t##*/}
    case "$f" in "$SRC_PLUGIN"/*) kind=standard ;; *) kind=local ;; esac
    printf '%s\t%s\t%s\n' "$t" "$kind" "$(src_field "$f" title)"
  done
}

# src_expand PATH: "~/x" -> "$HOME/x"; backslashes -> slashes; no trailing "/".
src_expand() {
  local p
  p=$(printf '%s' "$1" | tr '\\' '/')
  case "$p" in "~/"*) p="$HOME/${p#\~/}" ;; esac
  printf '%s' "$p" | sed -e 's#//*#/#g' -e 's#\(.\)/$#\1#'
}

# src_is_abs PATH: "/x", "~/x" or "C:/x".
src_is_abs() {
  case "$1" in /*|"~/"*) return 0 ;; esac
  printf '%s' "$1" | grep -Eq '^[A-Za-z]:[/\\]'
}

# src_has_dots PATH: true if a path segment is "." or "..".
src_has_dots() {
  case "/$(printf '%s' "$1" | tr '\\' '/')/" in */./*|*/../*) return 0 ;; esac
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

# src_validate_contract FILE: check a SOURCE.md; prints one error per line.
src_validate_contract() {
  local f=$1 bad=0 k t dir p x s
  _src_ce() { src_err "$f: $1"; bad=1; }
  src_has_fm "$f" || { src_err "$f: no frontmatter block"; return 1; }
  for k in type title access cite_prefix; do
    [ -n "$(src_field "$f" "$k")" ] || _src_ce "missing '$k'"
  done
  t=$(src_field "$f" type)
  dir=${f%/SOURCE.md}
  [ "$t" = "${dir##*/}" ] || _src_ce "type '$t' doesn't match its folder '${dir##*/}'"
  case "$(src_field "$f" access)" in mcp|script|filesystem|'') ;; *) _src_ce "access must be mcp, script or filesystem" ;; esac
  p=$(src_list "$f" platforms)
  [ -n "$p" ] || _src_ce "no platforms listed"
  for x in $p; do case "$x" in linux|windows|macos) ;; *) _src_ce "unknown platform '$x'" ;; esac; done
  src_list "$f" state | src_names | grep -qx last_checked || _src_ce "state must include last_checked"
  for s in $(src_list "$f" scripts); do
    printf '%s' "$s" | grep -Eq '^[A-Za-z0-9_-]+\.sh$' || { _src_ce "script name '$s' must be a plain <name>.sh"; continue; }
    [ -f "$dir/$s" ] || _src_ce "script '$s' is listed but missing"
  done
  return $bad
}

# src_validate_instance ROOT KEY: check an instance file and its contract.
src_validate_instance() {
  local root=$1 k=$2 bad=0 f t c p r
  f="$(src_instance_dir "$root")/$k.md"
  _src_ie() { src_err "$f: $1"; bad=1; }
  [ -f "$f" ] || { src_err "no instance file $f"; return 1; }
  src_has_fm "$f" || { src_err "$f: no frontmatter block"; return 1; }
  printf '%s' "$k" | grep -Eq "$SRC_NAME_RE" || _src_ie "key must be kebab-case"
  [ "$k" != raw ] || _src_ie "'raw' is built in and can't be an instance"
  [ "$(src_field "$f" key)" = "$k" ] || _src_ie "key '$(src_field "$f" key)' doesn't match the file name"
  t=$(src_field "$f" type)
  [ -n "$t" ] || { _src_ie "missing 'type'"; return 1; }
  c=$(src_contract "$root" "$t") || { bad=1; return 1; }
  src_validate_contract "$c" || bad=1
  for p in $(src_list "$c" parameters | grep -F '(required)' | src_names); do
    [ -n "$(src_values "$f" "$p")" ] || _src_ie "required parameter '$p' is empty"
  done
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    src_is_abs "$r" || _src_ie "root '$r' isn't an absolute path"
    ! src_has_dots "$r" || _src_ie "root '$r' contains '.' or '..'"
  done <<EOF
$(src_values "$f" roots)
EOF
  return $bad
}
