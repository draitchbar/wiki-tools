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

. "$(dirname "$0")/../../scripts/lib-source.sh"

die() { printf 'ms-teams snapshot: %s\n' "$1" >&2; exit 1; }

[ $# -eq 2 ] || die "usage: snapshot.sh <key> <compare|save>"
key=$1 op=$2

case "$op" in compare|save) ;; *) die "operation '$op' is not allowed; ops are: compare save" ;; esac

root=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
wiki=$(basename "$root")
printf '%s' "$key" | grep -Eq "$SRC_NAME_RE" || die "invalid instance key '$key'"
inst="$(src_instance_dir "$root")/$key.md"
[ -f "$inst" ] || die "no instance '$key' ($inst)."
[ "$(src_field "$inst" type)" = ms-teams ] || die "instance '$key' is not an ms-teams instance."
src_validate_instance "$root" "$key" 2>/dev/null || die "instance file $inst doesn't validate; run /wiki:init to check it."

dir="$HOME/.cache/wiki-sources/$wiki/$key"
walk="$dir/walk.tsv" snap="$dir/files.tsv"
[ -f "$walk" ] || die "no walk file $walk; write this run's folder walk there first."

tmp=$(mktemp -d) || die "cannot create a temp dir"
trap 'rm -rf "$tmp"' EXIT

# clean NAME FILE OUT: drop CRs and blank lines, check each line is
# URI<TAB>path<TAB>size and no URI repeats.
clean() {
  tr -d '\r' < "$2" | grep -v '^[[:space:]]*$' > "$3"
  awk -F'\t' -v name="$1" '
    NF != 3 || $1 == "" || $2 == "" || $3 !~ /^[0-9]+$/ {
      printf "%s line %d is not URI<TAB>path<TAB>size: %s\n", name, NR, $0; bad = 1; next }
    seen[$1]++ { printf "%s line %d repeats URI %s\n", name, NR, $1; bad = 1 }
    END { exit bad }' "$3" >&2
}

clean walk.tsv "$walk" "$tmp/walk" || die "fix $walk and run it again."
nwalk=$(wc -l < "$tmp/walk" | tr -d ' ')
[ "$nwalk" -gt 0 ] || printf 'ms-teams snapshot: WARNING: walk.tsv is empty; a failed listing is more likely than an emptied library. Check the walk before saving.\n'

case "$op" in
  compare)
    if [ -f "$snap" ]; then
      clean files.tsv "$snap" "$tmp/snap" || die "$snap is malformed; delete it to start over (every file then counts as new)."
    else
      : > "$tmp/snap"
      printf 'ms-teams snapshot: no files.tsv yet; every file is new.\n'
    fi
    # FILENAME, not FNR == NR: the snapshot may be empty.
    awk -F'\t' -v OFS='\t' -v snapf="$tmp/snap" '
      FILENAME == snapf { opath[$1] = $2; osize[$1] = $3; next }
      { seen[$1] = 1 }
      !($1 in opath)     { print "new", $2, $3; n++; next }
      $3 != osize[$1]    { print "changed", $2, $3 " (was " osize[$1] ")"; c++; next }
      $2 != opath[$1]    { print "moved", $2, "from " opath[$1]; m++; next }
      { u++ }
      END {
        for (k in opath) if (!(k in seen)) { print "removed", opath[k], osize[k]; r++ }
        printf "summary: %d new, %d changed, %d moved, %d removed, %d unchanged\n", n, c, m, r, u > "/dev/stderr"
      }' "$tmp/snap" "$tmp/walk" > "$tmp/out" 2> "$tmp/summary"
    LC_ALL=C sort -t "$(printf '\t')" -k2,2 "$tmp/out"
    sed 's/^/ms-teams snapshot: /' "$tmp/summary"
    ;;
  save)
    cp "$tmp/walk" "$snap.new" && mv "$snap.new" "$snap" || die "cannot write $snap"
    rm -f "$walk"
    printf 'ms-teams snapshot: saved %s files to %s\n' "$nwalk" "$snap"
    ;;
esac
