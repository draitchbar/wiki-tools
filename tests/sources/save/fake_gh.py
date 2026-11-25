"""Stand-in for the gh CLI in tests/test_save.py, so tests never touch
GitHub. test_save.py puts a `gh` launcher for it first on PATH (a shell
script, or gh.cmd on Windows) that runs it with the test's Python.

Every call is appended to $FAKE_GH_LOG as one JSON line (the arguments).
$FAKE_GH_MODE picks the canned replies:
  ok          the base's rules include non_fast_forward and deletion (ruleset 1),
              ruleset 1 can't be bypassed; POST .../pulls opens draft PR 7
  no-deletion the rules lack deletion
  bypass      ruleset 1 says current_user_can_bypass "always"
  error       every call fails as an HTTP 404
  pr-error    as ok, but POST .../pulls fails (422)
"""

import json
import os
import sys

args = sys.argv[1:]
log = os.environ.get("FAKE_GH_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\n")
mode = os.environ.get("FAKE_GH_MODE", "ok")


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


if mode == "error":
    fail("gh: Not Found (HTTP 404)")
if args[:1] != ["api"]:
    fail("fake gh: only api calls")
path = [a for a in args[1:] if not a.startswith("-") and "=" not in a and a not in ("POST",)]
path = path[0] if path else ""
if "-X" in args:
    if path.endswith("/pulls") and mode != "pr-error":
        print(json.dumps({"number": 7, "draft": True, "html_url": "https://github.com/example/wiki/pull/7"}))
        sys.exit(0)
    fail("gh: Validation Failed (HTTP 422)")
if "/rules/branches/" in path:
    rules = [{"type": "non_fast_forward", "ruleset_source_type": "Repository", "ruleset_id": 1},
             {"type": "deletion", "ruleset_source_type": "Repository", "ruleset_id": 1}]
    if mode == "no-deletion":
        rules = rules[:1]
    print(json.dumps(rules))
elif "/rulesets/" in path:
    print(json.dumps({"id": 1, "name": "protect-default-branch",
                      "current_user_can_bypass": "always" if mode == "bypass" else "never"}))
else:
    fail("gh: Not Found (HTTP 404)")
