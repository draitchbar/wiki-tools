#!/usr/bin/env bash
# dev-lint.sh: the repo's lint, as CI's lint job runs it. No arguments.
#
#   bash scripts/dev-lint.sh
#
# Four steps, each run even after one fails: ruff (ruff.toml), mypy
# (mypy.ini), shellcheck -S warning on every tracked *.sh (.shellcheckrc),
# and LF line endings only. The tools come from .venv, which uv makes from
# uv.lock (docs/development.md, "Dev environment"):
#   uv sync --locked
# WIKI_TOOLS_DEV_VENV=off takes them from PATH instead, outside uv.lock.
# Repo tooling, not part of the plugin (the plugin's own lint.sh lints a
# wiki).

here=$(cd "$(dirname "$0")" && pwd)
. "$here/dev-env.sh"
cd "$_de_root" || exit 1
rc=0
_de_venv dev-lint || rc=$?
if [ "$rc" -eq 0 ]; then
  PATH="$_de_bin:$PATH"
elif [ "$rc" -ne 2 ]; then
  exit 1
fi

gh=
[ "${GITHUB_ACTIONS:-}" = true ] && gh=1
failed=()

# step NAME TOOL: a header line, and the tool must be there.
step() {
  printf '== %s\n' "$1"
  if ! command -v "$2" >/dev/null 2>&1; then
    printf 'dev-lint: %s is not installed\n' "$2" >&2
    return 1
  fi
}

if step ruff ruff; then
  if [ -n "$gh" ]; then ruff check --output-format=github .; else ruff check .; fi || failed+=(ruff)
else
  failed+=(ruff)
fi

if step mypy mypy; then
  mypy || failed+=(mypy)
else
  failed+=(mypy)
fi

if step shellcheck shellcheck; then
  git ls-files -z '*.sh' | xargs -0 shellcheck -S warning || failed+=(shellcheck)
else
  failed+=(shellcheck)
fi

printf '== %s\n' 'LF line endings'
if git ls-files -z | xargs -0 grep -lI $'\r' --; then
  if [ -n "$gh" ]; then
    echo "::error::CRLF line endings in the files above"
  else
    echo "dev-lint: CRLF line endings in the files above" >&2
  fi
  failed+=(LF)
fi

if [ "${#failed[@]}" -gt 0 ]; then
  printf 'dev-lint: failed: %s\n' "${failed[*]}" >&2
  exit 1
fi
echo 'dev-lint: clean'
