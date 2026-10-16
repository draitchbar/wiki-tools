#!/usr/bin/env bash
# pd-read.sh: read-only access to Proton Drive for the wiki skills.
#
#   bash ~/src/wiki-tools/plugins/wiki/scripts/pd-read.sh list     "<remote path>"
#   bash ~/src/wiki-tools/plugins/wiki/scripts/pd-read.sh info     "<remote path>"
#   bash ~/src/wiki-tools/plugins/wiki/scripts/pd-read.sh download "<remote file>"
#
# Rules:
# - Only the read operations in READ_OPS are passed to the CLI.
# - Remote paths must sit under a line of <wiki>/.claude/proton-roots.
# - Downloads always go to ~/.cache/wiki-sources/<wiki>/proton/<path below root>.
# - The CLI version must equal PINNED_VERSION, so a CLI update forces a review.
#
# Run it from inside a wiki (any directory of its git repo).
#
# SETUP (plan step 5.0): run `proton-drive version`,
# `proton-drive filesystem --help` and `proton-drive filesystem download --help`
# by hand, paste them into README.md, then set PINNED_VERSION and check that
# READ_OPS and the download call below match the recorded syntax. Until
# PINNED_VERSION is set, the wrapper refuses everything.

set -u

PINNED_VERSION=""            # e.g. "0.8.0", copied from `proton-drive version`
READ_OPS="list info"         # plus "download", handled separately below
CLI=proton-drive

die() { printf 'pd-read: %s\n' "$1" >&2; exit 1; }

[ $# -eq 2 ] || die "usage: pd-read.sh <list|info|download> \"<remote path>\""
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

# 4. CLI present and at the pinned version.
command -v "$CLI" >/dev/null 2>&1 || die "'$CLI' not found on PATH."
[ -n "$PINNED_VERSION" ] || die "PINNED_VERSION is not set. Record the CLI help in README.md (plan step 5.0) first."
have=$("$CLI" version 2>/dev/null | head -n 1)
case "$have" in
  *"$PINNED_VERSION"*) ;;
  *) die "CLI version '$have' differs from pinned '$PINNED_VERSION'. Re-record the help output in README.md and update the wrapper." ;;
esac

export PROTON_DRIVE_LOG_LEVEL=WARNING

# 5. Run. Nothing from the caller is passed through except the checked path.
case "$op" in
  list|info)
    exec "$CLI" filesystem "$op" --json "$remote"
    ;;
  download)
    [ "$remote" != "$matched_root" ] || die "download takes a single file, not a root folder; list it and download files one by one."
    rel=${remote#"$matched_root"/}
    dest_dir="$HOME/.cache/wiki-sources/$wiki/proton/$(dirname "$rel")"
    mkdir -p "$dest_dir" || die "cannot create $dest_dir"
    # Argument order (remote, then local folder) as in Proton's support example;
    # confirm against the recorded `filesystem download --help` (step 5.0).
    "$CLI" filesystem download --json "$remote" "$dest_dir" || exit $?
    printf 'pd-read: downloaded to %s/%s\n' "$dest_dir" "$(basename "$rel")"
    ;;
esac
