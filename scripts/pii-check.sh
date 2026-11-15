#!/usr/bin/env bash
# pii-check.sh: find personal data in commits, a tree or a text before it
# reaches the public repo. Usage and rules: pii_check.py beside this file;
# docs/development.md, "Personal data".
#
# Repo tooling, not part of the plugin: the wikis never run it. Python is
# found as the plugin's scripts find it (py-run.sh); no Python fails, so the
# pre-push hook blocks rather than let a push through unchecked.

here=$(cd "$(dirname "$0")" && pwd)
. "$here/../plugins/wiki/scripts/py-run.sh"
_pr_find || { printf 'pii-check: %s\n' "$_pr_nopy" >&2; exit 2; }
_pr_dir=$here _pr_found=1 _pr_call pii_check "$@"
