"""save.sh (save.py): saving a wiki's commits to its pinned remote.

Each test builds a wiki whose remote is a local bare repository, reached
through the file:// test seam (WIKI_SAVE_TEST_FILE_URLS=1); a second clone
plays the other side (another session, the user). GitHub's checks run on a
github.com pin whose git traffic the second seam
(WIKI_SAVE_TEST_GITHUB_REMOTE) sends to the bare repository, with a fake gh
first on PATH that logs its calls (tests/sources/save/fake_gh.py). Never
the network.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest
import save

from conftest import IS_WIN, PLUGIN, PLUGIN_BASH, SCRIPTS_P, TESTS, git, norm, posix, write

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
        if url == GH_URL:
            self.env["WIKI_SAVE_TEST_GITHUB_REMOTE"] = file_url(self.bare)

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


@pytest.fixture
def ghw(tmp_path, cli, fakebin):
    return Wiki(tmp_path, cli, fakebin, url=GH_URL)


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
    assert "need permission: .gitattributes CLAUDE.md\nrun: %s --allow .gitattributes CLAUDE.md\n" % CALL in se(r)
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


@pytest.mark.checks("save/allow-call-quoted")
def test_allow_call_quoted(wk):
    wk.commit("odd", "my notes.md")
    r = wk.save()
    assert "run: %s --allow 'my notes.md'\n" % CALL in se(r)
    assert wk.save("--allow", "my notes.md").rc == 0


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


@pytest.mark.checks("save/refuse-submodule")
def test_submodule(wk):
    _index_entry(wk, "160000", wk.head(), "wiki/sub")
    write(wk.w / ".gitmodules", '[submodule "sub"]\n\tpath = wiki/sub\n\turl = https://example.com/s.git\n')
    git(wk.w, "add", ".gitmodules")
    git(wk.w, "commit", "-qm", "sub")
    refused(wk.save("--allow", ".gitmodules", "wiki/sub"),
            "symlinks and submodules are never saved: .gitmodules wiki/sub")


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
    assert ghw.gh_calls() == [["api", "repos/example/wiki/rules/branches/main"],
                              ["api", "repos/example/wiki/rulesets/1"]]
    assert se(r) == ""


@pytest.mark.parametrize("mode,why", [
    pytest.param("no-deletion", "example/wiki doesn't protect main: no deletion rule",
                 id="save/refuse-github-no-deletion-rule"),
    pytest.param("bypass", "example/wiki's ruleset 1 lets you bypass it (current_user_can_bypass: always)",
                 id="save/refuse-github-bypass"),
    pytest.param("error", "can't check example/wiki's protection of main: gh api repos/example/wiki/rules/branches/main: "
                 "gh: Not Found (HTTP 404)", id="save/refuse-github-api-error"),
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
    assert post[:4] == ["api", "-X", "POST", "repos/example/wiki/pulls"]
    assert ["-f", "head=" + branch] == post[6:8] and ["-f", "base=main"] == post[8:10]
    assert post[-2:] == ["-F", "draft=true"]
    # Clean start of the next unattended run: refused while it waits.
    r = ghw.save("--update", "--unattended")
    refused(r, "merge or delete %s first" % branch)
    # An attended update isn't held up.
    assert ghw.save("--update").rc == 0


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
    pytest.param("https://github.com/o/r/x", None, id="save/gh-deep-path"),
])
def test_github_repo(url, repo):
    assert save.github_repo(url) == repo


@pytest.mark.parametrize("name,ok", [("main", True), ("wiki/main", True), ("-x", False), ("a..b", False),
                                     ("a b", False), ("x.lock", False), (".x", False), ("a/", False),
                                     ("@", False), ("a@{b", False)])
def test_valid_branch(name, ok):
    assert save.valid_branch(name) == ok
