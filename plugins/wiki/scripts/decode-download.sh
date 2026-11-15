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
#
# The decoding is in decode_download.py (docs/adr.md, 4); this
# script keeps the checks and the paths, which stay in the form the caller
# gave them, and hands Python their native forms.

set -u

d=${BASH_SOURCE[0]%/*}
[ "$d" != "${BASH_SOURCE[0]}" ] || d=.
. "$d/lib-source.sh"
. "$d/py-run.sh"

die() { printf 'decode-download: %s\n' "$1" >&2; exit 1; }

[ $# -eq 3 ] || die "usage: decode-download.sh <key> \"<input file>\" \"<path below the folder>\""
key=$1 input=$2 rel=$3

root=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
[[ $key =~ $SRC_NAME_RE ]] || die "invalid instance key '$key'"
[ -f "$(src_instance_dir "$root")/$key.md" ] || die "no instance '$key' in this wiki."
[ -f "$input" ] || die "no input file '$input'"

rel=${rel//\\//}
while [[ $rel == *//* ]]; do rel=${rel//\/\///}; done
rel=${rel#./}
case "$rel" in /*|[A-Za-z]:*|'') die "the target must be a relative path below the source folder, e.g. 'Projects/plan.drawio'." ;; esac
! src_has_dots "/$rel" || die "'.' and '..' are not allowed in the target path."

dest="$HOME/.cache/wiki-sources/${root##*/}/$key/$rel"
mkdir -p "${dest%/*}" || die "cannot create ${dest%/*}"
_pr_native "$input"; nin=$_pr_nat
_pr_native "$dest"; ndest=$_pr_nat
_pr_label=decode-download
n=$(_pr_call decode_download "$nin" "$ndest")
case $? in
  0) printf 'decode-download: wrote %s (%s bytes)\n' "$dest" "$n" ;;
  4) die "no base64 content found in '$input'." ;;
  5) die "'$input' isn't base64 (or a saved result with a \"content\" field)." ;;
  6) die "base64 decoding failed for '$input'." ;;
  *) exit 1 ;;
esac
