"""Stand-in for the gh CLI in tests/test_save.py, so tests never touch
GitHub. test_save.py puts a `gh` launcher for it first on PATH (a shell
script, or gh.cmd on Windows) that runs it with the test's Python.

Every call is appended to $FAKE_GH_LOG as one JSON line (the arguments).
A set GH_HOST fails the call (save.py must drop it). $FAKE_GH_MODE picks
the canned replies:
  ok                 the base's rules include non_fast_forward and deletion
                     (ruleset 1), ruleset 1 can't be bypassed; POST .../pulls
                     opens draft PR 7
  no-deletion        the rules lack deletion
  bypass             ruleset 1 says current_user_can_bypass "always"
  pull-requests-only ruleset 1 says "pull_requests_only"
  no-bypass-field    ruleset 1 has no current_user_can_bypass
  no-ruleset-id      the non_fast_forward rule has no ruleset_id
  many-rules         100 rules (a full page)
  error              every call fails as an HTTP 404
  pr-error           as ok, but POST .../pulls fails (422)
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


if os.environ.get("GH_HOST"):
    fail("fake gh: GH_HOST is set")
if mode == "error":
    fail("gh: Not Found (HTTP 404)")
if args[:1] != ["api"]:
    fail("fake gh: only api calls")
path = next((a for a in args if a.startswith("repos/")), "")
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
    if mode == "no-ruleset-id":
        del rules[0]["ruleset_id"]
    if mode == "many-rules":
        rules += [{"type": "creation", "ruleset_id": 2}] * 98
    print(json.dumps(rules))
elif "/rulesets/" in path:
    rs = {"id": 1, "name": "protect-default-branch", "current_user_can_bypass": "never"}
    if mode == "bypass":
        rs["current_user_can_bypass"] = "always"
    if mode == "pull-requests-only":
        rs["current_user_can_bypass"] = "pull_requests_only"
    if mode == "no-bypass-field":
        del rs["current_user_can_bypass"]
    print(json.dumps(rs))
else:
    fail("gh: Not Found (HTTP 404)")
