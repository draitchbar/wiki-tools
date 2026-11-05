# py-launch.sh: run one of this plugin's Python hooks, failing closed.
# Sourced by the hook command, so no bash starts besides Claude Code's own:
#
#   . "${CLAUDE_PLUGIN_ROOT}/scripts/py-launch.sh" <name>
#
# runs <this folder>/<name>.py on the hook's stdin and exits with its code.
# Any exit other than 0 (allow) or 2 (block) becomes a block: Python exits
# 1 on an error before the script's own handler runs, and bash 126/127 when
# it can't start the program.
#
# The interpreter: the path cached in $CLAUDE_PLUGIN_DATA/python, if it is
# absolute, executable and named python*. Otherwise each of python3, python
# and `py -3` is asked for its version and sys.executable; the first 3.9 or
# later is cached and used. The probe rejects the Windows Store alias
# (it doesn't run) and turns `py -3` into a real path. Without
# CLAUDE_PLUGIN_DATA nothing is cached and every call probes (slow, safe).
# The cache is under ~/.claude/plugins/, which the guard protects: a cache
# pointing at a program that exits 0 would let every call through.
#
# WIKI_HOOK_TIMING=1 appends "<script> <ms> rc=<code> <interpreter>
# <plugin scripts folder>" to $CLAUDE_PLUGIN_DATA/hook-timing.log.
#
# Builtins only on the fast path: every process start costs ~30-50 ms in
# Git Bash.

_pl_block() {
  printf 'wiki guard: %s; refusing (fail closed).\n' "$1" >&2
  exit 2
}

case "${1:-}" in
  ''|*[!a-z_]*) _pl_block "py-launch.sh: bad script name '${1:-}'" ;;
esac
_pl_dir=${BASH_SOURCE[0]%/*}
[ "$_pl_dir" != "${BASH_SOURCE[0]}" ] || _pl_dir=.
[ -f "$_pl_dir/$1.py" ] || _pl_block "py-launch.sh: no script $_pl_dir/$1.py"

# _pl_ok PATH: an absolute path to an executable named python*.
_pl_ok() {
  case "$1" in /*|[A-Za-z]:/*) ;; *) return 1 ;; esac
  case "${1##*/}" in python*|Python*) ;; *) return 1 ;; esac
  [ -f "$1" ] && [ -x "$1" ]
}

_pl_cache=${CLAUDE_PLUGIN_DATA:+$CLAUDE_PLUGIN_DATA/python}
_pl_py=
if [ -n "$_pl_cache" ] && [ -f "$_pl_cache" ]; then
  IFS= read -r _pl_py < "$_pl_cache" || true
  _pl_py=${_pl_py%$'\r'}
  _pl_ok "$_pl_py" || _pl_py=
fi

if [ -z "$_pl_py" ]; then
  # Slow path: one run per candidate. Forward slashes, so Git Bash can test
  # a Windows path with -x.
  _pl_probe='import sys; print(("ok " if sys.version_info >= (3, 9) else "old ") + sys.executable.replace(chr(92), "/"))'
  for _pl_c in python3 python "py -3"; do
    # shellcheck disable=SC2086 # "py -3" is two words
    _pl_out=$($_pl_c -I -S -c "$_pl_probe" 2>/dev/null </dev/null) || continue
    _pl_out=${_pl_out%$'\r'}
    case "$_pl_out" in "ok "*) ;; *) continue ;; esac
    _pl_ok "${_pl_out#ok }" || continue
    _pl_py=${_pl_out#ok }
    break
  done
  [ -n "$_pl_py" ] || _pl_block "no Python 3.9 or later found (tried python3, python, py -3). Install it (Windows: from python.org, and turn off the python3 App execution alias), then start Claude again"
  if [ -n "$_pl_cache" ]; then
    { mkdir -p "$CLAUDE_PLUGIN_DATA" &&
      printf '%s\n' "$_pl_py" > "$_pl_cache.$$" &&
      mv -f "$_pl_cache.$$" "$_pl_cache"; } 2>/dev/null || rm -f "$_pl_cache.$$" 2>/dev/null
  fi
fi

_pl_t0=${EPOCHREALTIME//[!0-9]/}
"$_pl_py" -I -S -X utf8 "$_pl_dir/$1.py"
_pl_rc=$?
if [ "${WIKI_HOOK_TIMING:-}" = 1 ] && [ -n "${CLAUDE_PLUGIN_DATA:-}" ]; then
  _pl_t1=${EPOCHREALTIME//[!0-9]/}
  printf '%s %d rc=%d %s %s\n' "$1" $(((_pl_t1 - _pl_t0) / 1000)) "$_pl_rc" "$_pl_py" "$_pl_dir" \
    >> "$CLAUDE_PLUGIN_DATA/hook-timing.log" 2>/dev/null
fi
case "$_pl_rc" in
  0|2) exit "$_pl_rc" ;;
  *) _pl_block "$1.py failed (exit $_pl_rc)" ;;
esac
