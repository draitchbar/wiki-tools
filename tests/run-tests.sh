#!/usr/bin/env bash
# Run every hook fixture through its guard script and check the exit code.
#
#   bash tests/run-tests.sh
#
# Fixtures live in tests/fixtures/<script>/<pass|block>-<case>.json, where
# <script> is block-push or guard. "pass" expects exit 0, "block" expects 2.
# They run with CLAUDE_PROJECT_DIR on a copy of tests/guard-wiki (its
# .claude/sources/ has gmail, local-folder, ms-teams and local-type instances)
# and HOME=/home/u, the home directory the fixtures use.
# Also runs the proton-drive wrapper's refusal checks against a fake Proton CLI.

here=$(cd "$(dirname "$0")" && pwd)
scripts="$here/../plugins/wiki/scripts"
fail=0
total=0
# The test repos have no .gitattributes; keep a user's core.autocrlf (Windows)
# from converting their files or warning on every git add.
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.autocrlf GIT_CONFIG_VALUE_0=false

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

# Fixtures name the plugin folder @PLUGIN@ (as pwd prints it) or
# @PLUGIN_DRIVE@ (as Claude Code substitutes it on Windows: C:/...; on Linux
# the same as @PLUGIN@).
plugin=$(cd "$scripts/.." && pwd)
plugin_drive=$(printf '%s' "$plugin" | sed 's#^/\([a-z]\)/#\U\1:/#')
for f in "$here"/fixtures/*/*.json; do
  script=$(basename "$(dirname "$f")")
  case=$(basename "$f" .json)
  case "$case" in
    pass-*) want=0 ;;
    block-*) want=2 ;;
    *) printf 'skip  %s (name must start with pass- or block-)\n' "$case"; continue ;;
  esac
  sed -e "s#@PLUGIN_DRIVE@#$plugin_drive#g" -e "s#@PLUGIN@#$plugin#g" "$f" | hook "$script" >/dev/null 2>&1
  check "$script/$case" "$want" "$?"
done
# The plugin folder written with ~, when it is under HOME.
tilde_cmd="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash ~/$(basename "$plugin")/scripts/lint.sh\"}}"
printf '%s' "$tilde_cmd" | CLAUDE_PROJECT_DIR="$tmp/gw" HOME=$(dirname "$plugin") bash "$scripts/guard.sh" >/dev/null 2>&1
check "guard/pass-lint-tilde-form" 0 "$?"
# The plugin folder with Windows backslashes (JSON-escaped).
bs_cmd="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash $(printf '%s' "$plugin_drive" | sed 's#/#\\\\#g')\\\\scripts\\\\lint.sh\"}}"
printf '%s' "$bs_cmd" | hook guard >/dev/null 2>&1
check "guard/pass-lint-backslash-form" 0 "$?"

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
gbroken filesystem-no-roots     'printf -- "---\nkey: x\ntype: local-folder\n---\n" > .claude/sources/instances/x.md'
# While broken: read-only diagnostics pass, everything else is refused.
rm -rf "$tmp/gb"; cp -r "$here/guard-wiki" "$tmp/gb"
printf 'key: x\n' > "$tmp/gb/.claude/sources/instances/x.md"
gdiag() { # NAME EXPECTED-EXIT TOOL-INPUT-JSON (Bash command or Write)
  printf '{"session_id":"t","cwd":"/home/u/wikis/mywiki","hook_event_name":"PreToolUse","tool_name":"%s","tool_input":%s,"tool_use_id":"x"}' "$3" "$4" |
    CLAUDE_PROJECT_DIR="$tmp/gb" HOME=/home/u bash "$scripts/guard.sh" >/dev/null 2>&1
  check "guard/broken-$1" "$2" "$?"
}
gdiag git-status        0 Bash '{"command":"git status"}'
gdiag git-diff-sources  0 Bash '{"command":"git diff .claude/sources/instances/x.md"}'
gdiag git-log           0 Bash '{"command":"git log --oneline -5 -- .claude/sources"}'
gdiag git-show          0 Bash '{"command":"git show HEAD:.claude/sources/instances/x.md"}'
gdiag sources-show      0 Bash "{\"command\":\"bash $plugin/scripts/sources.sh show x\"}"
gdiag sources-list      0 Bash "{\"command\":\"bash $plugin/scripts/sources.sh list\"}"
gdiag sources-list-other-clone 2 Bash '{"command":"bash ~/src/wiki-tools/plugins/wiki/scripts/sources.sh list"}'
gdiag sources-settings  2 Bash "{\"command\":\"bash $plugin/scripts/sources.sh settings\"}"
gdiag lint              2 Bash "{\"command\":\"bash $plugin/scripts/lint.sh\"}"
gdiag git-diff-output   2 Bash '{"command":"git diff --output=/tmp/x"}'
gdiag git-status-chain  2 Bash '{"command":"git status && rm -rf wiki"}'
gdiag git-status-redir  2 Bash '{"command":"git status > wiki/x.md"}'
gdiag git-commit        2 Bash '{"command":"git commit -m x"}'
gdiag write-md          2 Write '{"file_path":"/home/u/wikis/mywiki/wiki/a.md","content":"x"}'
msg=$(printf '{"session_id":"t","cwd":"/x","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"},"tool_use_id":"x"}' |
  CLAUDE_PROJECT_DIR="$tmp/gb" HOME=/home/u bash "$scripts/guard.sh" 2>&1)
case "$msg" in *'its first line is "key: x"'*'Read still works'*) r=ok ;; *) r="$msg" ;; esac
check "guard/broken-message" ok "$r"
win='{"session_id":"t","cwd":"C:\\Users\\u\\wikis\\mywiki","hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"C:\\Users\\u\\Pictures\\Receipts\\a.txt","content":"x"},"tool_use_id":"x"}'
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

# proton-drive/read.sh against the fake CLI, in a throwaway wiki with two
# proton-drive instances ("drive"; "plans", whose root has a space) and a gmail one.
pdr="$here/../plugins/wiki/sources/proton-drive/read.sh"
git -C "$tmp" init -q pdw
mkdir -p "$tmp/pdw/.claude/sources/instances"
printf -- '---\nkey: drive\ntype: proton-drive\nroots:\n  - /my-files/Archive\n  - /my-files/Projects/manual.pdf\n---\n' > "$tmp/pdw/.claude/sources/instances/drive.md"
printf -- '---\nkey: plans\ntype: proton-drive\nroots:\n  - /my-files/Projects/alpha/plan 2026\n---\n' > "$tmp/pdw/.claude/sources/instances/plans.md"
printf -- '---\nkey: mail\ntype: gmail\nlabels: X\n---\n' > "$tmp/pdw/.claude/sources/instances/mail.md"
pdn() { (cd "$tmp/pdw" && HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$pdr" "$@" 2>&1); }
pdnx() { (cd "$tmp/pdw" && HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$pdr" "$@" >/dev/null 2>&1); echo $?; }
plan='/my-files/Projects/alpha/plan 2026'

check "proton-drive/list"                 "FAKE filesystem list --json /my-files/Archive/2026" "$(pdn drive list /my-files/Archive/2026)"
check "proton-drive/list-space"           "FAKE filesystem list --json $plan/offers" "$(pdn plans list "$plan/offers")"
check "proton-drive/size"                 "FAKE filesystem size --json $plan" "$(pdn plans size "$plan")"
out=$(pdn drive download "/my-files/Archive/2026/contract.pdf" | head -n 1)
check "proton-drive/download-to-key"      "FAKE filesystem download --json -f remove -d merge /my-files/Archive/2026/contract.pdf $tmp/home/.cache/wiki-sources/pdw/drive/2026" "$out"
out=$(pdn plans download "$plan/a.pdf" | head -n 1)
check "proton-drive/download-top-level"   "FAKE filesystem download --json -f remove -d merge $plan/a.pdf $tmp/home/.cache/wiki-sources/pdw/plans" "$out"
out=$(pdn drive download "/my-files/Projects/manual.pdf")
check "proton-drive/download-file-root"   "FAKE filesystem download --json -f remove -d merge /my-files/Projects/manual.pdf $tmp/home/.cache/wiki-sources/pdw/drive" "$(printf '%s\n' "$out" | head -n 1)"
check "proton-drive/download-file-root-msg" "proton-drive: downloaded to $tmp/home/.cache/wiki-sources/pdw/drive/manual.pdf" "$(printf '%s\n' "$out" | tail -n 1)"
check "proton-drive/refuse-download-folder" 1 "$(pdnx plans download "$plan/offers")"
check "proton-drive/refuse-download-root" 1 "$(pdnx plans download "$plan")"
check "proton-drive/refuse-outside"       1 "$(pdnx drive list /my-files/Projects)"
check "proton-drive/refuse-sibling"       1 "$(pdnx plans list "$plan-old")"
check "proton-drive/refuse-dotdot"        1 "$(pdnx drive list /my-files/Archive/../Projects)"
check "proton-drive/refuse-relative"      1 "$(pdnx drive list my-files/Archive)"
check "proton-drive/refuse-write-ops"     "1 1 1" "$(pdnx drive upload /my-files/Archive) $(pdnx drive trash /my-files/Archive/a.pdf) $(pdnx drive delete /my-files/Archive/a.pdf)"
check "proton-drive/refuse-two-args"      1 "$(pdnx list /my-files/Archive)"
check "proton-drive/refuse-extra-args"    1 "$(pdnx drive list /my-files/Archive --force)"
check "proton-drive/refuse-wrong-type"    1 "$(pdnx mail list /my-files/Archive)"
check "proton-drive/refuse-no-instance"   1 "$(pdnx nosuch list /my-files/Archive)"
check "proton-drive/refuse-outside-git"   1 "$(cd "$tmp" && PATH="$fakebin:$PATH" bash "$pdr" drive list /my-files/Archive >/dev/null 2>&1; echo $?)"
printf '/my-files\n' > "$tmp/pdw/.claude/proton-roots"
check "proton-drive/ignore-proton-roots"  1 "$(pdnx proton list /my-files)"
rm "$tmp/pdw/.claude/proton-roots"
out=$(cd "$tmp/pdw" && FAKE_PD_SYNTAX=changed HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$pdr" drive download /my-files/Archive/a.pdf 2>&1; echo "exit=$?")
case "$out" in *"syntax changed"*exit=1) r=refused ;; *) r="not refused: $out" ;; esac
check "proton-drive/refuse-changed-syntax" refused "$r"
# new: walk the roots against the fake's canned tree (FAKE_PD_TREE=1).
pdtree() { (cd "$tmp/pdw" && FAKE_PD_TREE=1 HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$pdr" "$@" 2>&1); }
out=$(pdtree drive new 2026-10-20)
check "proton-drive/new-same-day"       yes "$(printf '%s\n' "$out" | grep -qxF 'f 2026-10-20 15:21 12 /my-files/Archive/2026/contract.pdf' && echo yes)"
check "proton-drive/new-quoted-name"    yes "$(printf '%s\n' "$out" | grep -qxF 'f 2026-10-20 12:00 21 /my-files/Archive/a "quoted" name.pdf' && echo yes)"
check "proton-drive/new-deep-escaped"   yes "$(printf '%s\n' "$out" | grep -qxF 'f 2026-10-25 07:00 8 /my-files/Archive/2026/sub\/slash/deep.pdf' && echo yes)"
check "proton-drive/new-proton-doc"     yes "$(printf '%s\n' "$out" | grep -qxF 'p 2026-10-21 09:30 5 /my-files/Archive/Notes' && echo yes)"
check "proton-drive/new-file-root"      yes "$(printf '%s\n' "$out" | grep -qxF 'f 2026-10-22 08:00 10 /my-files/Projects/manual.pdf' && echo yes)"
check "proton-drive/new-older-dropped"  no  "$(printf '%s\n' "$out" | grep -q 'old.pdf' && echo yes || echo no)"
check "proton-drive/new-no-folders"     no  "$(printf '%s\n' "$out" | grep -q '^d ' && echo yes || echo no)"
check "proton-drive/new-undecryptable"  yes "$(printf '%s\n' "$out" | grep -q 'cannot be decrypted' && echo yes)"
check "proton-drive/new-walk-count"     yes "$(printf '%s\n' "$out" | grep -qxF 'proton-drive: walked 3 folders' && echo yes)"
check "proton-drive/new-sorted"         "2026-10-20 2026-10-20 2026-10-21 2026-10-22 2026-10-25" "$(printf '%s\n' "$out" | grep '^[fp] ' | cut -d' ' -f2 | paste -sd' ' -)"
check "proton-drive/new-never"          yes "$(pdtree drive new never | grep -q 'old.pdf' && echo yes)"
check "proton-drive/new-bad-date"       1 "$(cd "$tmp/pdw" && FAKE_PD_TREE=1 PATH="$fakebin:$PATH" bash "$pdr" drive new yesterday >/dev/null 2>&1; echo $?)"
check "proton-drive/new-path-not-date"  1 "$(cd "$tmp/pdw" && FAKE_PD_TREE=1 PATH="$fakebin:$PATH" bash "$pdr" drive new /my-files/Archive >/dev/null 2>&1; echo $?)"
out=$(cd "$tmp/pdw" && FAKE_PD_FORMAT=changed FAKE_PD_TREE=1 PATH="$fakebin:$PATH" bash "$pdr" drive new never 2>&1; echo "exit=$?")
case "$out" in *"no longer has the shape"*exit=1) r=refused ;; *) r="$out" ;; esac
check "proton-drive/new-format-changed" refused "$r"

# lint.sh against the fixture wiki in tests/lint-wiki (one planted problem per check).
cp -r "$here/lint-wiki" "$tmp/lw"
git -C "$tmp/lw" init -q
lint_out=$(cd "$tmp/lw" && WIKI_LINT_TODAY=2026-10-16 bash "$scripts/lint.sh" 2>&1)
expect() { # NAME TEXT
  case "$lint_out" in *"$2"*) r=found ;; *) r=missing ;; esac
  check "lint/$1" found "$r"
}
expect summary            'Pages: 6. Errors: 4. Warnings: 10. Info: 1.'
expect no-frontmatter     '`topics/no-frontmatter.md`: no YAML frontmatter'
expect missing-fields     '`tasks/missing-fields.md`: missing title sources'
expect broken-alias       '`[[missing-page]]` (no such page) linked from `people/broken-person.md`'
expect broken-path-anchor '`[[also-missing]]` (no such page)'
expect orphan             '`topics/no-frontmatter.md`: no inbound links from other pages'
expect not-in-index       '`tasks/missing-fields.md`: not listed in index.md'
expect no-sources         '`notes/no-sources.md`: `sources:` is empty'
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
case "$findings" in *broken-person]]*) r=flagged ;; *) r=clean ;; esac
check "lint/case-insensitive-links" clean "$r"
case "$lint_out" in *"matches no source"*) r=flagged ;; *) r=clean ;; esac
check "lint/no-prefix-check-without-instances" clean "$r"
# status_as_of: required only for types whose template has it.
case "$lint_out" in *'broken-person.md` (person): no `status_as_of`'*) r=flagged ;; *) r=clean ;; esac
check "lint/status-not-required-by-template" clean "$r"
rm "$tmp/lw/templates/decision.md"
lint_nt=$(cd "$tmp/lw" && WIKI_LINT_TODAY=2026-10-16 bash "$scripts/lint.sh" 2>&1)
case "$lint_nt" in *'no `status_as_of`'*) r=flagged ;; *) r=clean ;; esac
check "lint/status-type-from-template" clean "$r"
# The same wiki with a gmail instance: citations must match a source.
cp -r "$here/lint-wiki" "$tmp/lw2"
git -C "$tmp/lw2" init -q
mkdir -p "$tmp/lw2/.claude/sources/instances"
printf -- '---\nkey: gmail\ntype: gmail\nlabels: X\n---\n' > "$tmp/lw2/.claude/sources/instances/gmail.md"
mkdir -p "$tmp/lw2/raw"; printf 'last_checked_raw: never\nlast_checked_web: never\n' > "$tmp/lw2/raw/sync-log.md"
printf -- '---\ntitle: Cites\ntype: note\nsources:\n  - "Gmail: A (2026-09-01)"\n  - "Proton: x.pdf, p. 1"\n  - raw/a.pdf\n  - "raw: b.pdf, p. 2"\n  - "web: example.com, buyer guide"\n  - "User statement (2026-10-01)"\n  - https://example.com\nrelated: []\ncreated: 2026-10-01\nupdated: 2026-10-01\n---\n' > "$tmp/lw2/wiki/cites.md"
lint2=$(cd "$tmp/lw2" && WIKI_LINT_TODAY=2026-10-16 bash "$scripts/lint.sh" 2>&1)
case "$lint2" in *'`cites.md`: source `Proton: x.pdf, p. 1` matches no source of this wiki'*) r=found ;; *) r=missing ;; esac
check "lint/unknown-source-prefix" found "$r"
n=$(printf '%s\n' "$lint2" | grep -c 'matches no source')
check "lint/known-prefixes-pass" 2 "$n"   # cites.md Proton + broken-person.md "Proton Drive"
# Case-insensitive prefixes, "Local file: raw/", and as_of pages.
printf -- '---\ntitle: Cites2\ntype: note\nsources:\n  - "Web: example.com"\n  - "gmail: B (2026-09-02)"\n  - "Local file: raw/a.pdf"\nrelated: []\ncreated: 2026-10-01\nupdated: 2026-10-01\n---\n[[cites]]\n' > "$tmp/lw2/wiki/cites2.md"
printf -- '---\ntitle: Old analysis\ntype: research\nsources:\n  - raw/a.pdf\nrelated: []\ncreated: 2026-01-01\nupdated: 2026-01-01\nas_of: 2026-01-01\n---\nThe offer is still pending.\n' > "$tmp/lw2/wiki/old-analysis.md"
printf -- '---\ntitle: Old note\ntype: research\nsources:\n  - raw/a.pdf\nrelated: []\ncreated: 2026-01-01\nupdated: 2026-01-01\nas_of: soon\n---\nThe offer is still pending.\n' > "$tmp/lw2/wiki/old-note.md"
lint3=$(cd "$tmp/lw2" && WIKI_LINT_TODAY=2026-10-16 bash "$scripts/lint.sh" 2>&1)
check "lint/prefix-case-and-local-file" absent "$(printf '%s\n' "$lint3" | grep -q 'cites2.md`: source' && echo present || echo absent)"
check "lint/as-of-not-stale" absent "$(printf '%s\n' "$lint3" | grep -q 'old-analysis.md`: updated' && echo present || echo absent)"
check "lint/as-of-bad-date" present "$(printf '%s\n' "$lint3" | grep -q 'old-note.md`: `as_of: soon` is not a YYYY-MM-DD date' && echo present || echo absent)"

# log.md: its links aren't checked (old entries keep renamed pages' names);
# removed or changed lines are errors, appended entries are not.
check "lint/log-links-not-checked" absent "$(printf '%s\n' "$lint_out" | grep -q 'ghost-from-log' && echo present || echo absent)"
git -C "$tmp/lw" add -A
git -C "$tmp/lw" -c user.name=t -c user.email=t@t commit -qm init
lintlog() { (cd "$tmp/lw" && WIKI_LINT_TODAY=2026-10-16 bash "$scripts/lint.sh" 2>&1) | sed -n '/^### ERROR: wiki\/log.md/,/^###/p'; }
printf '# Log\n## 2026-10-16 | ingest | new\n## 2026-01-01 | init | [[ghost-from-log]]\n' > "$tmp/lw/wiki/log.md"
check "lint/log-append-ok" "" "$(lintlog)"
git -C "$tmp/lw" -c user.name=t -c user.email=t@t commit -qam append
sed -i 's/| init |/| init (edited) |/' "$tmp/lw/wiki/log.md"
case "$(lintlog)" in *'uncommitted changes remove or rewrite 1 line(s)'*) r=found ;; *) r=missing ;; esac
check "lint/log-uncommitted-edit" found "$r"
git -C "$tmp/lw" -c user.name=t -c user.email=t@t commit -qam "Rewrite log"
case "$(lintlog)" in *'commit '*'Rewrite log) removes or rewrites 1 line(s)'*) r=found ;; *) r=missing ;; esac
check "lint/log-committed-edit" found "$r"
check "lint/log-append-commit-ok" 1 "$(lintlog | grep -c '^- commit')"

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
case "$ss_out" in *"- gmail: never checked (manual key: enters via raw/ or user statements)"*) r=ok ;; *) r="$ss_out" ;; esac
check "sync-status/manual-never" ok "$r"
case "$ss_out" in *"days ago) (manual key"*) r=ok ;; *) r="$ss_out" ;; esac
check "sync-status/manual-dated" ok "$r"

# wiki-check.sh: a freshly initialised wiki passes; each planted fault fails.
mkwiki() { # DIR
  git -C "$tmp" init -q "$1"
  w="$tmp/$1"
  mkdir -p "$w/raw" "$w/wiki/notes" "$w/outputs" "$w/templates" "$w/.claude"
  printf '# Test wiki\n\n## Purpose\n\nTesting.\n' > "$w/CLAUDE.md"
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
  sed "s|  \"enabledPlugins\"|  \"x-source-rules\": [$rules],\n  \"enabledPlugins\"|" "$here/../plugins/wiki/templates/project-settings.json" > "$w/.claude/settings.json"
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

mkwiki f1; printf '@~/src/wiki-tools/schema/wiki-layout.md\n' >> "$tmp/f1/CLAUDE.md"
wc_expect old-import f1 "FAIL CLAUDE.md still imports the schema by path: @~/src/wiki-tools/schema/wiki-layout.md"
wc_expect no-import good "PASS CLAUDE.md has no schema imports"
check "wiki-check/fault-exits-1" 1 "$(wc_exit f1)"

mkwiki f2; printf 'last_checked_web: soon\n' >> "$tmp/f2/raw/sync-log.md"
wc_expect bad-sync-value f2 "FAIL \`last_checked_web: soon\` in raw/sync-log.md"

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
mkwiki f16; printf '\nNotes.\n' >> "$tmp/f16/.claude/sources/instances/scans.md"
wc_expect instance-dirty f16 'FAIL `.claude/sources/instances/scans.md` has uncommitted changes'
mkwiki f17; sed -i 's/"wiki@wiki-tools": true/"wiki@wiki-tools": true /' "$tmp/f17/.claude/settings.json"
wc_expect settings-dirty f17 'FAIL `.claude/settings.json` has uncommitted changes'
mkwiki f18; sed -i '/last_checked_raw/d' "$tmp/f18/raw/sync-log.md"
wc_expect no-raw-line f18 'FAIL raw/sync-log.md has no `last_checked_raw` line'

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
check "lib-source/values-scalar"    "Receipts" "$(lsrun 'src_values .claude/sources/instances/loc1.md labels')"
check "lib-source/values-list"      "/data/one ~/two" "$(lsrun 'src_values .claude/sources/instances/good.md roots | paste -sd" " -')"
check "lib-source/names"            "roots note" "$(lsrun 'src_list "$SRC_PLUGIN/sources/std/SOURCE.md" parameters | src_names | paste -sd" " -')"
check "lib-source/instances"        "bad-root good loc1 missing-param unknown-type uses-broken wrong-key" "$(lsrun 'src_instances "$PWD" | paste -sd" " -')"
check "lib-source/contract-std"     "$tmp/ls/plugin/sources/std/SOURCE.md" "$(lsrun 'src_contract "$PWD" std')"
check "lib-source/contract-local"   "$lsw/.claude/sources/types/loc/SOURCE.md" "$(lsrun 'src_contract "$PWD" loc')"
check "lib-source/contract-unknown" 1 "$(lsrun 'src_contract "$PWD" nosuch >/dev/null 2>&1; echo $?')"
check "lib-source/contract-badname" 1 "$(lsrun 'src_contract "$PWD" ../std >/dev/null 2>&1; echo $?')"
check "lib-source/catalog"          "loc:local std:standard" "$(lsrun 'src_catalog "$PWD" | cut -f1,2 | tr "\t" : | grep -v broken | sort | paste -sd" " -')"
check "lib-source/valid-std"        0 "$(lsrun 'src_validate_contract "$SRC_PLUGIN/sources/std/SOURCE.md"; echo $?')"
mkdir -p "$tmp/cut/std" && sed '/^## Fetch$/,$d' "$tmp/ls/plugin/sources/std/SOURCE.md" > "$tmp/cut/std/SOURCE.md" && touch "$tmp/cut/std/read.sh"
out=$(lsrun "src_validate_contract '$tmp/cut/std/SOURCE.md'; echo \$?")
case "$out" in *"missing section '## Fetch'"*"missing section '## Caveats'"*1) r=refused ;; *) r="$out" ;; esac
check "lib-source/cut-body"         refused "$r"
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

# sources.sh against a copy of guard-wiki (gmail, scans, teams, local type books).
cp -r "$here/guard-wiki" "$tmp/sw"
git -C "$tmp/sw" init -q
mkdir -p "$tmp/sw/raw"
printf 'last_checked_gmail: 2026-10-01\nlast_checked_raw: never\nlast_checked_web: 2026-10-02\n' > "$tmp/sw/raw/sync-log.md"
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
sexpect list-manual     '- web: manual key (no source file; enters via raw/ or user statements; /wiki:ingest cannot read it), last checked: 2026-10-02' list
sexpect show-header     'Source scans: valid' show scans
sexpect show-instance   '  - ~/Pictures/Receipts' show scans
sexpect show-contract   '# Source type: Local folder' show scans
sexpect show-raw        'raw is built in' show raw
sexpect show-unknown    "no source 'nosuch' in this wiki" show nosuch
sexpect catalog         '- bookish (local, script): Bookish (local test type)' catalog
sexpect contract        'type: gmail' contract gmail
sexpect settings-allow  '"Bash(bash .claude/sources/types/bookish/fetch.sh *)",' settings
sexpect settings-deny   '"mcp__claude_ai_Gmail__send_message",' settings
sexpect settings-type   '"Bash(bash */sources/local-folder/read.sh *)"' settings local-folder
sexpect contract-root   "bash $plugin/sources/local-folder/read.sh <key> list" contract local-folder
out=$(srun contract local-folder)
case "$out" in *'${CLAUDE_PLUGIN_ROOT}'*) r=left ;; *) r=filled ;; esac
check "sources/contract-root-filled" filled "$r"
sexpect settings-gdrive '"mcp__claude_ai_Google_Drive__trash_file"' settings google-drive
sexpect catalog-gdrive  '- google-drive (standard, mcp): Google Drive' catalog
sexpect catalog-teams   '- ms-teams (standard, mcp): Microsoft Teams' catalog
sexpect settings-teams-deny  '"mcp__claude_ai_Microsoft_365__teams_send_chat_message"' settings ms-teams
sexpect settings-teams-edit  '"Edit(~/.cache/wiki-sources/*/*/walk.tsv)"' settings ms-teams
sexpect settings-teams-script '"Bash(bash */sources/ms-teams/snapshot.sh *)"' settings ms-teams
# Every standard contract validates.
for c in "$here"/../plugins/wiki/sources/*/SOURCE.md; do
  t=$(basename "$(dirname "$c")")
  r=$(bash -c '. "$1"; src_validate_contract "$2" 2>&1 && echo valid' _ "$scripts/lib-source.sh" "$c")
  check "contract/$t-valid" valid "$r"
done
# Check needed: the instance file changed since the last ingest.
sexpect check-uncommitted 'Check needed: the instance file has uncommitted changes since the last ingest (2026-10-01).' show gmail
swc() { # DATE MESSAGE: commit everything in the sw wiki at that time
  git -C "$tmp/sw" add -A >/dev/null 2>&1
  GIT_COMMITTER_DATE="$1" GIT_AUTHOR_DATE="$1" git -C "$tmp/sw" -c user.name=t -c user.email=t@t commit -qm "$2" >/dev/null 2>&1
}
swc 2026-10-01T10:00:00 init
check "sources/check-same-commit" absent "$(srun show gmail | grep -q 'Check needed' && echo present || echo absent)"
printf '\nNotes.\n' >> "$tmp/sw/.claude/sources/instances/gmail.md"; swc 2026-10-01T15:00:00 'edit instance'
sexpect check-committed-after "Check needed: the instance file changed (2026-10-01) since the last ingest (2026-10-01)." show gmail
sed -i 's/^last_checked_gmail: .*/last_checked_gmail: 2026-10-02/' "$tmp/sw/raw/sync-log.md"; swc 2026-10-02T09:00:00 ingest
check "sources/check-not-needed" absent "$(srun show gmail | grep -q 'Check needed' && echo present || echo absent)"
check "sources/check-not-for-never" absent "$(srun show books | grep -q 'Check needed' && echo present || echo absent)"
# Placeholders in parameter values.
for v in FOLDER-ID-TBD '<label>' 'todo' '?' '...'; do
  printf -- '---\nkey: ph\ntype: gmail\nlabels: %s\n---\n' "$v" > "$tmp/sw/.claude/sources/instances/ph.md"
  check "sources/placeholder-$v" found "$(srun show ph | grep -q "parameter 'labels' holds a placeholder" && echo found)"
done
printf -- '---\nkey: ph\ntype: gmail\nlabels: Todoroki\nsenders:\n  - xxl@example.com\n---\n' > "$tmp/sw/.claude/sources/instances/ph.md"
check "sources/placeholder-word-inside" valid "$(srun show ph | grep -q '^Source ph: valid' && echo valid)"
rm "$tmp/sw/.claude/sources/instances/ph.md"
# Leave bookish only a platform that isn't this host's.
other=$(bash -c '. "$1"; [ "$(src_platform)" = linux ] && echo macos || echo linux' _ "$scripts/lib-source.sh")
sed -i "/^  - \(linux\|macos\|windows\)$/d; s/^platforms:/platforms:\n  - $other/" "$tmp/sw/.claude/sources/types/bookish/SOURCE.md"
sexpect show-platform   "isn't available on" show books
printf -- '---\nkey: bad\ntype: gmail\n---\n' > "$tmp/sw/.claude/sources/instances/bad.md"
sed -i 's/^key: bad/key: worse/' "$tmp/sw/.claude/sources/instances/bad.md"
sexpect show-invalid    "doesn't validate" show bad

# install-source-file.sh against a throwaway wiki (the user's installer).
isf="$scripts/install-source-file.sh"
git -C "$tmp" init -q iw
printf '# W\n' > "$tmp/iw/CLAUDE.md"
mkdir -p "$tmp/iw/.claude"
printf '{\n  "permissions": {\n    "allow": [\n      "mcp__claude_ai_Gmail__search_threads"\n    ]\n  }\n}\n' > "$tmp/iw/.claude/settings.json"
inst() { # ANSWER TARGET CONTENT: run with the content on stdin; prints output, then exit code
  out=$(cd "$tmp/iw" && printf '%b' "$3" | env -u CLAUDECODE WIKI_INSTALL_ANSWER="$1" bash "$isf" "$2" 2>&1)
  printf '%s\n@%s' "$out" "$?"
}
iexpect() { # NAME TEXT EXIT ANSWER TARGET CONTENT
  n=$1 t=$2 x=$3; shift 3
  o=$(inst "$@")
  case "$o" in *"$t"*"@$x") r=ok ;; *) r="$o" ;; esac
  check "install/$n" ok "$r"
}
gm='---\nkey: gmail\ntype: gmail\nlabels: Projects\n---\n\nNotes.\n'
iexpect no-frontmatter  'first line pasted: "key: gmail"' 1 y instances/gmail.md 'key: gmail\ntype: gmail\n'
[ -f "$tmp/iw/.claude/sources/instances/gmail.md" ] && r=written || r=absent
check "install/no-frontmatter-not-written" absent "$r"
iexpect key-mismatch    "key 'mail' doesn't match the file name" 1 y instances/gmail.md '---\nkey: mail\ntype: gmail\nlabels: X\n---\n'
iexpect unknown-type    "unknown source type 'nosuch' (looked in" 1 y instances/x.md '---\nkey: x\ntype: nosuch\n---\n'
iexpect bad-target      'target must be instances/<key>.md' 1 y sources/instances/gmail.md "$gm"
iexpect dotdot-target   'must be a plain name' 1 y 'types/bookish/../x.sh' 'x\n'
iexpect standard-name   "'gmail' is a standard type" 1 y types/gmail/SOURCE.md 'x\n'
iexpect empty-paste     'nothing pasted' 1 y instances/gmail.md ''
iexpect answer-no       'Not installed.' 1 n instances/gmail.md "$gm"
o=$(cd "$tmp/iw" && printf '%b' "$gm" | CLAUDECODE=1 WIKI_INSTALL_ANSWER=y bash "$isf" instances/gmail.md 2>&1; printf '@%s' "$?")
case "$o" in *'outside Claude'*@1) r=ok ;; *) r="$o" ;; esac
check "install/refused-in-claude" ok "$r"
iexpect gmail-new       'New file .claude/sources/instances/gmail.md' 0 y instances/gmail.md "$gm"
iexpect gmail-rules     '"mcp__claude_ai_Gmail__send_message",' 0 y instances/gmail.md "${gm}More.\n"
o=$(inst y instances/gmail.md "${gm}More.\n")
case "$o" in *'"mcp__claude_ai_Gmail__search_threads"'*) r=listed ;; *) r=omitted ;; esac
check "install/present-rule-omitted" omitted "$r"
iexpect unchanged       'already exactly this' 0 y instances/gmail.md "${gm}More.\n"
iexpect diff-shown      '+Changed.' 0 y instances/gmail.md "${gm}Changed.\n"
iexpect crlf            'Installed' 0 y instances/gmail.md '---\r\nkey: gmail\r\ntype: gmail\r\nlabels: Y\r\n---\r\n'
grep -q $'\r' "$tmp/iw/.claude/sources/instances/gmail.md" && r=crlf || r=lf
check "install/crlf-stripped" lf "$r"
iexpect fs-no-roots     "required parameter 'roots' is empty" 1 y instances/scans.md '---\nkey: scans\ntype: local-folder\n---\n'
bk=$(sed 's/$/\\n/' "$here/guard-wiki/.claude/sources/types/bookish/SOURCE.md" | tr -d '\n')
iexpect cut-contract    "missing section '## Resolve citation'" 1 y types/bookish/SOURCE.md "$(printf '%s' "$bk" | sed 's/## Resolve citation.*//')"
[ -f "$tmp/iw/.claude/sources/types/bookish/SOURCE.md" ] && r=written || r=absent
check "install/cut-contract-not-written" absent "$r"
iexpect script-first    "SOURCE.md doesn't exist yet" 1 y types/bookish/fetch.sh '#!/bin/bash\n'
iexpect contract-note   "script 'fetch.sh' is listed but missing (install it next)" 0 y types/bookish/SOURCE.md "$bk"
iexpect script-unlisted "other.sh isn't listed under scripts" 1 y types/bookish/other.sh '#!/bin/bash\n'
iexpect script-ok       'Installed .claude/sources/types/bookish/fetch.sh' 0 y types/bookish/fetch.sh '#!/bin/bash\necho hi\n'
iexpect local-instance  'Installed .claude/sources/instances/books.md' 0 y instances/books.md '---\nkey: books\ntype: bookish\nshelf: Byg\n---\n'
iexpect breaks-other    "required parameter 'colour' is empty" 1 y types/bookish/SOURCE.md "$(printf '%s' "$bk" | sed 's/  - shelf (required): shelf name/  - shelf (required): shelf name\\n  - colour (required): x/')"
[ -z "$(git -C "$tmp/iw" status --porcelain -- .claude/sources | grep -v '^??')" ] && r=untouched || r=staged
check "install/no-git" untouched "$r"
# decode-download.sh against the installer's wiki (instance gmail exists).
dds="$scripts/decode-download.sh"
dd() { (cd "$tmp/iw" && HOME="$tmp/home" bash "$dds" "$@" 2>&1); printf '@%s' "$?"; }
mkdir -p "$tmp/dd"
want=$(printf '<mxfile>\n  <diagram name="Plan"/>\n</mxfile>\n')
printf '%s' "$want" | base64 > "$tmp/dd/plain.b64"                    # wrapped base64, as written with Write
printf '{"content":"%s","mimeType":"application/xml"}' "$(printf '%s' "$want" | base64 | tr -d '\n' | sed 's#/#\\/#g')" > "$tmp/dd/saved.json"
printf '[{"type":"text","text":"{\\"content\\":\\"%s\\"}"}]' "$(printf '%s' "$want" | base64 | tr -d '\n')" > "$tmp/dd/nested.json"
out="$tmp/home/.cache/wiki-sources/iw/gmail/Projects/plan.drawio"
for k in plain.b64 saved.json nested.json; do
  rm -f "$out"
  o=$(dd gmail "$tmp/dd/$k" Projects/plan.drawio)
  case "$o" in *"wrote $out"*@0) [ "$(cat "$out")" = "$want" ] && r=ok || r="content differs" ;; *) r="$o" ;; esac
  check "decode-download/$k" ok "$r"
done
check "decode-download/refuse-dotdot"   1 "$(dd gmail "$tmp/dd/plain.b64" ../../x.drawio | tail -n 1 | sed "s/.*@//")"
check "decode-download/refuse-absolute" 1 "$(dd gmail "$tmp/dd/plain.b64" /tmp/x.drawio | tail -n 1 | sed "s/.*@//")"
check "decode-download/refuse-no-key"   1 "$(dd nosuch "$tmp/dd/plain.b64" a.drawio | tail -n 1 | sed "s/.*@//")"
printf 'not base64 at all!\n' > "$tmp/dd/bad.txt"
check "decode-download/refuse-not-b64"  1 "$(dd gmail "$tmp/dd/bad.txt" a.drawio | tail -n 1 | sed "s/.*@//")"
check "decode-download/refuse-args"     1 "$(dd gmail "$tmp/dd/plain.b64" | tail -n 1 | sed "s/.*@//")"
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

# ms-teams/snapshot.sh against a throwaway wiki and cache.
mts="$here/../plugins/wiki/sources/ms-teams/snapshot.sh"
git -C "$tmp" init -q mtw
mkdir -p "$tmp/mtw/.claude/sources/instances"
printf -- '---\nkey: teams\ntype: ms-teams\nfolders:\n  - Files | file:///b!d/\n---\n' > "$tmp/mtw/.claude/sources/instances/teams.md"
printf -- '---\nkey: mail\ntype: gmail\nlabels: X\n---\n' > "$tmp/mtw/.claude/sources/instances/mail.md"
mtc="$tmp/mthome/.cache/wiki-sources/mtw/teams"
mkdir -p "$mtc"
mt() { (cd "$tmp/mtw" && HOME="$tmp/mthome" bash "$mts" "$@" 2>&1); }
mtx() { (cd "$tmp/mtw" && HOME="$tmp/mthome" bash "$mts" "$@" >/dev/null 2>&1); echo $?; }
walk() { printf '%b' "$1" > "$mtc/walk.tsv"; }
check "ms-teams/refuse-unknown-op"   1 "$(mtx teams delete)"
check "ms-teams/refuse-extra-args"   1 "$(mtx teams compare --force)"
check "ms-teams/refuse-no-instance"  1 "$(mtx nosuch compare)"
check "ms-teams/refuse-bad-key"      1 "$(mtx ../x compare)"
check "ms-teams/refuse-wrong-type"   1 "$(mtx mail compare)"
check "ms-teams/refuse-outside-git"  1 "$(cd "$tmp" && HOME="$tmp/mthome" bash "$mts" teams compare >/dev/null 2>&1; echo $?)"
check "ms-teams/refuse-no-walk"      1 "$(mtx teams compare)"
walk 'file:///b!d/1\tFiles/a.pdf\t10\nfile:///b!d/2\tFiles/b.docx\n'
check "ms-teams/refuse-two-fields"   1 "$(mtx teams compare)"
walk 'file:///b!d/1\tFiles/a.pdf\tten\n'
check "ms-teams/refuse-bad-size"     1 "$(mtx teams compare)"
walk 'file:///b!d/1\tFiles/a.pdf\t10\nfile:///b!d/1\tFiles/copy.pdf\t10\n'
case "$(mt teams compare)" in *'repeats URI file:///b!d/1'*) r=refused ;; *) r=accepted ;; esac
check "ms-teams/refuse-duplicate-uri" refused "$r"
walk 'file:///b!d/1\tFiles/a.pdf\t10\r\nfile:///b!d/2\tFiles/AP/plan 2026.pptx\t20\r\n\r\n'
out=$(mt teams compare)
case "$out" in *'no files.tsv yet'*) r=ok ;; *) r="$out" ;; esac
check "ms-teams/first-run-note"      ok "$r"
check "ms-teams/first-run-new"       2 "$(printf '%s\n' "$out" | grep -c '^new	')"
check "ms-teams/crlf-path-spaces"    "new	Files/AP/plan 2026.pptx	20" "$(printf '%s\n' "$out" | grep plan)"
check "ms-teams/compare-no-write"    absent "$([ -f "$mtc/files.tsv" ] && echo present || echo absent)"
out=$(mt teams save)
check "ms-teams/save"                "ms-teams snapshot: saved 2 files to $mtc/files.tsv" "$out"
check "ms-teams/save-removes-walk"   absent "$([ -f "$mtc/walk.tsv" ] && echo present || echo absent)"
grep -q $'\r' "$mtc/files.tsv" && r=crlf || r=lf
check "ms-teams/save-strips-cr"      lf "$r"
walk 'file:///b!d/2\tFiles/AP/plan 2026.pptx\t25\nfile:///b!d/3\tFiles/new.md\t5\n'
out=$(mt teams compare)
check "ms-teams/new"                 "new	Files/new.md	5" "$(printf '%s\n' "$out" | grep '^new')"
check "ms-teams/changed"             "changed	Files/AP/plan 2026.pptx	25 (was 20)" "$(printf '%s\n' "$out" | grep '^changed')"
check "ms-teams/removed"             "removed	Files/a.pdf	10" "$(printf '%s\n' "$out" | grep '^removed')"
check "ms-teams/summary"             "ms-teams snapshot: summary: 1 new, 1 changed, 0 moved, 1 removed, 0 unchanged" "$(printf '%s\n' "$out" | grep summary)"
walk 'file:///b!d/1\tFiles/Archive/a.pdf\t10\nfile:///b!d/2\tFiles/AP/plan 2026.pptx\t20\n'
out=$(mt teams compare)
check "ms-teams/moved"               "moved	Files/Archive/a.pdf	from Files/a.pdf" "$(printf '%s\n' "$out" | grep '^moved')"
check "ms-teams/unchanged-silent"    0 "$(printf '%s\n' "$out" | grep -c 'plan 2026')"
walk ''
out=$(mt teams compare)
case "$out" in *'WARNING: walk.tsv is empty'*) r=warned ;; *) r="$out" ;; esac
check "ms-teams/empty-walk-warns"    warned "$r"
check "ms-teams/empty-walk-removed"  2 "$(printf '%s\n' "$out" | grep -c '^removed')"
printf 'garbage\n' > "$mtc/files.tsv"; walk 'file:///b!d/1\tFiles/a.pdf\t10\n'
check "ms-teams/refuse-bad-snapshot" 1 "$(mtx teams compare)"

# ocr.sh with a fake ocrmypdf that writes its arguments into the sidecar.
ocrbin="$tmp/ocrbin"
mkdir -p "$ocrbin"
cat > "$ocrbin/ocrmypdf" <<'EOF'
#!/usr/bin/env bash
while [ $# -gt 0 ]; do
  case "$1" in -l) langs=$2 ;; --sidecar) side=$2 ;; esac
  shift
done
printf 'langs=%s\n' "$langs" > "$side"
EOF
chmod u+x "$ocrbin/ocrmypdf"
git -C "$tmp" init -q ocrw
printf 'pdf' > "$tmp/ocrw/scan.pdf"
ocr() { (cd "$tmp/ocrw" && PATH="$ocrbin:$PATH" bash "$scripts/ocr.sh" "$@" >/dev/null 2>&1); echo $?; }
check "ocr/default-eng"          "0 langs=eng"     "$(ocr scan.pdf) $(cat "$tmp/ocrw/raw/ocr/scan.txt")"
check "ocr/languages"            "0 langs=dan+eng" "$(ocr scan.pdf dan+eng) $(cat "$tmp/ocrw/raw/ocr/scan.txt")"
check "ocr/refuse-bad-languages" 1 "$(ocr scan.pdf 'dan;rm')"
check "ocr/refuse-extra-args"    1 "$(ocr scan.pdf eng x)"

# No merge-conflict markers anywhere in the plugin (the schema and skills
# reach every wiki session as they are).
r=$(grep -rlE '^(<<<<<<< |=======$|>>>>>>> )' "$scripts/.." 2>/dev/null | head -n 3)
check "plugin/no-conflict-markers" "" "$r"

# schema.sh: one file per call, the plugin root filled in, and each under
# the 10,000-character cap on hook context with room to spare, even with a
# long install path (a Windows plugin cache).
out=$(bash "$scripts/schema.sh" wiki-conventions)
case "$out" in *"Ask for context, don't guess"*) r=ok ;; *) r=missing ;; esac
check "schema/conventions" ok "$r"
out=$(bash "$scripts/schema.sh" wiki-layout)
case "$out" in *"Data model"*) r=ok ;; *) r=missing ;; esac
check "schema/layout" ok "$r"
case "$out" in *'${CLAUDE_PLUGIN_ROOT}'*) r=left ;; *) r=filled ;; esac
check "schema/root-filled" filled "$r"
check "schema/refuse-other-name" 1 "$(bash "$scripts/schema.sh" ../README >/dev/null 2>&1; echo $?)"
long=C:/Users/firstname.lastname/.claude/plugins/cache/wiki-tools/wiki/1.0.0
for s in wiki-conventions wiki-layout; do
  n=$(WIKI_SCHEMA_ROOT=$long bash "$scripts/schema.sh" "$s" | wc -c)
  [ "$n" -le 9000 ] && r=ok || r="$n bytes"
  check "schema/$s-under-9000-bytes" ok "$r"
done
# hooks.json loads every schema file.
for s in "$scripts"/../schema/*.md; do
  s=$(basename "$s" .md)
  grep -qF "schema.sh\\\" $s\"" "$scripts/../hooks/hooks.json" && r=ok || r=missing
  check "schema/hook-$s" ok "$r"
done

printf '\n%d checks, %d failed\n' "$total" "$fail"
[ "$fail" -eq 0 ]
