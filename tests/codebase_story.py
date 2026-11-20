"""The shared setup of the codebase tests (test_codebase*.py): a throwaway
repo with a bare "remote", a fake gh first on PATH, and a wiki with
codebase instances. Each test module builds its own copy (`build`) and
replays its own steps on it, so the modules run in parallel (xdist
--dist loadfile). The run aborts if the fake isn't the gh that PATH finds.

A module's check names are read from its own text: the literal first
arguments of has/chk/eq (`names`)."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import PLUGIN, TESTS, Story, git, posix, spellings, write

CBR = posix(PLUGIN / "sources/codebase/git.sh")
CBH = posix(PLUGIN / "sources/codebase/gh.sh")


def names(module_file):
    return sorted(set(re.findall(r'(?:has|chk|eq)\(\s*"((?:codebase|gh)/[^"]+)"', Path(module_file).read_text())))


def rev(d, ref="HEAD"):
    return subprocess.run(["git", "-C", str(d), "rev-parse", ref], stdout=subprocess.PIPE).stdout.decode().strip()


class Ctx:
    """The repo, the wiki and the calls a module's steps use."""

    def __init__(self, t, run):
        self.t, self.run, self.st = t, run, Story()
        fakebin = t / "bin"
        shutil.copy(TESTS / "sources/codebase/fake-gh", fakebin.mkdir() or fakebin / "gh")
        (fakebin / "gh").chmod(0o755)
        self.path = path = str(fakebin) + os.pathsep + os.environ.get("PATH", "")
        r = run(["bash", "-c", "command -v gh"], env={"PATH": path})
        if r.out.decode().strip() not in spellings(fakebin / "gh"):
            pytest.exit("ABORT: the fake gh is not first on PATH; refusing to run codebase tests against a real gh.", 3)

        self.cb = cb = t / "cb"
        cb.mkdir()
        git(cb, "init", "-q", "--bare", "remote.git")
        git(cb, "init", "-q", "clone")
        self.clone, self.remote = clone, remote = cb / "clone", cb / "remote.git"
        write(clone / "app/src/A.java", "l1\nfoo\nl3\nl4\nl5\nl6\n")
        write(clone / "lib/B.java", "b1\nb2\n")
        git(clone, "add", "-A")
        git(clone, "commit", "-qm", "one")
        git(clone, "remote", "add", "origin", posix(remote))
        git(clone, "push", "-q", "origin", "HEAD:main")
        git(clone, "fetch", "-q", "origin")
        git(clone, "remote", "set-head", "origin", "main")
        self.c1 = rev(clone)
        write(clone / "app/src/A.java", "l0\nl1\nfoo\nl3\nl4\nl5\nl6\n")
        git(clone, "commit", "-qam", "two: insert at top")
        write(clone / "app/src/A.java", "l0\nl1\nFOO\nl3\nl4\nl5\nl6\n")
        git(clone, "commit", "-qam", "three: change foo")
        self.c3 = rev(clone)
        write(clone / "lib/C.java", "c1\n")
        git(clone, "add", "-A")
        git(clone, "commit", "-qm", "four: add C")
        self.c4 = rev(clone)
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
        self.cbw = cbw = cb / "cbw"
        self.inst = inst = cbw / ".claude/sources/instances"
        self.C, self.CB = C, CB = posix(clone), posix(cb)
        write(inst / "code.md", "---\nkey: code\ntype: codebase\nroots:\n  - %s\n---\n" % C)
        write(inst / "sub.md", "---\nkey: sub\ntype: codebase\nroots:\n  - %s/app\nref: origin/main\n---\n" % C)
        write(inst / "hub.md", "---\nkey: hub\ntype: codebase\nroots:\n  - %s/ghclone\ngh_user: reader\n---\n" % CB)
        write(inst / "two.md", "---\nkey: two\ntype: codebase\nroots:\n  - %s\n  - %s/ghclone\n---\n" % (C, CB))
        write(inst / "mail.md", "---\nkey: mail\ntype: gmail\nlabels: X\n---\n")
        # HOME is a test folder: the instance cache (pattern files, last-fetch)
        # and a .gitconfig that sends the https GitHub remote of "hub" to the
        # local bare repo.
        self.cbhome = cbhome = cb / "home"
        self.cache = cbhome / ".cache/wiki-sources/cbw/code"
        self.cache.mkdir(parents=True)
        git(cb, "config", "-f", posix(cbhome / ".gitconfig"), "url.%s.insteadOf" % posix(remote),
            "https://github.com/acme/widgets.git")
        self.env = {"HOME": posix(cbhome), "PATH": path}

    def cbn(self, *args, extra=None):
        """git.sh: (merged output, exit code)."""
        r = self.run(["bash", CBR] + list(args), cwd=self.cbw, env=dict(self.env, **(extra or {})), merged=True)
        return r.merged.decode("utf-8", "surrogateescape"), r.rc

    def out(self, *args):
        return self.cbn(*args)[0]

    def cbx(self, *args):
        return str(self.cbn(*args)[1])

    def ghn(self, *args, extra=None):
        """gh.sh: (merged output, exit code)."""
        r = self.run(["bash", CBH] + list(args), cwd=self.cbw, env=dict({"PATH": self.path}, **(extra or {})),
                     merged=True)
        return r.merged.decode("utf-8", "surrogateescape"), r.rc

    def ghx(self, *args):
        return str(self.ghn(*args)[1])

    def has(self, name, text, sub):
        self.st.check(name, sub in text, "%r missing in:\n%s" % (sub, text))

    def chk(self, name, ok, detail=""):
        self.st.check(name, ok, detail)

    def eq(self, name, want, got):
        self.st.eq(name, want, got)


def build(tmp_path_factory, run, name):
    return Ctx(tmp_path_factory.mktemp(name), run)
