"""codebase/git.sh and gh.sh against a throwaway repo with a bare "remote"
and a fake gh, end to end through bash (formerly the codebase section of
run-tests.sh). Every gh.sh call runs with the fake first on PATH; the run
aborts if the fake isn't the gh that PATH finds.

The checks replay the old section's steps in order on one repository and
wiki (`Story`): later steps depend on the history and the cache the
earlier ones leave. The check names are read from this file's literal
first arguments of has/chk/eq, so each old check stays its own test."""

import os
import re
import shutil
import time
from pathlib import Path

import pytest

import sourcelib
from conftest import (PLUGIN, TESTS, Story, call_main, git, posix, spellings, story_assert, write)

CBR = posix(PLUGIN / "sources/codebase/git.sh")
CBH = posix(PLUGIN / "sources/codebase/gh.sh")
NAMES = sorted(set(re.findall(r'(?:has|chk|eq)\(\s*"((?:codebase|gh)/[^"]+)"', Path(__file__).read_text())))


def _rev(d, ref="HEAD"):
    import subprocess
    return subprocess.run(["git", "-C", str(d), "rev-parse", ref], stdout=subprocess.PIPE).stdout.decode().strip()


@pytest.fixture(scope="module")
def story(tmp_path_factory, run):
    t = tmp_path_factory.mktemp("cbt")
    st = Story()
    fakebin = t / "bin"
    shutil.copy(TESTS / "sources/codebase/fake-gh", fakebin.mkdir() or fakebin / "gh")
    (fakebin / "gh").chmod(0o755)
    path = str(fakebin) + os.pathsep + os.environ.get("PATH", "")
    r = run(["bash", "-c", "command -v gh"], env={"PATH": path})
    if r.out.decode().strip() not in spellings(fakebin / "gh"):
        pytest.exit("ABORT: the fake gh is not first on PATH; refusing to run codebase tests against a real gh.", 3)

    cb = t / "cb"
    cb.mkdir()
    git(cb, "init", "-q", "--bare", "remote.git")
    git(cb, "init", "-q", "clone")
    clone, remote = cb / "clone", cb / "remote.git"
    write(clone / "app/src/A.java", "l1\nfoo\nl3\nl4\nl5\nl6\n")
    write(clone / "lib/B.java", "b1\nb2\n")
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", "one")
    git(clone, "remote", "add", "origin", posix(remote))
    git(clone, "push", "-q", "origin", "HEAD:main")
    git(clone, "fetch", "-q", "origin")
    git(clone, "remote", "set-head", "origin", "main")
    c1 = _rev(clone)
    write(clone / "app/src/A.java", "l0\nl1\nfoo\nl3\nl4\nl5\nl6\n")
    git(clone, "commit", "-qam", "two: insert at top")
    write(clone / "app/src/A.java", "l0\nl1\nFOO\nl3\nl4\nl5\nl6\n")
    git(clone, "commit", "-qam", "three: change foo")
    c3 = _rev(clone)
    write(clone / "lib/C.java", "c1\n")
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", "four: add C")
    c4 = _rev(clone)
    git(clone, "mv", "lib/B.java", "lib/B2.java")
    git(clone, "rm", "-q", "lib/C.java")
    git(clone, "commit", "-qm", "five: rename B, delete C")
    write(clone / "app/src/A.java", "l0\nl1\nFOO\nl3\nl4\nl5\nL6\n")
    git(clone, "commit", "-qam", "six: change last line")
    git(clone, "push", "-q", "origin", "HEAD:main")
    git(clone, "fetch", "-q", "origin")
    git(clone, "checkout", "-q", "-b", "local-work")
    write(clone / "lib/local.txt", "local\n")  # uncommitted, unpushed branch
    git(cb, "clone", "-q", posix(remote), "ghclone")
    git(cb / "ghclone", "remote", "set-url", "origin", "https://github.com/acme/widgets.git")
    git(cb, "init", "-q", "cbw")
    cbw = cb / "cbw"
    inst = cbw / ".claude/sources/instances"
    C, CB = posix(clone), posix(cb)
    write(inst / "code.md", "---\nkey: code\ntype: codebase\nroots:\n  - %s\n---\n" % C)
    write(inst / "sub.md", "---\nkey: sub\ntype: codebase\nroots:\n  - %s/app\nref: origin/main\n---\n" % C)
    write(inst / "hub.md", "---\nkey: hub\ntype: codebase\nroots:\n  - %s/ghclone\ngh_user: reader\n---\n" % CB)
    write(inst / "two.md", "---\nkey: two\ntype: codebase\nroots:\n  - %s\n  - %s/ghclone\n---\n" % (C, CB))
    write(inst / "mail.md", "---\nkey: mail\ntype: gmail\nlabels: X\n---\n")
    # HOME is a test folder: the instance cache (pattern files, last-fetch)
    # and a .gitconfig that sends the https GitHub remote of "hub" to the
    # local bare repo.
    cbhome = cb / "home"
    cache = cbhome / ".cache/wiki-sources/cbw/code"
    cache.mkdir(parents=True)
    git(cb, "config", "-f", posix(cbhome / ".gitconfig"), "url.%s.insteadOf" % posix(remote),
        "https://github.com/acme/widgets.git")
    env = {"HOME": posix(cbhome), "PATH": path}

    def cbn(*args, extra=None):
        r = run(["bash", CBR] + list(args), cwd=cbw, env=dict(env, **(extra or {})), merged=True)
        return r.merged.decode("utf-8", "surrogateescape"), r.rc

    def out(*args):
        return cbn(*args)[0]

    def cbx(*args):
        return str(cbn(*args)[1])

    def ghn(*args, extra=None):
        r = run(["bash", CBH] + list(args), cwd=cbw, env=dict({"PATH": path}, **(extra or {})), merged=True)
        return r.merged.decode("utf-8", "surrogateescape"), r.rc

    def ghx(*args):
        return str(ghn(*args)[1])

    def has(name, text, sub):
        st.check(name, sub in text, "%r missing in:\n%s" % (sub, text))

    def chk(name, ok, detail=""):
        st.check(name, ok, detail)

    def eq(name, want, got):
        st.eq(name, want, got)

    s1 = c1[:12]
    o = out("code", "status")
    has("codebase/status-checkout", o, "checkout: local-work @")
    has("codebase/status-dirty", o, "1 uncommitted changes in the root")
    has("codebase/status-ref", o, "ref: origin/main @")
    has("codebase/status-shallow", o, "shallow: no")
    has("codebase/resolve", out("code", "resolve", s1), "%s %s" % (s1, c1))
    has("codebase/resolve-ref", out("code", "resolve", "ref"), "ref " + _rev(clone, "origin/main"))
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
    has("codebase/log", out("code", "log", "ref", "app/src/A.java"), "three: change foo")
    has("codebase/log-range", out("code", "log", "ref", "app/src/A.java", "L3-L3"), "three: change foo")
    eq("codebase/log-exit", "0 0 0", " ".join([cbx("code", "log", "ref"), cbx("code", "log", "ref", "app/src/A.java"),
                                               cbx("code", "log", "ref", "app/src/A.java", "L3-L3")]))
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
    eq("codebase/refuse-write-ops", "1 1 1 1", " ".join([cbx("code", "reset", "ref"), cbx("code", "worktree", "ref"),
                                                         cbx("code", "clone", "ref"), cbx("code", "push")]))
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
    # One bridge call reads the instance.
    def lines(key):
        r = call_main(sourcelib.main, ["codebase-instance", posix(cbw), key])
        return r.out.decode().split("\n")[:-1]
    eq("codebase/instance-lines", "codebase|1|1|%s/app|origin/main|" % C, "|".join(lines("sub")))
    eq("codebase/instance-lines-other", "gmail|1|0|||", "|".join(lines("mail")))
    write(inst / "ph.md", "---\nkey: ph\ntype: codebase\nroots:\n  - %s\nref: TBD\n---\n" % C)
    eq("codebase/instance-lines-invalid", "codebase|0", "|".join(lines("ph")[:2]))
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
    has("codebase/status-never-fetched", out("code", "status"), "last fetch: none by git.sh")
    has("codebase/status-outside-fetch", out("code", "status"), "outside git.sh (e.g. by the user)")
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
    has("codebase/fetch-refused-running", out("code", "fetch"), "a fetch is already running (started 2026-11-12 10:00")
    eq("codebase/fetch-refused-exit", "1", cbx("code", "fetch"))
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
    write(cache / "p.txt", "FO+|zzz\r\n^L6$\n")
    o = out("code", "grep", "ref", "@p.txt")
    has("codebase/grep-patfile", o, "app/src/A.java#L3: FOO")
    has("codebase/grep-patfile-or", o, "app/src/A.java#L7: L6")
    has("codebase/grep-patfile-head", o, "2 patterns from p.txt: FO+|zzz|^L6$")
    write(cache / "runs/r1/q.txt", "b1\n")
    has("codebase/grep-patfile-sub", out("code", "grep", "ref", "@runs/r1/q.txt", "lib/*"), "lib/B2.java#L1: b1")
    write(cache / "many.txt", "".join("p%d\n" % i for i in range(21)))
    write(cache / "empty.txt", "")
    eq("codebase/refuse-patfile", "1 1 1 1 1 1", " ".join(cbx("code", "grep", "ref", p) for p in
                                                          ("@../x", "@runs/../p.txt", "@/etc/passwd", "@nosuch.txt",
                                                           "@many.txt", "@empty.txt")))
    eq("codebase/refuse-patfile-other-key", "1", cbx("sub", "grep", "ref", "@p.txt"))
    # -e patterns, or-ed, and a leading @ as a regex.
    o = out("code", "grep", "ref", "-e", "FO+", "-e", "^L6")
    chk("codebase/grep-multi-e", all(s in o for s in ("app/src/A.java#L3: FOO", "app/src/A.java#L7: L6",
                                                      " grep FO+|^L6 in ")), o)
    has("codebase/grep-multi-e-spec", out("code", "grep", "ref", "-e", "b1", "-e", "zzz", "lib/*"), "lib/B2.java#L1: b1")
    has("codebase/igrep-multi-e", out("code", "igrep", "ref", "-e", "zzz", "-e", "foo"), "app/src/A.java#L3: FOO")
    o, rc = cbn("code", "grep", "ref", "-e", "@x")
    chk("codebase/grep-e-at", " grep @x in " in o and rc == 0, o)
    o, rc = cbn("code", "grep", "ref", "-e", "--output=x")
    chk("codebase/grep-e-dash", " grep --output=x in " in o and rc == 0, o)
    has("codebase/patfile-missing-hint", out("code", "grep", "ref", "@McpToolKit"), "for a regex starting with @, use -e")
    many = [w for i in range(20) for w in ("-e", "p%d" % i)]
    eq("codebase/grep-20-e", "0", cbx("code", "grep", "ref", *many))
    many += ["-e", "p20"]
    has("codebase/refuse-21-e-msg", out("code", "grep", "ref", *many), "at most 20 -e patterns.")
    eq("codebase/refuse-e-outside", "1 1", cbx("code", "grep", "ref", "-e", "a", "../x") + " "
       + cbx("sub", "grep", "ref", "-e", "a", "lib/*"))
    eq("codebase/refuse-e-mixed", "1", cbx("code", "grep", "ref", "foo", "-e", "bar"))
    eq("codebase/refuse-multi-e", "1 1 1 1 1", " ".join([
        cbx("code", "grep", "ref", "-e"), cbx("code", "grep", "ref", "-e", "a", "-e"),
        cbx("code", "grep", "ref", "-e", ""), cbx("code", "grep", "ref", "-e", "a", "x", "-e", "b"),
        cbx("code", "grep", "ref", *many)]))
    # Several pathspecs, -i pointed at igrep, the cache folder shown as ~.
    o = out("code", "grep", "ref", "-e", "b1", "-e", "FOO", "lib/*", "app/*")
    chk("codebase/grep-multi-spec", all(s in o for s in ("lib/B2.java#L1: b1", "app/src/A.java#L3: FOO",
                                                         " in lib/* app/*")), o)
    has("codebase/grep-multi-spec-pos", out("code", "grep", "ref", "b1", "app/*", "lib/*"), "lib/B2.java#L1: b1")
    elev = ["d%d" % i for i in range(11)]
    eq("codebase/refuse-grep-flags", "1 1 1 1 1", " ".join([
        cbx("code", "grep", "ref", "-i", "foo"), cbx("code", "grep", "ref", "-e", "foo", "-i"),
        cbx("code", "grep", "ref", "foo", "--ignore-case"), cbx("code", "grep", "ref", "foo", "-w"),
        cbx("code", "grep", "ref", "foo", *elev)]))
    has("codebase/refuse-i-hint", out("code", "grep", "ref", "-e", "foo", "-i"), "use igrep for a case-insensitive search")
    has("codebase/refuse-flag-hint", out("code", "grep", "ref", "foo", "-w"), "takes no flags but -e")
    o = out("code", "grep", "ref", "@nosuch.txt")
    chk("codebase/cache-shown-as-tilde", "'~/.cache/wiki-sources/cbw/code/nosuch.txt' not found" in o
        and not any(s in o for s in spellings(cbhome)), o)
    has("codebase/refuse-multi-e-msg", out("code", "grep", "ref", "-e", "a", "-e"), "-e needs a regex after it.")
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
    eq("gh/refuse-unknown-op", "1 1 1", " ".join([ghx("hub", "pr-merge", "12"), ghx("hub", "api", "x"),
                                                  ghx("hub", "auth", "x")]))
    eq("gh/refuse-bad-number", "1 1", ghx("hub", "pr", "12x") + " " + ghx("hub", "pr", "-R"))
    eq("gh/refuse-bad-sha", "1 1", ghx("hub", "pr-of", "xyz") + " " + ghx("hub", "pr-of", "deadbeefdead"))
    eq("gh/refuse-extra-args", "1", ghx("hub", "pr", "12", "--web"))
    write(hub, hub.read_text().replace("gh_user: reader", "gh_user: nobody"))
    eq("gh/refuse-no-token", "1", ghx("hub", "pr", "12"))
    write(hub, hub.read_text().replace("gh_user: nobody", "gh_user: reader"))
    o, rc = ghn("hub", "pr", "12", extra={"FAKE_GH_SYNTAX": "changed"})
    chk("gh/refuse-changed-syntax", "syntax changed" in o and rc == 1, o)
    return st


@pytest.mark.parametrize("name", [pytest.param(n, id=n) for n in NAMES])
def test_codebase(name, story):
    story_assert(story, name)


@pytest.mark.checks("codebase/every-check-run")
def test_every_check_run(story):
    assert sorted(story.results) == NAMES
