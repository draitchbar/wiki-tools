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
# Behaviour against a fake CLI (tests/fake-proton-drive), never the real one.
fakebin="$tmp/bin"
mkdir -p "$fakebin"
cp "$here/fake-proton-drive" "$fakebin/proton-drive"
chmod u+x "$fakebin/proton-drive"
fake() { (cd "$tmp/wiki" && HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$scripts/pd-read.sh" "$@" 2>&1); }
root='/my-files/Bolig/sommerhus/tilbygning 2026'

out=$(fake list "$root/tilbud")
check "pd-read/list-calls-cli"          "FAKE filesystem list --json $root/tilbud" "$out"
out=$(fake size "$root")
check "pd-read/size-calls-cli"          "FAKE filesystem size --json $root" "$out"
out=$(fake download "$root/tilbud/a.pdf" | head -n 1)
check "pd-read/download-args"           "FAKE filesystem download --json -f remove -d merge $root/tilbud/a.pdf $tmp/home/.cache/wiki-sources/wiki/proton/tilbud" "$out"
printf '/my-files/Bolig/fugtalarm.pdf\n' >> "$tmp/wiki/.claude/proton-roots"
out=$(fake download "/my-files/Bolig/fugtalarm.pdf" | head -n 1)
check "pd-read/download-file-root"      "FAKE filesystem download --json -f remove -d merge /my-files/Bolig/fugtalarm.pdf $tmp/home/.cache/wiki-sources/wiki/proton" "$out"
out=$(fake download "$root/a.pdf" | head -n 1)
check "pd-read/download-top-level"      "FAKE filesystem download --json -f remove -d merge $root/a.pdf $tmp/home/.cache/wiki-sources/wiki/proton" "$out"
check "pd-read/refuse-download-folder"  1 "$(cd "$tmp/wiki" && HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$scripts/pd-read.sh" download "$root/tilbud" >/dev/null 2>&1; echo $?)"
check "pd-read/refuse-download-root"    1 "$(cd "$tmp/wiki" && HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$scripts/pd-read.sh" download "$root" >/dev/null 2>&1; echo $?)"
out=$(cd "$tmp/wiki" && FAKE_PD_SYNTAX=changed HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$scripts/pd-read.sh" download "$root/a.pdf" 2>&1; echo "exit=$?")
case "$out" in *"syntax changed"*exit=1) r=refused ;; *) r="not refused: $out" ;; esac
check "pd-read/refuse-changed-syntax"   refused "$r"

# lint.sh against the fixture wiki in tests/lint-wiki (one planted problem per check).
cp -r "$here/lint-wiki" "$tmp/lw"
git -C "$tmp/lw" init -q
lint_out=$(cd "$tmp/lw" && WIKI_LINT_TODAY=2026-10-16 bash "$scripts/lint.sh" 2>&1)
expect() { # NAME TEXT
  case "$lint_out" in *"$2"*) r=found ;; *) r=missing ;; esac
  check "lint/$1" found "$r"
}
expect summary            'Pages: 6. Errors: 5. Warnings: 10. Info: 1.'
expect no-frontmatter     '`rooms/no-frontmatter.md`: no YAML frontmatter'
expect missing-fields     '`approvals/missing-fields.md`: missing title sources'
expect broken-alias       '`[[missing-page]]` (no such page) linked from `contractors/broken-contractor.md`'
expect broken-path-anchor '`[[also-missing]]` (no such page)'
expect broken-in-log      '`[[ghost-from-log]]` (no such page) linked from `log.md`'
expect orphan             '`rooms/no-frontmatter.md`: no inbound links from other pages'
expect not-in-index       '`approvals/missing-fields.md`: not listed in index.md'
expect no-sources         '`budget/no-sources.md`: `sources:` is empty'
expect future-date        '`updated: 2027-01-01` is in the future'
expect invalid-date       '`updated: 2026-31-12` is not a YYYY-MM-DD date'
expect updated-before     'updated (2026-08-01) is before created (2026-09-01)'
expect stale-words        '`decisions/stale-decision.md`: updated 283 days ago and still says: awaiting,pending'
expect stale-status       'status_as_of 2026-01-01 is 287 days old'
expect no-status          '`decisions/stale-decision.md` (decision): no `status_as_of`'
expect clusters           '- **decisions**: `decisions/good-decision.md`, `decisions/stale-decision.md`'
findings=$(printf '%s\n' "$lint_out" | sed '/^## Clusters/,$d')
case "$findings" in *good-decision.md*) r=flagged ;; *) r=clean ;; esac
check "lint/clean-page-not-flagged" clean "$r"
case "$findings" in *broken-contractor\]\]*) r=flagged ;; *) r=clean ;; esac
check "lint/case-insensitive-links" clean "$r"
nowiki=$(cd "$tmp" && git init -q nowiki && cd nowiki && bash "$scripts/lint.sh" 2>&1)
case "$nowiki" in *"no wiki/ folder"*) r=ok ;; *) r="$nowiki" ;; esac
check "lint/no-wiki-folder" ok "$r"

printf '\n%d checks, %d failed\n' "$total" "$fail"
[ "$fail" -eq 0 ]
