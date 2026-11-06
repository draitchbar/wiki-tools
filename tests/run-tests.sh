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
# block-push fixtures also run through block_push.py (via the hooks.json
# command and py-launch.sh): exit code and message must match bash, except
# the cases in tests/fixtures/py-stricter.txt. contract.py is checked against
# lib-source.sh (contract-parity). guard.py runs every guard and block-push
# case and must match block-push.sh then guard.sh (gdual). Needs Python 3.9
# or later.

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

# WIKI_TEST_TIMING=1: time each section and print the times at the end.
# EPOCHREALTIME (bash 5) costs no process; its separator may be "." or ",".
sec_name= sec_start=0 sec_checks=0 sec_lines=
now_us() {
  if [ -n "${EPOCHREALTIME:-}" ]; then now=${EPOCHREALTIME//[!0-9]/}
  else now=$(($(date +%s%N) / 1000)); fi
}
section() { # NAME (or "" to close the last one)
  [ -n "${WIKI_TEST_TIMING:-}" ] || return 0
  now_us
  if [ -n "$sec_name" ]; then
    sec_lines+=$(printf '%-15s %8d ms %4d checks' "$sec_name" $(((now - sec_start) / 1000)) $((total - sec_checks)))$'\n'
  fi
  sec_name=$1 sec_start=$now sec_checks=$total
}
section setup

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -r "$here/guard-wiki" "$tmp/gw"
hook() { CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/home/u bash "$scripts/$1.sh"; }

# Python hooks run through the exact command hooks.json gives them (speed
# plan, step 2b), with a test cache folder as CLAUDE_PLUGIN_DATA.
plugin=$(cd "$scripts/.." && pwd)
pycmd() { # NAME: the hooks.json command for a py-launch.sh hook, unescaped
  sed -n 's/^ *"command": "\(\. .*py-launch\.sh\\" '"$1"'\)",\{0,1\}$/\1/p' "$plugin/hooks/hooks.json" | sed 's/\\"/"/g'
}
pyhook() { # NAME [ROOT]: run it as Claude Code would, in $tmp/gw
  CLAUDE_PLUGIN_ROOT="${2:-$plugin}" CLAUDE_PLUGIN_DATA="${PYDATA-$tmp/pdata}" \
    CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/home/u bash -c "$(pycmd "$1")"
}
# Fixture cases where Python is deliberately stricter (tests/fixtures/py-stricter.txt).
py_stricter=$(grep -v '^#' "$here/fixtures/py-stricter.txt")
py_kind() { # DIR/CASE: stricter, message or nothing
  local l
  while IFS= read -r l; do
    case "$l" in "$1 "*) printf '%s' "${l#"$1 "}"; return ;; esac
  done <<< "$py_stricter"
}
pycmp() { # NAME WANT KIND BASH-RESULT PY-RESULT ("<exit> <message>")
  case "$3" in
    stricter|message|locale) check "$1" "$2" "${5%% *}" ;;
    *)        check "$1 (same as bash)" "$4" "$5" ;;
  esac
}
# A Python script run directly, with the interpreter py-launch.sh caches.
pyrun() { # SCRIPT ARGS...
  [ -s "$tmp/pyrun/python" ] || printf '{}' | PYDATA="$tmp/pyrun" pyhook block_push >/dev/null 2>&1
  local py; IFS= read -r py < "$tmp/pyrun/python"
  "$py" -I -S -X utf8 "$scripts/$1.py" "${@:2}"
}
# Pure string functions: keep Git Bash from rewriting /paths and HOME.
pystr() { MSYS2_ARG_CONV_EXCL='*' MSYS2_ENV_CONV_EXCL=HOME pyrun "$@"; }
# Python sees Git Bash's /tmp and /c/... as C:/...; messages map them back.
ptmp=$(pyrun contract expand "$tmp") pplugin=$(pyrun contract expand "$plugin")
pymap() { # Git Bash may hand over either slash style.
  local m=$1
  m=${m//"$ptmp"/$tmp}; m=${m//"${ptmp//\//\\}"/$tmp}
  m=${m//"$pplugin"/$plugin}; printf '%s' "${m//"${pplugin//\//\\}"/$plugin}"
}

# guard.py is compared with what Claude Code gets from the bash hooks:
# block-push.sh's block, else guard.sh's result. Callers set
# CLAUDE_PROJECT_DIR and HOME, and pass results they already have; PYHOME
# gives Python a different HOME (Windows: the C:\Users\... a real session
# hands it). The bash hooks run with LC_COLLATE=C, so their globs sort as
# Python's do: in a real session the locale's order may name a different
# first broken file or guard word (same decision).
run_hook() { # SCRIPT INPUT: "<exit> <message>"
  local m rc
  m=$(printf '%s' "$2" | LC_COLLATE=C bash "$scripts/$1.sh" 2>&1 >/dev/null); rc=$?
  printf '%s %s' "$rc" "$m"
}
gpy() { # INPUT: "<exit> <message>" of guard.py, through py-launch.sh
  local m rc
  m=$(printf '%s' "$1" | HOME=${PYHOME:-$HOME} CLAUDE_PLUGIN_ROOT="$plugin" CLAUDE_PLUGIN_DATA="$tmp/pyrun" MSYS2_ENV_CONV_EXCL=HOME \
    bash -c '. "$CLAUDE_PLUGIN_ROOT/scripts/py-launch.sh" guard' 2>&1 >/dev/null); rc=$?
  printf '%s %s' "$rc" "$(pymap "$m")"
}
gdual() { # NAME WANT KIND INPUT [GUARD.SH-RESULT [BLOCK-PUSH.SH-RESULT]]
  local p=${6:-} b
  # block-push.sh blocks only on a push or on input guard.sh also refuses
  # with the same message.
  [ -n "$p" ] || case "$4" in *[pP][uU][sS][hH]*) p=$(run_hook block-push "$4") ;; *) p="0 " ;; esac
  case "$p" in "2 "*) b=$p ;; *) b=${5:-$(run_hook guard "$4")} ;; esac
  pycmp "guard_py/$1" "$2" "$3" "$b" "$(gpy "$4")"
}

section guard-fixtures
# Fixtures name the plugin folder @PLUGIN@ (as pwd prints it) or
# @PLUGIN_DRIVE@ (as Claude Code substitutes it on Windows: C:/...; on Linux
# the same as @PLUGIN@).
plugin_drive=$(printf '%s' "$plugin" | sed 's#^/\([a-z]\)/#\U\1:/#')
check "py-launch/hooks-json-block-push" yes "$([ -n "$(pycmd block_push)" ] && echo yes)"
for f in "$here"/fixtures/*/*.json; do
  script=$(basename "$(dirname "$f")")
  case=$(basename "$f" .json)
  case "$case" in
    pass-*) want=0 ;;
    block-*) want=2 ;;
    *) printf 'skip  %s (name must start with pass- or block-)\n' "$case"; continue ;;
  esac
  input=$(sed -e "s#@PLUGIN_DRIVE@#$plugin_drive#g" -e "s#@PLUGIN@#$plugin#g" "$f")
  # Python twins: dual run, comparing exit code and message. guard.py runs
  # every fixture, since it carries block-push too.
  kind=$(py_kind "$script/$case")
  r=$(CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/home/u run_hook "$script" "$input")
  case "$kind" in
    stricter) check "$script/$case (bash, known gap)" 0 "${r%% *}" ;;
    locale) ;; # bash's result depends on the locale
    *) check "$script/$case" "$want" "${r%% *}" ;;
  esac
  if [ "$script" = block-push ]; then
    pmsg=$(printf '%s' "$input" | pyhook block_push 2>&1 >/dev/null); prc=$?
    pycmp "block_push/$case" "$want" "$kind" "$r" "$prc $pmsg"
    CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/home/u gdual "$script/$case" "$want" "$kind" "$input" "" "$r"
  else
    CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/home/u gdual "$script/$case" "$want" "$kind" "$input" "$r"
  fi
done
# Every listed case still exists.
while IFS= read -r l; do
  [ -n "$l" ] || continue
  check "py-stricter/${l%% *} exists" yes "$([ -f "$here/fixtures/${l%% *}.json" ] && echo yes)"
done <<< "$py_stricter"

section py-launch
# The launcher: interpreter cache, probe, fail-closed exits. Fake
# interpreters live in $tmp/fk/<name>/; $realpy is the one the probe found.
push='{"tool_name":"Bash","tool_input":{"command":"git push"}}'
ls_='{"tool_name":"Bash","tool_input":{"command":"ls"}}'
rm -rf "$tmp/pdata"
printf '%s' "$ls_" | pyhook block_push >/dev/null 2>&1
check "py-launch/probe-and-run" 0 "$?"
realpy=$(cat "$tmp/pdata/python" 2>/dev/null)
case "$realpy" in /*/python*|[A-Za-z]:/*/python*) r=ok ;; *) r="cache: '$realpy'" ;; esac
check "py-launch/cache-written" ok "$r"
check "py-launch/cache-trailing-newline" 1 "$(grep -c '' "$tmp/pdata/python")"
fk() { # NAME PROGRAM BODY: a fake interpreter $tmp/fk/NAME/PROGRAM
  mkdir -p "$tmp/fk/$1"
  printf '#!/bin/sh\n%s\n' "$3" > "$tmp/fk/$1/$2"
  chmod +x "$tmp/fk/$1/$2"
}
fk store python3 'echo "Python was not found; run without arguments to install from the Microsoft Store." >&2; exit 9009'
fk pyonly py '[ "$1" = -3 ] && shift; exec "'"$realpy"'" "$@"'
fk old python3 'echo "old $0"'
fk exit1 python 'echo "Traceback (most recent call last):" >&2; echo "SyntaxError: invalid syntax" >&2; exit 1'
fk exit127 python 'exit 127'
mkdir -p "$tmp/fk/none"
setcache() { mkdir -p "$tmp/pdata"; printf "$2" "$1" > "$tmp/pdata/python"; }
pyx() { # INPUT [PATH]: exit code of block_push, PATH optionally replaced
  if [ -n "${2:-}" ]; then
    printf '%s' "$1" | CLAUDE_PLUGIN_ROOT="$plugin" CLAUDE_PLUGIN_DATA="$tmp/pdata" PATH="$2" "$BASH" -c "$(pycmd block_push)" >/dev/null 2>&1
  else
    printf '%s' "$1" | pyhook block_push >/dev/null 2>&1
  fi
  echo $?
}
pymsg() { printf '%s' "$1" | CLAUDE_PLUGIN_ROOT="$plugin" CLAUDE_PLUGIN_DATA="$tmp/pdata" PATH="${2:-$PATH}" "$BASH" -c "$(pycmd block_push)" 2>&1 >/dev/null; }
# A warm cache, used with no python on PATH at all.
setcache "$realpy" '%s\n'
check "py-launch/warm-cache-pass" 0 "$(pyx "$ls_" "$tmp/fk/none")"
check "py-launch/warm-cache-push" 2 "$(pyx "$push" "$tmp/fk/none")"
setcache "$realpy" '%s'
check "py-launch/cache-no-newline" 0 "$(pyx "$ls_" "$tmp/fk/none")"
# Stale, relative or non-python cache entries: ignored, probed again, rewritten.
setcache "$tmp/gone/python3" '%s\n'
check "py-launch/stale-cache" 0 "$(pyx "$ls_")"
check "py-launch/stale-cache-rewritten" "$realpy" "$(cat "$tmp/pdata/python")"
setcache python3 '%s\n'
check "py-launch/relative-cache" 0 "$(pyx "$ls_")"
check "py-launch/relative-cache-rewritten" "$realpy" "$(cat "$tmp/pdata/python")"
setcache "$(command -v true)" '%s\n'
check "py-launch/non-python-cache-push" 2 "$(pyx "$push")"
# A cached interpreter that fails: blocked, whatever the call.
setcache "$tmp/fk/exit1/python" '%s\n'
check "py-launch/exit1-pass-blocked" 2 "$(pyx "$ls_")"
case "$(pymsg "$ls_")" in *"block_push.py failed (exit 1)"*) r=ok ;; *) r=other ;; esac
check "py-launch/exit1-message" ok "$r"
setcache "$tmp/fk/exit127/python" '%s\n'
check "py-launch/exit127-pass-blocked" 2 "$(pyx "$ls_")"
# Probing: the Store alias, an old Python, `py -3` only, nothing.
rm -f "$tmp/pdata/python"
check "py-launch/store-alias-only" 2 "$(pyx "$ls_" "$tmp/fk/store")"
case "$(pymsg "$ls_" "$tmp/fk/store")" in *"no Python 3.9 or later found"*) r=ok ;; *) r=other ;; esac
check "py-launch/store-alias-message" ok "$r"
check "py-launch/old-python-only" 2 "$(pyx "$ls_" "$tmp/fk/old")"
check "py-launch/py-only-pass" 0 "$(pyx "$ls_" "$tmp/fk/pyonly")"
rm -f "$tmp/pdata/python"
check "py-launch/py-only-push" 2 "$(pyx "$push" "$tmp/fk/pyonly")"
check "py-launch/none" 2 "$(pyx "$ls_" "$tmp/fk/none")"
# Probe order: python before python3 (on Windows python3 is usually the
# Store alias, slow to fail). A working python means python3 never runs.
fk order python 'exec "'"$realpy"'" "$@"'
fk order python3 ': > "'"$tmp"'/python3-ran"; exit 9009'
rm -f "$tmp/pdata/python" "$tmp/python3-ran"
check "py-launch/order-python-first" 0 "$(pyx "$ls_" "$tmp/fk/order")"
check "py-launch/order-python3-not-run" no "$([ -e "$tmp/python3-ran" ] && echo yes || echo no)"
# No CLAUDE_PLUGIN_DATA: probes every time, caches nothing.
r=$(printf '%s' "$ls_" | PYDATA= pyhook block_push >/dev/null 2>&1; echo $?)
check "py-launch/no-plugin-data" 0 "$r"
# Empty stdin; a bad or missing script name.
check "py-launch/empty-stdin" 2 "$(pyx '')"
r=$(printf '%s' "$ls_" | "$BASH" -c '. "$1/scripts/py-launch.sh" ../block_push' _ "$plugin" >/dev/null 2>&1; echo $?)
check "py-launch/bad-name" 2 "$r"
r=$(printf '%s' "$ls_" | "$BASH" -c '. "$1/scripts/py-launch.sh" no_such_hook' _ "$plugin" >/dev/null 2>&1; echo $?)
check "py-launch/missing-script" 2 "$r"
# A plugin folder with a space in its path.
mkdir -p "$tmp/plug in" && cp -r "$plugin" "$tmp/plug in/wiki"
r=$(printf '%s' "$push" | pyhook block_push "$tmp/plug in/wiki" >/dev/null 2>&1; echo $?)
check "py-launch/space-in-root-push" 2 "$r"
r=$(printf '%s' "$ls_" | pyhook block_push "$tmp/plug in/wiki" >/dev/null 2>&1; echo $?)
check "py-launch/space-in-root-pass" 0 "$r"
# WIKI_HOOK_TIMING=1 logs one line per call.
setcache "$realpy" '%s\n'
printf '%s' "$push" | WIKI_HOOK_TIMING=1 pyhook block_push >/dev/null 2>&1
case "$(cat "$tmp/pdata/hook-timing.log" 2>/dev/null)" in "block_push "[0-9]*" rc=2 $realpy "*) r=ok ;; *) r=other ;; esac
check "py-launch/timing-log" ok "$r"
# The plugin folder written with ~, when it is under HOME.
tilde_cmd="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash ~/$(basename "$plugin")/scripts/lint.sh\"}}"
r=$(CLAUDE_PROJECT_DIR="$tmp/gw" HOME=$(dirname "$plugin") run_hook guard "$tilde_cmd")
check "guard/pass-lint-tilde-form" 0 "${r%% *}"
CLAUDE_PROJECT_DIR="$tmp/gw" HOME=$(dirname "$plugin") gdual pass-lint-tilde-form 0 "" "$tilde_cmd" "$r"
# The plugin folder with Windows backslashes (JSON-escaped).
bs_cmd="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash $(printf '%s' "$plugin_drive" | sed 's#/#\\\\#g')\\\\scripts\\\\lint.sh\"}}"
r=$(CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/home/u run_hook guard "$bs_cmd")
check "guard/pass-lint-backslash-form" 0 "${r%% *}"
CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/home/u gdual pass-lint-backslash-form 0 "" "$bs_cmd" "$r"

section guard-broken
# guard.sh fails closed on source files it can't read, and knows Windows paths.
fx="$here/fixtures/guard"
gbroken() { # NAME SETUP-SNIPPET (run in a fresh copy of guard-wiki)
  rm -rf "$tmp/gb"; cp -r "$here/guard-wiki" "$tmp/gb"
  (cd "$tmp/gb" && eval "$2")
  r=$(CLAUDE_PROJECT_DIR="$tmp/gb" HOME=/home/u run_hook guard "$(cat "$fx/pass-ordinary-bash.json")")
  check "guard/fail-closed-$1" 2 "${r%% *}"
  CLAUDE_PROJECT_DIR="$tmp/gb" HOME=/home/u gdual "fail-closed-$1" 2 "" "$(cat "$fx/pass-ordinary-bash.json")" "$r"
}
gbroken instance-no-frontmatter 'printf "key: x\n" > .claude/sources/instances/x.md'
gbroken instance-unknown-type   'printf -- "---\nkey: x\ntype: nosuch\n---\n" > .claude/sources/instances/x.md'
gbroken local-type-shadows      'mkdir -p .claude/sources/types/gmail && cp .claude/sources/types/bookish/SOURCE.md .claude/sources/types/gmail/'
gbroken contract-no-frontmatter 'printf "# no fm\n" > .claude/sources/types/bookish/SOURCE.md'
gbroken filesystem-no-roots     'printf -- "---\nkey: x\ntype: local-folder\n---\n" > .claude/sources/instances/x.md'
# Two broken files: the message names the first (guard.py checked by the dual run).
gbroken first-of-two            'printf "key: a\n" > .claude/sources/instances/a-x.md; printf "key: b\n" > .claude/sources/instances/b-x.md'
# While broken: read-only diagnostics pass, everything else is refused.
rm -rf "$tmp/gb"; cp -r "$here/guard-wiki" "$tmp/gb"
printf 'key: x\n' > "$tmp/gb/.claude/sources/instances/x.md"
gdiag() { # NAME EXPECTED-EXIT TOOL-INPUT-JSON (Bash command or Write)
  local in
  in=$(printf '{"session_id":"t","cwd":"/home/u/wikis/mywiki","hook_event_name":"PreToolUse","tool_name":"%s","tool_input":%s,"tool_use_id":"x"}' "$3" "$4")
  r=$(CLAUDE_PROJECT_DIR="$tmp/gb" HOME=/home/u run_hook guard "$in")
  check "guard/broken-$1" "$2" "${r%% *}"
  CLAUDE_PROJECT_DIR="$tmp/gb" HOME=/home/u gdual "broken-$1" "$2" "" "$in" "$r"
}
gdiag git-status        0 Bash '{"command":"git status"}'
gdiag git-diff-sources  0 Bash '{"command":"git diff .claude/sources/instances/x.md"}'
gdiag git-log           0 Bash '{"command":"git log --oneline -5 -- .claude/sources"}'
gdiag git-show          0 Bash '{"command":"git show HEAD:.claude/sources/instances/x.md"}'
gdiag sources-show      0 Bash "{\"command\":\"bash $plugin/scripts/sources.sh show x\"}"
gdiag sources-list      0 Bash "{\"command\":\"bash $plugin/scripts/sources.sh list\"}"
gdiag sources-contract  0 Bash "{\"command\":\"bash $plugin/scripts/sources.sh contract gmail\"}"
gdiag sources-contract-chain 2 Bash "{\"command\":\"bash $plugin/scripts/sources.sh contract gmail && rm -rf wiki\"}"
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
r=$(CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/c/Users/u run_hook guard "$win")
check "guard/windows-drive-root" 2 "${r%% *}"
CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/c/Users/u gdual windows-drive-root 2 "" "$win" "$r"
# An agent_only root written with ~, read by the main session as C:\...
rm -rf "$tmp/gc"; cp -r "$here/guard-wiki" "$tmp/gc"
sed -i 's#  - /home/u/src/components#  - ~/src/components#' "$tmp/gc/.claude/sources/instances/code.md"
gwin() { # NAME EXPECTED AGENT-FIELD
  local in
  in=$(printf '{"session_id":"t","cwd":"C:\\\\Users\\\\u\\\\wikis\\\\mywiki","hook_event_name":"PreToolUse"%s,"tool_name":"Read","tool_input":{"file_path":"C:\\\\Users\\\\u\\\\src\\\\components\\\\app\\\\A.java"},"tool_use_id":"x"}' "$3")
  r=$(CLAUDE_PROJECT_DIR="$tmp/gc" HOME=/c/Users/u run_hook guard "$in")
  check "guard/$1" "$2" "${r%% *}"
  CLAUDE_PROJECT_DIR="$tmp/gc" HOME=/c/Users/u gdual "$1" "$2" "" "$in" "$r"
}
gwin codebase-read-windows-main  2 ''
gwin codebase-read-windows-agent 0 ',"agent_id":"a1"'
# ".." at the drive root stays there, as in guard.sh: C:\..\Users is C:/Users.
in=$(printf '{"session_id":"t","cwd":"C:\\\\Users\\\\u\\\\wikis\\\\mywiki","hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"C:\\\\..\\\\Users\\\\u\\\\src\\\\components\\\\A.java"},"tool_use_id":"x"}')
r=$(CLAUDE_PROJECT_DIR="$tmp/gc" HOME=/c/Users/u run_hook guard "$in")
check "guard/codebase-read-windows-dotdot" 2 "${r%% *}"
CLAUDE_PROJECT_DIR="$tmp/gc" HOME=/c/Users/u gdual codebase-read-windows-dotdot 2 "" "$in" "$r"
# Windows: a real session hands Python HOME as C:\Users\u, not /c/Users/u.
CLAUDE_PROJECT_DIR="$tmp/gw" HOME=/c/Users/u PYHOME='C:\Users\u' gdual windows-drive-root-native-home 2 "" "$win"
in=$(printf '{"session_id":"t","cwd":"C:\\\\Users\\\\u\\\\wikis\\\\mywiki","hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"C:\\\\Users\\\\u\\\\src\\\\components\\\\app\\\\A.java"},"tool_use_id":"x"}')
CLAUDE_PROJECT_DIR="$tmp/gc" HOME=/c/Users/u PYHOME='C:\Users\u' gdual codebase-read-windows-native-home 2 "" "$in"

# Cases from the review of guard.py, each in a fresh copy of guard-wiki at
# $GK (default $tmp/gk). KIND as in py-stricter.txt, plus "locale": bash's
# result depends on the locale (sed's [[:space:]] takes U+2003 only in a
# UTF-8 one), so only guard.py is checked.
gcase() { # NAME WANT KIND SETUP-SNIPPET INPUT-JSON (@PLUGIN@ = the plugin folder)
  local gk=${GK:-$tmp/gk} in r
  rm -rf "$gk"; mkdir -p "$(dirname "$gk")"; cp -r "$here/guard-wiki" "$gk"
  (cd "$gk" && eval "$4")
  in=$(printf '%s' "$5" | sed "s#@PLUGIN@#$plugin#g")
  r=$(CLAUDE_PROJECT_DIR="$gk" HOME=/home/u run_hook guard "$in")
  case "$3" in
    stricter) check "guard/$1 (bash, known gap)" 0 "${r%% *}" ;;
    locale) ;;
    *) check "guard/$1" "$2" "${r%% *}" ;;
  esac
  CLAUDE_PROJECT_DIR="$gk" HOME=/home/u gdual "$1" "$2" "$3" "$in" "$r"
}
gbash() { printf '{"session_id":"t","cwd":"/home/u/wikis/mywiki","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"%s"},"tool_use_id":"x"}' "$1"; }
em=$(printf '\342\200\203')
inst() { # KEY TYPE ROOTS-LINE...: write an instance file
  local k=$1 t=$2; shift 2
  { printf -- '---\nkey: %s\ntype: %s\n' "$k" "$t"; printf '%s\n' "$@"; printf 'state:\n  - last_checked\n---\n'; } > ".claude/sources/instances/$k.md"
}
# Unicode whitespace around a contract value: stripped, as sed does in a UTF-8 locale.
gcase unicode-space-root 2 locale "inst uni local-folder 'roots: /home/u/Uni$em'" "$(gbash 'cat /home/u/Uni/x')"
gcase unicode-space-agent-only 2 locale "mkdir -p .claude/sources/types/cb && sed 's/^type: codebase/type: cb/; s/^agent_only: yes/agent_only: yes$em/' '$plugin/sources/codebase/SOURCE.md' > .claude/sources/types/cb/SOURCE.md && inst cb cb roots: '  - /home/u/cbsrc'" \
  '{"session_id":"t","cwd":"/home/u/wikis/mywiki","hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"/home/u/cbsrc/A.java"},"tool_use_id":"x"}'
# Unicode whitespace in a command: guard.py takes ASCII whitespace only.
gcase unicode-space-command 2 locale "" "$(gbash "bash$em@PLUGIN@/scripts/lint.sh")"
# Lowercasing is ASCII only in both, so messages keep non-ASCII letters and
# the Kelvin sign is not a k.
gcase non-ascii-root 2 "" "inst ae local-folder roots: '  - /home/u/Æble'" "$(gbash 'cat /home/u/Æble/x')"
kelvin=$(printf '\342\204\252')
gcase kelvin-sign 0 "" "" "$(gbash "cat x/hoo${kelvin}s.json")"
# JSON null is an absent field.
gcase null-path 0 "" "" '{"session_id":"t","cwd":"/home/u/wikis/mywiki","hook_event_name":"PreToolUse","tool_name":"Grep","tool_input":{"pattern":"x","path":null,"glob":null},"tool_use_id":"x"}'
gcase null-agent-id 2 "" "" '{"session_id":"t","cwd":"/home/u/wikis/mywiki","hook_event_name":"PreToolUse","tool_name":"Read","agent_id":null,"tool_input":{"file_path":"/home/u/src/components/A.java"},"tool_use_id":"x"}'
# Two broken local types: the first in byte order is named.
gcase first-of-two-types 2 "" 'for t in a-x ab; do mkdir -p .claude/sources/types/$t; printf "# x\n" > .claude/sources/types/$t/SOURCE.md; done' "$(gbash ls)"
# Instance file names that aren't keys: bash splits them into words.
gcase instance-key-space 2 stricter 'cp .claude/sources/instances/gmail.md ".claude/sources/instances/gmail scans.md"' "$(gbash ls)"
gcase instance-key-copy 2 message 'cp .claude/sources/instances/scans.md ".claude/sources/instances/scans - Copy.md"' "$(gbash ls)"
# A main-session wrapper call whose key or operation isn't a plain word.
gcase main-op-quoted 2 stricter "" "$(gbash 'bash @PLUGIN@/sources/codebase/git.sh code\" \"status grep x')"
gcase main-op-backslash 2 stricter "" "$(gbash 'bash @PLUGIN@/sources/codebase/git.sh code\\ status grep x')"
# A wiki path with a space: bash splits the agent_only instance paths.
GK="$tmp/sp ace/gw" gcase wiki-path-space-read 2 stricter "" \
  '{"session_id":"t","cwd":"/home/u/wikis/mywiki","hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"/home/u/src/components/A.java"},"tool_use_id":"x"}'
# A source folder that can't be listed (not testable as root or on Windows).
rm -rf "$tmp/gu"; cp -r "$here/guard-wiki" "$tmp/gu"; chmod 000 "$tmp/gu/.claude/sources/instances"
if ls "$tmp/gu/.claude/sources/instances" >/dev/null 2>&1; then
  printf 'skip  guard/unreadable-instances (the folder stays readable here)\n'
else
  in=$(gbash 'cat /home/u/Scans/x')
  r=$(CLAUDE_PROJECT_DIR="$tmp/gu" HOME=/home/u run_hook guard "$in")
  check "guard/unreadable-instances (bash, known gap)" 0 "${r%% *}"
  CLAUDE_PROJECT_DIR="$tmp/gu" HOME=/home/u gdual unreadable-instances 2 stricter "$in" "$r"
fi
chmod 755 "$tmp/gu/.claude/sources/instances"

section proton-drive
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
# The download folder as read.sh hands it to the CLI: C:/... where cygpath
# exists (Git Bash), unchanged elsewhere.
pdlocal() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

check "proton-drive/list"                 "FAKE filesystem list --json /my-files/Archive/2026" "$(pdn drive list /my-files/Archive/2026)"
check "proton-drive/list-space"           "FAKE filesystem list --json $plan/offers" "$(pdn plans list "$plan/offers")"
check "proton-drive/size"                 "FAKE filesystem size --json $plan" "$(pdn plans size "$plan")"
out=$(pdn drive download "/my-files/Archive/2026/contract.pdf" | head -n 1)
check "proton-drive/download-to-key"      "FAKE filesystem download --json -f remove -d merge /my-files/Archive/2026/contract.pdf $(pdlocal "$tmp/home/.cache/wiki-sources/pdw/drive/2026")" "$out"
out=$(pdn plans download "$plan/a.pdf" | head -n 1)
check "proton-drive/download-top-level"   "FAKE filesystem download --json -f remove -d merge $plan/a.pdf $(pdlocal "$tmp/home/.cache/wiki-sources/pdw/plans")" "$out"
out=$(pdn drive download "/my-files/Projects/manual.pdf")
check "proton-drive/download-file-root"   "FAKE filesystem download --json -f remove -d merge /my-files/Projects/manual.pdf $(pdlocal "$tmp/home/.cache/wiki-sources/pdw/drive")" "$(printf '%s\n' "$out" | head -n 1)"
check "proton-drive/download-file-root-msg" "proton-drive: downloaded to $tmp/home/.cache/wiki-sources/pdw/drive/manual.pdf" "$(printf '%s\n' "$out" | tail -n 1)"
# Git Bash path conversion is off for every CLI call (it turned /my-files/...
# into C:/Program Files/Git/my-files/...), and the download folder goes
# through cygpath instead; a fake cygpath shows that on Linux too.
out=$(cd "$tmp/pdw" && FAKE_PD_ENV=1 HOME="$tmp/home" PATH="$fakebin:$PATH" bash "$pdr" drive list /my-files/Archive 2>&1 >/dev/null)
check "proton-drive/no-msys-pathconv"     "FAKE env MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL=*" "$(printf '%s\n' "$out" | sort -u)"
mkdir -p "$tmp/cygbin" && printf '#!/usr/bin/env bash\n[ "$1" = -m ] && printf "W:%%s\\n" "$2"\n' > "$tmp/cygbin/cygpath" && chmod u+x "$tmp/cygbin/cygpath"
out=$(cd "$tmp/pdw" && HOME="$tmp/home" PATH="$fakebin:$tmp/cygbin:$PATH" bash "$pdr" drive download /my-files/Archive/a.pdf 2>&1)
check "proton-drive/download-cygpath"     "FAKE filesystem download --json -f remove -d merge /my-files/Archive/a.pdf W:$tmp/home/.cache/wiki-sources/pdw/drive" "$(printf '%s\n' "$out" | head -n 1)"
check "proton-drive/download-cygpath-msg" "proton-drive: downloaded to $tmp/home/.cache/wiki-sources/pdw/drive/a.pdf" "$(printf '%s\n' "$out" | tail -n 1)"
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

section codebase
# codebase/git.sh and gh.sh against a throwaway repo with a bare "remote"
# and a fake gh. Every gh.sh call runs with the fake first on PATH; abort if
# the fake isn't the gh that PATH finds.
cp "$here/sources/codebase/fake-gh" "$fakebin/gh" && chmod u+x "$fakebin/gh"
if [ "$(PATH="$fakebin:$PATH" command -v gh)" != "$fakebin/gh" ]; then
  printf 'ABORT: the fake gh is not first on PATH; refusing to run codebase tests against a real gh.\n'
  exit 1
fi
cb="$tmp/cb"
mkdir -p "$cb"
git init -q --bare "$cb/remote.git"
git -c init.defaultBranch=main init -q "$cb/clone"
cg() { git -C "$cb/clone" -c user.name=T -c user.email=t@t -c core.autocrlf=false "$@" >/dev/null 2>&1; }
cg config core.autocrlf false
mkdir -p "$cb/clone/app/src" "$cb/clone/lib"
printf 'l1\nfoo\nl3\nl4\nl5\nl6\n' > "$cb/clone/app/src/A.java"
printf 'b1\nb2\n' > "$cb/clone/lib/B.java"
cg add -A; cg commit -m one
cg remote add origin "$cb/remote.git"; cg push origin HEAD:main; cg fetch origin; cg remote set-head origin main
c1=$(git -C "$cb/clone" rev-parse HEAD)
printf 'l0\nl1\nfoo\nl3\nl4\nl5\nl6\n' > "$cb/clone/app/src/A.java"; cg commit -am "two: insert at top"
c2=$(git -C "$cb/clone" rev-parse HEAD)
printf 'l0\nl1\nFOO\nl3\nl4\nl5\nl6\n' > "$cb/clone/app/src/A.java"; cg commit -am "three: change foo"
c3=$(git -C "$cb/clone" rev-parse HEAD)
printf 'c1\n' > "$cb/clone/lib/C.java"; cg add -A; cg commit -m "four: add C"
c4=$(git -C "$cb/clone" rev-parse HEAD)
cg mv lib/B.java lib/B2.java; cg rm -q lib/C.java; cg commit -m "five: rename B, delete C"
printf 'l0\nl1\nFOO\nl3\nl4\nl5\nL6\n' > "$cb/clone/app/src/A.java"; cg commit -am "six: change last line"
cg push origin HEAD:main; cg fetch origin
cg checkout -q -b local-work; printf 'local\n' > "$cb/clone/lib/local.txt"   # uncommitted, unpushed branch
git clone -q "$cb/remote.git" "$cb/ghclone" 2>/dev/null
git -C "$cb/ghclone" remote set-url origin https://github.com/acme/widgets.git
git -C "$cb" init -q cbw
mkdir -p "$cb/cbw/.claude/sources/instances"
printf -- '---\nkey: code\ntype: codebase\nroots:\n  - %s\n---\n' "$cb/clone" > "$cb/cbw/.claude/sources/instances/code.md"
printf -- '---\nkey: sub\ntype: codebase\nroots:\n  - %s/app\nref: origin/main\n---\n' "$cb/clone" > "$cb/cbw/.claude/sources/instances/sub.md"
printf -- '---\nkey: hub\ntype: codebase\nroots:\n  - %s\ngh_user: reader\n---\n' "$cb/ghclone" > "$cb/cbw/.claude/sources/instances/hub.md"
printf -- '---\nkey: two\ntype: codebase\nroots:\n  - %s\n  - %s\n---\n' "$cb/clone" "$cb/ghclone" > "$cb/cbw/.claude/sources/instances/two.md"
printf -- '---\nkey: mail\ntype: gmail\nlabels: X\n---\n' > "$cb/cbw/.claude/sources/instances/mail.md"
cbr="$here/../plugins/wiki/sources/codebase/git.sh"
cbh="$here/../plugins/wiki/sources/codebase/gh.sh"
# HOME is a test folder: the instance cache (pattern files, last-fetch) and a
# .gitconfig that sends the https GitHub remote of "hub" to the local bare repo.
cbhome="$cb/home"
cbcache="$cbhome/.cache/wiki-sources/cbw"
mkdir -p "$cbcache/code"
git config -f "$cbhome/.gitconfig" "url.$cb/remote.git.insteadOf" https://github.com/acme/widgets.git
cbn() { (cd "$cb/cbw" && HOME="$cbhome" PATH="$fakebin:$PATH" bash "$cbr" "$@" 2>&1); }
cbx() { (cd "$cb/cbw" && HOME="$cbhome" PATH="$fakebin:$PATH" bash "$cbr" "$@" >/dev/null 2>&1); echo $?; }
ghn() { (cd "$cb/cbw" && PATH="$fakebin:$PATH" bash "$cbh" "$@" 2>&1); }
ghx() { (cd "$cb/cbw" && PATH="$fakebin:$PATH" bash "$cbh" "$@" >/dev/null 2>&1); echo $?; }
has() { case "$1" in *"$2"*) echo yes ;; *) echo "no: $1" ;; esac; }
s1=$(printf '%s' "$c1" | cut -c1-12) s3=$(printf '%s' "$c3" | cut -c1-12)
out=$(cbn code status)
check "codebase/status-checkout"  yes "$(has "$out" 'checkout: local-work @')"
check "codebase/status-dirty"     yes "$(has "$out" '1 uncommitted changes in the root')"
check "codebase/status-ref"       yes "$(has "$out" 'ref: origin/main @')"
check "codebase/status-shallow"   yes "$(has "$out" 'shallow: no')"
check "codebase/resolve"          yes "$(has "$(cbn code resolve "$s1")" "$s1 $c1")"
check "codebase/resolve-ref"      yes "$(has "$(cbn code resolve ref)" "ref $(git -C "$cb/clone" rev-parse origin/main)")"
check "codebase/grep"             yes "$(has "$(cbn code grep "$c1" 'fo+')" 'app/src/A.java#L2: foo')"
check "codebase/igrep"            yes "$(has "$(cbn code igrep ref 'foo')" 'app/src/A.java#L3: FOO')"
check "codebase/grep-none"        yes "$(has "$(cbn code grep ref 'nomatch')" 'no matches')"
check "codebase/grep-pathspec"    yes "$(has "$(cbn code grep ref 'b' 'lib/*.java')" 'lib/B2.java#L1: b1')"
check "codebase/grep-dash-regex"  yes "$(has "$(cbn code grep ref '-x')" 'no matches')"
out=$(cbn code show "$c1" app/src/A.java L2-L3)
check "codebase/show-header"      yes "$(has "$out" "app/src/A.java#L2-L3 @$s1 (6 lines in the file)")"
check "codebase/show-lines"       yes "$(has "$out" '     3  l3')"
check "codebase/show-more"        yes "$(has "$out" "(more: show $c1 app/src/A.java L4-L6)")"
check "codebase/show-folder"      1   "$(cbx code show ref app)"
check "codebase/ls"               yes "$(has "$(cbn code ls ref lib)" "f 6 lib/B2.java")"
check "codebase/log"              yes "$(has "$(cbn code log ref app/src/A.java)" 'three: change foo')"
check "codebase/log-range"        yes "$(has "$(cbn code log ref app/src/A.java L3-L3)" 'three: change foo')"
check "codebase/blame"            yes "$(has "$(cbn code blame ref app/src/A.java L3-L3)" 'FOO')"
check "codebase/branches"         "main" "$(cbn code branches | cut -d' ' -f1 | sed 's#^origin/##' | paste -sd' ' -)"
check "codebase/contains"         "origin/main" "$(cbn code contains "$c1")"
cg commit -q -m "seven: local only" --allow-empty
check "codebase/contains-unpushed" yes "$(has "$(cbn code contains local-work)" 'unpushed:')"
check "codebase/verify"           "ok: app/src/A.java#L2-L3 @$s1" "$(cbn code verify "$c1" app/src/A.java L2-L3)"
check "codebase/verify-past-end"  1 "$(cbx code verify "$c1" app/src/A.java L5-L9)"
check "codebase/verify-missing"   1 "$(cbx code verify "$c1" app/src/Z.java L1-L1)"
check "codebase/drift-elsewhere"  yes "$(has "$(cbn code drift "$c3" app/src/A.java L1-L2)" "changed-elsewhere")"
check "codebase/drift-moved"      yes "$(has "$(cbn code drift "$c1" app/src/A.java L4-L5)" 'moved L5-L6')"
check "codebase/drift-overlap"    yes "$(has "$(cbn code drift "$c1" app/src/A.java L2-L3)" 'changed-overlap')"
check "codebase/drift-renamed"    yes "$(has "$(cbn code drift "$c3" lib/B.java L1-L2)" "renamed lib/B2.java")"
check "codebase/drift-deleted"    yes "$(has "$(cbn code drift "$c4" lib/C.java L1-L1)" 'deleted')"
check "codebase/drift-same"       yes "$(has "$(cbn code drift ref app/src/A.java L1-L2)" 'unchanged')"
mkdir -p "$cb/cbw/wiki" "$cbcache/code/runs/r2"
printf 'a (Codebase code: app/src/A.java#L2-L3 @%s) b app/src/A.java#L5-L9 @%s\nc lib/C.java#L1 @%s; again app/src/A.java#L2-L3 @%s\n' "$s1" "$s1" "$c4" "$s1" > "$cb/cbw/wiki/page.md"
printf 'C1: app/src/A.java#L2-L3 @%s\r\n' "$s1" > "$cbcache/code/runs/r2/answer.md"
out=$(cbn code verify-all wiki/page.md; echo "exit=$?")
check "codebase/verify-all-quiet"  no  "$(printf '%s\n' "$out" | grep -qF -- "-> ok:" && echo yes || echo no)"
check "codebase/verify-all-ok"     yes "$(has "$(cbn code verify-all wiki/page.md --all)" "app/src/A.java#L2-L3 @$s1 -> ok: app/src/A.java#L2-L3 @$s1")"
check "codebase/verify-all-nofetch" no "$(printf '%s\n' "$out" | grep -qF "compared with" && echo yes || echo no)"
check "codebase/refuse-all-flag"   1   "$(cbx code verify-all wiki/page.md --quiet)"
check "codebase/verify-all-broken" yes "$(has "$out" "app/src/A.java#L5-L9 @$s1 -> broken: app/src/A.java has 6 lines")"
check "codebase/verify-all-tally"  yes "$(has "$out" '3 citations: 1 broken, 2 ok')"
check "codebase/verify-all-exit"   yes "$(has "$out" 'exit=1')"
out=$(cbn code drift-all wiki/page.md)
check "codebase/drift-all"         yes "$(has "$out" "lib/C.java#L1 @$c4 -> deleted")"
check "codebase/drift-all-tally"   yes "$(has "$out" '3 citations: 1 broken, 1 changed-overlap, 1 deleted')"
check "codebase/drift-all-fetch"   yes "$(has "$out" "compared with origin/main as of the last fetch")"
check "codebase/drift-all-stamp"   yes "$(has "$out" "last fetch: ")"
check "codebase/verify-all-cache"  yes "$(has "$(cbn code verify-all @runs/r2/answer.md; echo "exit=$?")" '1 citations: 1 ok
exit=0')"
check "codebase/refuse-all-paths"  "1 1 1 1" "$(cbx code verify-all ../x.md) $(cbx code verify-all @runs/../../x) $(cbx code verify-all /etc/passwd) $(cbx code verify-all wiki/none.md)"
check "codebase/sub-ls"          yes "$(has "$(cbn sub ls ref)" 'd - app/src')"
check "codebase/sub-outside"      1   "$(cbx sub show ref lib/B2.java)"
check "codebase/sub-sibling"      1   "$(cbx sub show ref apples/x)"
check "codebase/sub-grep-scoped"  yes "$(has "$(cbn sub grep ref 'b1')" 'no matches')"
check "codebase/refuse-unknown-op" 1  "$(cbx code checkout ref)"
check "codebase/refuse-write-ops" "1 1 1 1" "$(cbx code reset ref) $(cbx code worktree ref) $(cbx code clone ref) $(cbx code push)"
check "codebase/refuse-extra-args" 1  "$(cbx code show ref app/src/A.java L1-L2 --output=x)"
check "codebase/refuse-few-args"  1   "$(cbx code show ref)"
check "codebase/refuse-dotdot"    1   "$(cbx code show ref app/../lib/B2.java)"
check "codebase/refuse-abs"       1   "$(cbx code show ref /etc/passwd)"
check "codebase/refuse-drive"     1   "$(cbx code show ref C:/x)"
check "codebase/refuse-option-path" 1 "$(cbx code show ref --output=x)"
check "codebase/refuse-magic-spec" 1  "$(cbx code grep ref x ':(top)')"
check "codebase/refuse-option-rev" 1  "$(cbx code show --output=x app/src/A.java)"
check "codebase/refuse-range-rev" 1   "$(cbx code show 'ref..HEAD' app/src/A.java)"
check "codebase/refuse-bad-range" "1 1" "$(cbx code show ref app/src/A.java L3-L1) $(cbx code show ref app/src/A.java 3x)"
check "codebase/refuse-unknown-rev" 1 "$(cbx code show deadbeef app/src/A.java)"
check "codebase/refuse-two-roots" 1   "$(cbx two status)"
check "codebase/refuse-wrong-type" 1  "$(cbx mail status)"
check "codebase/refuse-no-instance" 1 "$(cbx nosuch status)"
check "codebase/refuse-outside-git" 1 "$(cd "$tmp" && bash "$cbr" code status >/dev/null 2>&1; echo $?)"
check "codebase/status-never-fetched" yes "$(has "$(cbn code status)" 'last fetch: started')"
check "codebase/fetch"            yes "$(has "$(cbn code fetch)" "fetched origin (using the user's git credentials, started ")"
check "codebase/fetch-stamp"      yes "$(has "$(cat "$cbcache/code/last-fetch")" ', origin/main @')"
check "codebase/status-fetched"   yes "$(has "$(cbn code status)" 'last fetch: completed ')"
touch -d '+1 hour' "$cb/clone/.git/FETCH_HEAD"
check "codebase/status-fetch-running" yes "$(has "$(cbn code status)" 'has not completed')"
check "codebase/fetch-gh-user"    yes "$(has "$(cbn hub fetch)" 'using gh account reader')"
check "codebase/fetch-no-token"   yes "$(sed -i 's/gh_user: reader/gh_user: nobody/' "$cb/cbw/.claude/sources/instances/hub.md"; has "$(cbn hub fetch)" "using the user's git credentials")"
sed -i 's/gh_user: nobody/gh_user: reader/' "$cb/cbw/.claude/sources/instances/hub.md"
printf 'FO+|zzz\r\n^L6$\n' > "$cbcache/code/p.txt"
out=$(cbn code grep ref @p.txt)
check "codebase/grep-patfile"     yes "$(has "$out" 'app/src/A.java#L3: FOO')"
check "codebase/grep-patfile-or"  yes "$(has "$out" 'app/src/A.java#L7: L6')"
check "codebase/grep-patfile-head" yes "$(has "$out" '2 patterns from p.txt: FO+|zzz|^L6$')"
mkdir -p "$cbcache/code/runs/r1"; printf 'b1\n' > "$cbcache/code/runs/r1/q.txt"
check "codebase/grep-patfile-sub" yes "$(has "$(cbn code grep ref @runs/r1/q.txt 'lib/*')" 'lib/B2.java#L1: b1')"
i=0; : > "$cbcache/code/many.txt"; while [ $i -lt 21 ]; do printf 'p%s\n' "$i" >> "$cbcache/code/many.txt"; i=$((i + 1)); done
: > "$cbcache/code/empty.txt"
check "codebase/refuse-patfile"   "1 1 1 1 1 1" "$(cbx code grep ref @../x) $(cbx code grep ref @runs/../p.txt) $(cbx code grep ref @/etc/passwd) $(cbx code grep ref @nosuch.txt) $(cbx code grep ref @many.txt) $(cbx code grep ref @empty.txt)"
check "codebase/refuse-patfile-other-key" 1 "$(cbx sub grep ref @p.txt)"
check "gh/pr-of"                  yes "$(has "$(ghn hub pr-of "$(printf '%s' "$c1" | cut -c1-7)")" "FAKE gh api -X GET repos/acme/widgets/commits/$c1/pulls --jq")"
check "gh/pr-of-token"            yes "$(has "$(ghn hub pr-of "$c1")" 'token=tok-reader')"
check "gh/pr"                     yes "$(has "$(ghn hub pr 12)" 'FAKE gh pr view 12 -R acme/widgets --json')"
check "gh/pr-diff"                yes "$(has "$(ghn hub pr-diff 12)" 'FAKE gh pr diff 12 -R acme/widgets --color never')"
check "gh/pr-search"              yes "$(has "$(ghn hub pr-search 'payment routing')" 'FAKE gh pr list -R acme/widgets --state all --search payment routing --limit 30')"
check "gh/issue"                  yes "$(has "$(ghn hub issue 7)" 'FAKE gh issue view 7 -R acme/widgets')"
check "gh/issue-search"           yes "$(has "$(ghn hub issue-search 'is:open bug')" 'FAKE gh issue list -R acme/widgets --state all --search is:open bug')"
check "gh/refuse-no-gh-user"      1 "$(ghx code pr 12)"
check "gh/refuse-not-github"      1 "$(sed -i 's/^key: code/key: code\ngh_user: reader/' "$cb/cbw/.claude/sources/instances/code.md"; ghx code pr 12)"
check "gh/refuse-unknown-op"      "1 1 1" "$(ghx hub pr-merge 12) $(ghx hub api x) $(ghx hub auth x)"
check "gh/refuse-bad-number"      "1 1" "$(ghx hub pr 12x) $(ghx hub pr -R)"
check "gh/refuse-bad-sha"         "1 1" "$(ghx hub pr-of xyz) $(ghx hub pr-of deadbeefdead)"
check "gh/refuse-extra-args"      1 "$(ghx hub pr 12 --web)"
check "gh/refuse-no-token"        1 "$(sed -i 's/gh_user: reader/gh_user: nobody/' "$cb/cbw/.claude/sources/instances/hub.md"; ghx hub pr 12)"
sed -i 's/gh_user: nobody/gh_user: reader/' "$cb/cbw/.claude/sources/instances/hub.md"
out=$(cd "$cb/cbw" && FAKE_GH_SYNTAX=changed PATH="$fakebin:$PATH" bash "$cbh" hub pr 12 2>&1; echo "exit=$?")
case "$out" in *"syntax changed"*exit=1) r=refused ;; *) r="not refused: $out" ;; esac
check "gh/refuse-changed-syntax" refused "$r"

section lint
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

section sync-status
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
# A research instance (mode: research) is left out, line or no line.
printf -- '---\nkey: code\ntype: codebase\nroots:\n  - /x\n---\n' > "$tmp/ss/.claude/sources/instances/code.md"
printf -- '---\nkey: repo\ntype: codebase\nroots:\n  - /y\n---\n' > "$tmp/ss/.claude/sources/instances/repo.md"
printf 'last_checked_code: 2026-01-01\n' >> "$tmp/ss/raw/sync-log.md"
ss_out=$(cd "$tmp/ss" && CLAUDE_PROJECT_DIR= bash "$scripts/sync-status.sh" 2>&1)
case "$ss_out" in *"code"*|*"repo"*) r="$ss_out" ;; *"- scans:"*) r=ok ;; *) r="$ss_out" ;; esac
check "sync-status/research-skipped" ok "$r"
# The plugin running from a git working tree: a note only when it has
# uncommitted plugin changes (the plugin cache is no git repo: no note).
mkdir -p "$tmp/pt/plugins/wiki/scripts"
cp "$scripts/sync-status.sh" "$scripts/lib-source.sh" "$tmp/pt/plugins/wiki/scripts/"
git -C "$tmp/pt" init -q && git -C "$tmp/pt" add -A && git -C "$tmp/pt" -c user.name=t -c user.email=t@t commit -qm init
ss_out=$(cd "$tmp/ss" && CLAUDE_PROJECT_DIR= bash "$tmp/pt/plugins/wiki/scripts/sync-status.sh" 2>&1)
case "$ss_out" in *"runs from the working tree"*) r="$ss_out" ;; *"Wiki sync status"*) r=ok ;; *) r="$ss_out" ;; esac
check "sync-status/plugin-clean" ok "$r"
printf '\n' >> "$tmp/pt/plugins/wiki/scripts/lib-source.sh"
ss_out=$(cd "$tmp/ss" && CLAUDE_PROJECT_DIR= bash "$tmp/pt/plugins/wiki/scripts/sync-status.sh" 2>&1)
case "$ss_out" in *"runs from the working tree"*"lib-source.sh"*"Wiki sync status"*) r=ok ;; *) r="$ss_out" ;; esac
check "sync-status/plugin-dirty" ok "$r"
mkdir -p "$tmp/pc/scripts" && cp "$scripts/sync-status.sh" "$scripts/lib-source.sh" "$tmp/pc/scripts/"
ss_out=$(cd "$tmp/ss" && CLAUDE_PROJECT_DIR= GIT_CEILING_DIRECTORIES="$tmp" bash "$tmp/pc/scripts/sync-status.sh" 2>&1)
case "$ss_out" in *"runs from the working tree"*) r="$ss_out" ;; *) r=ok ;; esac
check "sync-status/plugin-cache" ok "$r"

section wiki-check
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

mkwiki f19; sed -i 's/"x-source-rules": \[/"x-source-rules": [,/' "$tmp/f19/.claude/settings.json"
wc_expect settings-not-json f19 'FAIL `.claude/settings.json` is not valid JSON: unexpected ","'

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

section lib-source
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
lsbad broken-access   uses-broken   "access must be mcp, script, filesystem or tools"
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
# Contract keys for research types.
lsc() { # NAME FRONTMATTER-ADDITION EXPECTED-TEXT|valid [BODY-ADDITION]
  mkdir -p "$tmp/rk/$1"
  sed "s/^cite_prefix:/$2\ncite_prefix:/" "$tmp/ls/plugin/sources/std/SOURCE.md" | sed "s/^type: .*/type: $1/" > "$tmp/rk/$1/SOURCE.md"
  [ -z "${4:-}" ] || printf '\n## Research\n%s\n' "$4" >> "$tmp/rk/$1/SOURCE.md"
  for s in $(sed -n '/^scripts:/,/^[a-z_]*:/s/^  - //p' "$tmp/rk/$1/SOURCE.md"); do touch "$tmp/rk/$1/$s"; done
  out=$(lsrun "src_validate_contract '$tmp/rk/$1/SOURCE.md'; echo exit=\$?")
  if [ "$3" = valid ]; then case "$out" in exit=0) r=ok ;; *) r="$out" ;; esac
  else case "$out" in *"$3"*exit=1) r=ok ;; *) r="$out" ;; esac; fi
  check "lib-source/$1" ok "$r"
}
lsc research-ok      'mode: research\nmain_ops:\n  - status' valid 'How to research.'
lsc agent-only-fs    'agent_only: yes' 'agent_only: yes needs access: filesystem'
lsc research-nobody  'mode: research' "mode: research needs a '## Research' section"
lsc bad-mode         'mode: sometimes' 'mode must be ingest or research'
lsc bad-agent-only   'agent_only: maybe' 'agent_only must be yes or no'
lsc bad-main-op      'main_ops:\n  - rm -rf' "main_ops item '-rf' must be a plain operation name"
check "lib-source/mode-default" ingest "$(lsrun 'src_mode "$SRC_PLUGIN/sources/std/SOURCE.md"')"
# access: tools names no tools: every tool list must be empty.
mkdir -p "$tmp/at/tl"
sed 's/^type: std/type: tl/; s/^access: script/access: tools/' "$tmp/ls/plugin/sources/std/SOURCE.md" > "$tmp/at/tl/SOURCE.md"
touch "$tmp/at/tl/read.sh"
out=$(lsrun "src_validate_contract '$tmp/at/tl/SOURCE.md'; echo exit=\$?")
for k in forbidden_tools guard_words scripts; do
  case "$out" in *"access: tools names no tools, so '$k' must be empty"*exit=1) r=ok ;; *) r="$out" ;; esac
  check "lib-source/tools-$k" ok "$r"
done
case "$out" in *"'read_tools' may hold only Read/Edit rules on ~/.cache/wiki-sources/"*exit=1) r=ok ;; *) r="$out" ;; esac
check "lib-source/tools-read_tools" ok "$r"
case "$out" in *"'bookkeeping_tools' must be empty"*) r="$out" ;; *) r=ok ;; esac
check "lib-source/tools-empty-ok" ok "$r"
awk '/^(read_tools|forbidden_tools|guard_words|scripts):/ { print; skip = 1; next } skip && /^  - / { next } { skip = 0; print }' \
  "$tmp/ls/plugin/sources/std/SOURCE.md" | sed 's/^type: std/type: tl/; s/^access: script/access: tools/' > "$tmp/at/tl/SOURCE.md"
check "lib-source/tools-valid" 0 "$(lsrun "src_validate_contract '$tmp/at/tl/SOURCE.md'; echo \$?")"
sed -i 's#^read_tools:#read_tools:\n  - Read(~/.cache/wiki-sources/*/*/**)\n  - Edit(~/.cache/wiki-sources/*/*/**)#' "$tmp/at/tl/SOURCE.md"
check "lib-source/tools-cache-rules" 0 "$(lsrun "src_validate_contract '$tmp/at/tl/SOURCE.md'; echo \$?")"

section contract-parity
# contract.py (speed plan, step 2b) against lib-source.sh: has-fm and the
# values of every frontmatter key (and one absent key) must match byte for
# byte, for every contract and instance file in the plugin and the tests,
# and for edge cases. Run directly with pyrun (see setup).
cp_edge="$tmp/cp-edge"
mkdir -p "$cp_edge"
printf -- '---\ntype: x\n  - y\n' > "$cp_edge/no-close.md"
: > "$cp_edge/empty.md"
printf '\357\273\277---\ntype: x\n---\n' > "$cp_edge/bom.md"
printf -- '--- \t\ntitle:   padded value \t \nkey:value\ntab:\tx\nempty:\nlist:\n  - a\n\t- tabbed\n  -nospace\n  - \n    - nested\n  -  trailing  \n- notindented\nFoo:\n  - upper\nfoo bar: not a key\n  - under-foo\nother: x\n  - after-scalar\n----\n---\nbody: ignored\n' > "$cp_edge/spaces.md"
sed 's/$/\r/' "$cp_edge/spaces.md" > "$cp_edge/crlf.md"
printf -- '---\ntitle: a\rb\nlist:\n  - c\r\r\n---\n' > "$cp_edge/bare-cr.md"
printf -- '---\ntitle: caf\351\nlist:\n  - \377\376\n  - ok\n---\n' > "$cp_edge/non-utf8.md"
printf -- '---\ntitle: first\ntitle: second\nlist:\n  - a\nlist:\n  - b\n---\n' > "$cp_edge/dup-keys.md"
printf -- '---\ntitle: x\n---' > "$cp_edge/no-final-newline.md"
printf -- '---\ntitle: y' > "$cp_edge/open-no-newline.md"
printf -- 'title: no fence\n---\n' > "$cp_edge/no-fence.md"
cp_bash() { # FILE KEY...
  (. "$scripts/lib-source.sh"; f=$1; shift
   src_has_fm "$f"; echo "has_fm $?"
   for k; do echo "-- $k"; src_values "$f" "$k"; done) 2>&1
}
for f in "$plugin"/sources/*/SOURCE.md $(find "$here" "$tmp/ls" -path '*/.claude/sources/*' -name '*.md' | LC_ALL=C sort) \
         "$here"/sources/*/plugin/sources/*/SOURCE.md "$cp_edge"/*.md; do
  # shellcheck disable=SC2046 # one key per word
  set -- $( (. "$scripts/lib-source.sh"; src_fm "$f") | sed -n 's/^\([A-Za-z_]\{1,\}\):.*/\1/p' | LC_ALL=C sort -u) nosuch_key
  b=$(cp_bash "$f" "$@" | od -An -tx1)
  p=$(pyrun contract parity "$f" "$@" 2>&1 | od -An -tx1)
  name=${f#"$here/"}; name=${name#"$tmp/"}; name=${name#"$plugin/"}
  check "contract-parity/$name" same "$([ "$b" = "$p" ] && echo same || printf 'bash %s python %s' "$b" "$p")"
done
# Lookups and paths.
cp_one() { # NAME BASH-SNIPPET CONTRACT.PY-ARGS...
  local name=$1 b p
  b=$(lsrun "SRC_PLUGIN='$tmp/ls/plugin'; $2; echo \"rc=\$?\"")
  shift 2
  p=$("$@" 2>&1; echo "rc=$?")
  check "contract-py/$name" "$b" "${p//"$ptmp"/$tmp}"
}
cpl="--plugin $tmp/ls/plugin"
# shellcheck disable=SC2086 # $cpl is two words
{
cp_one contract-std     'src_contract "$PWD" std'      pyrun contract $cpl contract "$lsw" std
cp_one contract-local   'src_contract "$PWD" loc'      pyrun contract $cpl contract "$lsw" loc
cp_one contract-unknown 'src_contract "$PWD" nosuch'   pyrun contract $cpl contract "$lsw" nosuch
cp_one contract-badname 'src_contract "$PWD" ../std'   pyrun contract $cpl contract "$lsw" ../std
cp_one contract-empty   'src_contract "$PWD" ""'       pyrun contract $cpl contract "$lsw" ""
mkdir -p "$lsw/.claude/sources/types/std"
cp "$tmp/ls/plugin/sources/std/SOURCE.md" "$lsw/.claude/sources/types/std/"
cp_one contract-shadow  'src_contract "$PWD" std'      pyrun contract $cpl contract "$lsw" std
rm -r "$lsw/.claude/sources/types/std"
mkdir "$lsw/.claude/sources/instances/dir.md"
touch "$lsw/.claude/sources/instances/.hidden.md" "$lsw/.claude/sources/instances/Upper.md" "$lsw/.claude/sources/instances/notes.txt"
cp_one instances        'src_instances "$PWD"'         pyrun contract instances "$lsw"
rmdir "$lsw/.claude/sources/instances/dir.md"
rm "$lsw/.claude/sources/instances/.hidden.md" "$lsw/.claude/sources/instances/Upper.md" "$lsw/.claude/sources/instances/notes.txt"
cp_one instances-none   'src_instances "$PWD/nosuch"'  pyrun contract instances "$lsw/nosuch"
}
i=0
for p in '~/two/' '~\two' 'C:\Users\x\' '//a//b//' '/' 'rel/x/' '~' '~/' 'a/./b' '/a/../b' '/a/.b/c' 'c:/x' 'C:x' '..' '.' '' 'x/..'; do
  i=$((i + 1))
  for op in expand is_abs has_dots; do
    b=$(lsrun "HOME=/home/u; src_$op '$p'; echo \" rc=\$?\"")
    q=$(HOME=/home/u pystr contract "${op//_/-}" "$p" 2>&1; echo " rc=$?")
    check "contract-py/$op-$i" "$b" "$q"
  done
done

section sources
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
sexpect catalog-jira    '- jira (standard, mcp): Jira' catalog
sexpect settings-jira-allow '"mcp__claude_ai_Atlassian__getJiraIssue"' settings jira
sexpect settings-jira-deny  '"mcp__claude_ai_Atlassian__editJiraIssue"' settings jira
sexpect settings-jira-deny2 '"mcp__claude_ai_Atlassian_MCP__executeWrite"' settings jira
check "sources/settings-jira-no-cache" 0 "$(srun settings jira | grep -c 'wiki-sources')"
sexpect list-research   '- code: type codebase (standard), research (/wiki:research code "<question>"; not ingested), valid' list
sexpect catalog-codebase '- codebase (standard, filesystem): Codebase' catalog
sexpect settings-teams-deny  '"mcp__claude_ai_Microsoft_365__teams_send_chat_message"' settings ms-teams
sexpect settings-teams-edit  '"Edit(~/.cache/wiki-sources/*/*/walk.tsv)"' settings ms-teams
sexpect settings-teams-script '"Bash(bash */sources/ms-teams/snapshot.sh *)"' settings ms-teams
sexpect settings-narrow-key   '"Edit(~/.cache/wiki-sources/sw/code/**)"' settings codebase --key code
sexpect settings-narrow-read  '"Read(~/.cache/wiki-sources/sw/code/**)"' settings codebase --key code
sexpect settings-narrow-teams '"Edit(~/.cache/wiki-sources/sw/x/walk.tsv)"' settings ms-teams --key x
sexpect settings-narrow-all   '"Edit(~/.cache/wiki-sources/sw/code/**)"' settings
sexpect settings-narrow-note  'covers them too' settings codebase --key code
sexpect settings-key-alone    '--key goes with a type' settings --key code
sexpect settings-key-bad      "invalid instance key" settings codebase --key 'a b'
sexpect catalog-onenote       '- onenote (standard, tools): OneNote' catalog
sexpect settings-tools-note   'onenote (access: tools) names no tools, so it adds no tool rules here' settings onenote
check "sources/settings-tools-empty" 0 "$(srun settings onenote | grep -c 'mcp__\|Bash(')"
check "sources/settings-tools-quiet" 0 "$(srun settings gmail | grep -c 'access: tools')"
printf -- '---\nkey: notes\ntype: onenote\nsections:\n  - Book > Tab\nstate:\n  - last_checked\n  - cursor\n---\n' > "$tmp/sw/.claude/sources/instances/notes.md"
sexpect show-tools-instance   'Source notes: valid' show notes
sexpect settings-tools-all    'onenote (access: tools) names no tools' settings
sexpect settings-tools-cache  '"Edit(~/.cache/wiki-sources/sw/notes/**)"' settings onenote --key notes
rm "$tmp/sw/.claude/sources/instances/notes.md"
# A local type shadowing a standard one: the error names the fix order, and
# `contract` still shows the standard contract to migrate to.
mkdir -p "$tmp/sw/.claude/sources/types/onenote"
cp "$tmp/sw/.claude/sources/types/bookish/SOURCE.md" "$tmp/sw/.claude/sources/types/onenote/"
sexpect shadow-fix-order      'delete the folder .claude/sources/types/onenote/' contract onenote
sexpect shadow-contract       'shown is the standard contract' contract onenote
sexpect shadow-contract-body  '# Source type: OneNote' contract onenote
rm -r "$tmp/sw/.claude/sources/types/onenote"
# check-settings: start from what `settings` prints, then plant one fault each.
sjson=$(srun settings | sed -n '/^{/,/^}/p')
sck() { # NAME EXIT TEXT [SED]: plant SED in settings.json, run check-settings
  printf '%s\n' "$sjson" > "$tmp/sw/.claude/settings.json"
  [ -z "${4:-}" ] || sed -i "$4" "$tmp/sw/.claude/settings.json"
  o=$(srun check-settings; printf '@%s' "$?")
  case "$o" in *"$3"*"@$2") r=ok ;; *) r="$o" ;; esac
  check "sources/check-settings-$1" ok "$r"
}
sck ok          0 'missing: none'
sck ok-json     0 'settings.json: valid JSON'
sck trailing    1 'NOT valid JSON: comma before ]' '0,/",$/s//",\n/; 0,/^      "[^"]*"$/s//&,/'
sck no-comma    1 'NOT valid JSON: expected , or ] (a missing comma?)' '0,/",$/s/",$/"/'
sck unclosed    1 'NOT valid JSON: unexpected end of file' '$d'
sck missing     1 'allow: Edit(~/.cache/wiki-sources/sw/code/**)' '/wiki-sources\/sw\/code\/\*\*)"/{/Edit/d}'
sck dup         1 'duplicates:' 's#^\(      "mcp__claude_ai_Gmail__send_message"\)\(,\{0,1\}\)$#\1,\n\1\2#'
sck conflict    1 'in both allow and deny' 's#^\(      "Bash(bash \*/sources/codebase/git.sh \*)"\)\(,\{0,1\}\)$#\1,\n      "mcp__claude_ai_Gmail__send_message"\2#'
sck broad-ok    0 'note: these rules reach every wiki' 's#"Edit(~/.cache/wiki-sources/sw/code/\*\*)"#"Edit(~/.cache/wiki-sources/**)"#'
rm -f "$tmp/sw/.claude/settings.json"
sexpect check-settings-none 'settings.json: missing' check-settings
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

section install
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
cbi="---\nkey: code\ntype: codebase\nroots:\n  - $tmp/iw\n---\n"
iexpect codebase-narrow '"Edit(~/.cache/wiki-sources/iw/code/**)",' 0 y instances/code.md "$cbi"
sed -i 's#"mcp__claude_ai_Gmail__search_threads"#"mcp__claude_ai_Gmail__search_threads", "Edit(~/.cache/wiki-sources/**)"#' "$tmp/iw/.claude/settings.json"
o=$(inst y instances/code.md "${cbi}Notes.\n")
case "$o" in *'"Edit(~/.cache/wiki-sources/iw/code/**)"'*) r=listed ;; *) r=omitted ;; esac
check "install/broad-cache-rule-counts" omitted "$r"
rm -f "$tmp/iw/.claude/sources/instances/code.md"
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

section ms-teams
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

section ocr
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

section plugin-schema
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

section ""
[ -n "$sec_lines" ] && printf '\n%s' "$sec_lines"
printf '\n%d checks, %d failed\n' "$total" "$fail"
[ "$fail" -eq 0 ]
