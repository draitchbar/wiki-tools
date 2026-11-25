"""save.sh (save.py): saving a wiki's commits to its pinned remote.

Each test builds a wiki whose remote is a local bare repository, reached
through the file:// test seam (WIKI_SAVE_TEST_FILE_URLS=1); a second clone
plays the other side (another session, the user). GitHub's checks run on a
github.com pin in-process, with save.transport patched to send its git
traffic to the bare repository, and a fake gh first on PATH that logs its
calls (tests/sources/save/fake_gh.py). Never the network.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys

import guard
import hookjson
import pytest
import save

from conftest import IS_WIN, call_main, PLUGIN, PLUGIN_BASH, SCRIPTS_P, TESTS, git, norm, posix, write

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

    def __init__(self, t, cli, fakebin, url=None):
        self.t, self.cli = t, cli
        self.bare, self.w, self.other = t / "remote.git", t / "wiki", t / "other"
        self.log = t / "gh.log"
        git(t, "init", "-q", "--bare", "remote.git")
        git(t, "init", "-q", "wiki")
        self.ident(self.w)
        self.url = url or file_url(self.bare)
        write(self.w / "CLAUDE.md", "# Test wiki\n")
        write(self.w / "wiki/index.md", "# Index\n\nline\n")
        write(self.w / "wiki/log.md", "# Log\n")
        self.config(enabled=True, url=self.url, base="main")
        git(self.w, "add", "-A")
        git(self.w, "commit", "-qm", "init")
        git(self.w, "push", "-q", posix(self.bare), "HEAD:refs/heads/main")
        git(t, "clone", "-q", posix(self.bare), "other")
        self.ident(self.other)
        self.env = {"WIKI_SAVE_TEST_FILE_URLS": "1", "PATH": fakebin, "FAKE_GH_LOG": posix(self.log)}

    @staticmethod
    def ident(d):
        for k, v in (("user.name", "t"), ("user.email", "t@example.com"), ("core.autocrlf", "false")):
            git(d, "config", k, v)

    def config(self, commit=False, **cfg):
        write(self.w / save.CONFIG, json.dumps(cfg) + "\n")
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

    def gh_calls(self):
        return [json.loads(ln) for ln in self.log.read_text().splitlines()] if self.log.exists() else []


@pytest.fixture
def wk(tmp_path, cli, fakebin):
    return Wiki(tmp_path, cli, fakebin)


class GhWiki(Wiki):
    """A wiki pinned to github.com: save.py runs in-process (also with
    --e2e), its git traffic sent to the bare repository by patching
    save.transport; gh is the fake."""

    def __init__(self, t, cli, fakebin, monkeypatch):
        super().__init__(t, cli, fakebin, url=GH_URL)
        bare = file_url(self.bare)
        monkeypatch.setattr(save, "transport", lambda u: bare if u == GH_URL else u)

    def save(self, *args, env=None):
        return call_main(save.main, ["--plugin", PLUGIN_BASH] + list(args), cwd=self.w,
                         env=dict(self.env, **(env or {})))


@pytest.fixture
def ghw(tmp_path, cli, fakebin, monkeypatch):
    return GhWiki(tmp_path, cli, fakebin, monkeypatch)


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


# --- arguments ----------------------------------------------------------------

@pytest.mark.parametrize("args", [
    pytest.param(["--force"], id="save/refuse-unknown-flag"),
    pytest.param(["main"], id="save/refuse-word"),
    pytest.param(["--check", "--update"], id="save/refuse-two-forms"),
    pytest.param(["--unattended", "--update"], id="save/refuse-flag-order"),
    pytest.param(["--allow"], id="save/refuse-allow-without-path"),
    pytest.param(["--check", "--allow", "CLAUDE.md"], id="save/refuse-allow-not-first"),
    pytest.param(["--update", "--update"], id="save/refuse-repeated"),
    pytest.param(["--che"], id="save/refuse-abbreviation"),
    pytest.param(["--allow=CLAUDE.md"], id="save/refuse-allow-equals"),
    pytest.param(["--check=yes"], id="save/refuse-flag-value"),
    pytest.param(["-c"], id="save/refuse-short-flag"),
])
def test_unknown_arguments(args, wk):
    r = wk.save(*args)
    refused(r, "unknown arguments: ")
    assert "usage: save.sh [--check | --update | --unattended | --update --unattended | --allow <path>...]" in se(r)
    assert wk.remote() == out("rev-parse", "HEAD", cwd=wk.other)


# --- the config ---------------------------------------------------------------

@pytest.mark.checks("save/off-no-config")
def test_off_without_config(wk):
    git(wk.w, "rm", "-q", save.CONFIG)
    git(wk.w, "commit", "-qm", "off")
    refused(wk.save(), "saving is off for this wiki (no committed .claude/settings.wiki-save.json)")


@pytest.mark.checks("save/off-disabled")
def test_off_when_disabled(wk):
    wk.config(commit=True, enabled=False, url=wk.url, base="main")
    refused(wk.save(), "saving is off for this wiki (`enabled` isn't true")


@pytest.mark.checks("save/refuse-config-changed-in-work-tree")
def test_config_work_tree(wk):
    wk.config(enabled=True, url=file_url(wk.t / "elsewhere.git"), base="main")
    r = wk.save()
    refused(r, ".claude/settings.wiki-save.json differs from the committed one")
    (wk.w / save.CONFIG).unlink()
    refused(wk.save(), ".claude/settings.wiki-save.json differs from the committed one")


@pytest.mark.parametrize("cfg,env,why", [
    pytest.param({"url": "http://example.com/w.git"}, {}, "`url` must be", id="save/refuse-http-url"),
    pytest.param({}, {"WIKI_SAVE_TEST_FILE_URLS": None}, "`url` must be", id="save/refuse-file-url-without-seam"),
    pytest.param({"base": "a..b"}, {}, "`base` must be a branch name", id="save/refuse-bad-base"),
    pytest.param({"content_paths": ["../x/"]}, {}, "`content_paths`: \"../x/\"", id="save/refuse-dotdot-path"),
    pytest.param({"content_paths": ["/wiki/"]}, {}, "`content_paths`: \"/wiki/\" must be relative",
                 id="save/refuse-absolute-path"),
])
def test_config_invalid(cfg, env, why, wk):
    wk.config(commit=True, **dict({"enabled": True, "url": wk.url, "base": "main"}, **cfg))
    r = wk.save(env=env)
    refused(r, ".claude/settings.wiki-save.json is invalid: ")
    assert why in se(r)


@pytest.mark.checks("save/refuse-remote-pin-differs")
def test_remote_pin_differs(wk):
    """A pin changed only locally (or only remotely) is refused."""
    write(wk.other / save.CONFIG, json.dumps({"enabled": True, "url": file_url(wk.t / "moved.git"),
                                              "base": "main"}) + "\n")
    git(wk.other, "commit", "-qam", "move")
    git(wk.other, "push", "-q", "origin", "HEAD:main")
    r = wk.save()
    refused(r, "the wiki's remote pins %s, this commit %s" % (file_url(wk.t / "moved.git"), wk.url))
    refused(wk.save("--update"), "the wiki's remote pins")


# --- where the push goes --------------------------------------------------------

@pytest.mark.checks("save/refuse-insteadof")
def test_insteadof(wk):
    git(wk.w, "config", "url.%s.insteadOf" % file_url(wk.t / "evil.git"), wk.url)
    r = wk.save()
    refused(r, "git rewrites the wiki's URL %s to %s" % (wk.url, file_url(wk.t / "evil.git")))


@pytest.mark.parametrize("suffix", [pytest.param("", id="save/refuse-remote-config-for-url"),
                                    pytest.param("/", id="save/refuse-remote-config-for-url-variant")])
def test_remote_config_for_url(suffix, wk):
    """git takes the URL argument as a remote name first: a remote.<url>.*
    setting (pushurl) would send the push elsewhere."""
    git(wk.t, "init", "-q", "--bare", "evil.git")
    wk.commit("page", "wiki/page.md")
    git(wk.w, "config", "remote.%s.pushurl" % (wk.url + suffix), file_url(wk.t / "evil.git"))
    r = wk.save()
    refused(r, "git config has a remote named like the wiki's URL")
    assert wk.remote() != wk.head()
    assert out("for-each-ref", cwd=wk.t / "evil.git") == ""


@pytest.mark.checks("save/refuse-pushinsteadof")
def test_pushinsteadof(wk):
    git(wk.w, "config", "url.%s.pushInsteadOf" % file_url(wk.t / "evil.git"), "file://")
    refused(wk.save(), "git config has a url.*.pushInsteadOf setting")


@pytest.mark.checks("save/git-env-cleaned")
def test_git_env_cleaned(wk):
    """Inherited GIT_* variables don't steer the save: an insteadOf in
    GIT_CONFIG_* (as the cloud sets them), a GIT_DIR elsewhere."""
    wk.commit("page", "wiki/page.md")
    evil = file_url(wk.t / "evil.git")
    r = wk.save(env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "url.%s.insteadOf" % evil,
                     "GIT_CONFIG_VALUE_0": wk.url, "GIT_DIR": posix(wk.t / "nowhere")})
    assert r.rc == 0, r
    assert wk.remote() == wk.head()


@pytest.mark.checks("save/hooks-off")
def test_hooks_off(wk):
    """The wiki's own hooks don't run: core.hooksPath is the empty folder."""
    for d in (wk.w / ".git/hooks", wk.t / "myhooks"):
        write(d / "pre-push", "#!/bin/sh\necho hook ran >&2\nexit 1\n").chmod(0o755)
    git(wk.w, "config", "core.hooksPath", posix(wk.t / "myhooks"))
    wk.commit("page", "wiki/page.md")
    r = wk.save()
    assert r.rc == 0, r
    assert "hook ran" not in se(r)
    assert wk.remote() == wk.head()


@pytest.mark.checks("save/hooks-folder-only-readme")
def test_hooks_folder_is_empty():
    assert sorted(p.name for p in (PLUGIN / save.HOOKS_DIR).iterdir()) == ["README"]
    tracked = out("ls-files", "--full-name", posix(PLUGIN / save.HOOKS_DIR), cwd=PLUGIN)
    assert tracked == "plugins/wiki/git-hooks-off/README"


@pytest.mark.checks("save/no-tags-pushed")
def test_no_tags(wk):
    wk.commit("page", "wiki/page.md")
    git(wk.w, "tag", "-a", "-m", "t", "v1")
    assert wk.save().rc == 0
    assert out("tag", cwd=wk.bare) == ""


@pytest.mark.checks("save/cloud-origin-differs", "save/cloud-origin-matches")
def test_cloud_origin(wk):
    wk.commit("page", "wiki/page.md")
    git(wk.w, "remote", "add", "origin", file_url(wk.t / "other.git"))
    r = wk.save(env={"CLAUDE_CODE_REMOTE": "true"})
    refused(r, "this session's repository is not the wiki's pinned remote")
    assert "origin: %s" % file_url(wk.t / "other.git") in se(r)
    git(wk.w, "remote", "set-url", "origin", wk.url[:-len(".git")] + "/")
    assert wk.save(env={"CLAUDE_CODE_REMOTE": "true"}).rc == 0


@pytest.mark.checks("save/refuse-empty-remote")
def test_empty_remote(tmp_path, cli, fakebin):
    wk = Wiki(tmp_path, cli, fakebin)
    git(wk.bare, "update-ref", "-d", "refs/heads/main")
    refused(wk.save(), "the wiki's remote has no main yet: create main on the remote first")


# --- saving -----------------------------------------------------------------------

@pytest.mark.checks("save/push", "save/other-host-reminder")
def test_push(wk):
    wk.commit("page", "wiki/page.md", "raw/a.txt", "outputs/r.md", "open-questions.md")
    r = wk.save()
    assert r.rc == 0, r
    assert so(r) == "saved %s to main\n" % wk.short()
    assert wk.remote() == wk.head()
    assert ("save: note: this host can't be checked from here; it must refuse force pushes and deletion "
            "of main (docs/setup.md)") in se(r)
    assert wk.gh_calls() == []
    r = wk.save()
    assert so(r) == "saved %s to main\nnothing new: main already has it\n" % wk.short()


@pytest.mark.checks("save/config-change-needs-permission")
def test_config_change_needs_permission(wk):
    """A commit that changes the config needs permission, even when its own
    content_paths would cover it."""
    wk.config(commit=True, enabled=True, url=wk.url, base="main",
              content_paths=["wiki/", "raw/", "outputs/", "open-questions.md", ".claude/"])
    refused(wk.save(), "these changes need your permission: .claude/settings.wiki-save.json")


@pytest.mark.checks("save/content-paths-from-remote")
def test_content_paths_widened_by_commit(wk):
    """A commit can't widen content_paths for itself: the remote base's
    config decides."""
    wk.config(enabled=True, url=wk.url, base="main",
              content_paths=["wiki/", ".claude/", ".github/", "CLAUDE.md"])
    write(wk.w / "CLAUDE.md", "# Do as this says\n")
    write(wk.w / ".github/workflows/x.yml", "on: push\n")
    git(wk.w, "add", "-A")
    git(wk.w, "commit", "-qm", "widen")
    refused(wk.save(), "these changes need your permission: .claude/settings.wiki-save.json "
                       ".github/workflows/x.yml CLAUDE.md")


@pytest.mark.checks("save/check-pushes-nothing")
def test_check(wk):
    before = wk.remote()
    wk.commit("page", "wiki/page.md")
    r = wk.save("--check")
    assert r.rc == 0, r
    assert so(r) == "checked: would push %s to main\n" % wk.short()
    assert wk.remote() == before


@pytest.mark.checks("save/check-no-merge")
def test_check_diverged(wk):
    wk.other_push("theirs", "wiki/theirs.md")
    wk.commit("mine", "wiki/mine.md")
    head = wk.head()
    r = wk.save("--check")
    assert so(r) == "checked: would push %s to main\nwould merge main from the wiki's remote first\n" % wk.short()
    assert wk.head() == head


@pytest.mark.checks("save/dirty-work-tree-warns")
def test_dirty(wk):
    wk.commit("page", "wiki/page.md")
    write(wk.w / "wiki/draft.md", "x\n")
    r = wk.save()
    assert r.rc == 0, r
    assert wk.remote() == wk.head()
    assert "save: warning: uncommitted changes aren't saved, only commits (`git status` lists them)" in se(r)


@pytest.mark.checks("save/content-paths-from-config")
def test_content_paths(wk):
    wk.config(commit=True, enabled=True, url=wk.url, base="main", content_paths=["notes/", "README.md"])
    # The config change itself needs permission once.
    r = wk.save("--allow", save.CONFIG)
    assert r.rc == 0, r
    wk.commit("n", "notes/a.md", "README.md")
    assert wk.save().rc == 0
    wk.commit("w", "wiki/x.md")
    r = wk.save()
    refused(r, "these changes need your permission: wiki/x.md")


# --- paths ---------------------------------------------------------------------

@pytest.mark.checks("save/refuse-permission-tier", "save/permission-call-printed")
def test_permission_refused(wk):
    before = wk.remote()
    wk.commit("rules", "CLAUDE.md", ".gitattributes", "wiki/page.md")
    r = wk.save()
    refused(r, "these changes need your permission: .gitattributes CLAUDE.md")
    assert se(r) == (
        "save: refused: these changes need your permission: .gitattributes CLAUDE.md\n"
        "look: git diff %s %s -- .gitattributes CLAUDE.md\n"
        "run: %s --allow .gitattributes CLAUDE.md\n" % (wk.short(before), wk.short(), CALL))
    assert wk.remote() == before
    refused(wk.save("--check"), "these changes need your permission: .gitattributes CLAUDE.md")


@pytest.mark.checks("save/allow")
def test_allow(wk):
    wk.commit("rules", "CLAUDE.md", ".gitattributes", "wiki/page.md")
    r = wk.save("--allow", "CLAUDE.md", ".gitattributes")
    assert r.rc == 0, r
    assert so(r) == "saved %s to main\n" % wk.short()
    assert wk.remote() == wk.head()


@pytest.mark.parametrize("allow", [
    pytest.param(["CLAUDE.md"], id="save/refuse-allow-too-few"),
    pytest.param(["CLAUDE.md", ".gitattributes", ".mcp.json"], id="save/refuse-allow-too-many"),
    pytest.param(["CLAUDE.md", "wiki/page.md"], id="save/refuse-allow-wrong"),
])
def test_allow_wrong_set(allow, wk):
    before = wk.remote()
    wk.commit("rules", "CLAUDE.md", ".gitattributes", "wiki/page.md")
    r = wk.save("--allow", *allow)
    refused(r, "the --allow list isn't the set of paths that need permission")
    # A fresh look: line, as the plain refusal prints it, for the diff to show again.
    assert se(r) == (
        "save: refused: the --allow list isn't the set of paths that need permission\n"
        "need permission: .gitattributes CLAUDE.md\n"
        "look: git diff %s %s -- .gitattributes CLAUDE.md\n"
        "run: %s --allow .gitattributes CLAUDE.md\n" % (wk.short(before), wk.short(), CALL))
    assert wk.remote() == before


@pytest.mark.parametrize("path", [
    pytest.param("../CLAUDE.md", id="save/refuse-allow-dotdot"),
    pytest.param("wiki/../CLAUDE.md", id="save/refuse-allow-inner-dotdot"),
    pytest.param("/CLAUDE.md", id="save/refuse-allow-absolute"),
    pytest.param("--check", id="save/refuse-allow-flag"),
    pytest.param("-x", id="save/refuse-allow-dash"),
    pytest.param("*.md", id="save/refuse-allow-glob"),
    pytest.param("CLAUDE.md\nrm", id="save/refuse-allow-control"),
    pytest.param("", id="save/refuse-allow-empty"),
])
def test_allow_bad_path(path, wk):
    wk.commit("rules", "CLAUDE.md")
    before = wk.remote()
    r = wk.save("--allow", "CLAUDE.md", path)
    refused(r, "not a plain relative path after --allow: ")
    assert wk.remote() == before


@pytest.mark.checks("save/refuse-allow-prose")
def test_allow_prose(wk):
    """Extra words in the list are refused: it must be exactly the set."""
    wk.commit("rules", "CLAUDE.md")
    before = wk.remote()
    r = wk.save("--allow", "CLAUDE.md", "and", "everything", "else")
    refused(r, "the --allow list isn't the set of paths that need permission")
    assert wk.remote() == before


@pytest.mark.checks("save/refuse-allow-nothing-needed")
def test_allow_nothing_needed(wk):
    wk.commit("page", "wiki/page.md")
    r = wk.save("--allow", "CLAUDE.md")
    refused(r, "no path needs permission")
    assert "run: %s\n" % CALL in se(r)


@pytest.mark.parametrize("name", [pytest.param("my notes.md", id="save/unallowable-space"),
                                  pytest.param("a(b).md", id="save/unallowable-paren"),
                                  pytest.param("it's.md", id="save/unallowable-quote"),
                                  pytest.param("x#1.md", id="save/unallowable-hash"),
                                  pytest.param("[x].md", id="save/unallowable-bracket")])
def test_unallowable_path(name, wk):
    """A path the guard wouldn't let through --allow gets no dead-end run:
    line, but the way out."""
    wk.commit("odd", name, "CLAUDE.md")
    r = wk.save()
    refused(r, "these changes need your permission: ")
    assert "run:" not in se(r)
    assert ("can't be allowed by --allow: %s. Rename it, or save with --unattended (a holding branch "
            "for you to merge)" % shlex.quote(name)) in se(r)
    r = wk.save("--allow", "CLAUDE.md")
    refused(r, "the --allow list isn't the set of paths that need permission")
    assert "run:" not in se(r)


@pytest.mark.parametrize("plugin,want", [
    pytest.param("/opt/plug ins/wiki", 'run: bash "/opt/plug ins/wiki/scripts/save.sh" --allow CLAUDE.md\n',
                 id="save/call-path-double-quoted"),
    pytest.param("/opt/plugins/wiki", "run: bash /opt/plugins/wiki/scripts/save.sh --allow CLAUDE.md\n",
                 id="save/call-path-plain"),
    pytest.param("/opt/$x/wiki", "the plugin's path /opt/$x/wiki/scripts/save.sh holds a character the call "
                 "can't carry", id="save/call-path-unusable"),
])
def test_call_script_path(plugin, want, wk):
    wk.commit("rules", "CLAUDE.md")
    r = call_main(save.main, ["--plugin", plugin], cwd=wk.w, env=wk.env)
    assert r.rc == 1
    assert want in r.err.decode()
    if "$" in plugin:
        assert "run:" not in r.err.decode()


@pytest.mark.checks("save/allow-limits-as-guard")
def test_allow_limits_match_guard():
    """save.py can't import the guard's limits (a hook module): equal by test."""
    assert (save.ALLOW_MAX_PATHS, save.ALLOW_MAX_CHARS) == (guard.SAVE_MAX_PATHS, guard.SAVE_MAX_CHARS)


def _long_paths(total):
    """Paths whose --allow words are exactly `total` characters long."""
    paths, n = [], len("--allow")
    while n < total:
        p = "t/%02d" % len(paths) + "a" * min(150, total - n - 5)
        paths.append(p)
        n += 1 + len(p)
    assert n == total
    return paths


@pytest.mark.checks("save/allow-limits")
@pytest.mark.parametrize("paths,ok", [
    pytest.param(["t/%02d.md" % i for i in range(50)], True, id="save/allow-50-paths"),
    pytest.param(["t/%02d.md" % i for i in range(51)], False, id="save/allow-51-paths"),
    pytest.param(_long_paths(2000), True, id="save/allow-2000-chars"),
    pytest.param(_long_paths(2001), False, id="save/allow-2001-chars"),
])
def test_allow_limits(paths, ok):
    """A run: line only where the guard lets the call through; past its
    limits, the way out instead of a call it would refuse."""
    line = save.call("/opt/plugins/wiki/scripts/save.sh", paths)
    assert (guard.allow_problem(["--allow"] + paths) == "") == ok
    if ok:
        assert line == "run: bash /opt/plugins/wiki/scripts/save.sh --allow " + " ".join(paths)
    else:
        assert line == ("can't be allowed by --allow: %d paths, more than one call carries (at most 50 "
                        "paths and 2000 characters). Save with --unattended (a holding branch for you "
                        "to merge)" % len(paths))


@pytest.mark.checks("save/refuse-too-many-to-allow")
def test_too_many_to_allow(wk):
    wk.commit("many", *["templates/%02d.md" % i for i in range(51)])
    r = wk.save()
    refused(r, "these changes need your permission: templates/00.md")
    assert "run:" not in se(r)
    assert "can't be allowed by --allow: 51 paths, more than one call carries" in se(r)


@pytest.mark.parametrize("plugin,paths,want", [
    pytest.param("/opt/git/wiki", ["CLAUDE.md", "templates/Push-plan.md"],
                 "can't be allowed by --allow: templates/Push-plan.md (the guard refuses a call that holds "
                 "the words git and push, as a git push). Rename it, or save with --unattended",
                 id="save/unallowable-push-word"),
    pytest.param("/opt/plugins/wiki", ["CLAUDE.md", "git/a.md", "templates/push.md"],
                 "can't be allowed by --allow: templates/push.md (the guard", id="save/unallowable-git-in-path"),
    pytest.param("/opt/push/wiki", ["CLAUDE.md", "templates/git/a.md"],
                 "run: bash /opt/push/wiki/scripts/save.sh --allow CLAUDE.md templates/git/a.md",
                 id="save/allow-git-after-push"),
    pytest.param("/opt/git/push/wiki", ["CLAUDE.md"],
                 "the plugin's path /opt/git/push/wiki/scripts/save.sh holds the words git and push",
                 id="save/call-path-push-word"),
    pytest.param("/opt/plugins/wiki", ["CLAUDE.md", "templates/push-plan.md"],
                 "run: bash /opt/plugins/wiki/scripts/save.sh --allow CLAUDE.md templates/push-plan.md",
                 id="save/allow-push-word-without-git"),
    pytest.param("/opt/git/wiki", ["CLAUDE.md", "templates/pushes.md"],
                 "run: bash /opt/git/wiki/scripts/save.sh --allow CLAUDE.md templates/pushes.md",
                 id="save/allow-push-in-longer-word"),
])
def test_push_word(plugin, paths, want, wk):
    """The guard's no_push refuses a command holding the words git and push:
    such an --allow call is a dead end, so save prints the way out instead."""
    wk.commit("rules", *paths)
    r = call_main(save.main, ["--plugin", plugin], cwd=wk.w, env=wk.env)
    assert r.rc == 1
    err = r.err.decode()
    assert want in err
    # Agreement with the guard's own match on the call save would print.
    cmd = "bash %s/scripts/save.sh --allow %s" % (plugin, " ".join(sorted(paths, key=save._key)))
    refused_by_guard = bool(guard._PUSH.search(guard._STASH_PUSH.sub("git stash", hookjson.norm(cmd))))
    assert refused_by_guard == (not want.startswith("run: "))
    assert ("run:" in err) == want.startswith("run: ")


def _index_entry(wk, mode, sha, path):
    git(wk.w, "update-index", "--add", "--cacheinfo", "%s,%s,%s" % (mode, sha, path))


@pytest.mark.checks("save/refuse-symlink")
def test_symlink(wk):
    blob = subprocess.run(["git", "-C", str(wk.w), "hash-object", "-w", "--stdin"], input=b"index.md",
                          stdout=subprocess.PIPE, check=True).stdout.decode().strip()
    _index_entry(wk, "120000", blob, "wiki/link.md")
    git(wk.w, "commit", "-qm", "link")
    refused(wk.save(), "symlinks and submodules are never saved: wiki/link.md")
    refused(wk.save("--allow", "wiki/link.md"), "symlinks and submodules are never saved: wiki/link.md")


@pytest.mark.checks("save/delete-symlink-needs-permission")
def test_delete_symlink(wk):
    """Removing a symlink the remote already has needs permission; it isn't
    'never'."""
    blob = subprocess.run(["git", "-C", str(wk.w), "hash-object", "-w", "--stdin"], input=b"index.md",
                          stdout=subprocess.PIPE, check=True).stdout.decode().strip()
    _index_entry(wk, "120000", blob, "wiki/link.md")
    git(wk.w, "commit", "-qm", "link")
    git(wk.w, "push", "-q", posix(wk.bare), "HEAD:refs/heads/main")
    git(wk.w, "rm", "-q", "--cached", "wiki/link.md")
    git(wk.w, "commit", "-qm", "unlink")
    refused(wk.save(), "these changes need your permission: wiki/link.md")
    assert wk.save("--allow", "wiki/link.md").rc == 0


@pytest.mark.checks("save/refuse-submodule")
def test_submodule(wk):
    _index_entry(wk, "160000", wk.head(), "wiki/sub")
    write(wk.w / ".gitmodules", '[submodule "sub"]\n\tpath = wiki/sub\n\turl = https://example.com/s.git\n')
    git(wk.w, "add", ".gitmodules")
    git(wk.w, "commit", "-qm", "sub")
    refused(wk.save("--allow", ".gitmodules", "wiki/sub"),
            "symlinks and submodules are never saved: .gitmodules wiki/sub")


@pytest.mark.checks("save/nested-control-files")
def test_nested_control_files(wk):
    """Files that configure Claude or git need permission at any depth,
    inside content folders too."""
    paths = ["wiki/CLAUDE.md", "wiki/notes/claude.local.md", "wiki/.claude/settings.json", "raw/x/.gitattributes",
             "outputs/.gitignore", "wiki/.MCP.json", "wiki/.github/workflows/a.yml", "raw/.githooks/pre-push"]
    for p in paths:
        write(wk.w / p, "x\n")
    write(wk.w / "wiki/claude-notes.md", "x\n")
    git(wk.w, "add", "-A")
    git(wk.w, "commit", "-qm", "nested")
    r = wk.save()
    refused(r, "these changes need your permission: " + " ".join(sorted(paths)))


@pytest.mark.checks("save/refuse-nested-gitmodules")
def test_nested_gitmodules(wk):
    wk.commit("m", "wiki/.gitmodules")
    refused(wk.save("--allow", "wiki/.gitmodules"), "symlinks and submodules are never saved: wiki/.gitmodules")


@pytest.mark.checks("save/config-autocrlf")
def test_config_autocrlf(wk):
    """A checkout with core.autocrlf=true has CRLF in the config; git
    still sees it unchanged."""
    git(wk.w, "config", "core.autocrlf", "true")
    p = wk.w / save.CONFIG
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    write(wk.w / "wiki/page.md", "page\n")
    git(wk.w, "add", "wiki/page.md")   # (the test's git turns autocrlf off)
    git(wk.w, "commit", "-qm", "page")
    r = wk.save()
    assert r.rc == 0, r


@pytest.mark.checks("save/refuse-config-staged")
def test_config_staged(wk):
    p = wk.w / save.CONFIG
    good = p.read_bytes()
    wk.config(enabled=True, url=file_url(wk.t / "elsewhere.git"), base="main")
    git(wk.w, "add", save.CONFIG)
    p.write_bytes(good)
    refused(wk.save(), ".claude/settings.wiki-save.json differs from the committed one")


@pytest.mark.checks("save/setext-heading-not-a-marker")
def test_setext_heading(wk):
    wk.commit("h", "wiki/page.md", content="Title\n=======\n\ntext\n")
    wk.commit("h2", "wiki/half.md", content="<<<<<<< not a conflict on its own\n")
    assert wk.save().rc == 0


@pytest.mark.checks("save/markers-fail-closed")
def test_markers_fail_closed(wk):
    """A blob that can't be read refuses (never counts as clean)."""
    g = call_in(wk, save.Git)
    with pytest.raises(save.Refused, match="can't read wiki/x.md"):
        call_in(wk, save.marked, g, [("100644", "100644", "1" * 40, "wiki/x.md")])


def call_in(wk, fn, *args):
    here = os.getcwd()
    os.chdir(wk.w)
    try:
        return fn(*args)
    finally:
        os.chdir(here)


@pytest.mark.checks("save/refuse-conflict-markers")
def test_markers(wk):
    wk.commit("m", "wiki/page.md", content="a\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> theirs\n")
    refused(wk.save(), "conflict markers left in wiki/page.md")
    wk.commit("fixed", "wiki/page.md", content="a\nx\ny\n")
    assert wk.save().rc == 0


# --- merging -----------------------------------------------------------------------

@pytest.mark.checks("save/merge-then-push")
def test_non_ff_merge(wk):
    wk.other_push("theirs", "wiki/theirs.md")
    wk.commit("mine", "wiki/mine.md")
    r = wk.save()
    assert r.rc == 0, r
    assert so(r) == "saved %s to main\nmerged main from the wiki's remote first (merge)\n" % wk.short()
    assert wk.remote() == wk.head()
    assert out("log", "-1", "--format=%s", cwd=wk.w) == "Merge main from the wiki's remote"
    assert len(out("log", "-1", "--format=%P", cwd=wk.w).split()) == 2


@pytest.mark.checks("save/conflict-exit-3", "save/refuse-merge-in-progress")
def test_non_ff_conflict(wk):
    wk.other_push("theirs", "wiki/index.md", content="# Index\n\ntheirs\n")
    wk.commit("mine", "wiki/index.md", content="# Index\n\nmine\n")
    before = wk.remote()
    r = wk.save()
    assert r.rc == 3, r
    assert so(r) == "conflict: wiki/index.md\n"
    assert se(r) == ("save: merge conflict: the merge of main from the wiki's remote is left in progress; "
                     "resolve the files listed, commit the merge, then save again\n")
    assert (wk.w / ".git/MERGE_HEAD").exists()
    assert wk.remote() == before
    refused(wk.save(), "a merge is in progress")
    refused(wk.save("--update"), "a merge is in progress")


@pytest.mark.checks("save/update-ff", "save/update-up-to-date", "save/update-no-gh")
def test_update_ff(wk):
    wk.other_push("theirs", "wiki/theirs.md")
    r = wk.save("--update")
    assert r.rc == 0, r
    assert so(r) == "updated main: ff\n"
    assert wk.head() == wk.remote()
    assert so(wk.save("--update")) == "updated main: up to date\n"
    assert se(wk.save("--update")) == ""


@pytest.mark.checks("save/update-merge")
def test_update_merge(wk):
    wk.other_push("theirs", "wiki/theirs.md")
    wk.commit("mine", "wiki/mine.md")
    before = wk.remote()
    r = wk.save("--update")
    assert so(r) == "updated main: merge\n"
    assert wk.remote() == before
    assert out("merge-base", "--is-ancestor", before, "HEAD", cwd=wk.w) == ""


@pytest.mark.checks("save/update-conflict")
def test_update_conflict(wk):
    wk.other_push("theirs", "wiki/index.md", content="# Index\n\ntheirs\n")
    wk.commit("mine", "wiki/index.md", content="# Index\n\nmine\n")
    r = wk.save("--update")
    assert r.rc == 3
    assert so(r) == "conflict: wiki/index.md\n"


@pytest.mark.checks("save/shallow-unshallow")
def test_shallow(tmp_path, cli, fakebin):
    """A shallow clone whose merge base lies below its boundary is
    deepened once (the cloud's clones are shallow)."""
    wk = Wiki(tmp_path, cli, fakebin)
    a = wk.head()
    wk.commit("b", "wiki/b.md")
    git(wk.w, "push", "-q", posix(wk.bare), "HEAD:refs/heads/main")
    git(tmp_path, "clone", "-q", "--depth", "1", file_url(wk.bare), "shallow")
    s = tmp_path / "shallow"
    Wiki.ident(s)
    # The remote's main moves to a sibling of b (set up by force here).
    git(wk.w, "checkout", "-q", a)
    wk.commit("c", "wiki/c.md")
    git(wk.w, "push", "-q", "-f", posix(wk.bare), "HEAD:refs/heads/main")
    wk.commit("d", "wiki/d.md", d=s)
    r = cli("save", cwd=s, env=wk.env)
    assert r.rc == 0, r
    assert out("rev-parse", "--is-shallow-repository", cwd=s) == "false"
    assert wk.remote() == out("rev-parse", "HEAD", cwd=s)


# --- GitHub ---------------------------------------------------------------------

@pytest.mark.checks("save/github-protection-ok")
def test_github_ok(ghw):
    ghw.commit("page", "wiki/page.md")
    r = ghw.save()
    assert r.rc == 0, r
    assert so(r) == "saved %s to main\n" % ghw.short()
    assert ghw.remote() == ghw.head()
    assert ghw.gh_calls() == [["api", "--hostname", "github.com", "repos/example/wiki/rules/branches/main?per_page=100"],
                              ["api", "--hostname", "github.com", "repos/example/wiki/rulesets/1"]]
    assert se(r) == ""


@pytest.mark.parametrize("mode,why", [
    pytest.param("no-deletion", "example/wiki doesn't protect main: no deletion rule",
                 id="save/refuse-github-no-deletion-rule"),
    pytest.param("bypass", "example/wiki's ruleset 1 lets you bypass it (current_user_can_bypass: always)",
                 id="save/refuse-github-bypass"),
    pytest.param("error", "can't check example/wiki's protection of main: gh: Not Found (HTTP 404)",
                 id="save/refuse-github-api-error"),
    pytest.param("pull-requests-only", "example/wiki's ruleset 1 lets you bypass it (current_user_can_bypass: "
                 "pull_requests_only)", id="save/refuse-github-bypass-pull-requests"),
    pytest.param("no-bypass-field", "example/wiki's ruleset 1 doesn't say whether you can bypass it "
                 "(no current_user_can_bypass)", id="save/refuse-github-bypass-absent"),
    pytest.param("no-ruleset-id", "example/wiki's non_fast_forward rule names no ruleset",
                 id="save/refuse-github-no-ruleset-id"),
    pytest.param("many-rules", "example/wiki has 100 or more rules on main; too many to check",
                 id="save/refuse-github-too-many-rules"),
])
def test_github_refused(mode, why, ghw):
    before = ghw.remote()
    ghw.commit("page", "wiki/page.md")
    for args in ([], ["--check"], ["--unattended"]):
        r = ghw.save(*args, env={"FAKE_GH_MODE": mode})
        refused(r, why)
        assert 'Set up the ruleset as docs/setup.md, "Optional: the wiki on GitHub" shows.' in se(r)
    assert ghw.remote() == before


@pytest.mark.checks("save/refuse-github-no-gh")
def test_github_no_gh(ghw, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(save.Refused, match="gh isn't installed"):
        save.protection(None, GH_URL, "main")


@pytest.mark.checks("save/github-gh-host-pinned")
def test_github_gh_host(ghw):
    """GH_HOST can't point gh at another host."""
    ghw.commit("page", "wiki/page.md")
    assert ghw.save(env={"GH_HOST": "evil.example.com"}).rc == 0
    assert all(c[1:3] == ["--hostname", "github.com"] for c in ghw.gh_calls())


@pytest.mark.parametrize("url,base,why", [
    pytest.param("https://github.com/example/wi{ki}", "main", "can't check a GitHub repository named example/wi{ki}",
                 id="save/refuse-github-odd-repo"),
    pytest.param("https://github.com/example/wiki/extra", "main", "can't check a GitHub repository named "
                 "example/wiki/extra", id="save/refuse-github-deep-path"),
    pytest.param("ssh://ssh.github.com:443/example/wiki.git", "main", "gh isn't installed",
                 id="save/github-ssh-host-checked"),
    pytest.param(GH_URL, "ma#in", "can't check GitHub's protection of a branch named ma#in",
                 id="save/refuse-github-odd-base"),
])
def test_github_names(url, base, why, ghw, monkeypatch):
    """A github.com pin is always checked: names gh would expand or that
    break the API path refuse, never fall back to the other-host note."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(save.Refused, match=re.escape(why)):
        save.protection(None, url, base)


@pytest.mark.checks("save/no-github-seam")
def test_no_github_seam(monkeypatch):
    monkeypatch.setenv("WIKI_SAVE_TEST_FILE_URLS", "1")
    monkeypatch.setenv("WIKI_SAVE_TEST_GITHUB_REMOTE", "file:///x/remote.git")
    assert save.transport(GH_URL) == GH_URL


@pytest.mark.parametrize("url", [pytest.param("file:////server/share/w.git", id="save/refuse-file-unc"),
                                 pytest.param("file://host/w.git", id="save/refuse-file-host")])
def test_file_url_forms(url, monkeypatch):
    monkeypatch.setenv("WIKI_SAVE_TEST_FILE_URLS", "1")
    assert save.url_parts(url) is None
    assert save.url_parts("file:///x/w.git") == ("", "/x/w.git")


@pytest.mark.checks("save/git-hardening")
def test_git_hardening(wk, monkeypatch):
    monkeypatch.setenv("GIT_NO_REPLACE_OBJECTS", "0")
    assert save.clean_env()["GIT_NO_REPLACE_OBJECTS"] == "1"
    g = call_in(wk, save.Git)
    assert "http.sslVerify=true" in g.argv("status")


@pytest.mark.checks("save/update-skips-protection")
def test_github_update(ghw):
    ghw.other_push("theirs", "wiki/theirs.md")
    r = ghw.save("--update", env={"FAKE_GH_MODE": "error"})
    assert so(r) == "updated main: ff\n"
    assert ghw.gh_calls() == []


@pytest.mark.checks("save/unattended-holding-branch", "save/unattended-draft-pr")
def test_unattended_hold(ghw):
    before = ghw.remote()
    ghw.commit("rules", "CLAUDE.md")
    first = ghw.head()
    ghw.commit("page", "wiki/page.md")
    r = ghw.save("--unattended")
    assert r.rc == 0, r
    branch = "claude/wiki-" + first[:12]
    assert so(r) == ("held %s\ndraft pull request: https://github.com/example/wiki/pull/7\n"
                     "needs your permission: CLAUDE.md\n" % branch)
    assert ghw.remote() == before
    assert ghw.remote(branch) == ghw.head()
    post = ghw.gh_calls()[-1]
    assert post[:6] == ["api", "--hostname", "github.com", "-X", "POST", "repos/example/wiki/pulls"]
    assert ["-f", "head=" + branch] == post[8:10] and ["-f", "base=main"] == post[10:12]
    assert post[-2:] == ["-F", "draft=true"]
    # Clean start of the next unattended run: refused while it waits.
    r = ghw.save("--update", "--unattended")
    refused(r, "a holding branch is on the wiki's remote (%s): merge it, then delete the branch" % branch)
    # An attended update isn't held up.
    assert ghw.save("--update").rc == 0


@pytest.mark.checks("save/unattended-refused-while-held")
def test_unattended_while_held(ghw):
    """A plain unattended save doesn't stack on a holding branch either."""
    ghw.commit("rules", "CLAUDE.md")
    assert ghw.save("--unattended").rc == 0
    branch = "claude/wiki-" + ghw.head()[:12]
    ghw.commit("page", "wiki/page.md")
    refused(ghw.save("--unattended"), "a holding branch is on the wiki's remote (%s): merge it" % branch)


@pytest.mark.parametrize("how,blocks", [
    pytest.param("merge", False, id="save/held-merged-ignored"),
    pytest.param("squash", True, id="save/held-squash-merged-blocks"),
])
def test_held_merged(how, blocks, wk):
    """A holding branch the base already has (a real merge) no longer
    holds runs up; after a squash merge it does, until it is deleted."""
    wk.commit("rules", "CLAUDE.md")
    assert wk.save("--unattended").rc == 0
    branch = "claude/wiki-" + wk.head()[:12]
    git(wk.other, "fetch", "-q", "origin", branch)
    if how == "merge":
        git(wk.other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")
    else:
        git(wk.other, "merge", "-q", "--squash", "FETCH_HEAD")
        git(wk.other, "commit", "-qm", "squashed")
    git(wk.other, "push", "-q", "origin", "HEAD:main")
    r = wk.save("--update", "--unattended")
    if blocks:
        refused(r, "a holding branch is on the wiki's remote (%s): merge it, then delete the branch" % branch)
        git(wk.other, "push", "-q", "origin", ":refs/heads/" + branch)
        r = wk.save("--update", "--unattended")
    assert r.rc == 0, r
    assert so(r).startswith("updated main: ")


@pytest.mark.checks("save/hold-name-exact")
def test_hold_name_exact(wk):
    """Only claude/wiki-<12 hex> is a holding branch."""
    wk.commit("side", "wiki/side.md", d=wk.other)  # a tip main doesn't have
    for name in ("claude/wiki-notes", "claude/wiki-0123456789AB", "claude/wiki-0123456789abc",
                 "claude/wiki-0123456789a", "x/claude/wiki-0123456789ab"):
        git(wk.other, "push", "-q", "origin", "HEAD:refs/heads/" + name)
    r = wk.save("--update", "--unattended")
    assert so(r) == "updated main: up to date\n", r
    git(wk.other, "push", "-q", "origin", "HEAD:refs/heads/claude/wiki-0123456789ab")
    refused(wk.save("--update", "--unattended"), "a holding branch is on the wiki's remote "
            "(claude/wiki-0123456789ab)")


@pytest.mark.checks("save/holding-branch-exists")
def test_holding_branch_exists(ghw, monkeypatch):
    """A holding branch of the same name already there (a race past the
    check): its own message, not "moved meanwhile"."""
    ghw.commit("rules", "CLAUDE.md")
    branch = "claude/wiki-" + ghw.head()[:12]
    ghw.commit("elsewhere", "wiki/x.md", d=ghw.other)
    git(ghw.other, "push", "-q", "origin", "HEAD:refs/heads/" + branch)
    real = save.remote_heads
    monkeypatch.setattr(save, "remote_heads", lambda g, u: {k: v for k, v in real(g, u).items()
                                                            if "claude/wiki-" not in k})
    r = ghw.save("--unattended")
    refused(r, "%s already exists on the wiki's remote: merge it, then delete the branch" % branch)


@pytest.mark.checks("save/error-after-push")
def test_error_after_push(wk, monkeypatch):
    """An internal error once the push went through doesn't say refused."""
    wk.commit("page", "wiki/page.md")
    real = save._say

    def boom(s):
        if s.startswith("saved "):
            raise RuntimeError("late")
        real(s)
    monkeypatch.setattr(save, "_say", boom)
    r = call_main(save.main, ["--plugin", PLUGIN_BASH], cwd=wk.w, env=wk.env)
    assert r.rc == 1
    assert wk.remote() == wk.head()
    assert r.err.decode() == ("save: internal error after the push (%s is on main): RuntimeError: late\n"
                              % wk.head()[:12])


@pytest.mark.skipif(IS_WIN, reason="a file name that isn't UTF-8 needs a POSIX file system")
@pytest.mark.checks("save/non-utf8-path")
def test_non_utf8_path(wk, run):
    blob = subprocess.run(["git", "-C", str(wk.w), "hash-object", "-w", "--stdin"], input=b"x\n",
                          stdout=subprocess.PIPE, check=True).stdout.decode().strip()
    subprocess.run([b"git", b"-C", str(wk.w).encode(), b"update-index", b"--add", b"--cacheinfo",
                    b"100644," + blob.encode() + b",bad\xff.md"], check=True)
    git(wk.w, "commit", "-qm", "odd name")
    r = run(["bash", SCRIPTS_P + "/save.sh"], cwd=wk.w, env=wk.env)
    assert r.rc == 1
    assert r.err.startswith(b"save: refused: these changes need your permission: bad\xff.md\n"), r


@pytest.mark.checks("save/unattended-pr-fails")
def test_unattended_pr_error(ghw):
    ghw.commit("rules", "CLAUDE.md")
    r = ghw.save("--unattended", env={"FAKE_GH_MODE": "pr-error"})
    assert r.rc == 0, r
    branch = "claude/wiki-" + ghw.head()[:12]
    assert so(r) == "held %s\nneeds your permission: CLAUDE.md\n" % branch
    assert "save: warning: no draft pull request opened" in se(r)


@pytest.mark.checks("save/unattended-free-paths-push")
def test_unattended_free(wk):
    wk.commit("page", "wiki/page.md")
    r = wk.save("--unattended")
    assert so(r) == "saved %s to main\n" % wk.short()
    assert wk.remote() == wk.head()
    assert so(wk.save("--update", "--unattended")) == "updated main: up to date\n"


@pytest.mark.checks("save/unattended-other-host")
def test_unattended_other_host(wk):
    wk.commit("rules", "CLAUDE.md")
    r = wk.save("--unattended")
    branch = "claude/wiki-" + wk.head()[:12]
    assert so(r) == "held %s\nneeds your permission: CLAUDE.md\n" % branch
    assert "save: note: open a merge request for %s into main on the wiki's host" % branch in se(r)
    assert wk.gh_calls() == []


# --- the launcher --------------------------------------------------------------

@pytest.mark.checks("save/launcher-call-path")
def test_launcher(wk, run):
    """Through save.sh the printed call names the script as bash spells it."""
    wk.commit("rules", "CLAUDE.md")
    r = run(["bash", SCRIPTS_P + "/save.sh"], cwd=wk.w, env=wk.env)
    assert r.rc == 1
    assert "run: bash %s/scripts/save.sh --allow CLAUDE.md\n" % PLUGIN_BASH in r.err.decode()
    r = run(["bash", SCRIPTS_P + "/save.sh", "--allow", "CLAUDE.md"], cwd=wk.w, env=wk.env)
    assert r.rc == 0, r
    assert r.out.decode() == "saved %s to main\n" % wk.short()


# --- helpers ---------------------------------------------------------------------

@pytest.mark.parametrize("a,b,same", [
    pytest.param("https://GitHub.com/o/r.git", "https://github.com/o/r", True, id="save/normal-host-git"),
    pytest.param("https://github.com/o/r/", "https://github.com/o/r", True, id="save/normal-slash"),
    pytest.param("https://github.com/O/r", "https://github.com/o/r", False, id="save/normal-path-case"),
    pytest.param("git@github.com:o/r.git", "https://github.com/o/r", False, id="save/normal-forms-differ"),
])
def test_normal(a, b, same):
    assert (save.normal(a) == save.normal(b)) == same


@pytest.mark.parametrize("url,repo", [
    pytest.param("https://github.com/o/r.git", ("o", "r"), id="save/gh-https"),
    pytest.param("ssh://git@github.com/o/r", ("o", "r"), id="save/gh-ssh"),
    pytest.param("git@GitHub.com:o/r.git", ("o", "r"), id="save/gh-scp"),
    pytest.param("https://gitlab.example.com/o/r", None, id="save/gh-other-host"),
    pytest.param("ssh://ssh.github.com:443/o/r.git", ("o", "r"), id="save/gh-ssh-host"),
])
def test_github_repo(url, repo):
    assert save.github_repo(url) == repo


@pytest.mark.parametrize("name,ok", [("main", True), ("wiki/main", True), ("-x", False), ("a..b", False),
                                     ("a b", False), ("x.lock", False), (".x", False), ("a/", False),
                                     ("@", False), ("a@{b", False)])
def test_valid_branch(name, ok):
    assert save.valid_branch(name) == ok
