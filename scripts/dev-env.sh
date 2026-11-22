# dev-env.sh: the repo's dev environment (.venv, made by `uv sync --locked`
# from uv.lock; docs/development.md, "Dev environment"), for run-tests.sh
# and dev-lint.sh. Sourced, never run: it only defines things, never exits,
# and is safe under set -u.
#
#   _de_root        the repo root
#   _de_venv LABEL  0: .venv is current; sets _de_py (its Python) and
#                   _de_bin (its tool folder)
#                   1: it can't be used; the reason on stderr
#                   2: WIKI_TOOLS_DEV_VENV=off: use the tools on PATH,
#                   outside uv.lock
#
# Repo tooling, not part of the plugin: the wikis never run it. uv is a
# prerequisite; this never installs anything (`uv sync --locked --check`
# only checks) and never runs a tool through uv.

_de_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
_de_py=
_de_bin=

_de_venv() {
  local label=$1 rc=0
  _de_py= _de_bin=
  case ${WIKI_TOOLS_DEV_VENV:-} in
    '') ;;
    off)
      printf '%s: WIKI_TOOLS_DEV_VENV=off: tools from PATH, outside uv.lock\n' "$label" >&2
      return 2 ;;
    *)
      printf '%s: WIKI_TOOLS_DEV_VENV must be off or unset\n' "$label" >&2
      return 1 ;;
  esac
  if [ -n "${UV_PROJECT_ENVIRONMENT:-}" ]; then
    printf '%s: UV_PROJECT_ENVIRONMENT is set; these scripts use .venv. Unset it.\n' "$label" >&2
    return 1
  fi
  if ! command -v uv >/dev/null 2>&1; then
    printf '%s: uv not found. Install uv 0.13.7 or later (https://docs.astral.sh/uv/getting-started/installation/; a distribution'"'"'s package may be older), then run: uv sync --locked\n' "$label" >&2
    return 1
  fi
  # A subshell cd, so no path goes through Git Bash's argument conversion.
  # UV_PYTHON_DOWNLOADS: a user's own value would override pyproject.toml's
  # python-downloads = "never", and --check downloads too.
  (cd "$_de_root" && UV_PYTHON_DOWNLOADS=never uv sync --locked --check -q) || rc=$?
  if [ "$rc" -eq 1 ]; then
    printf '%s: .venv is missing or out of date with uv.lock. Run: uv sync --locked\n' "$label" >&2
    return 1
  elif [ "$rc" -ne 0 ]; then
    printf '%s: uv could not check .venv (its message is above)\n' "$label" >&2
    return 1
  fi
  if [ -f "$_de_root/.venv/bin/python" ] && [ -x "$_de_root/.venv/bin/python" ]; then
    _de_bin=$_de_root/.venv/bin _de_py=$_de_root/.venv/bin/python
  elif [ -f "$_de_root/.venv/Scripts/python.exe" ] && [ -x "$_de_root/.venv/Scripts/python.exe" ]; then
    _de_bin=$_de_root/.venv/Scripts _de_py=$_de_root/.venv/Scripts/python.exe
  else
    printf '%s: .venv is missing or out of date with uv.lock. Run: uv sync --locked\n' "$label" >&2
    return 1
  fi
  return 0
}
