"""save.sh (save.py): its arguments, the config, where the push goes, saving.

The setup is in save_wiki.py."""

import json
import subprocess

import pytest
import save

from conftest import PLUGIN, git, posix, write
import save_wiki
from save_wiki import file_url, out, refused, se, so

# save_wiki's fixtures, which pytest looks up in this module.
fakebin, built, wk, ghw = save_wiki.fakebin, save_wiki.built, save_wiki.wk, save_wiki.ghw


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
    refused(wk.save(), "saving is off for this wiki (no committed .claude/settings.wiki.json)")


@pytest.mark.checks("save/off-disabled")
def test_off_when_disabled(wk):
    wk.config(commit=True, enabled=False, url=wk.url, base="main")
    refused(wk.save(), "saving is off for this wiki (`save.enabled` isn't true")


@pytest.mark.checks("save/off-flat-format")
def test_off_flat_format(wk):
    """The first, flat format (save fields at the top level) is no `save`
    section: off, with a pointer to the section."""
    write(wk.w / save.CONFIG, json.dumps({"enabled": True, "url": wk.url, "base": "main"}) + "\n")
    git(wk.w, "commit", "-qam", "flat")
    r = wk.save()
    refused(r, "saving is off for this wiki (no `save` section in .claude/settings.wiki.json)")
    assert "Move `enabled`, `url`, `base` under `save` (you, not Claude)" in se(r)


@pytest.mark.parametrize("data", [
    pytest.param({"later": {"enabled": True}}, id="save/off-no-save-section"),
    pytest.param({"save": [{"enabled": True}]}, id="save/off-save-not-object"),
])
def test_off_no_save_section(data, wk):
    write(wk.w / save.CONFIG, json.dumps(data) + "\n")
    git(wk.w, "commit", "-qam", "off")
    r = wk.save()
    refused(r, "saving is off for this wiki (no `save` section in .claude/settings.wiki.json)")
    assert "Move" not in se(r)


@pytest.mark.checks("save/off-not-object")
def test_off_not_object(wk):
    write(wk.w / save.CONFIG, json.dumps([{"save": {"enabled": True}}]) + "\n")
    git(wk.w, "commit", "-qam", "off")
    refused(wk.save(), "saving is off for this wiki (.claude/settings.wiki.json is not a JSON object)")


@pytest.mark.checks("save/other-sections-ignored")
def test_other_sections_ignored(wk):
    """Other top-level keys are left to later features; the change that
    adds them needs permission like any change to the file."""
    wk.config(commit=True, top={"later": {"x": 1}}, enabled=True, url=wk.url, base="main")
    refused(wk.save(), "these changes need your permission: .claude/settings.wiki.json")
    assert wk.save("--allow", save.CONFIG).rc == 0
    wk.commit("page", "wiki/page.md")
    r = wk.save()
    assert r.rc == 0, r
    assert wk.remote() == wk.head()


@pytest.mark.checks("save/refuse-config-changed-in-work-tree")
def test_config_work_tree(wk):
    wk.config(enabled=True, url=file_url(wk.t / "elsewhere.git"), base="main")
    r = wk.save()
    refused(r, ".claude/settings.wiki.json differs from the committed one")
    (wk.w / save.CONFIG).unlink()
    refused(wk.save(), ".claude/settings.wiki.json differs from the committed one")


@pytest.mark.parametrize("cfg,env,why", [
    pytest.param({"url": "http://example.com/w.git"}, {}, "`save.url` must be", id="save/refuse-http-url"),
    pytest.param({}, {"WIKI_SAVE_TEST_FILE_URLS": None}, "`save.url` must be",
                 id="save/refuse-file-url-without-seam"),
    pytest.param({"base": "a..b"}, {}, "`save.base` must be a branch name", id="save/refuse-bad-base"),
    pytest.param({"content_paths": ["../x/"]}, {}, "`save.content_paths`: \"../x/\"",
                 id="save/refuse-dotdot-path"),
    pytest.param({"content_paths": ["/wiki/"]}, {}, "`save.content_paths`: \"/wiki/\" must be relative",
                 id="save/refuse-absolute-path"),
])
def test_config_invalid(cfg, env, why, wk):
    wk.config(commit=True, **dict({"enabled": True, "url": wk.url, "base": "main"}, **cfg))
    r = wk.save(env=env)
    refused(r, ".claude/settings.wiki.json is invalid: ")
    assert why in se(r)


@pytest.mark.checks("save/refuse-remote-pin-differs")
def test_remote_pin_differs(wk):
    """A pin changed only locally (or only remotely) is refused."""
    write(wk.other / save.CONFIG, json.dumps({"save": {"enabled": True, "url": file_url(wk.t / "moved.git"),
                                                       "base": "main"}}) + "\n")
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


def origin_ref(wk):
    """refs/remotes/origin/main in the wiki, or None."""
    r = subprocess.run(["git", "-C", str(wk.w), "rev-parse", "-q", "--verify", "refs/remotes/origin/main"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def with_origin(wk, url):
    """origin set to url, its main at the remote's main (as a clone has it)."""
    git(wk.w, "remote", "add", "origin", url)
    git(wk.w, "update-ref", "refs/remotes/origin/main", wk.remote())
    return wk.remote()


@pytest.mark.checks("save/origin-ref-after-save", "save/origin-ref-after-update")
def test_origin_ref_follows(wk):
    """origin is the pinned URL (another spelling): its main follows the
    remote's main after a save and after --update; the output is as without."""
    with_origin(wk, wk.url[:-len(".git")] + "/")
    wk.commit("page", "wiki/page.md")
    r = wk.save()
    assert r.rc == 0, r
    assert so(r) == "saved %s to main\n" % wk.short()
    assert "warning" not in se(r)
    assert origin_ref(wk) == wk.remote() == wk.head()
    wk.other_push("theirs", "wiki/theirs.md")
    r = wk.save("--update")
    assert so(r) == "updated main: ff\n"
    assert origin_ref(wk) == wk.remote()
    # Nothing new to push: it stays at the remote's main.
    git(wk.w, "update-ref", "refs/remotes/origin/main", "HEAD~1")
    r = wk.save("--unattended")
    assert so(r) == "saved %s to main\nnothing new: main already has it\n" % wk.short()
    assert origin_ref(wk) == wk.remote()
    # An unattended save with free paths pushes to main: the same.
    wk.commit("more", "wiki/more.md")
    assert wk.save("--unattended").rc == 0
    assert origin_ref(wk) == wk.remote() == wk.head()


@pytest.mark.checks("save/origin-ref-other-origin")
def test_origin_ref_other_origin(wk):
    before = with_origin(wk, file_url(wk.t / "other.git"))
    wk.commit("page", "wiki/page.md")
    assert wk.save().rc == 0
    wk.other_push("theirs", "wiki/theirs.md")
    assert wk.save("--update").rc == 0
    assert wk.remote() != before
    assert origin_ref(wk) == before


@pytest.mark.checks("save/origin-ref-no-origin")
def test_origin_ref_no_origin(wk):
    wk.commit("page", "wiki/page.md")
    assert wk.save().rc == 0
    wk.other_push("theirs", "wiki/theirs.md")
    assert wk.save("--update").rc == 0
    assert out("for-each-ref", "refs/remotes", cwd=wk.w) == ""


@pytest.mark.checks("save/origin-ref-not-held", "save/origin-ref-not-check")
def test_origin_ref_untouched(wk):
    """A holding branch and --check leave origin's main as it was."""
    before = with_origin(wk, wk.url)
    wk.other_push("theirs", "wiki/theirs.md")
    wk.commit("page", "wiki/page.md")
    r = wk.save("--check")
    assert r.rc == 0, r
    assert origin_ref(wk) == before
    wk.commit("rules", "CLAUDE.md")
    r = wk.save("--unattended")
    assert so(r).startswith("held claude/wiki-"), r
    assert origin_ref(wk) == before


@pytest.mark.checks("save/origin-ref-fails-warns")
def test_origin_ref_fails(wk):
    """A failed update of origin's main is a warning after the push, exit 0."""
    before = with_origin(wk, wk.url)
    lock = wk.w / ".git" / "refs" / "remotes" / "origin" / "main.lock"
    write(lock, "")
    wk.commit("page", "wiki/page.md")
    r = wk.save()
    assert r.rc == 0, r
    assert so(r) == "saved %s to main\n" % wk.short()
    assert wk.remote() == wk.head()
    assert "save: warning: origin/main not updated: " in se(r)
    lock.unlink()
    assert origin_ref(wk) == before


@pytest.mark.checks("save/refuse-empty-remote")
def test_empty_remote(wk):
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
    refused(wk.save(), "these changes need your permission: .claude/settings.wiki.json")


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
    refused(wk.save(), "these changes need your permission: .claude/settings.wiki.json "
                       ".github/workflows/x.yml CLAUDE.md")


@pytest.mark.checks("save/other-section-change-needs-permission")
def test_other_section_change_needs_permission(wk):
    """A change to another section of the settings file needs permission
    too: the whole file is protected, not only `save`."""
    wk.config(commit=True, top={"later": {"x": 2}}, enabled=True, url=wk.url, base="main")
    refused(wk.save(), "these changes need your permission: .claude/settings.wiki.json")


@pytest.mark.parametrize("remote,need", [
    # No `save` key on the remote counts as no config there: this commit's
    # content_paths sort the paths.
    pytest.param({"later": {}}, "", id="save/remote-no-save-section-uses-own"),
    # A `save` key that isn't an object is unreadable: the defaults.
    pytest.param({"save": 5}, " notes/a.md", id="save/remote-bad-save-section-uses-defaults"),
])
def test_content_paths_remote_without_section(remote, need, wk):
    write(wk.other / save.CONFIG, json.dumps(remote) + "\n")
    git(wk.other, "commit", "-qam", "no save section")
    git(wk.other, "push", "-q", "origin", "HEAD:main")
    git(wk.w, "pull", "-q", "--no-rebase", wk.url, "main")
    wk.config(enabled=True, url=wk.url, base="main", content_paths=["notes/"])
    wk.commit("n", "notes/a.md")
    r = wk.save()
    refused(r, "these changes need your permission: .claude/settings.wiki.json" + need)
    assert se(r).split("\n")[0] == ("save: refused: these changes need your permission: "
                                     ".claude/settings.wiki.json" + need), se(r)


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
