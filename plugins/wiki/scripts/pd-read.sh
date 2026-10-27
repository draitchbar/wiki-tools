#!/usr/bin/env bash
# pd-read.sh: transition shim for wikis set up before source types.
#
#   bash <plugin>/scripts/pd-read.sh <list|info|size|download> "<remote path>"
#
# Runs the proton-drive type's wrapper for instance key "proton":
#   sources/proton-drive/read.sh proton <op> <path>
# Removed once every wiki uses .claude/sources/ (see /wiki:init's migration).

[ $# -eq 2 ] || { printf 'pd-read: usage: pd-read.sh <list|info|size|download> "<remote path>"\n' >&2; exit 1; }
exec bash "$(dirname "$0")/../sources/proton-drive/read.sh" proton "$1" "$2"
