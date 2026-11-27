"""save.sh (save.py): GitHub's protection check, unattended saves and
holding branches, the launcher, the helpers.

The setup is in save_wiki.py."""

import re
import shutil
import subprocess

import pytest
import save

from conftest import IS_WIN, call_main, PLUGIN_BASH, SCRIPTS_P, git
import save_wiki
from save_wiki import GH_URL, call_in, refused, se, so

# save_wiki's fixtures, which pytest looks up in this module.
fakebin, built, wk, ghw = save_wiki.fakebin, save_wiki.built, save_wiki.wk, save_wiki.ghw


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


# The first case in all three forms that check (save calls protection the
# same way in each); the others once.
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
    forms = ([], ["--check"], ["--unattended"]) if mode == "no-deletion" else ([],)
    for args in forms:
        r = ghw.save(*args, env={"FAKE_GH_MODE": mode})
        refused(r, why)
        assert 'Set up the ruleset as docs/setup.md, "Optional: the wiki on GitHub" shows.' in se(r)
    assert ghw.remote() == before


@pytest.mark.checks("save/refuse-github-no-gh")
def test_github_no_gh(monkeypatch):
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
def test_github_names(url, base, why, monkeypatch):
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
    # py-run.sh's MSYS2_ARG_CONV_EXCL='*' is for Python's own arguments: git's
    # helpers run by Git Bash's sh need the conversion (Windows: a local
    # remote's /C:/... path for git-upload-pack).
    monkeypatch.setenv("MSYS2_ARG_CONV_EXCL", "*")
    assert "MSYS2_ARG_CONV_EXCL" not in save.clean_env()
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
    post = ghw.gh_log()[-1]
    # The fields go as JSON on stdin: a multi-line body survives a gh.cmd launcher.
    assert post["args"] == ["api", "--hostname", "github.com", "-X", "POST", "repos/example/wiki/pulls",
                            "--input", "-"]
    body = post["input"]
    assert {k: body[k] for k in ("title", "head", "base", "draft")} == {
        "title": "Wiki changes that need your permission", "head": branch, "base": "main", "draft": True}
    assert body["body"].startswith("An unattended wiki run changed paths that need your permission:\n\n"
                                   "- `CLAUDE.md`\n\nLook at the diff")
    assert sorted(body) == ["base", "body", "draft", "head", "title"]
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
    # Upper case hex isn't a holding branch. Its own step, then deleted: on
    # Windows a remote's loose refs are files on a case-insensitive file
    # system, where it and the lower-case name can't both exist.
    git(wk.other, "push", "-q", "origin", ":refs/heads/claude/wiki-0123456789AB")
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
