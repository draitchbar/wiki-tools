#!/usr/bin/env bash
# install-source-file.sh: the user installs one file into a wiki's
# protected .claude/sources/ tree, after checking it.
#
#   bash <plugin>/scripts/install-source-file.sh instances/<key>.md
#   bash <plugin>/scripts/install-source-file.sh types/<type>/<file>
#
# Run it in a terminal outside Claude, from inside the wiki. On Windows, use
# Git Bash: plain `bash` from PowerShell starts WSL instead. Give it the file
# on stdin, which is safest (a terminal paste can break long lines or cut the
# file off):
#
#   bash <plugin>/scripts/install-source-file.sh instances/<key>.md < <file>
#
# or paste the content and end with Ctrl-D. The script then:
#   1. checks the file in a scratch copy of .claude/sources/ (frontmatter,
#      key matches the file name, the type exists, required parameters,
#      roots of filesystem instances, the contract of a local type) and
#      re-checks every instance, so one file can't break another;
#   2. shows the diff against the current file and asks before writing;
#   3. prints the settings rules (.claude/settings.json) the source types
#      need that are still missing.
# It never touches git: commit the installed files yourself.
#
# Claude can't run it: the guard blocks every command that names the
# plugin folder except its listed scripts, and the script refuses to run
# inside a Claude Code session.
#
# The checks and the writing are in install_source.py (docs/adr.md, 4);
# this launcher keeps the terminal: the paste, the diff, the
# prompt (native Windows Python can't open /dev/tty).
#
# Environment (for tests only): WIKI_INSTALL_ANSWER=y|n answers the prompt.

set -u

die() { printf 'install-source-file: %s\n' "$1" >&2; exit 1; }

[ -z "${CLAUDECODE:-}" ] || die "run this in a terminal outside Claude; it writes protected files."
[ $# -eq 1 ] || die "usage: install-source-file.sh <instances/<key>.md | types/<type>/<file>> [< file] (on Windows, in Git Bash)"

d=${BASH_SOURCE[0]%/*}
[ "$d" != "${BASH_SOURCE[0]}" ] || d=.
. "$d/py-run.sh"
plugin=$(cd "$d/.." && pwd)
_pr_label=install-source-file
py() { _pr_call install_source --plugin "$plugin" "$@"; }

target=${1#./}
target=${target#.claude/sources/}

# On a terminal, check the target before asking for the paste.
if [ -t 0 ]; then
  py target "$1" || exit $?
fi

scratch=$(mktemp -d) || die "cannot create a temp dir"
trap 'rm -rf "$scratch"' EXIT
# Python on Windows can't open a Git Bash mount path (/tmp/...).
case "${MSYSTEM:-}${OSTYPE:-}" in *MINGW*|*MSYS*|*msys*|*cygwin*) scratch=$(cd "$scratch" && pwd -W) ;; esac

if [ -t 0 ]; then
  printf 'Paste the content of .claude/sources/%s, then press Ctrl-D on an empty line\n(safer for a long file: save it and run this again with < <file>):\n' "$target" >&2
fi
cat > "$scratch/pasted"

# 1. Check.
py check "$1" "$scratch"
rc=$?
case $rc in 0) ;; 2) exit 0 ;; *) exit $rc ;; esac

# 2. Diff and confirm.
if [ -f "$scratch/current" ]; then
  printf '\nChanges to .claude/sources/%s:\n' "$target"
  diff -u "$scratch/current" "$scratch/new" | sed -e "1s#.*#--- current#" -e "2s#.*#+++ pasted#"
else
  printf '\nNew file .claude/sources/%s:\n' "$target"
  sed 's/^/  /' "$scratch/new"
fi
printf '\nInstall it? [y/N] '
if [ -n "${WIKI_INSTALL_ANSWER:-}" ]; then
  answer=$WIKI_INSTALL_ANSWER; printf '%s\n' "$answer"
elif [ -r /dev/tty ]; then
  read -r answer < /dev/tty || answer=""
else
  answer=""
fi
case "$answer" in y|Y|yes|Yes) ;; *) printf 'Not installed.\n'; exit 1 ;; esac

# 3. Install, and the settings rules still missing.
py write "$1" "$scratch"
exit $?
