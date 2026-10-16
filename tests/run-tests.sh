#!/usr/bin/env bash
# Run every hook fixture through its guard script and check the exit code.
#
#   bash tests/run-tests.sh
#
# Fixtures live in tests/fixtures/<script>/<pass|block>-<case>.json, where
# <script> is block-push or guard. "pass" expects exit 0, "block" expects 2.
# Also runs pd-read.sh refusal checks that need no Proton CLI.

here=$(cd "$(dirname "$0")" && pwd)
scripts="$here/../plugins/wiki/scripts"
fail=0
total=0

check() { # NAME EXPECTED ACTUAL
  total=$((total + 1))
  if [ "$2" = "$3" ]; then
    printf 'ok    %s\n' "$1"
  else
    printf 'FAIL  %s (expected %s, got %s)\n' "$1" "$2" "$3"
    fail=$((fail + 1))
  fi
}

for f in "$here"/fixtures/*/*.json; do
  script=$(basename "$(dirname "$f")")
  case=$(basename "$f" .json)
  case "$case" in
    pass-*) want=0 ;;
    block-*) want=2 ;;
    *) printf 'skip  %s (name must start with pass- or block-)\n' "$case"; continue ;;
  esac
  bash "$scripts/$script.sh" < "$f" >/dev/null 2>&1
  check "$script/$case" "$want" "$?"
done

# pd-read.sh refusals, run inside a throwaway git repo with a roots file.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git -C "$tmp" init -q wiki
mkdir -p "$tmp/wiki/.claude"
printf '/my-files/Bolig/sommerhus/tilbygning 2026\r\n' > "$tmp/wiki/.claude/proton-roots"
pd() { (cd "$tmp/wiki" && bash "$scripts/pd-read.sh" "$@" >/dev/null 2>&1); echo $?; }
pdout() { (cd "$tmp/wiki" && bash "$scripts/pd-read.sh" "$@" 2>&1); }

check "pd-read/refuse-trash"            1 "$(pd trash '/my-files/Bolig/sommerhus/tilbygning 2026/a.pdf')"
check "pd-read/refuse-upload"           1 "$(pd upload '/my-files/Bolig/sommerhus/tilbygning 2026')"
check "pd-read/refuse-delete"           1 "$(pd delete '/my-files/Bolig/sommerhus/tilbygning 2026/a.pdf')"
check "pd-read/refuse-outside-roots"    1 "$(pd list /my-files)"
check "pd-read/refuse-sibling-prefix"   1 "$(pd list '/my-files/Bolig/sommerhus/tilbygning 2026-old')"
check "pd-read/refuse-dotdot"           1 "$(pd list '/my-files/Bolig/sommerhus/tilbygning 2026/../..')"
check "pd-read/refuse-relative"         1 "$(pd list 'my-files/Bolig')"
check "pd-read/refuse-extra-args"       1 "$(pd list '/my-files/Bolig/sommerhus/tilbygning 2026' --force)"
check "pd-read/refuse-outside-git"      1 "$(cd "$tmp" && bash "$scripts/pd-read.sh" list '/my-files/Bolig/sommerhus/tilbygning 2026' >/dev/null 2>&1; echo $?)"
# An in-root path gets past the path checks and stops at the CLI or version pin,
# which proves the roots file (with CRLF) was parsed.
inroot=$(pdout list '/my-files/Bolig/sommerhus/tilbygning 2026/tilbud')
case "$inroot" in
  *"not found on PATH"*|*"PINNED_VERSION"*|*"differs from pinned"*) r=accepted ;;
  *) r="rejected: $inroot" ;;
esac
check "pd-read/in-root-path-accepted"   accepted "$r"

printf '\n%d checks, %d failed\n' "$total" "$fail"
[ "$fail" -eq 0 ]
