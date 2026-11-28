"""codebase/git.sh's fetch and status, and gh.sh against a fake gh, end to end
through bash. Every gh.sh call runs with the fake first on PATH.

The steps run in order on one repository and wiki (`codebase_story.Ctx`):
later steps depend on the history and the cache the earlier ones leave.
Each check is its own test, named by the literal first argument of
has/chk/eq."""

import os
import time

import pytest

from codebase_story import build, names
from conftest import story_assert, write

NAMES = names(__file__)


@pytest.fixture(scope="module")
def story(tmp_path_factory, run):
    c = build(tmp_path_factory, run, "cbf")
    has, chk, eq, out, cbn, cbx = c.has, c.chk, c.eq, c.out, c.cbn, c.cbx
    ghn, ghx = c.ghn, c.ghx
    clone, cb, remote, inst, cache, c1 = c.clone, c.cb, c.remote, c.inst, c.cache, c.c1

    o = out("code", "status")
    has("codebase/status-never-fetched", o, "last fetch: none by git.sh")
    has("codebase/status-outside-fetch", o, "outside git.sh (e.g. by the user)")
    has("codebase/fetch", out("code", "fetch"), "fetched origin (using the user's git credentials, started ")
    has("codebase/fetch-stamp", (cache / "last-fetch").read_text(), ", origin/main @")
    chk("codebase/fetch-marker-gone", not (cache / "fetch-running").exists())
    o = out("code", "status")
    has("codebase/status-fetched", o, "last fetch: completed ")
    chk("codebase/status-fetched-quiet", o.count("fetch:") < 2 and "outside git.sh" not in o, o)
    later = time.time() + 3600
    os.utime(clone / ".git/FETCH_HEAD", (later, later))
    has("codebase/status-outside-later", out("code", "status"), "outside git.sh (e.g. by the user)")
    # A fetch by git.sh is running: its marker names a live process (a
    # bash pid, which is what git.sh tests with kill -0).
    spid = run(["bash", "-c", "sleep 120 >/dev/null 2>&1 & echo $!"]).out.decode().strip()
    cbm = cache / "fetch-running"
    write(cbm, "%s %d 2026-11-12 10:00\n" % (spid, int(time.time())))
    o = out("code", "status")
    has("codebase/status-fetch-running", o, "fetch: running since 2026-11-12 10:00 (pid %s)" % spid)
    chk("codebase/status-running-no-outside", "outside git.sh" not in o, o)
    o, rc = cbn("code", "fetch")
    has("codebase/fetch-refused-running", o, "a fetch is already running (started 2026-11-12 10:00")
    eq("codebase/fetch-refused-exit", 1, rc)
    chk("codebase/fetch-refused-keeps-marker", cbm.is_file())
    # Stale: the same live process, but the marker is over FETCH_MAX_AGE old
    # (a reused PID); then a process that is gone; then a garbled marker.
    write(cbm, "%s %d 2026-11-12 07:00\n" % (spid, int(time.time()) - 10800))
    has("codebase/status-fetch-stale-age", out("code", "status"),
        "fetch: one started 2026-11-12 07:00 did not complete (its process is gone, or it is over 2 hours old); "
        "safe to fetch again")
    run(["bash", "-c", 'kill "$1"; while kill -0 "$1" 2>/dev/null; do sleep 0.1; done', "_", spid])
    write(cbm, "%s %d 2026-11-12 10:00\n" % (spid, int(time.time())))
    has("codebase/status-fetch-stale-dead", out("code", "status"), "fetch: one started 2026-11-12 10:00 did not complete")
    has("codebase/fetch-after-stale", out("code", "fetch"), "fetched origin")
    chk("codebase/fetch-after-stale-gone", not cbm.exists())
    write(cbm, "garbled\n")
    has("codebase/status-fetch-stale-garbled", out("code", "status"), "fetch: one started ? did not complete")
    cbm.unlink()
    # A failed fetch is recorded until the next one completes.
    remote.rename(cb / "remote.gone")
    eq("codebase/fetch-fails", "1", cbx("code", "fetch"))
    chk("codebase/fetch-fails-marker-gone", not cbm.exists())
    has("codebase/status-fetch-failed", out("code", "status"), "fetch: the last attempt failed: ")
    (cb / "remote.gone").rename(remote)
    out("code", "fetch")
    chk("codebase/status-fetch-failed-cleared", "last attempt failed" not in out("code", "status"))
    has("codebase/fetch-gh-user", out("hub", "fetch"), "using gh account reader")
    hub = inst / "hub.md"
    write(hub, hub.read_text().replace("gh_user: reader", "gh_user: nobody"))
    has("codebase/fetch-no-token", out("hub", "fetch"), "using the user's git credentials")
    write(hub, hub.read_text().replace("gh_user: nobody", "gh_user: reader"))
    has("gh/pr-of", ghn("hub", "pr-of", c1[:7])[0], "FAKE gh api -X GET repos/acme/widgets/commits/%s/pulls --jq" % c1)
    has("gh/pr-of-token", ghn("hub", "pr-of", c1)[0], "token=tok-reader")
    has("gh/pr", ghn("hub", "pr", "12")[0], "FAKE gh pr view 12 -R acme/widgets --json")
    has("gh/pr-diff", ghn("hub", "pr-diff", "12")[0], "FAKE gh pr diff 12 -R acme/widgets --color never")
    has("gh/pr-search", ghn("hub", "pr-search", "payment routing")[0],
        "FAKE gh pr list -R acme/widgets --state all --search payment routing --limit 30")
    has("gh/issue", ghn("hub", "issue", "7")[0], "FAKE gh issue view 7 -R acme/widgets")
    has("gh/issue-search", ghn("hub", "issue-search", "is:open bug")[0],
        "FAKE gh issue list -R acme/widgets --state all --search is:open bug")
    eq("gh/refuse-no-gh-user", "1", ghx("code", "pr", "12"))
    code = inst / "code.md"
    write(code, code.read_text().replace("key: code\n", "key: code\ngh_user: reader\n", 1))
    eq("gh/refuse-not-github", "1", ghx("code", "pr", "12"))
    eq("gh/refuse-unknown-op", "1", ghx("hub", "pr-merge", "12"))
    eq("gh/refuse-bad-number", "1 1", ghx("hub", "pr", "12x") + " " + ghx("hub", "pr", "-R"))
    eq("gh/refuse-bad-sha", "1 1", ghx("hub", "pr-of", "xyz") + " " + ghx("hub", "pr-of", "deadbeefdead"))
    eq("gh/refuse-extra-args", "1", ghx("hub", "pr", "12", "--web"))
    write(hub, hub.read_text().replace("gh_user: reader", "gh_user: nobody"))
    eq("gh/refuse-no-token", "1", ghx("hub", "pr", "12"))
    write(hub, hub.read_text().replace("gh_user: nobody", "gh_user: reader"))
    o, rc = ghn("hub", "pr", "12", extra={"FAKE_GH_SYNTAX": "changed"})
    chk("gh/refuse-changed-syntax", "syntax changed" in o and rc == 1, o)
    return c.st


@pytest.mark.parametrize("name", [pytest.param(n, id=n) for n in NAMES])
def test_codebase(name, story):
    story_assert(story, name)


@pytest.mark.checks("codebase/fetch-every-check-run")
def test_every_check_run(story):
    assert sorted(story.results) == NAMES
