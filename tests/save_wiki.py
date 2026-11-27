"""The shared setup of the save.sh tests (test_save*.py), split into
modules so they run on separate workers (xdist --dist loadfile, #115).

Each test gets a wiki whose remote is a local bare repository, reached
through the file:// test seam (WIKI_SAVE_TEST_FILE_URLS=1); a second clone
plays the other side (another session, the user). GitHub's checks run on a
github.com pin in-process, with save.transport patched to send its git
traffic to the bare repository, and a fake gh first on PATH that logs its
calls (tests/sources/save/fake_gh.py). Never the network.

Building a wiki takes about 14 git processes, slow on Windows (#115), so
each kind is built once per module (`built`) and copied for every test,
always to the same folder (`cur`): the committed pin and the other
clone's origin name that folder, so a copy needs no rewiring.
"""

import json
import os
import shutil
import stat
import subprocess
import sys

import pytest
import save

from conftest import IS_WIN, call_main, PLUGIN_BASH, TESTS, git, norm, posix, write

FAKE_GH = TESTS / "sources" / "save" / "fake_gh.py"
GH_URL = "https://github.com/example/wiki"


def out(*args, cwd):
    return subprocess.run(["git", "-C", str(cwd)] + list(args), stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, check=True).stdout.decode().strip()


def file_url(p):
    p = posix(p)
    return "file://" + ("" if p.startswith("/") else "/") + p


@pytest.fixture(scope="module")
def fakebin(tmp_path_factory):
    d = tmp_path_factory.mktemp("fakegh")
    if IS_WIN:
        write(d / "gh.cmd", '@"%s" "%s" %%*\r\n' % (sys.executable, FAKE_GH))
    else:
        write(d / "gh", '#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, FAKE_GH)).chmod(0o755)
    path = str(d) + os.pathsep + os.environ.get("PATH", "")
    found = shutil.which("gh", path=path)
    if not found or os.path.dirname(os.path.abspath(found)) != os.path.abspath(str(d)):
        pytest.exit("ABORT: the fake gh is not first on PATH; refusing to run save tests against a real gh.", 3)
    return path


class Wiki:
    """A wiki (w), its bare remote (bare) and another clone (other)."""

    def __init__(self, t, cli, fakebin, url=None, build=True):
        """build=False: t already holds a copy of a wiki built with this url."""
        self.t, self.cli = t, cli
        self.bare, self.w, self.other = t / "remote.git", t / "wiki", t / "other"
        self.log = t / "gh.log"
        self.url = url or file_url(self.bare)
        self.env = {"WIKI_SAVE_TEST_FILE_URLS": "1", "PATH": fakebin, "FAKE_GH_LOG": posix(self.log)}
        if build:
            self.build()

    def build(self):
        t = self.t
        # No template (sample hooks): fewer files to copy for each test.
        git(t, "init", "-q", "--template=", "--bare", "remote.git")
        git(t, "init", "-q", "--template=", "wiki")
        self.ident(self.w)
        write(self.w / "CLAUDE.md", "# Test wiki\n")
        write(self.w / "wiki/index.md", "# Index\n\nline\n")
        write(self.w / "wiki/log.md", "# Log\n")
        self.config(enabled=True, url=self.url, base="main")
        git(self.w, "add", "-A")
        git(self.w, "commit", "-qm", "init")
        git(self.w, "push", "-q", posix(self.bare), "HEAD:refs/heads/main")
        git(t, "clone", "-q", "--template=", posix(self.bare), "other")
        self.ident(self.other)

    @staticmethod
    def ident(d):
        for k, v in (("user.name", "t"), ("user.email", "t@example.com"), ("core.autocrlf", "false")):
            git(d, "config", k, v)

    def config(self, commit=False, top=None, **cfg):
        """The settings file with cfg as its `save` section, beside the
        other top-level keys in top; with top alone, no `save` key."""
        data = dict(top or {})
        if cfg:
            data["save"] = cfg
        write(self.w / save.CONFIG, json.dumps(data) + "\n")
        if commit:
            git(self.w, "add", "-A")
            git(self.w, "commit", "-q", "--allow-empty", "-m", "config")

    def commit(self, msg, *paths, d=None, content=None):
        d = d or self.w
        for p in paths:
            if content is not None:
                write(d / p, content)
            elif not (d / p).exists():
                write(d / p, msg + "\n")
            else:
                write(d / p, (d / p).read_text() + msg + "\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", msg)

    def other_push(self, msg, *paths, content=None):
        git(self.other, "pull", "-q", "--no-rebase", "origin", "main")
        self.commit(msg, *paths, d=self.other, content=content)
        git(self.other, "push", "-q", "origin", "HEAD:main")

    def save(self, *args, env=None):
        return self.cli("save", *args, cwd=self.w, env=dict(self.env, **(env or {})))

    def remote(self, ref="main"):
        return out("rev-parse", "refs/heads/" + ref, cwd=self.bare)

    def head(self):
        return out("rev-parse", "HEAD", cwd=self.w)

    def short(self, ref="HEAD"):
        return out("rev-parse", "--short", ref, cwd=self.w)

    def gh_log(self):
        return [json.loads(ln) for ln in self.log.read_text().splitlines()] if self.log.exists() else []

    def gh_calls(self):
        return [c["args"] for c in self.gh_log()]


def _rmtree(p):
    """rmtree that also removes read-only files (git's objects on Windows)."""
    def unlock(fn, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        fn(path)
    if sys.version_info >= (3, 12):
        shutil.rmtree(str(p), onexc=unlock)
    else:
        shutil.rmtree(str(p), onerror=unlock)


@pytest.fixture(scope="module")
def built(tmp_path_factory, cli, fakebin):
    """fresh(url) -> the folder `cur`, holding a new copy of the wiki pinned
    to url (None: its bare remote). Each kind is built once, in `cur`, then
    moved aside as the template."""
    base = tmp_path_factory.mktemp("save")
    cur, done = base / "cur", {}

    def fresh(url):
        if cur.exists():
            _rmtree(cur)
        if url not in done:
            cur.mkdir()
            Wiki(cur, cli, fakebin, url=url)
            done[url] = base / ("template%d" % len(done))
            os.rename(str(cur), str(done[url]))
        shutil.copytree(str(done[url]), str(cur), symlinks=True)
        return cur
    return fresh


@pytest.fixture
def wk(built, cli, fakebin):
    return Wiki(built(None), cli, fakebin, build=False)


class GhWiki(Wiki):
    """A wiki pinned to github.com: save.py runs in-process (also with
    --e2e), its git traffic sent to the bare repository by patching
    save.transport; gh is the fake."""

    def __init__(self, t, cli, fakebin, monkeypatch, build=True):
        super().__init__(t, cli, fakebin, url=GH_URL, build=build)
        bare = file_url(self.bare)
        monkeypatch.setattr(save, "transport", lambda u: bare if u == GH_URL else u)

    def save(self, *args, env=None):
        return call_main(save.main, ["--plugin", PLUGIN_BASH] + list(args), cwd=self.w,
                         env=dict(self.env, **(env or {})))


@pytest.fixture
def ghw(built, cli, fakebin, monkeypatch):
    return GhWiki(built(GH_URL), cli, fakebin, monkeypatch, build=False)


def so(r):
    return norm(r.out)


def se(r):
    return norm(r.err)


def refused(r, reason):
    assert r.rc == 1, r
    first = se(r).split("\n")[0]
    assert first.startswith("save: refused: " + reason), se(r)
    assert so(r) == "", r


CALL = "bash @PLUGIN@/scripts/save.sh"


def call_in(wk, fn, *args):
    here = os.getcwd()
    os.chdir(wk.w)
    try:
        return fn(*args)
    finally:
        os.chdir(here)
