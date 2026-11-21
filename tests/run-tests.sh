#!/usr/bin/env bash
# Run the test suite (pytest: tests/test_*.py, tests/conftest.py).
#
#   bash tests/run-tests.sh            every test
#   bash tests/run-tests.sh --e2e      in-process tests through the launchers instead
#   bash tests/run-tests.sh ARGS...    pytest's options, e.g. -k guard -x
#
# With pytest-xdist installed the modules run in parallel, one module per
# worker (-n auto --dist loadfile: a module's story fixture runs once);
# -n 0 runs serially. Optional; CI installs it (docs/adr.md, 15).
#
# pytest is the only thing to install for the tests, not pinned:
#   python -m pip install --user --upgrade pytest   (Windows: py -3 -m pip ...)
#   ... pytest pytest-xdist                         (optional: parallel runs)
#   sudo apt install python3-pytest                 (Debian/Ubuntu's own Python)
# Python is found as the plugin's scripts find it (py-run.sh). No -I: it
# would hide a pip --user pytest.

here=$(cd "$(dirname "$0")" && pwd)
. "$here/../plugins/wiki/scripts/py-run.sh"
_pr_find || { printf 'run-tests: %s\n' "$_pr_nopy" >&2; exit 1; }
if ! "$_pr_py" -c 'import pytest' 2>/dev/null; then
  printf 'run-tests: pytest is not installed for %s. Install it:\n  %s -m pip install --user --upgrade pytest\n(Debian/Ubuntu system Python: sudo apt install python3-pytest)\n' "$_pr_py" "$_pr_py" >&2
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
if "$_pr_py" -c 'import xdist' 2>/dev/null; then
  par=(-n auto --dist loadfile)
  for a in "$@"; do [ "$a" = --check-names ] && par=(); done
fi

exec "$_pr_py" -X utf8 -m pytest "$here" "${par[@]}" "$@"
