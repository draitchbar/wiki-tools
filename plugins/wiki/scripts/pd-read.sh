#!/usr/bin/env bash
# pd-read.sh: read-only access to Proton Drive for the wiki skills.
#
#   bash ~/src/wiki-tools/plugins/wiki/scripts/pd-read.sh list     "<remote path>"
#   bash ~/src/wiki-tools/plugins/wiki/scripts/pd-read.sh info     "<remote path>"
#   bash ~/src/wiki-tools/plugins/wiki/scripts/pd-read.sh size     "<remote path>"
#   bash ~/src/wiki-tools/plugins/wiki/scripts/pd-read.sh download "<remote file>"
#
# Rules:
# - Only the read operations in READ_OPS are passed to the CLI.
# - Remote paths must sit under a line of <wiki>/.claude/proton-roots.
# - Downloads always go to ~/.cache/wiki-sources/<wiki>/proton/<path below root>.
# - No version pin: any CLI version works as long as its help output still
#   shows the syntax this wrapper relies on (check_syntax below). If Proton
#   changes that syntax, the wrapper refuses until it is reviewed.
#
# Run it from inside a wiki (any directory of its git repo).
# The syntax was recorded in README.md from cli-drive@0.9.0 (16.10.2026).

set -u

READ_OPS="list info size"    # plus "download", handled separately below
CLI=proton-drive

die() { printf 'pd-read: %s\n' "$1" >&2; exit 1; }

[ $# -eq 2 ] || die "usage: pd-read.sh <list|info|size|download> \"<remote path>\""
op=$1
remote=$2

# 1. Operation allowlist (checked before anything touches the CLI).
case " $READ_OPS download " in
  *" $op "*) ;;
  *) die "operation '$op' is not allowed; read-only ops are: $READ_OPS download" ;;
esac

# 2. Wiki root and its Proton roots.
root=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null) || die "not inside a git repo; run from a wiki."
roots_file="$root/.claude/proton-roots"
[ -f "$roots_file" ] || die "no .claude/proton-roots in $root; this wiki has no Proton access."
wiki=$(basename "$root")

# 3. Normalise and check the remote path.
case "$remote" in /*) ;; *) die "remote path must be absolute, e.g. /my-files/..." ;; esac
remote=$(printf '%s' "$remote" | sed -e 's#//*#/#g' -e 's#/$##')
case "/$remote/" in
  */./*|*/../*) die "'.' and '..' are not allowed in remote paths." ;;
esac

matched_root=""
while IFS= read -r r || [ -n "$r" ]; do
  r=${r%$'\r'}
  r=$(printf '%s' "$r" | sed -e 's#//*#/#g' -e 's#/$##')
  case "$r" in ''|\#*) continue ;; esac
  if [ "$remote" = "$r" ] || case "$remote" in "$r"/*) true ;; *) false ;; esac; then
    matched_root=$r
    break
  fi
done < "$roots_file"
[ -n "$matched_root" ] || die "'$remote' is outside this wiki's Proton roots ($roots_file)."

# 4. CLI present and still speaking the syntax this wrapper was written for.
command -v "$CLI" >/dev/null 2>&1 || die "'$CLI' not found on PATH."

check_syntax() { # TEXT EXPECTED...
  text=$1; shift
  for want in "$@"; do
    case "$text" in
      *"$want"*) ;;
      *) die "proton-drive syntax changed (missing '$want'). Re-record the help output in README.md and review pd-read.sh before using it." ;;
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
    dest_dir="$HOME/.cache/wiki-sources/$wiki/proton"
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
