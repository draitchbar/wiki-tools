# py-run.sh: run one of this plugin's Python scripts (not hooks;
# docs/adr.md, 4). Two uses:
#
#   bash py-run.sh <name> ARGS...   run <this folder>/<name>.py with ARGS,
#                                   stdin passed through, its exit code kept
#   . py-run.sh                     (sourced) define _pr_call <name> ARGS...,
#                                   which does the same and returns the code
#
# lib-source.sh sources it inside its bridged functions, so scripts that
# never call one pay nothing. Sourced, it only defines functions: it must
# never exit, and it is safe under set -u.
#
# For hooks use py-launch.sh, which fails closed. This file is never in the
# guard's CORE_SCRIPTS or an allow rule: it would run any .py beside it.
#
# The interpreter (no cache is written): the path in
# $CLAUDE_PLUGIN_DATA/python-3.11 (the hooks and the tests set it), else the
# hooks' cache ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/data/wiki-wiki-tools/python-3.11,
# if it is absolute, executable and named python*; else the same probe as
# py-launch.sh (python, python3, `py -3`; 3.11 or later; not the Store
# alias). The floor, _pr_floor, names the cache file, as in py-launch.sh: a
# cache from before the floor rose (the old `python`) is never read.
# No Python: exit 1 with a message (not "refusing": a script isn't a guard).
#
# Windows (Git Bash): Git Bash rewrites a native program's arguments that
# look like POSIX paths. The Python command alone runs with
# MSYS2_ARG_CONV_EXCL='*' (a prefix, never exported: the caller's later
# native calls still need conversion), so arguments arrive as written; the
# .py path is handed over in native form. The scripts refuse Git Bash mount
# paths (/tmp, /home, ...): callers pass those as `pwd -W` prints them.
#
# Builtins only on the fast path: every process start costs ~25 ms in Git
# Bash.

# The Python floor: the cache's name, the probe and the message (the same
# as py-launch.sh's _pl_floor; a test checks it).
_pr_floor=3.11

# _pr_ok PATH: an absolute path to an executable named python*.
_pr_ok() {
  case "$1" in /*|[A-Za-z]:/*) ;; *) return 1 ;; esac
  case "${1##*/}" in python*|Python*) ;; *) return 1 ;; esac
  [ -f "$1" ] && [ -x "$1" ]
}

# _pr_find: set _pr_py to the interpreter, or return 1.
_pr_find() {
  local f c out
  _pr_py=
  for f in ${CLAUDE_PLUGIN_DATA:+"$CLAUDE_PLUGIN_DATA/python-$_pr_floor"} \
           "${CLAUDE_CONFIG_DIR:-${HOME:-}/.claude}/plugins/data/wiki-wiki-tools/python-$_pr_floor"; do
    [ -f "$f" ] || continue
    IFS= read -r _pr_py < "$f" || true
    _pr_py=${_pr_py%$'\r'}
    _pr_ok "$_pr_py" && return 0
    _pr_py=
  done
  # Same candidates, in the same order, as py-launch.sh (a test checks it).
  local probe='import sys; print(("ok " if sys.version_info >= ('"${_pr_floor/./, }"') else "old ") + sys.executable.replace(chr(92), "/"))'
  for c in python python3 "py -3"; do
    # shellcheck disable=SC2086 # "py -3" is two words
    out=$($c -I -S -c "$probe" 2>/dev/null </dev/null) || continue
    out=${out%$'\r'}
    case "$out" in "ok "*) ;; *) continue ;; esac
    _pr_ok "${out#ok }" || continue
    _pr_py=${out#ok }
    return 0
  done
  return 1
}

# _pr_native PATH: set _pr_nat to PATH as a Windows program opens it
# (/c/x -> c:/x; a Git Bash mount through pwd -W); unchanged off Windows.
_pr_native() {
  _pr_nat=$1
  case "${MSYSTEM:-}${OSTYPE:-}" in *MINGW*|*MSYS*|*msys*|*cygwin*) ;; *) return 0 ;; esac
  case "$1" in
    /[A-Za-z]/*) _pr_nat="${1:1:1}:/${1:3}" ;;
    /*) _pr_nat="$(cd "${1%/*}" 2>/dev/null && pwd -W)/${1##*/}" ;;
  esac
}

# The no-Python message, after "<script>: ".
_pr_nopy="no Python $_pr_floor or later found (tried python, python3, py -3). Install it (Windows: from python.org, and turn off the python3 App execution alias), then start Claude again"

# _pr_call NAME ARGS...: run NAME.py from this folder; its exit code.
# $_pr_label, if set, names the script in the no-Python message instead
# (wiki-check, not wiki_check). $_pr_found set: a caller's own _pr_find
# just succeeded, so _pr_py is used without a second lookup.
_pr_call() {
  local name=$1 dir
  shift
  dir=${_pr_dir:-.}
  if [ -z "${_pr_found:-}" ] && ! _pr_find; then
    printf '%s: %s\n' "${_pr_label:-$name}" "$_pr_nopy" >&2
    return 1
  fi
  _pr_native "$dir/$name.py"
  MSYS2_ARG_CONV_EXCL='*' "$_pr_py" -I -S -X utf8 "$_pr_nat" "$@"
}

_pr_dir=${BASH_SOURCE[0]%/*}
[ "$_pr_dir" != "${BASH_SOURCE[0]}" ] || _pr_dir=.

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  case "${1:-}" in
    ''|*[!a-z_]*) printf 'py-run.sh: bad script name %s\n' "'${1:-}'" >&2; exit 2 ;;
  esac
  [ -f "$_pr_dir/$1.py" ] || { printf 'py-run.sh: no script %s\n' "$_pr_dir/$1.py" >&2; exit 2; }
  _pr_call "$@"
  exit $?
fi
