#!/usr/bin/env bash
# cloud-update.sh: in a Claude Code cloud session, bring this plugin up to
# date from the wiki-tools clone the environment's setup script made
# (cloud/SETUP.md, "Keeping the plugin current"; docs/adr.md, 27).
#
#   bash <plugin>/scripts/cloud-update.sh
#
# Runs as the first SessionStart hook (matcher startup|resume: a resumed
# session in a fresh container starts from the snapshot too). A cloud
# environment caches its setup script's result as a snapshot for about a
# week, so without this a session could run a plugin that old.
#
# It acts only when all hold, else exits silently:
#   - CLAUDE_CODE_REMOTE is true;
#   - the plugin root (this folder's parent) is the setup script's copy:
#     it has .wiki-tools-ref;
#   - the setup script's clone exists: `clone=` in the plugin root's
#     .wiki-tools-setup, else /opt/wiki-tools;
#   - the setup script took a branch: `kind=branch` in .wiki-tools-setup;
#     without that file's `kind=` line, the clone being on a branch. A
#     commit (`kind=commit`, or a detached clone) is pinned: nothing to do.
# Then it fetches that branch from the clone's origin, resets the clone's
# branch to it, copies plugins/wiki/. over the plugin root in place, writes
# the commit to .wiki-tools-ref and prunes what the commit no longer has.
#
# Output (stdout becomes session context, as schema.sh's): one line,
#   wiki plugin updated <old> -> <new>
#   wiki plugin: update check failed; this session runs the snapshot's <old>
#   wiki plugin: update to <new> failed; this session runs the snapshot's <old>
#   wiki plugin: update to <new> failed while copying; files may be mixed until the next session
# and nothing when already current or not applicable. "update check
# failed" also covers a clone git can't read (e.g. dubious ownership).
#
# A hook that must never block or slow a session: it exits 0 on every
# path, and the fetch is stopped after 15 s (git's low-speed limit, and a
# watchdog, which needs no `timeout` program: Git Bash's PATH may find
# Windows' own timeout.exe first). Git runs in a cleaned environment, as
# save.py's: every GIT_* variable is dropped except GIT_SSL_CAINFO and
# GIT_SSL_CAPATH (the cloud proxy's CA), GIT_TERMINAL_PROMPT=0, with
# `-c core.hooksPath=<the plugin's empty git-hooks-off>` and
# `-c http.sslVerify=true`. HOME and the proxy variables (HTTPS_PROXY, ...)
# stay: the cloud fetch needs them.
#
# Copied in place first, then pruned, never by deleting the plugin folder:
# the guard runs on every tool call and a missing plugin would block calls.
# The prune removes files under the plugin root that the commit's
# plugins/wiki doesn't have (a removed source type's SOURCE.md would stay
# live: the guard and sources.sh glob the types, skills and agents are found
# by folder, save.sh refuses anything but git-hooks-off/README), keeping
# the root's .wiki-tools-* files and __pycache__ folders, then the folders
# left empty. The other SessionStart hooks of the same session start
# alongside this one and may run the old version; Claude Code read
# hooks.json before. The whole script is one function, parsed before it
# runs: the copy may overwrite this very file.

_cu_git() {
  git -c core.hooksPath="$_cu_hooks" -c http.sslVerify=true "$@"
}

# _cu_prune ROOT CLONE: remove what the clone's plugins/wiki doesn't track.
_cu_prune() {
  local root=$1 clone=$2 f rel d
  local -A keep=()
  local -a gone=()
  while IFS= read -r -d '' f; do
    keep[${f#plugins/wiki/}]=1
  done < <(_cu_git -C "$clone" ls-files -z -- plugins/wiki 2>/dev/null)
  [ -n "${keep[.claude-plugin/plugin.json]:-}" ] || return 0
  shopt -s globstar dotglob nullglob
  for f in "$root"/**; do
    rel=${f#"$root"/}
    [ -n "$rel" ] || continue
    case "/$rel/" in */__pycache__/*) continue ;; esac
    case "$rel" in .wiki-tools-*) continue ;; esac
    if [ -d "$f" ] && [ ! -L "$f" ]; then continue; fi
    [ -n "${keep[$rel]:-}" ] || gone+=("$f")
  done
  [ "${#gone[@]}" -gt 0 ] || return 0
  rm -f -- "${gone[@]}" 2>/dev/null
  for f in "${gone[@]}"; do
    d=${f%/*}
    while [ "$d" != "$root" ] && rmdir -- "$d" 2>/dev/null; do d=${d%/*}; done
  done
  return 0
}

_cu_main() {
  [ "${CLAUDE_CODE_REMOTE:-}" = true ] || return 0
  local d root rec clone=/opt/wiki-tools kind= k v old new branch pid w rc
  d=${BASH_SOURCE[0]%/*}
  [ "$d" != "${BASH_SOURCE[0]}" ] || d=.
  root=$(cd "$d/.." 2>/dev/null && pwd) || return 0
  [ -f "$root/.wiki-tools-ref" ] || return 0
  IFS= read -r old < "$root/.wiki-tools-ref" || [ -n "$old" ] || return 0
  old=${old%$'\r'}
  rec=$root/.wiki-tools-setup
  if [ -f "$rec" ]; then
    while IFS='=' read -r k v || [ -n "$k" ]; do
      v=${v%$'\r'}
      case "$k" in
        clone) clone=$v ;;
        kind) kind=$v ;;
      esac
    done < "$rec"
  fi
  case "$clone" in /*|[A-Za-z]:/*) ;; *) return 0 ;; esac
  [ -d "$clone/.git" ] && [ -d "$clone/plugins/wiki" ] || return 0
  _cu_hooks=$root/git-hooks-off
  [ -d "$_cu_hooks" ] || return 0
  case "$kind" in
    commit) return 0 ;;
    branch|'') ;;
    *) return 0 ;;
  esac
  for v in $(compgen -e); do
    case "$v" in
      GIT_SSL_CAINFO|GIT_SSL_CAPATH) ;;
      GIT_*) unset "$v" ;;
    esac
  done
  export GIT_TERMINAL_PROMPT=0 GIT_NO_REPLACE_OBJECTS=1

  # Detached (exit 1): pinned. Any other failure: git can't read the clone.
  rc=0
  branch=$(_cu_git -C "$clone" symbolic-ref -q --short HEAD 2>/dev/null) || rc=$?
  if [ "$rc" -eq 1 ]; then
    return 0
  elif [ "$rc" -ne 0 ]; then
    printf "wiki plugin: update check failed; this session runs the snapshot's %s\n" "${old:0:7}"
    return 0
  fi
  case "$branch" in ''|-*|*[!A-Za-z0-9._/-]*) return 0 ;; esac

  # The fetch, stopped after 15 s whatever hangs (DNS, the proxy, a stall).
  _cu_git -C "$clone" -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=10 \
    fetch -q --no-tags origin "+refs/heads/$branch:refs/remotes/origin/$branch" \
    </dev/null >/dev/null 2>&1 &
  pid=$!
  ( sleep 15; kill "$pid" ) </dev/null >/dev/null 2>&1 &
  w=$!
  rc=0
  wait "$pid" || rc=$?
  kill "$w" 2>/dev/null
  new=
  [ "$rc" -eq 0 ] && new=$(_cu_git -C "$clone" rev-parse -q --verify "refs/remotes/origin/$branch^{commit}" 2>/dev/null)
  if [ -z "$new" ]; then
    printf "wiki plugin: update check failed; this session runs the snapshot's %s\n" "${old:0:7}"
    return 0
  fi
  [ "$new" != "$old" ] || return 0
  if ! _cu_git -C "$clone" reset -q --hard "$new" </dev/null >/dev/null 2>&1 \
     || [ ! -f "$clone/plugins/wiki/.claude-plugin/plugin.json" ]; then
    printf "wiki plugin: update to %s failed; this session runs the snapshot's %s\n" "${new:0:7}" "${old:0:7}"
    return 0
  fi
  if cp -r "$clone/plugins/wiki/." "$root/" 2>/dev/null \
     && printf '%s\n' "$new" > "$root/.wiki-tools-ref"; then
    _cu_prune "$root" "$clone"
    printf 'wiki plugin updated %s -> %s\n' "${old:0:7}" "${new:0:7}"
  else
    printf 'wiki plugin: update to %s failed while copying; files may be mixed until the next session\n' "${new:0:7}"
  fi
  return 0
}

_cu_main; exit 0
