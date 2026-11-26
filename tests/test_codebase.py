"""codebase/git.sh's read operations and its refusals, end to end through bash
(formerly the codebase section of run-tests.sh). The fetch and status steps
and gh.sh are in test_codebase_fetch.py, the grep patterns in
test_codebase_grep.py.

The steps run in order on one repository and wiki (`codebase_story.Ctx`):
later steps depend on the history and the cache the earlier ones leave.
Each check is its own test, named by the literal first argument of
has/chk/eq."""

import shutil

import pytest

import sourcelib
from codebase_story import CBR, build, names, rev
from conftest import call_main, git, posix, story_assert, write

NAMES = names(__file__)


@pytest.fixture(scope="module")
def story(tmp_path_factory, run):
    c = build(tmp_path_factory, run, "cbt")
    has, chk, eq, out, cbn, cbx = c.has, c.chk, c.eq, c.out, c.cbn, c.cbx
    clone, cbw, inst, cache, C, CB = c.clone, c.cbw, c.inst, c.cache, c.C, c.CB
    c1, c3, c4, t = c.c1, c.c3, c.c4, c.t

    s1 = c1[:12]
    o = out("code", "status")
    has("codebase/status-checkout", o, "checkout: local-work @")
    has("codebase/status-dirty", o, "1 uncommitted changes in the root")
    has("codebase/status-ref", o, "ref: origin/main @")
    has("codebase/status-shallow", o, "shallow: no")
    has("codebase/resolve", out("code", "resolve", s1), "%s %s" % (s1, c1))
    has("codebase/resolve-ref", out("code", "resolve", "ref"), "ref " + rev(clone, "origin/main"))
    has("codebase/grep", out("code", "grep", c1, "fo+"), "app/src/A.java#L2: foo")
    has("codebase/igrep", out("code", "igrep", "ref", "foo"), "app/src/A.java#L3: FOO")
    has("codebase/grep-none", out("code", "grep", "ref", "nomatch"), "no matches")
    has("codebase/grep-pathspec", out("code", "grep", "ref", "b", "lib/*.java"), "lib/B2.java#L1: b1")
    has("codebase/grep-dash-regex", out("code", "grep", "ref", "-x"), "no matches")
    o = out("code", "show", c1, "app/src/A.java", "L2-L3")
    has("codebase/show-header", o, "app/src/A.java#L2-L3 @%s (6 lines in the file)" % s1)
    has("codebase/show-lines", o, "     3  l3")
    has("codebase/show-more", o, "(more: show %s app/src/A.java L4-L6)" % c1)
    eq("codebase/show-folder", "1", cbx("code", "show", "ref", "app"))
    has("codebase/ls", out("code", "ls", "ref", "lib"), "f 6 lib/B2.java")
    o, rc_file = cbn("code", "log", "ref", "app/src/A.java")
    has("codebase/log", o, "three: change foo")
    o, rc_range = cbn("code", "log", "ref", "app/src/A.java", "L3-L3")
    has("codebase/log-range", o, "three: change foo")
    eq("codebase/log-exit", "0 0 0", " ".join([cbx("code", "log", "ref"), str(rc_file), str(rc_range)]))
    has("codebase/blame", out("code", "blame", "ref", "app/src/A.java", "L3-L3"), "FOO")
    eq("codebase/branches", "main",
       " ".join(ln.split(" ")[0].replace("origin/", "", 1) for ln in out("code", "branches").splitlines()))
    eq("codebase/contains", "origin/main", out("code", "contains", c1).rstrip("\n"))
    git(clone, "commit", "-q", "-m", "seven: local only", "--allow-empty")
    has("codebase/contains-unpushed", out("code", "contains", "local-work"), "unpushed:")
    eq("codebase/verify", "ok: app/src/A.java#L2-L3 @%s" % s1,
       out("code", "verify", c1, "app/src/A.java", "L2-L3").rstrip("\n"))
    eq("codebase/verify-past-end", "1", cbx("code", "verify", c1, "app/src/A.java", "L5-L9"))
    eq("codebase/verify-missing", "1", cbx("code", "verify", c1, "app/src/Z.java", "L1-L1"))
    has("codebase/drift-elsewhere", out("code", "drift", c3, "app/src/A.java", "L1-L2"), "changed-elsewhere")
    has("codebase/drift-moved", out("code", "drift", c1, "app/src/A.java", "L4-L5"), "moved L5-L6")
    has("codebase/drift-overlap", out("code", "drift", c1, "app/src/A.java", "L2-L3"), "changed-overlap")
    has("codebase/drift-renamed", out("code", "drift", c3, "lib/B.java", "L1-L2"), "renamed lib/B2.java")
    has("codebase/drift-deleted", out("code", "drift", c4, "lib/C.java", "L1-L1"), "deleted")
    has("codebase/drift-same", out("code", "drift", "ref", "app/src/A.java", "L1-L2"), "unchanged")
    write(cbw / "wiki/page.md", "a (Codebase code: app/src/A.java#L2-L3 @%s) b app/src/A.java#L5-L9 @%s\n"
          "c lib/C.java#L1 @%s; again app/src/A.java#L2-L3 @%s\n" % (s1, s1, c4, s1))
    write(cache / "runs/r2/answer.md", "C1: app/src/A.java#L2-L3 @%s\r\n" % s1)
    o, rc = cbn("code", "verify-all", "wiki/page.md")
    o += "exit=%d\n" % rc
    chk("codebase/verify-all-quiet", "-> ok:" not in o, o)
    has("codebase/verify-all-ok", out("code", "verify-all", "wiki/page.md", "--all"),
        "app/src/A.java#L2-L3 @%s -> ok: app/src/A.java#L2-L3 @%s" % (s1, s1))
    chk("codebase/verify-all-nofetch", "compared with" not in o, o)
    eq("codebase/refuse-all-flag", "1", cbx("code", "verify-all", "wiki/page.md", "--quiet"))
    has("codebase/verify-all-broken", o, "app/src/A.java#L5-L9 @%s -> broken: app/src/A.java has 6 lines" % s1)
    has("codebase/verify-all-tally", o, "3 citations: 1 broken, 2 ok")
    has("codebase/verify-all-exit", o, "exit=1")
    o = out("code", "drift-all", "wiki/page.md")
    has("codebase/drift-all", o, "lib/C.java#L1 @%s -> deleted" % c4)
    has("codebase/drift-all-tally", o, "3 citations: 1 broken, 1 changed-overlap, 1 deleted")
    has("codebase/drift-all-fetch", o, "compared with origin/main as of the last fetch")
    has("codebase/drift-all-stamp", o, "last fetch: ")
    o, rc = cbn("code", "verify-all", "@runs/r2/answer.md")
    has("codebase/verify-all-cache", o + "exit=%d" % rc, "1 citations: 1 ok\nexit=0")
    eq("codebase/refuse-all-paths", "1 1 1 1", " ".join(cbx("code", "verify-all", p) for p in
                                                       ("../x.md", "@runs/../../x", "/etc/passwd", "wiki/none.md")))
    has("codebase/sub-ls", out("sub", "ls", "ref"), "d - app/src")
    eq("codebase/sub-outside", "1", cbx("sub", "show", "ref", "lib/B2.java"))
    eq("codebase/sub-sibling", "1", cbx("sub", "show", "ref", "apples/x"))
    has("codebase/sub-grep-scoped", out("sub", "grep", "ref", "b1"), "no matches")
    eq("codebase/refuse-unknown-op", "1", cbx("code", "checkout", "ref"))
    eq("codebase/refuse-write-ops", "1", cbx("code", "push"))
    eq("codebase/refuse-extra-args", "1", cbx("code", "show", "ref", "app/src/A.java", "L1-L2", "--output=x"))
    eq("codebase/refuse-few-args", "1", cbx("code", "show", "ref"))
    eq("codebase/refuse-dotdot", "1", cbx("code", "show", "ref", "app/../lib/B2.java"))
    eq("codebase/refuse-abs", "1", cbx("code", "show", "ref", "/etc/passwd"))
    eq("codebase/refuse-drive", "1", cbx("code", "show", "ref", "C:/x"))
    eq("codebase/refuse-option-path", "1", cbx("code", "show", "ref", "--output=x"))
    eq("codebase/refuse-magic-spec", "1", cbx("code", "grep", "ref", "x", ":(top)"))
    eq("codebase/refuse-option-rev", "1", cbx("code", "show", "--output=x", "app/src/A.java"))
    eq("codebase/refuse-range-rev", "1", cbx("code", "show", "ref..HEAD", "app/src/A.java"))
    eq("codebase/refuse-bad-range", "1 1", cbx("code", "show", "ref", "app/src/A.java", "L3-L1") + " "
       + cbx("code", "show", "ref", "app/src/A.java", "3x"))
    eq("codebase/refuse-unknown-rev", "1", cbx("code", "show", "deadbeef", "app/src/A.java"))
    eq("codebase/refuse-two-roots", "1", cbx("two", "status"))
    eq("codebase/refuse-wrong-type", "1", cbx("mail", "status"))
    eq("codebase/refuse-no-instance", "1", cbx("nosuch", "status"))
    r = run(["bash", CBR, "code", "status"], cwd=t, merged=True)
    eq("codebase/refuse-outside-git", 1, r.rc)
    # One bridge call reads the instance (the fields git.sh asks for).
    def lines(key):
        r = call_main(sourcelib.main, ["instance-fields", posix(cbw), key, "type", "roots[]", "ref", "gh_user"])
        return r.out.decode().split("\n")[:-1]
    eq("codebase/instance-lines", "1|codebase|1|%s/app|origin/main|" % C, "|".join(lines("sub")))
    eq("codebase/instance-lines-other", "1|gmail|0|||", "|".join(lines("mail")))
    write(inst / "ph.md", "---\nkey: ph\ntype: codebase\nroots:\n  - %s\nref: TBD\n---\n" % C)
    eq("codebase/instance-lines-invalid", "0|codebase", "|".join(lines("ph")[:2]))
    has("codebase/refuse-invalid-instance", out("ph", "status"), "doesn't validate")
    (inst / "ph.md").unlink()
    has("codebase/refuse-newline-key", out("code\nx", "status"), "invalid instance key")
    # A root with backslashes, doubled slashes and a trailing one (src_expand).
    write(inst / "bs.md", "---\nkey: bs\ntype: codebase\nroots:\n  - %s\\\\clone//app\\\\\nref: origin/main\n---\n" % CB)
    has("codebase/root-expanded", out("bs", "status"), "root: %s/clone/app (folder app of" % CB)
    (inst / "bs.md").unlink()
    shutil.copy(cbw / "wiki/page.md", cbw / "wiki/my page.md")
    has("codebase/verify-all-space", out("code", "verify-all", "wiki/my page.md"), "citations: ")
    (cbw / "wiki/my page.md").unlink()
    return c.st


@pytest.mark.parametrize("name", [pytest.param(n, id=n) for n in NAMES])
def test_codebase(name, story):
    story_assert(story, name)


@pytest.mark.checks("codebase/every-check-run")
def test_every_check_run(story):
    assert sorted(story.results) == NAMES
