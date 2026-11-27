"""cloud-update.sh, the SessionStart hook that fast-forwards the wiki-tools
clone a cloud session's plugin runs from (cloud/SETUP.md, "Keeping the
plugin current"; docs/adr.md, 27). End to end through bash: a local bare
repository stands in for GitHub, and a clone of it, on main, for the setup
script's /opt/wiki-tools; the hook runs from the clone's plugins/wiki."""

import json
import shutil
import subprocess
import time

import pytest

from conftest import PLUGIN, SCRIPTS, git, posix, write

REMOTE = {"CLAUDE_CODE_REMOTE": "true"}
SCRIPT = (SCRIPTS / "cloud-update.sh").read_bytes()
FAILED = "wiki plugin: update check failed; this session runs %s\n"


def head(repo, ref="HEAD"):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", ref], stdout=subprocess.PIPE,
                          check=True).stdout.decode().strip()


def commit(work, files, msg, push=True):
    for name, text in files.items():
        write(work / name, text)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", msg)
    if push:
        git(work, "push", "-q", "origin", "main")
    return head(work)


@pytest.fixture
def cu(tmp_path):
    """upstream work tree, its bare origin, and the setup script's clone of
    it (on main); root is the clone's plugins/wiki."""
    bare, work, clone = (tmp_path / n for n in ("origin.git", "work", "clone"))
    git(tmp_path, "init", "-q", "--bare", "-b", "main", posix(bare))
    git(tmp_path, "clone", "-q", posix(bare), posix(work))
    # No line-ending conversion in the clone, whatever git config the
    # machine has (the hook drops the tests' core.autocrlf=false).
    first = commit(work, {".gitattributes": "* -text\n",
                          "plugins/wiki/.claude-plugin/plugin.json": '{"name": "wiki"}\n',
                          "plugins/wiki/scripts/cloud-update.sh": SCRIPT,
                          "plugins/wiki/git-hooks-off/README": (PLUGIN / "git-hooks-off/README").read_bytes(),
                          "plugins/wiki/schema/a.md": "old a\n",
                          "plugins/wiki/sources/old/SOURCE.md": "a type removed upstream later\n",
                          "README.md": "not the plugin\n"}, "first")
    git(tmp_path, "clone", "-q", posix(bare), posix(clone))
    return {"bare": bare, "work": work, "clone": clone, "root": clone / "plugins" / "wiki",
            "first": first}


def hook(run, cu, env=REMOTE, root=None):
    r = run(["bash", posix((root or cu["root"]) / "scripts/cloud-update.sh")], env=env, merged=True)
    assert r.rc == 0, r
    return r.merged.decode()


def new_commit(cu):
    git(cu["work"], "rm", "-q", "plugins/wiki/sources/old/SOURCE.md")
    return commit(cu["work"], {"plugins/wiki/schema/a.md": "new a\n", "plugins/wiki/new.md": "added\n"},
                  "second")


def unchanged(cu):
    assert head(cu["clone"]) == cu["first"]
    assert (cu["root"] / "schema/a.md").read_text() == "old a\n"
    assert not (cu["root"] / "new.md").exists()


@pytest.mark.checks("cloud-update/updates")
def test_updates(run, cu):
    new = new_commit(cu)
    assert hook(run, cu) == "wiki plugin updated %s -> %s\n" % (cu["first"][:7], new[:7])
    root = cu["root"]
    assert (root / "schema/a.md").read_text() == "new a\n"
    assert (root / "new.md").read_text() == "added\n"
    # git removes what the commit dropped: a removed source type goes.
    assert not (root / "sources").exists()
    assert head(cu["clone"]) == new
    sym = subprocess.run(["git", "-C", str(cu["clone"]), "symbolic-ref", "-q", "HEAD"],
                         stdout=subprocess.PIPE).stdout.decode().strip()
    assert sym == "refs/heads/main"
    # Current now: a second start says nothing.
    assert hook(run, cu) == ""


@pytest.mark.parametrize("size", [
    pytest.param("larger", id="cloud-update/self-overwrite-larger"),
    pytest.param("smaller", id="cloud-update/self-overwrite-smaller"),
])
def test_self_overwrite(run, cu, size):
    """The merge replaces the running script; bash has parsed it all, so
    neither a larger nor a smaller new version changes this run."""
    body = (b"echo BAD\n" * 2000 + SCRIPT) if size == "larger" else b"#!/bin/sh\necho BAD\n"
    new = commit(cu["work"], {"plugins/wiki/scripts/cloud-update.sh": body}, "new script")
    assert hook(run, cu) == "wiki plugin updated %s -> %s\n" % (cu["first"][:7], new[:7])
    assert (cu["root"] / "scripts/cloud-update.sh").read_bytes() == body


@pytest.mark.checks("cloud-update/current")
def test_current(run, cu):
    assert hook(run, cu) == ""
    unchanged(cu)


@pytest.mark.parametrize("env", [
    pytest.param({}, id="cloud-update/not-remote"),
    pytest.param({"CLAUDE_CODE_REMOTE": "false"}, id="cloud-update/remote-false"),
])
def test_not_remote(run, cu, env):
    new_commit(cu)
    assert hook(run, cu, env) == ""
    unchanged(cu)


@pytest.mark.checks("cloud-update/pinned-detached")
def test_pinned(run, cu):
    """A setup script whose REF is a commit leaves the clone detached: pinned."""
    git(cu["clone"], "checkout", "-q", "--detach")
    new_commit(cu)
    assert hook(run, cu) == ""
    unchanged(cu)


@pytest.mark.checks("cloud-update/not-a-clone")
def test_not_a_clone(run, cu, tmp_path):
    """A plugin folder that isn't plugins/wiki of a git clone (an installed
    copy, a plugin directory elsewhere): nothing."""
    root = tmp_path / "copy" / "plugins" / "wiki"
    shutil.copytree(cu["root"], root)
    new_commit(cu)
    assert hook(run, cu, root=root) == ""
    assert (root / "schema/a.md").read_text() == "old a\n"


@pytest.mark.checks("cloud-update/not-at-plugins-wiki")
def test_not_at_plugins_wiki(run, cu, tmp_path):
    """A clone whose plugin folder is somewhere else in it: nothing."""
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", posix(cu["bare"]), posix(other))
    root = other / "vendor" / "plugins" / "wiki"
    shutil.copytree(cu["root"], root)
    new_commit(cu)
    assert hook(run, cu, root=root) == ""
    assert head(other) == cu["first"]


@pytest.mark.parametrize("env,out", [
    pytest.param(REMOTE, "wiki plugin: this environment copies the plugin, so it can't update; "
                 "see the setup script in cloud/SETUP.md\n", id="cloud-update/old-style-copy"),
    pytest.param({}, "", id="cloud-update/old-style-copy-not-remote"),
])
def test_old_style_copy(run, cu, tmp_path, env, out):
    """An environment made with the first setup script (a copy of the
    plugin with .wiki-tools-ref, beside its clone): a hint, nothing else."""
    root = tmp_path / "wiki-plugin"
    shutil.copytree(cu["root"], root)
    write(root / ".wiki-tools-ref", cu["first"] + "\n")
    write(root / ".wiki-tools-setup", "clone=%s\nkind=branch\n" % posix(cu["clone"]))
    new_commit(cu)
    assert hook(run, cu, env, root=root) == out
    assert (root / "schema/a.md").read_text() == "old a\n"
    unchanged(cu)


@pytest.mark.checks("cloud-update/fetch-fails")
def test_fetch_fails(run, cu, tmp_path):
    git(cu["clone"], "remote", "set-url", "origin", posix(tmp_path / "gone.git"))
    assert hook(run, cu) == FAILED % cu["first"][:7]
    unchanged(cu)


@pytest.mark.checks("cloud-update/diverged")
def test_diverged(run, cu):
    """A clone with a commit of its own can't fast-forward: it says so and
    leaves the clone's files."""
    mine = commit(cu["clone"], {"plugins/wiki/schema/a.md": "local a\n"}, "local", push=False)
    new_commit(cu)
    assert hook(run, cu) == FAILED % mine[:7]
    assert head(cu["clone"]) == mine
    assert (cu["root"] / "schema/a.md").read_text() == "local a\n"
    assert not (cu["root"] / "new.md").exists()


@pytest.mark.checks("cloud-update/clone-unreadable")
def test_clone_unreadable(run, cu):
    """git can't read the clone (as with dubious ownership): not a silent
    no-op, the check failed."""
    write(cu["clone"] / ".git/HEAD", "not a ref\n")
    new_commit(cu)
    assert hook(run, cu) == FAILED % "an unreadable clone"


@pytest.mark.checks("cloud-update/no-git-hooks")
def test_no_git_hooks(run, cu, tmp_path):
    """The clone's own hooks never run (core.hooksPath is the empty folder)."""
    mark = tmp_path / "hook-ran"
    for h in ("post-merge", "post-checkout", "reference-transaction"):
        write(cu["clone"] / ".git/hooks" / h, "#!/bin/sh\necho x > '%s'\n" % posix(mark))
        (cu["clone"] / ".git/hooks" / h).chmod(0o755)
    new_commit(cu)
    assert hook(run, cu).startswith("wiki plugin updated ")
    assert not mark.exists()


@pytest.mark.checks("cloud-update/fetch-timeout")
def test_fetch_timeout(run, cu):
    """A fetch that hangs is stopped after about 15 s; the session goes on."""
    git(cu["clone"], "remote", "set-url", "origin", "ssh://example.invalid/x.git")
    # Hangs a little longer than the limit, so no long-lived leftover
    # process holds the test folder (Windows).
    git(cu["clone"], "config", "core.sshCommand", "sleep 20;:")
    git(cu["clone"], "config", "ssh.variant", "simple")
    t = time.monotonic()
    out = hook(run, cu)
    took = time.monotonic() - t
    assert out == FAILED % cu["first"][:7]
    assert 10 < took < 19, took


# --- the cleaned git environment ------------------------------------------

@pytest.mark.checks("cloud-update/env-config-global")
def test_env_config_global(run, cu, tmp_path):
    """An inherited GIT_CONFIG_GLOBAL can't redirect the fetch."""
    g = write(tmp_path / "gitconfig", "[url \"%s\"]\n\tinsteadOf = %s\n"
              % (posix(tmp_path / "elsewhere.git"), posix(cu["bare"])))
    new = new_commit(cu)
    out = hook(run, cu, dict(REMOTE, GIT_CONFIG_GLOBAL=posix(g)))
    assert out == "wiki plugin updated %s -> %s\n" % (cu["first"][:7], new[:7])


@pytest.mark.checks("cloud-update/env-config-count")
def test_env_config_count(run, cu, tmp_path):
    """Config from GIT_CONFIG_COUNT/KEY/VALUE doesn't apply: an fsmonitor
    command never runs."""
    mark = tmp_path / "fsmonitor-ran"
    script = write(tmp_path / "fsmon.sh", "#!/bin/sh\necho x > '%s'\n" % posix(mark))
    script.chmod(0o755)
    new_commit(cu)
    env = dict(REMOTE, GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_1="core.fsmonitor",
               GIT_CONFIG_VALUE_1=posix(script))
    assert hook(run, cu, env).startswith("wiki plugin updated ")
    assert not mark.exists()


@pytest.mark.checks("cloud-update/env-git-dir")
def test_env_git_dir(run, cu, tmp_path):
    """Inherited GIT_DIR/GIT_WORK_TREE, run from another repo: that repo is
    untouched, the clone is updated."""
    other = tmp_path / "other"
    git(tmp_path, "init", "-q", posix(other))
    write(other / "f.txt", "mine\n")
    git(other, "add", "f.txt")
    git(other, "commit", "-q", "-m", "other")
    before = head(other)
    new = new_commit(cu)
    env = dict(REMOTE, GIT_DIR=posix(other / ".git"), GIT_WORK_TREE=posix(other))
    r = run(["bash", posix(cu["root"] / "scripts/cloud-update.sh")], cwd=str(other), env=env, merged=True)
    assert r.rc == 0 and r.merged.decode().startswith("wiki plugin updated ")
    assert head(other) == before and (other / "f.txt").read_text() == "mine\n"
    assert head(cu["clone"]) == new


# --- hooks.json -----------------------------------------------------------

@pytest.mark.checks("hooks-json/cloud-update-first")
def test_hooks_json_cloud_update_first():
    """The update runs first, at startup and resume (a resumed session in a
    fresh container starts from the snapshot), not on /clear or compaction,
    with a timeout; the schema and the sync status keep their groups."""
    groups = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]["SessionStart"]
    first = groups[0]
    assert first.get("matcher") == "startup|resume"
    assert [h["command"] for h in first["hooks"]] == ['bash "${CLAUDE_PLUGIN_ROOT}/scripts/cloud-update.sh"']
    assert 15 < first["hooks"][0]["timeout"] <= 60
    assert "onFailure" not in first["hooks"][0]
    later = [h["command"] for g in groups[1:] for h in g["hooks"]]
    assert not any("cloud-update" in c for c in later)
    assert sum("schema.sh" in c for c in later) == 2 and sum("sync-status.sh" in c for c in later) == 1
