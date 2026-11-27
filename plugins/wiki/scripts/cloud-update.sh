#!/usr/bin/env bash
# cloud-update.sh: in a Claude Code cloud session, fast-forward the
# wiki-tools clone the plugin runs from (cloud/SETUP.md, "Keeping the
# plugin current"; docs/adr.md, 19). The first SessionStart hook, at
# startup and resume: a cloud environment keeps its setup script's clone
# in a snapshot for about a week.
#
# Acts only when CLAUDE_CODE_REMOTE is true and the plugin root (this
# folder's parent) is plugins/wiki of a git clone on main (for now the only
# branch followed; anything else, detached included, is left alone). It
# fetches main from origin and fast-forwards.
# Output (stdout, into the session context), one line or nothing:
#   wiki plugin updated <old> -> <new>
#   wiki plugin: update check failed; this session runs <old>
# Never blocks a session: exit 0 always; the fetch stops after 15 s (git's
# low-speed limit and a watchdog: Git Bash may find Windows' timeout.exe
# first). Git runs cleaned, as save.py's: every GIT_* variable dropped but
# GIT_SSL_CAINFO and GIT_SSL_CAPATH (the cloud proxy's CA), no prompt, no
# replace objects, the plugin's empty git-hooks-off as hooks, TLS checked.
# One function, parsed before it runs: the merge may replace this file.

_cu_main() {
  [ "${CLAUDE_CODE_REMOTE:-}" = true ] || return 0
  local d root top old new branch v pid w rc=0
  d=${BASH_SOURCE[0]%/*}
  [ "$d" != "${BASH_SOURCE[0]}" ] || d=.
  root=$(cd "$d/.." 2>/dev/null && pwd) || return 0
  if [ -f "$root/.wiki-tools-ref" ]; then
    echo "wiki plugin: this environment copies the plugin, so it can't update; see the setup script in cloud/SETUP.md"
    return 0
  fi
  top=$(cd "$root/../.." 2>/dev/null && pwd) || return 0
  [ -e "$top/.git" ] && [ -f "$top/plugins/wiki/.claude-plugin/plugin.json" ] || return 0
  for v in $(compgen -e); do
    case "$v" in GIT_SSL_CAINFO|GIT_SSL_CAPATH) ;; GIT_*) unset "$v" ;; esac
  done
  export GIT_TERMINAL_PROMPT=0 GIT_NO_REPLACE_OBJECTS=1
  local -a g=(git -C "$top" -c core.hooksPath="$root/git-hooks-off" -c http.sslVerify=true)
  local fail="wiki plugin: update check failed; this session runs"
  if ! old=$("${g[@]}" rev-parse -q --verify 'HEAD^{commit}' 2>/dev/null); then
    echo "$fail an unreadable clone"
    return 0
  fi
  [ "$("${g[@]}" -C "$root" rev-parse --show-prefix 2>/dev/null)" = plugins/wiki/ ] || return 0
  branch=$("${g[@]}" symbolic-ref -q --short HEAD 2>/dev/null) || return 0
  [ "$branch" = main ] || return 0

  # The fetch, stopped after 15 s whatever hangs (DNS, the proxy, a stall).
  "${g[@]}" -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=10 fetch -q --no-tags origin \
    "+refs/heads/$branch:refs/remotes/origin/$branch" </dev/null >/dev/null 2>&1 &
  pid=$!
  ( sleep 15; kill "$pid" ) </dev/null >/dev/null 2>&1 &
  w=$!
  wait "$pid" || rc=$?
  kill "$w" 2>/dev/null
  if [ "$rc" -ne 0 ] \
     || ! "${g[@]}" merge -q --ff-only "refs/remotes/origin/$branch" </dev/null >/dev/null 2>&1 \
     || ! new=$("${g[@]}" rev-parse -q --verify 'HEAD^{commit}' 2>/dev/null); then
    echo "$fail ${old:0:7}"
  elif [ "$new" != "$old" ]; then
    echo "wiki plugin updated ${old:0:7} -> ${new:0:7}"
  fi
  return 0
}

_cu_main; exit 0
