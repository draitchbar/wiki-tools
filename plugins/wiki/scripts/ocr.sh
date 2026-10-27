#!/usr/bin/env bash
# ocr.sh: give a scanned (image-only) PDF a Danish text layer.
#
#   bash <plugin>/scripts/ocr.sh "<local pdf>"
#
# Writes only <wiki>/raw/ocr/<name>.txt (the OCR sidecar text). The source PDF
# is never modified. Linux only: needs `ocrmypdf` and `tesseract-ocr-dan`.
# On Windows, read the PDF's pages as images with the Read tool instead.

set -u

die() { printf 'ocr: %s\n' "$1" >&2; exit 1; }

[ $# -eq 1 ] || die "usage: ocr.sh \"<local pdf>\""
pdf=$1
[ -f "$pdf" ] || die "no such file: $pdf"

command -v ocrmypdf >/dev/null 2>&1 || die "ocrmypdf not installed (Linux: sudo apt install ocrmypdf tesseract-ocr-dan). On Windows, read the pages as images instead."

root=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null) || die "not inside a git repo; run from a wiki."
name=$(basename "$pdf")
name=${name%.*}
out_dir="$root/raw/ocr"
mkdir -p "$out_dir" || die "cannot create $out_dir"
sidecar="$out_dir/$name.txt"

tmp=$(mktemp "${TMPDIR:-/tmp}/ocr.XXXXXX.pdf") || die "cannot create temp file"
trap 'rm -f "$tmp"' EXIT

# --skip-text leaves pages that already have text alone; dan+eng covers
# Danish documents with English terms.
ocrmypdf --quiet -l dan+eng --skip-text --sidecar "$sidecar" "$pdf" "$tmp" ||
  die "ocrmypdf failed on $pdf"

printf 'ocr: wrote %s\n' "$sidecar"
