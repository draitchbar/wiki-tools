#!/usr/bin/env bash
# Run the test suite (pytest: tests/test_*.py, tests/conftest.py).
#
#   bash tests/run-tests.sh            every test
#   bash tests/run-tests.sh --e2e      most in-process tests through the launchers (docs/development.md, "Tests")
#   bash tests/run-tests.sh ARGS...    pytest's options, e.g. -k guard -x
#
# pytest, pytest-xdist and the lint tools come from .venv, which uv makes
# from uv.lock (docs/development.md, "Dev environment"). Once per clone
# and per worktree, and whenever this says .venv is out of date:
#   uv sync --locked
# The modules run in parallel, one module per worker (-n auto --dist
# loadfile: a module's story fixture runs once); -n 0 runs serially.
#
# WIKI_TOOLS_DEV_VENV=off runs pytest from the Python the plugin's scripts
# would find (py-run.sh), outside uv.lock; it then needs pytest installed
# there (pytest-xdist optional):
#   python -m pip install --user --upgrade pytest   (Windows: py -3 -m pip ...)
#   sudo apt install python3-pytest                 (Debian/Ubuntu's own Python)

here=$(cd "$(dirname "$0")" && pwd)
. "$here/../scripts/dev-env.sh"
rc=0
_de_venv run-tests || rc=$?
if [ "$rc" -eq 0 ]; then
  py=$_de_py
elif [ "$rc" -eq 2 ]; then
  . "$here/../plugins/wiki/scripts/py-run.sh"
  _pr_find || { printf 'run-tests: %s\n' "$_pr_nopy" >&2; exit 1; }
  if ! "$_pr_py" -c 'import pytest' 2>/dev/null; then
    printf 'run-tests: pytest is not installed for %s. Install it:\n  %s -m pip install --user --upgrade pytest\n(Debian/Ubuntu system Python: sudo apt install python3-pytest)\n' "$_pr_py" "$_pr_py" >&2
    exit 1
  fi
  py=$_pr_py
else
  exit 1
fi

# The personal-data hook (docs/development.md, "Personal data"): say so
# when this clone hasn't switched it on. Not in CI, which checks PRs itself.
if [ -z "${CI:-}" ] && [ "$(git -C "$here/.." config core.hooksPath 2>/dev/null)" != .githooks ]; then
  printf 'run-tests: the pre-push personal-data check is off in this clone. Switch it on:\n  git config core.hooksPath .githooks\n' >&2
fi

# Parallel when pytest-xdist is there, except for --check-names, which
# prints at collection and so needs one process. Arguments after these
# win (-n 0).
par=()
if "$py" -c 'import xdist' 2>/dev/null; then
  par=(-n auto --dist loadfile)
  for a in "$@"; do [ "$a" = --check-names ] && par=(); done
fi

# In CI, the 20 slowest tests after the summary: a module that grows slow
# shows up in the log (#115). No time limit is checked.
dur=()
[ -n "${CI:-}" ] && dur=(--durations=20)

exec "$py" -X utf8 -m pytest "$here" "${par[@]}" "${dur[@]}" "$@"
