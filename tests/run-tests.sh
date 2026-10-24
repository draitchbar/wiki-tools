#!/usr/bin/env bash
# Run every hook fixture through its guard script and check the exit code.
#
#   bash tests/run-tests.sh
#
# Fixtures live in tests/fixtures/<script>/<pass|block>-<case>.json, where
# <script> is block-push or guard. "pass" expects exit 0, "block" expects 2.
# They run with CLAUDE_PROJECT_DIR on a copy of tests/guard-wiki (its
# .claude/sources/ has a gmail, a local-folder and a local-type instance)
# and HOME=/home/u, the home directory the fixtures use.
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

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -r "$here/guard-wiki" "$tmp/gw"
hook() { CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/home/u bash "$scripts/$1.sh"; }

for f in "$here"/fixtures/*/*.json; do
  script=$(basename "$(dirname "$f")")
  case=$(basename "$f" .json)
  case "$case" in
    pass-*) want=0 ;;
    block-*) want=2 ;;
    *) printf 'skip  %s (name must start with pass- or block-)\n' "$case"; continue ;;
  esac
  hook "$script" < "$f" >/dev/null 2>&1
  check "$script/$case" "$want" "$?"
done

# guard.sh fails closed on source files it can't read, and knows Windows paths.
fx="$here/fixtures/guard"
gbroken() { # NAME SETUP-SNIPPET (run in a fresh copy of guard-wiki)
  rm -rf "$tmp/gb"; cp -r "$here/guard-wiki" "$tmp/gb"
  (cd "$tmp/gb" && eval "$2")
  CLAUDE_PROJECT_DIR="$tmp/gb" HOME=/home/u bash "$scripts/guard.sh" < "$fx/pass-ordinary-bash.json" >/dev/null 2>&1
  check "guard/fail-closed-$1" 2 "$?"
}
gbroken instance-no-frontmatter 'printf "key: x\n" > .claude/sources/instances/x.md'
gbroken instance-unknown-type   'printf -- "---\nkey: x\ntype: nosuch\n---\n" > .claude/sources/instances/x.md'
gbroken local-type-shadows      'mkdir -p .claude/sources/types/gmail && cp .claude/sources/types/bookish/SOURCE.md .claude/sources/types/gmail/'
gbroken contract-no-frontmatter 'printf "# no fm\n" > .claude/sources/types/bookish/SOURCE.md'
win='{"session_id":"t","cwd":"C:\\Users\\u\\wikis\\udbygning","hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"C:\\Users\\u\\Pictures\\Receipts\\a.txt","content":"x"},"tool_use_id":"x"}'
printf '%s' "$win" | CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/c/Users/u bash "$scripts/guard.sh" >/dev/null 2>&1
check "guard/windows-drive-root" 2 "$?"

# Every Proton test runs with the fake CLI (tests/sources/proton-drive/
# fake-proton-drive) first on PATH, never the real one. Abort if the fake
# isn't the proton-drive that PATH finds.
fakebin="$tmp/bin"
mkdir -p "$fakebin"
cp "$here/sources/proton-drive/fake-proton-drive" "$fakebin/proton-drive" && chmod u+x "$fakebin/proton-drive"
if [ "$(PATH="$fakebin:$PATH" command -v proton-drive)" != "$fakebin/proton-drive" ]; then
  printf 'ABORT: the fake proton-drive is not first on PATH; refusing to run Proton tests against a real CLI.\n'
  exit 1
fi

# pd-read.sh refusals, run inside a throwaway git repo with a roots file.
git -C "$tmp" init -q wiki
mkdir -p "$tmp/wiki/.claude"
printf '/my-files/Bolig/sommerhus/tilbygning 2026\r\n' > "$tmp/wiki/.claude/proton-roots"
pd() { (cd "$tmp/wiki" && PATH="$fakebin:$PATH" bash "$scripts/pd-read.sh" "$@" >/dev/null 2>&1); echo $?; }
pdout() { (cd "$tmp/wiki" && PATH="$fakebin:$PATH" bash "$scripts/pd-read.sh" "$@" 2>&1); }

check "pd-read/refuse-trash"            1 "$(pd trash '/my-files/Bolig/sommerhus/tilbygning 2026/a.pdf')"
check "pd-read/refuse-upload"           1 "$(pd upload '/my-files/Bolig/sommerhus/tilbygning 2026')"
check "pd-read/refuse-delete"           1 "$(pd delete '/my-files/Bolig/sommerhus/tilbygning 2026/a.pdf')"
check "pd-read/refuse-outside-roots"    1 "$(pd list /my-files)"
check "pd-read/refuse-sibling-prefix"   1 "$(pd list '/my-files/Bolig/sommerhus/tilbygning 2026-old')"
check "pd-read/refuse-dotdot"           1 "$(pd list '/my-files/Bolig/sommerhus/tilbygning 2026/../..')"
check "pd-read/refuse-relative"         1 "$(pd list 'my-files/Bolig')"
check "pd-read/refuse-extra-args"       1 "$(pd list '/my-files/Bolig/sommerhus/tilbygning 2026' --force)"
check "pd-read/refuse-outside-git"      1 "$(cd "$tmp" && PATH="$fakebin:$PATH" bash "$scripts/pd-read.sh" list '/my-files/Bolig/sommerhus/tilbygning 2026' >/dev/null 2>&1; echo $?)"
# Behaviour against the fake CLI. pd-read.sh is the transition shim for key
# "proton" with .claude/proton-roots; proton-drive/read.sh checks follow.
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

# proton-drive/read.sh with instance files (new layout).
pdr="$here/../plugins/wiki/sources/proton-drive/read.sh"
git -C "$tmp" init -q pdw
mkdir -p "$tmp/pdw/.claude/sources/instances"
printf -- '---\nkey: drive\ntype: proton-drive\nroots:\n  - /my-files/Bil\n  - /my-files/Bolig/fugtalarm.pdf\n---\n' > "$tmp/pdw/.claude/sources/instances/drive.md"
printf -- '---\nkey: mail\ntype: gmail\nlabels: X\n---\n' > "$tmp/pdw/.claude/sources/instances/mail.md"
printf '/my-files\n' > "$tmp/pdw/.claude/proton-roots"
pdn() { (cd "$tmp/pdw" && HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$pdr" "$@" 2>&1); }
pdnx() { (cd "$tmp/pdw" && HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$pdr" "$@" >/dev/null 2>&1); echo $?; }
check "proton-drive/list"                 "FAKE filesystem list --json /my-files/Bil/2026" "$(pdn drive list /my-files/Bil/2026)"
out=$(pdn drive download "/my-files/Bil/2026/kontrakt.pdf" | head -n 1)
check "proton-drive/download-to-key"      "FAKE filesystem download --json -f remove -d merge /my-files/Bil/2026/kontrakt.pdf $tmp/home/.cache/wiki-sources/pdw/drive/2026" "$out"
out=$(pdn drive download "/my-files/Bolig/fugtalarm.pdf" | tail -n 1)
check "proton-drive/download-file-root"   "pd-read: downloaded to $tmp/home/.cache/wiki-sources/pdw/drive/fugtalarm.pdf" "$out"
check "proton-drive/refuse-outside"       1 "$(pdnx drive list /my-files/Bolig)"
check "proton-drive/refuse-sibling"       1 "$(pdnx drive list /my-files/Bil-old)"
check "proton-drive/refuse-dotdot"        1 "$(pdnx drive list /my-files/Bil/../Bolig)"
check "proton-drive/refuse-write-op"      1 "$(pdnx drive upload /my-files/Bil)"
check "proton-drive/refuse-two-args"      1 "$(pdnx list /my-files/Bil)"
check "proton-drive/refuse-wrong-type"    1 "$(pdnx mail list /my-files/Bil)"
check "proton-drive/refuse-no-instance"   1 "$(pdnx nosuch list /my-files/Bil)"
check "proton-drive/legacy-only-proton"   1 "$(pdnx other list /my-files/Bil)"
check "proton-drive/legacy-proton-roots"  "FAKE filesystem list --json /my-files/X" "$(pdn proton list /my-files/X)"
printf -- '---\nkey: proton\ntype: proton-drive\nroots:\n  - /my-files/Bil\n---\n' > "$tmp/pdw/.claude/sources/instances/proton.md"
check "proton-drive/instance-beats-legacy" 1 "$(pdnx proton list /my-files/X)"

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
case "$lint_out" in *"matches no source"*) r=flagged ;; *) r=clean ;; esac
check "lint/no-prefix-check-without-instances" clean "$r"
# The same wiki with a gmail instance: citations must match a source.
cp -r "$here/lint-wiki" "$tmp/lw2"
git -C "$tmp/lw2" init -q
mkdir -p "$tmp/lw2/.claude/sources/instances"
printf -- '---\nkey: gmail\ntype: gmail\nlabels: X\n---\n' > "$tmp/lw2/.claude/sources/instances/gmail.md"
printf -- '---\ntitle: Cites\ntype: note\nsources:\n  - "Gmail: A (2026-09-01)"\n  - "Proton: x.pdf, p. 1"\n  - raw/a.pdf\n  - "User statement (2026-10-01)"\n  - https://example.com\nrelated: []\ncreated: 2026-10-01\nupdated: 2026-10-01\n---\n' > "$tmp/lw2/wiki/cites.md"
lint2=$(cd "$tmp/lw2" && WIKI_LINT_TODAY=2026-10-16 bash "$scripts/lint.sh" 2>&1)
case "$lint2" in *'`cites.md`: source `Proton: x.pdf, p. 1` matches no source of this wiki'*) r=found ;; *) r=missing ;; esac
check "lint/unknown-source-prefix" found "$r"
n=$(printf '%s\n' "$lint2" | grep -c 'matches no source')
check "lint/known-prefixes-pass" 2 "$n"   # cites.md Proton + broken-contractor.md "Proton Drive"

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
mkdir -p "$tmp/ss/.claude/sources/instances"
printf -- '---\nkey: scans\ntype: local-folder\nroots:\n  - /x\n---\n' > "$tmp/ss/.claude/sources/instances/scans.md"
ss_out=$(cd "$tmp/ss" && CLAUDE_PROJECT_DIR= bash "$scripts/sync-status.sh" 2>&1)
case "$ss_out" in *"- scans: no last_checked_scans line yet"*) r=ok ;; *) r="$ss_out" ;; esac
check "sync-status/instance-without-line" ok "$r"

# wiki-check.sh: a freshly initialised wiki passes; each planted fault fails.
mkwiki() { # DIR
  git -C "$tmp" init -q "$1"
  w="$tmp/$1"
  mkdir -p "$w/raw" "$w/wiki/notes" "$w/outputs" "$w/templates" "$w/.claude"
  printf '# Test wiki\n\n@~/src/wiki-tools/schema/wiki-conventions.md\n@~/src/wiki-tools/schema/wiki-layout.md\n' > "$w/CLAUDE.md"
  printf '.obsidian/\n.claude/*\n!.claude/settings.json\n!.claude/sources/\n' > "$w/.gitignore"
  printf '# Sync Log\n\nlast_checked_raw: never\nlast_checked_gmail: never\nlast_checked_scans: never\n' > "$w/raw/sync-log.md"
  mkdir -p "$w/.claude/sources/instances"
  printf -- '---\nkey: gmail\ntype: gmail\nlabels: Test\nstate:\n  - last_checked\n---\n' > "$w/.claude/sources/instances/gmail.md"
  printf -- '---\nkey: scans\ntype: local-folder\nroots:\n  - /x/scans\nstate:\n  - last_checked\n---\n' > "$w/.claude/sources/instances/scans.md"
  printf '# Index\n\n## Notes\n\n| Page | Summary |\n|---|---|\n' > "$w/wiki/index.md"
  printf '# Log\n\n## 2026-10-16 | init | Wiki created\n' > "$w/wiki/log.md"
  printf -- '---\ntitle: Name\ntype: entity\nsources: []\nrelated: []\ncreated: YYYY-MM-DD\nupdated: YYYY-MM-DD\n---\n' > "$w/templates/entity.md"
  touch "$w/outputs/.gitkeep" "$w/wiki/notes/.gitkeep"
  # Template plus the rules of the two source types (wiki-check only looks for them).
  rules=$(cd "$w" && bash "$scripts/sources.sh" settings | grep -oE '"[^"]+"' | grep -vxE '"(permissions|allow|deny)"' | paste -sd, -)
  sed "s|  \"enabledPlugins\"|  \"x-source-rules\": [$rules],\n  \"enabledPlugins\"|" "$here/../templates/project-settings.json" > "$w/.claude/settings.json"
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

mkwiki f3; printf '/my-files/Test\n' > "$tmp/f3/.claude/proton-roots"
wc_expect old-layout f3 "FAIL old source layout"

mkwiki f4; sed -i '/Bash(git push \*)/d' "$tmp/f4/.claude/settings.json"
wc_expect missing-permission f4 'FAIL permission rules missing from .claude/settings.json: "Bash(git push *)"'

mkwiki f5; sed -i 's/"wiki@wiki-tools": true/"wiki@wiki-tools": false/' "$tmp/f5/.claude/settings.json"
wc_expect plugin-disabled f5 'FAIL plugin `wiki@wiki-tools` is not enabled'

mkwiki f6; git -C "$tmp/f6" rm -q --cached .claude/settings.json
wc_expect settings-uncommitted f6 "FAIL \`.claude/settings.json\` isn't committed"

mkwiki f7; sed -i 's#  - /x/scans#  - relative/path#' "$tmp/f7/.claude/sources/instances/scans.md"
wc_expect roots-relative f7 "root 'relative/path' isn't an absolute path"

mkwiki f8; rm -r "$tmp/f8/templates"
wc_expect no-templates f8 'FAIL folder `templates/` is missing'

mkwiki f9; printf 'extra\n' >> "$tmp/f9/CLAUDE.md"
wc_expect uncommitted-setup f9 'FAIL uncommitted setup files: CLAUDE.md'

mkwiki f10; printf -- '---\ntitle: X\ntype: entity\nsources: []\ncreated: 2026-10-16\nupdated: 2026-10-16\n---\nSee [[nowhere]].\n' > "$tmp/f10/wiki/notes/x.md"
wc_expect lint-error f10 'FAIL lint finds 1 structural error(s)'

mkwiki f11; git -C "$tmp/f11" rm -q --cached .claude/sources/instances/scans.md
wc_expect instance-uncommitted f11 "FAIL \`.claude/sources/instances/scans.md\` isn't committed"

mkwiki f12; sed -i '/last_checked_scans/d' "$tmp/f12/raw/sync-log.md"
wc_expect instance-no-sync-line f12 "FAIL source \`scans\` has no \`last_checked_scans\` line"

mkwiki f13; sed -i 's/"mcp__claude_ai_Gmail__send_message",//' "$tmp/f13/.claude/settings.json"
wc_expect source-rule-missing f13 'FAIL source permission rules missing from .claude/settings.json: "mcp__claude_ai_Gmail__send_message"'

mkwiki f14; sed -i '/!.claude\/sources/d' "$tmp/f14/.gitignore"
wc_expect gitignore-sources f14 "FAIL \`.gitignore\` lacks \`!.claude/sources/\`"

mkwiki f15; printf -- '---\nkey: bad\ntype: nosuch\n---\n' > "$tmp/f15/.claude/sources/instances/bad.md"
wc_expect instance-invalid f15 "FAIL source \`bad\` doesn't validate: unknown source type 'nosuch'"

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

# sources.sh against a copy of guard-wiki (gmail, scans, local type books).
cp -r "$here/guard-wiki" "$tmp/sw"
git -C "$tmp/sw" init -q
mkdir -p "$tmp/sw/raw"
printf 'last_checked_gmail: 2026-10-01\nlast_checked_raw: never\n' > "$tmp/sw/raw/sync-log.md"
srun() { (cd "$tmp/sw" && bash "$scripts/sources.sh" "$@" 2>&1); }
sexpect() { # NAME TEXT ARGS...
  n=$1 t=$2; shift 2
  out=$(srun "$@")
  case "$out" in *"$t"*) r=found ;; *) r="missing in: $out" ;; esac
  check "sources/$n" found "$r"
}
sexpect list-raw        '- raw: built in (raw/), last checked: never' list
sexpect list-standard   '- gmail: type gmail (standard), valid, available here: yes, last checked: 2026-10-01' list
sexpect list-local      '- books: type bookish (local), valid' list
sexpect list-no-state   'last checked: no last_checked_scans line' list
sexpect show-header     'Source scans: valid' show scans
sexpect show-instance   '  - ~/Pictures/Receipts' show scans
sexpect show-contract   '# Source type: Local folder' show scans
sexpect show-raw        'raw is built in' show raw
sexpect show-unknown    "no source 'nosuch' in this wiki" show nosuch
sexpect catalog         '- bookish (local, script): Bookish (local test type)' catalog
sexpect contract        'type: gmail' contract gmail
sexpect settings-allow  '"Bash(bash .claude/sources/types/bookish/fetch.sh *)",' settings
sexpect settings-deny   '"mcp__claude_ai_Gmail__send_message",' settings
sexpect settings-type   '"Bash(bash ~/src/wiki-tools/plugins/wiki/sources/local-folder/read.sh *)"' settings local-folder
sed -i 's/^platforms:/platforms:\n  - macos/; /^  - linux$/d' "$tmp/sw/.claude/sources/types/bookish/SOURCE.md"
sexpect show-platform   "isn't available on" show books
printf -- '---\nkey: bad\ntype: gmail\n---\n' > "$tmp/sw/.claude/sources/instances/bad.md"
sed -i 's/^key: bad/key: worse/' "$tmp/sw/.claude/sources/instances/bad.md"
sexpect show-invalid    "doesn't validate" show bad
rm "$tmp/sw/.claude/sources/instances/proton.md"
printf '/my-files/X\n' > "$tmp/sw/.claude/proton-roots"
sexpect list-old-layout 'Old layout: .claude/proton-roots' list

# local-folder/read.sh against a throwaway wiki and folder.
lfs="$here/../plugins/wiki/sources/local-folder/read.sh"
git -C "$tmp" init -q lfw
mkdir -p "$tmp/lfw/.claude/sources/instances" "$tmp/scans/2026/sub" "$tmp/scans-old" "$tmp/other"
printf -- '---\nkey: scans\ntype: local-folder\nroots:\n  - %s/scans\n  - %s/other/one.pdf\n---\n' "$tmp" "$tmp" > "$tmp/lfw/.claude/sources/instances/scans.md"
printf -- '---\nkey: notafolder\ntype: gmail\nlabels: X\n---\n' > "$tmp/lfw/.claude/sources/instances/notafolder.md"
printf 'old\n' > "$tmp/scans/2026/old.pdf"; touch -d 2026-01-01 "$tmp/scans/2026/old.pdf"
printf 'new\n' > "$tmp/scans/2026/sub/new file.pdf"; touch -d 2026-10-10 "$tmp/scans/2026/sub/new file.pdf"
printf 'one\n' > "$tmp/other/one.pdf"; touch -d 2026-09-01 "$tmp/other/one.pdf"
printf 'x\n' > "$tmp/scans-old/x.pdf"
lf() { (cd "$tmp/lfw" && HOME="$tmp/home" bash "$lfs" "$@" 2>&1); }
lfx() { (cd "$tmp/lfw" && HOME="$tmp/home" bash "$lfs" "$@" >/dev/null 2>&1); echo $?; }
check "local-folder/refuse-unknown-op"   1 "$(lfx scans delete "$tmp/scans/2026/old.pdf")"
check "local-folder/refuse-extra-args"   1 "$(lfx scans list "$tmp/scans" --force)"
check "local-folder/refuse-no-instance"  1 "$(lfx nosuch list "$tmp/scans")"
check "local-folder/refuse-bad-key"      1 "$(lfx ../x list "$tmp/scans")"
check "local-folder/refuse-wrong-type"   1 "$(lfx notafolder list "$tmp/scans")"
check "local-folder/refuse-outside"      1 "$(lfx scans list "$tmp")"
check "local-folder/refuse-sibling"      1 "$(lfx scans list "$tmp/scans-old")"
check "local-folder/refuse-dotdot"       1 "$(lfx scans list "$tmp/scans/../scans-old")"
check "local-folder/refuse-relative"     1 "$(lfx scans list scans)"
check "local-folder/refuse-bad-date"     1 "$(lfx scans new yesterday)"
check "local-folder/refuse-copy-folder"  1 "$(lfx scans copy "$tmp/scans/2026")"
check "local-folder/refuse-outside-git"  1 "$(cd "$tmp" && bash "$lfs" scans list "$tmp/scans" >/dev/null 2>&1; echo $?)"
out=$(lf scans list "$tmp/scans/2026" | awk '{print $1, $NF}' | paste -sd' ' -)
check "local-folder/list"                "f $tmp/scans/2026/old.pdf d $tmp/scans/2026/sub" "$out"
out=$(lf scans new 2026-10-01 | sed 's/.* [0-9]* //')
check "local-folder/new-since"           "$tmp/scans/2026/sub/new file.pdf" "$out"
out=$(lf scans new never | wc -l | tr -d ' ')
check "local-folder/new-never"           3 "$out"
out=$(lf scans copy "$tmp/scans/2026/sub/new file.pdf")
check "local-folder/copy"                "local-folder: copied to $tmp/home/.cache/wiki-sources/lfw/scans/2026/sub/new file.pdf" "$out"
check "local-folder/copy-content"        new "$(cat "$tmp/home/.cache/wiki-sources/lfw/scans/2026/sub/new file.pdf" 2>&1)"
out=$(lf scans copy "$tmp/other/one.pdf")
check "local-folder/copy-file-root"      "local-folder: copied to $tmp/home/.cache/wiki-sources/lfw/scans/one.pdf" "$out"
check "local-folder/source-untouched"    "old" "$(cat "$tmp/scans/2026/old.pdf")"

printf '\n%d checks, %d failed\n' "$total" "$fail"
[ "$fail" -eq 0 ]
