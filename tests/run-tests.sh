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

# sync-status.sh: "never" for sources /wiki:init created.
git -C "$tmp" init -q ss
mkdir -p "$tmp/ss/raw"
printf 'last_checked_gmail: never\nlast_checked_proton: 2026-10-01\nlast_checked_web: soon\n' > "$tmp/ss/raw/sync-log.md"
ss_out=$(cd "$tmp/ss" && CLAUDE_PROJECT_DIR= bash "$scripts/sync-status.sh" 2>&1)
case "$ss_out" in *"- gmail: never checked"*) r=ok ;; *) r="$ss_out" ;; esac
check "sync-status/never" ok "$r"
case "$ss_out" in *"- proton: last checked 2026-10-01"*) r=ok ;; *) r="$ss_out" ;; esac
check "sync-status/date-still-works" ok "$r"
case "$ss_out" in *"- web: unreadable date 'soon'"*) r=ok ;; *) r="$ss_out" ;; esac
check "sync-status/unreadable" ok "$r"

# wiki-check.sh: a freshly initialised wiki passes; each planted fault fails.
mkwiki() { # DIR
  git -C "$tmp" init -q "$1"
  w="$tmp/$1"
  mkdir -p "$w/raw" "$w/wiki/notes" "$w/outputs" "$w/templates" "$w/.claude"
  printf '# Test wiki\n\n@~/src/wiki-tools/schema/wiki-conventions.md\n@~/src/wiki-tools/schema/wiki-layout.md\n' > "$w/CLAUDE.md"
  printf '.obsidian/\n.claude/*\n!.claude/settings.json\n!.claude/proton-roots\n' > "$w/.gitignore"
  printf '# Sync Log\n\nlast_checked_gmail: never\nlast_checked_proton: never\n' > "$w/raw/sync-log.md"
  printf '# Index\n\n## Notes\n\n| Page | Summary |\n|---|---|\n' > "$w/wiki/index.md"
  printf '# Log\n\n## 2026-10-16 | init | Wiki created\n' > "$w/wiki/log.md"
  printf -- '---\ntitle: Name\ntype: entity\nsources: []\nrelated: []\ncreated: YYYY-MM-DD\nupdated: YYYY-MM-DD\n---\n' > "$w/templates/entity.md"
  touch "$w/outputs/.gitkeep" "$w/wiki/notes/.gitkeep"
  cp "$here/../templates/project-settings.json" "$w/.claude/settings.json"
  printf '/my-files/Test\n' > "$w/.claude/proton-roots"
  git -C "$w" add -A && git -C "$w" -c user.name=t -c user.email=t@t commit -qm init
}
wc_run() { (cd "$tmp/$1" && bash "$scripts/wiki-check.sh" 2>&1); }
wc_exit() { (cd "$tmp/$1" && bash "$scripts/wiki-check.sh" >/dev/null 2>&1); echo $?; }
wc_expect() { # NAME DIR TEXT
  out=$(wc_run "$2")
  case "$out" in *"$3"*) r=found ;; *) r="missing in: $out" ;; esac
  check "wiki-check/$1" found "$r"
}
mkwiki good
check "wiki-check/good-wiki-passes" 0 "$(wc_exit good)"
wc_expect good-summary good 'Failures: 0.'

mkwiki f1; sed -i '/wiki-layout/d' "$tmp/f1/CLAUDE.md"
wc_expect missing-import f1 "FAIL CLAUDE.md doesn't import \`wiki-layout.md\`"
check "wiki-check/fault-exits-1" 1 "$(wc_exit f1)"

mkwiki f2; printf 'last_checked_web: soon\n' >> "$tmp/f2/raw/sync-log.md"
wc_expect bad-sync-value f2 "FAIL \`last_checked_web: soon\` in raw/sync-log.md"

mkwiki f3; git -C "$tmp/f3" rm -q .claude/proton-roots
wc_expect missing-roots f3 "FAIL Proton is a source but \`.claude/proton-roots\` is missing"

mkwiki f4; sed -i '/Bash(git push \*)/d' "$tmp/f4/.claude/settings.json"
wc_expect missing-permission f4 'FAIL permission rules missing from .claude/settings.json: "Bash(git push *)"'

mkwiki f5; sed -i 's/"wiki@wiki-tools": true/"wiki@wiki-tools": false/' "$tmp/f5/.claude/settings.json"
wc_expect plugin-disabled f5 'FAIL plugin `wiki@wiki-tools` is not enabled'

mkwiki f6; git -C "$tmp/f6" rm -q --cached .claude/settings.json
wc_expect settings-uncommitted f6 "FAIL \`.claude/settings.json\` isn't committed"

mkwiki f7; printf 'relative/path\n' >> "$tmp/f7/.claude/proton-roots"
wc_expect roots-relative f7 "isn't an absolute path: \`relative/path\`"

mkwiki f8; rm -r "$tmp/f8/templates"
wc_expect no-templates f8 'FAIL folder `templates/` is missing'

mkwiki f9; printf 'extra\n' >> "$tmp/f9/CLAUDE.md"
wc_expect uncommitted-setup f9 'FAIL uncommitted setup files: CLAUDE.md'

mkwiki f10; printf -- '---\ntitle: X\ntype: entity\nsources: []\ncreated: 2026-10-16\nupdated: 2026-10-16\n---\nSee [[nowhere]].\n' > "$tmp/f10/wiki/notes/x.md"
wc_expect lint-error f10 'FAIL lint finds 1 structural error(s)'

nogit=$(cd "$tmp" && mkdir -p plain && cd plain && bash "$scripts/wiki-check.sh" >/dev/null 2>&1; echo $?)
check "wiki-check/outside-git" 1 "$nogit"

# lib-source.sh against the fixture plugin and wiki in tests/sources/lib-source.
ls_dir="$here/sources/lib-source"
cp -r "$ls_dir" "$tmp/ls"
git -C "$tmp/ls/wiki" init -q
lsrun() { # SHELL-SNIPPET: run with lib-source loaded and SRC_PLUGIN on the fixture
  (cd "$tmp/ls/wiki" && . "$scripts/lib-source.sh" && SRC_PLUGIN="$tmp/ls/plugin" && eval "$1") 2>&1
}
lsw="$tmp/ls/wiki"
check "lib-source/field"            "Standard test type" "$(lsrun 'src_field "$SRC_PLUGIN/sources/std/SOURCE.md" title')"
check "lib-source/list"             "linux windows" "$(lsrun 'src_list "$SRC_PLUGIN/sources/std/SOURCE.md" platforms | paste -sd" " -')"
check "lib-source/list-stops"       "read.sh" "$(lsrun 'src_list "$SRC_PLUGIN/sources/std/SOURCE.md" scripts')"
check "lib-source/values-scalar"    "Tisvilde" "$(lsrun 'src_values .claude/sources/instances/loc1.md labels')"
check "lib-source/values-list"      "/data/one ~/two" "$(lsrun 'src_values .claude/sources/instances/good.md roots | paste -sd" " -')"
check "lib-source/names"            "roots note" "$(lsrun 'src_list "$SRC_PLUGIN/sources/std/SOURCE.md" parameters | src_names | paste -sd" " -')"
check "lib-source/instances"        "bad-root good loc1 missing-param unknown-type uses-broken wrong-key" "$(lsrun 'src_instances "$PWD" | paste -sd" " -')"
check "lib-source/contract-std"     "$tmp/ls/plugin/sources/std/SOURCE.md" "$(lsrun 'src_contract "$PWD" std')"
check "lib-source/contract-local"   "$lsw/.claude/sources/types/loc/SOURCE.md" "$(lsrun 'src_contract "$PWD" loc')"
check "lib-source/contract-unknown" 1 "$(lsrun 'src_contract "$PWD" nosuch >/dev/null 2>&1; echo $?')"
check "lib-source/contract-badname" 1 "$(lsrun 'src_contract "$PWD" ../std >/dev/null 2>&1; echo $?')"
check "lib-source/catalog"          "loc:local std:standard" "$(lsrun 'src_catalog "$PWD" | cut -f1,2 | tr "\t" : | grep -v broken | sort | paste -sd" " -')"
check "lib-source/valid-std"        0 "$(lsrun 'src_validate_contract "$SRC_PLUGIN/sources/std/SOURCE.md"; echo $?')"
check "lib-source/valid-good"       0 "$(lsrun 'src_validate_instance "$PWD" good; echo $?')"
check "lib-source/valid-loc1"       0 "$(lsrun 'src_validate_instance "$PWD" loc1; echo $?')"
lsbad() { # NAME KEY EXPECTED-TEXT
  out=$(lsrun "src_validate_instance \"\$PWD\" $2; echo exit=\$?")
  case "$out" in *"$3"*exit=1) r=ok ;; *) r="$out" ;; esac
  check "lib-source/$1" ok "$r"
}
lsbad missing-param   missing-param "required parameter 'roots' is empty"
lsbad relative-root   bad-root      "root 'relative/path' isn't an absolute path"
lsbad dotdot-root     bad-root      "root '/data/../etc' contains '.' or '..'"
lsbad wrong-key       wrong-key     "key 'other' doesn't match the file name"
lsbad unknown-type    unknown-type  "unknown source type 'nosuch'"
lsbad broken-folder   uses-broken   "type 'other' doesn't match its folder 'broken'"
lsbad broken-access   uses-broken   "access must be mcp, script or filesystem"
lsbad broken-platform uses-broken   "unknown platform 'beos'"
lsbad broken-state    uses-broken   "state must include last_checked"
lsbad broken-prefix   uses-broken   "missing 'cite_prefix'"
lsbad broken-script   uses-broken   "script name '../evil.sh' must be a plain <name>.sh"
lsbad missing-script  uses-broken   "script 'missing.sh' is listed but missing"
mkdir -p "$lsw/.claude/sources/types/std"
cp "$tmp/ls/plugin/sources/std/SOURCE.md" "$lsw/.claude/sources/types/std/"
lsbad shadowing       good          "shadows the standard type"
rm -r "$lsw/.claude/sources/types/std"
sed 's/$/\r/' "$lsw/.claude/sources/instances/good.md" > "$lsw/.claude/sources/instances/crlf.md"
sed -i 's/^key: good/key: crlf/' "$lsw/.claude/sources/instances/crlf.md"
check "lib-source/crlf"             0 "$(lsrun 'src_validate_instance "$PWD" crlf; echo $?')"
check "lib-source/crlf-values"      "/data/one ~/two" "$(lsrun 'src_values .claude/sources/instances/crlf.md roots | paste -sd" " -')"
check "lib-source/expand"           "$HOME/two" "$(lsrun 'src_expand "~/two/"')"
check "lib-source/expand-backslash" "C:/Users/x" "$(lsrun 'src_expand "C:\\Users\\x\\"')"
check "lib-source/match-root"       "/data/one" "$(lsrun 'printf "/data/one\n/data/two\n" | src_match_root /data/one/a/b')"
check "lib-source/match-sibling"    1 "$(lsrun 'printf "/data/one\n" | src_match_root /data/one-old >/dev/null; echo $?')"
check "lib-source/dots"             0 "$(lsrun 'src_has_dots "/a/./b"; echo $?')"
check "lib-source/no-dots"          1 "$(lsrun 'src_has_dots "/a/.b/c"; echo $?')"

printf '\n%d checks, %d failed\n' "$total" "$fail"
[ "$fail" -eq 0 ]
