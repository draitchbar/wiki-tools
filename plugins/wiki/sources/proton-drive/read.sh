#!/usr/bin/env bash
# read.sh: read-only access to Proton Drive for the wiki skills.
#
#   bash ~/src/wiki-tools/plugins/wiki/sources/proton-drive/read.sh <key> list     "<remote path>"
#   bash ~/src/wiki-tools/plugins/wiki/sources/proton-drive/read.sh <key> info     "<remote path>"
#   bash ~/src/wiki-tools/plugins/wiki/sources/proton-drive/read.sh <key> size     "<remote path>"
#   bash ~/src/wiki-tools/plugins/wiki/sources/proton-drive/read.sh <key> download "<remote file>"
#
# Rules:
# - <key> is a proton-drive instance in <wiki>/.claude/sources/instances/.
#   Until a wiki is migrated, key "proton" without an instance file falls
#   back to the old <wiki>/.claude/proton-roots.
# - Only the read operations in READ_OPS are passed to the CLI.
# - Remote paths must sit under one of the instance's roots.
# - Downloads always go to ~/.cache/wiki-sources/<wiki>/<key>/<path below root>.
# - No version pin: any CLI version works as long as its help output still
#   shows the syntax this wrapper relies on (check_syntax below). If Proton
#   changes that syntax, the wrapper refuses until it is reviewed.
#
# Run it from inside a wiki (any directory of its git repo).
# The syntax was recorded in README.md from cli-drive@0.9.0 (16.10.2026).

set -u

. "$(dirname "$0")/../../scripts/lib-source.sh"

READ_OPS="list info size"    # plus "download", handled separately below
CLI=proton-drive

die() { printf 'pd-read: %s\n' "$1" >&2; exit 1; }

[ $# -eq 3 ] || die "usage: read.sh <key> <list|info|size|download> \"<remote path>\""
key=$1
op=$2
remote=$3

# 1. Operation allowlist (checked before anything touches the CLI).
case " $READ_OPS download " in
  *" $op "*) ;;
  *) die "operation '$op' is not allowed; read-only ops are: $READ_OPS download" ;;
esac

# 2. Wiki root and the instance's roots.
root=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
wiki=$(basename "$root")
printf '%s' "$key" | grep -Eq "$SRC_NAME_RE" || die "invalid instance key '$key'"
inst="$(src_instance_dir "$root")/$key.md"
if [ -f "$inst" ]; then
  [ "$(src_field "$inst" type)" = proton-drive ] || die "instance '$key' is not a proton-drive instance."
  src_validate_instance "$root" "$key" 2>/dev/null || die "instance file $inst doesn't validate; run /wiki:init to check it."
  roots=$(src_values "$inst" roots)
  where=$inst
elif [ "$key" = proton ] && [ -f "$root/.claude/proton-roots" ]; then
  roots=$(cat "$root/.claude/proton-roots")      # old layout, until migrated
  where="$root/.claude/proton-roots"
else
  die "no instance '$key' ($inst); this wiki has no such Proton access."
fi

# 3. Normalise and check the remote path.
case "$remote" in /*) ;; *) die "remote path must be absolute, e.g. /my-files/..." ;; esac
remote=$(printf '%s' "$remote" | sed -e 's#//*#/#g' -e 's#/$##')
! src_has_dots "$remote" || die "'.' and '..' are not allowed in remote paths."
matched_root=$(printf '%s\n' "$roots" | src_match_root "$remote") ||
  die "'$remote' is outside the Proton roots of '$key' ($where)."

# 4. CLI present and still speaking the syntax this wrapper was written for.
command -v "$CLI" >/dev/null 2>&1 || die "'$CLI' not found on PATH."

check_syntax() { # TEXT EXPECTED...
  text=$1; shift
  for want in "$@"; do
    case "$text" in
      *"$want"*) ;;
      *) die "proton-drive syntax changed (missing '$want'). Re-record the help output in README.md and review read.sh before using it." ;;
    esac
  done
}
check_syntax "$("$CLI" filesystem --help 2>&1)" \
  "filesystem list [-t TYPE] path" "filesystem info path" "filesystem size path"
if [ "$op" = download ]; then
  check_syntax "$("$CLI" filesystem download --help 2>&1)" \
    "filesystem download [-f STRATEGY] [-d STRATEGY] path... localFolder" \
    "--file-conflict-strategy" "remove:"
fi

export PROTON_DRIVE_LOG_LEVEL=WARNING

# 5. Run. Nothing from the caller is passed through except the checked path.
case "$op" in
  list|info|size)
    exec "$CLI" filesystem "$op" --json "$remote"
    ;;
  download)
    # Single files only: `info --json` reports one top-level "type"
    # ("file" or "folder"); folders have no activeRevision to mimic it.
    node=$("$CLI" filesystem info --json "$remote" 2>&1) || die "cannot read info for '$remote': $node"
    case "$node" in
      *'"type":"folder"'*) die "'$remote' is a folder; list it and download its files one by one." ;;
      *'"type":"file"'*) ;;
      *) die "'$remote' is not a plain file (info: $(printf '%s' "$node" | head -c 200))" ;;
    esac
    if [ "$remote" = "$matched_root" ]; then
      rel=$(basename "$remote")          # the root line names a single file
    else
      rel=${remote#"$matched_root"/}
    fi
    dest_dir="$HOME/.cache/wiki-sources/$wiki/$key"
    [ "$(dirname "$rel")" = . ] || dest_dir="$dest_dir/$(dirname "$rel")"
    mkdir -p "$dest_dir" || die "cannot create $dest_dir"
    # Recorded syntax: download [-f STRATEGY] [-d STRATEGY] path... localFolder.
    # Conflict strategies are always set, because a prompt would hang a
    # non-interactive call: -f remove replaces a stale copy in the cache
    # (local only), -d merge merges a folder into its cached copy.
    "$CLI" filesystem download --json -f remove -d merge "$remote" "$dest_dir" || exit $?
    printf 'pd-read: downloaded to %s/%s\n' "$dest_dir" "$(basename "$rel")"
    ;;
esac
