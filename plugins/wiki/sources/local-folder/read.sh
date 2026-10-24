#!/usr/bin/env bash
# read.sh: read-only access to a local folder outside the wiki.
#
#   bash ~/src/wiki-tools/plugins/wiki/sources/local-folder/read.sh <key> list "<folder>"
#   bash ~/src/wiki-tools/plugins/wiki/sources/local-folder/read.sh <key> info "<path>"
#   bash ~/src/wiki-tools/plugins/wiki/sources/local-folder/read.sh <key> new  "<YYYY-MM-DD|never>"
#   bash ~/src/wiki-tools/plugins/wiki/sources/local-folder/read.sh <key> copy "<file>"
#
# Rules:
# - <key> is a local-folder instance in <wiki>/.claude/sources/instances/.
# - Paths must sit under one of the instance's roots.
# - Nothing under a root is ever changed. `copy` puts a copy in
#   ~/.cache/wiki-sources/<wiki>/<key>/<path below root>, where the ingest
#   skill reads it.
#
# Run it from inside a wiki (any directory of its git repo).

set -u

. "$(dirname "$0")/../../scripts/lib-source.sh"

die() { printf 'local-folder: %s\n' "$1" >&2; exit 1; }

[ $# -eq 3 ] || die "usage: read.sh <key> <list|info|new|copy> \"<path or date>\""
key=$1 op=$2 arg=$3

case "$op" in list|info|new|copy) ;; *) die "operation '$op' is not allowed; ops are: list info new copy" ;; esac

root=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
wiki=$(basename "$root")
printf '%s' "$key" | grep -Eq "$SRC_NAME_RE" || die "invalid instance key '$key'"
inst="$(src_instance_dir "$root")/$key.md"
[ -f "$inst" ] || die "no instance '$key' ($inst)."
[ "$(src_field "$inst" type)" = local-folder ] || die "instance '$key' is not a local-folder instance."
src_validate_instance "$root" "$key" 2>/dev/null || die "instance file $inst doesn't validate; run /wiki:init to check it."
roots=$(src_values "$inst" roots)

listing() { # FIND-ARGS...: "<type> <YYYY-MM-DD HH:MM> <bytes> <path>" per entry
  find "$@" -printf '%y %TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | LC_ALL=C sort -k4
}

if [ "$op" = new ]; then
  case "$arg" in
    never) since="" ;;
    *) printf '%s' "$arg" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' && date -d "$arg" >/dev/null 2>&1 ||
         die "date must be YYYY-MM-DD or never" ; since=$arg ;;
  esac
  printf '%s\n' "$roots" | while IFS= read -r r; do
    [ -n "$r" ] || continue
    r=$(src_expand "$r")
    [ -e "$r" ] || { printf 'local-folder: root %s does not exist\n' "$r" >&2; continue; }
    if [ -n "$since" ]; then listing "$r" -type f -newermt "$since"
    else listing "$r" -type f; fi
  done
  exit 0
fi

# list, info, copy: one path, checked against the roots.
src_is_abs "$arg" || die "path must be absolute"
! src_has_dots "$arg" || die "'.' and '..' are not allowed in paths."
path=$(src_expand "$arg")
matched=$(printf '%s\n' "$roots" | src_match_root "$path") || die "'$arg' is outside the roots of instance '$key'."
[ -e "$path" ] || die "'$path' does not exist."

case "$op" in
  list)
    [ -d "$path" ] || die "'$path' is not a folder; use info."
    listing "$path" -mindepth 1 -maxdepth 1
    ;;
  info)
    listing "$path" -maxdepth 0
    ;;
  copy)
    [ -f "$path" ] || die "'$path' is not a plain file; list folders and copy files one by one."
    if [ "$path" = "$matched" ]; then rel=$(basename "$path")
    else rel=${path#"$matched"/}; fi
    dest_dir="$HOME/.cache/wiki-sources/$wiki/$key"
    [ "$(dirname "$rel")" = . ] || dest_dir="$dest_dir/$(dirname "$rel")"
    mkdir -p "$dest_dir" || die "cannot create $dest_dir"
    cp -p -- "$path" "$dest_dir/" || die "copy failed"
    printf 'local-folder: copied to %s/%s\n' "$dest_dir" "$(basename "$rel")"
    ;;
esac
