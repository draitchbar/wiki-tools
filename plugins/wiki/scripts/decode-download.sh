#!/usr/bin/env bash
# decode-download.sh: turn a base64 download (e.g. Google Drive's
# download_file_content) into a file in the wiki's source cache.
#
#   bash <plugin>/scripts/decode-download.sh <key> "<input file>" "<path below the folder>"
#
# <input file> is either a file of plain base64 (written with Write), or a
# tool result Claude Code saved to disk because it was too large (JSON with
# a "content" field, possibly nested and escaped). The decoded file goes to
# ~/.cache/wiki-sources/<wiki>/<key>/<path below the folder>, never anywhere
# else, and is overwritten if it exists.
#
# Run it from inside a wiki (any directory of its git repo).

set -u

. "$(dirname "$0")/lib-source.sh"

die() { printf 'decode-download: %s\n' "$1" >&2; exit 1; }

[ $# -eq 3 ] || die "usage: decode-download.sh <key> \"<input file>\" \"<path below the folder>\""
key=$1 input=$2 rel=$3

root=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
printf '%s' "$key" | grep -Eq "$SRC_NAME_RE" || die "invalid instance key '$key'"
[ -f "$(src_instance_dir "$root")/$key.md" ] || die "no instance '$key' in this wiki."
[ -f "$input" ] || die "no input file '$input'"

rel=$(printf '%s' "$rel" | tr '\\' '/' | sed -e 's#//*#/#g' -e 's#^\./##')
case "$rel" in /*|[A-Za-z]:*|'') die "the target must be a relative path below the source folder, e.g. 'Projects/plan.drawio'." ;; esac
! src_has_dots "/$rel" || die "'.' and '..' are not allowed in the target path."

# The base64 text: the longest "content" value in a saved tool result, or
# the whole file. Base64 has no backslashes, so removing them undoes JSON
# escaping (\/ and the \" of a nested result).
if grep -q 'content\\*"[[:space:]]*:[[:space:]]*\\*"' "$input"; then
  b64=$(grep -o 'content\\*"[[:space:]]*:[[:space:]]*\\*"[A-Za-z0-9+/=\\]*' "$input" |
    sed 's/^content\\*"[[:space:]]*:[[:space:]]*\\*"//' | tr -d '\\' |
    awk '{ if (length($0) > length(best)) best = $0 } END { print best }')
else
  b64=$(tr -d ' \t\r\n' < "$input")
fi
[ -n "$b64" ] || die "no base64 content found in '$input'."
printf '%s' "$b64" | grep -q '^[A-Za-z0-9+/]*=*$' || die "'$input' isn't base64 (or a saved result with a \"content\" field)."

dest="$HOME/.cache/wiki-sources/$(basename "$root")/$key/$rel"
mkdir -p "$(dirname "$dest")" || die "cannot create $(dirname "$dest")"
printf '%s' "$b64" | base64 -d > "$dest" 2>/dev/null || { rm -f "$dest"; die "base64 decoding failed for '$input'."; }
printf 'decode-download: wrote %s (%s bytes)\n' "$dest" "$(wc -c < "$dest" | tr -d ' ')"
