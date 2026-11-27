"""save.py's git calls: none repeated in a run, and exactly as many as each
form needs (a git process is slow on Windows, #123). In-process also with
--e2e: the calls are counted through save.Git.argv, which every git call
(run and marked's cat-file) goes through.

The setup is in save_wiki.py."""

import subprocess

import pytest
import save

from conftest import PLUGIN_BASH, call_main, git
import save_wiki
from save_wiki import file_url, refused, so

# save_wiki's fixtures, which pytest looks up in this module.
fakebin, built, wk = save_wiki.fakebin, save_wiki.built, save_wiki.wk


@pytest.fixture
def calls(monkeypatch):
    """The git argv of each call save.py makes, without the -c options."""
    seen = []
    real = save.Git.argv

    def argv(self, *args):
        seen.append(args)
        return real(self, *args)
    monkeypatch.setattr(save.Git, "argv", argv)
    return seen


def run(wk, calls, *args, env=None):
    """save.main in-process; the calls of this run only."""
    calls.clear()
    r = call_main(save.main, ["--plugin", PLUGIN_BASH] + list(args), cwd=wk.w,
                  env=dict(wk.env, **dict({"CLAUDE_CODE_REMOTE": None}, **(env or {}))))
    return r, list(calls)


def check(got, n):
    # No call twice with the same arguments (a merge conflict, never
    # counted here, checks MERGE_HEAD again after the merge: it changed).
    dups = sorted({c for c in got if got.count(c) > 1})
    assert dups == [], dups
    assert len(got) == n, "\n".join(" ".join(c) for c in got)


def names(got):
    return [c[0] for c in got]


@pytest.mark.checks("save/git-calls-save")
def test_save_up_to_date_then_ff(wk, calls):
    wk.commit("mine", "wiki/mine.md")
    r, got = run(wk, calls)
    assert r.rc == 0 and so(r).startswith("saved "), r
    check(got, 21)
    assert names(got).count("push") == 1
    wk.other_push("theirs", "wiki/theirs.md")
    r, got = run(wk, calls)
    assert so(r) == ("saved %s to main\nmerged main from the wiki's remote first (ff)\n"
                     "nothing new: main already has it\n" % wk.short()), r
    check(got, 20)
    assert "push" not in names(got)


@pytest.mark.checks("save/git-calls-merge")
def test_merge(wk, calls):
    wk.other_push("theirs", "wiki/theirs.md")
    wk.commit("mine", "wiki/mine.md")
    r, got = run(wk, calls)
    assert so(r).endswith("merged main from the wiki's remote first (merge)\n"), r
    check(got, 23)
    assert names(got).count("rev-parse") == 6


@pytest.mark.checks("save/git-calls-check")
def test_check_diverged(wk, calls):
    wk.other_push("theirs", "wiki/theirs.md")
    wk.commit("mine", "wiki/mine.md")
    r, got = run(wk, calls, "--check")
    assert so(r) == ("checked: would push %s to main\nwould merge main from the wiki's remote "
                     "first\n" % wk.short()), r
    check(got, 19)
    assert "merge" not in names(got)


@pytest.mark.checks("save/git-calls-update")
def test_update(wk, calls):
    wk.other_push("theirs", "wiki/theirs.md")
    r, got = run(wk, calls, "--update")
    assert so(r) == "updated main: ff\n", r
    check(got, 17)


@pytest.mark.checks("save/git-calls-refusal")
def test_permission_refusal(wk, calls):
    wk.commit("ctl", "CLAUDE.md")
    r, got = run(wk, calls)
    refused(r, "these changes need your permission: CLAUDE.md")
    check(got, 19)


@pytest.mark.checks("save/git-calls-cloud")
def test_cloud_origin_read_once(wk, calls):
    git(wk.w, "remote", "add", "origin", file_url(wk.bare))
    git(wk.w, "fetch", "-q", "origin")
    wk.commit("mine", "wiki/mine.md")
    r, got = run(wk, calls, env={"CLAUDE_CODE_REMOTE": "true"})
    assert r.rc == 0, r
    check(got, 22)
    assert got.count(("ls-remote", "--get-url", "origin")) == 1
    assert subprocess.run(["git", "-C", str(wk.w), "rev-parse", "origin/main"], stdout=subprocess.PIPE,
                          check=True).stdout.decode().strip() == wk.head()
