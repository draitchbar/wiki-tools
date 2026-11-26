"""cloud-update.sh, the SessionStart hook that brings a cloud session's
plugin copy up to date from the setup script's clone (cloud/SETUP.md,
"Keeping the plugin current"; docs/adr.md, 27). End to end through bash:
a local bare repository stands in for GitHub, a folder with the script, the
empty hooks folder, .wiki-tools-ref and .wiki-tools-setup for the setup
script's copy at /opt/wiki-plugin."""

import json
import os
import shutil
import subprocess
import time

import pytest

from conftest import PLUGIN, SCRIPTS, git, posix, write

REMOTE = {"CLAUDE_CODE_REMOTE": "true"}
SCRIPT = (SCRIPTS / "cloud-update.sh").read_bytes()


def head(repo, ref="HEAD"):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", ref], stdout=subprocess.PIPE,
                          check=True).stdout.decode().strip()


def commit(work, files, msg):
    for name, text in files.items():
        write(work / name, text)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", msg)
    git(work, "push", "-q", "origin", "main")
    return head(work)


@pytest.fixture
def cu(tmp_path):
    """upstream work tree, its bare origin, the setup script's clone of it
    (on main) and the plugin copy made from the clone's first commit."""
    bare, work, clone, root = (tmp_path / n for n in ("origin.git", "work", "clone", "plugin"))
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
    shutil.copytree(clone / "plugins" / "wiki", root)
    write(root / ".wiki-tools-ref", first + "\n")
    write(root / ".wiki-tools-setup", "clone=%s\nkind=branch\n" % posix(clone))
    return {"bare": bare, "work": work, "clone": clone, "root": root, "first": first}


def hook(run, cu, env=REMOTE):
    r = run(["bash", posix(cu["root"] / "scripts/cloud-update.sh")], env=env, merged=True)
    assert r.rc == 0, r
    return r.merged.decode()


def ref(cu):
    return (cu["root"] / ".wiki-tools-ref").read_text()


def new_commit(cu):
    return commit(cu["work"], {"plugins/wiki/schema/a.md": "new a\n", "plugins/wiki/new.md": "added\n"},
                  "second")


@pytest.mark.checks("cloud-update/updates")
def test_updates(run, cu):
    new = new_commit(cu)
    out = hook(run, cu)
    assert out == "wiki plugin updated %s -> %s\n" % (cu["first"][:7], new[:7])
    root = cu["root"]
    assert (root / "schema/a.md").read_text() == "new a\n"
    assert (root / "new.md").read_text() == "added\n"
    assert ref(cu) == new + "\n"
    # In place: the script, the hooks folder and the record stay.
    assert (root / "scripts/cloud-update.sh").is_file() and (root / "git-hooks-off/README").is_file()
    assert (root / ".wiki-tools-setup").is_file()
    assert not (root / "README.md").exists()
    # The clone follows, still on its branch.
    assert head(cu["clone"]) == new
    sym = subprocess.run(["git", "-C", str(cu["clone"]), "symbolic-ref", "-q", "HEAD"],
                         stdout=subprocess.PIPE).stdout.decode().strip()
    assert sym == "refs/heads/main"
    # Current now: a second start says nothing.
    assert hook(run, cu) == ""


@pytest.mark.checks("cloud-update/prune")
def test_prunes(run, cu):
    """After the copy, what the commit's plugins/wiki doesn't have goes: a
    removed source type (the guard and sources.sh glob the types), an extra
    file in git-hooks-off/ (save.sh refuses it), and the folders left
    empty; the root's .wiki-tools-* files and __pycache__ folders stay."""
    root = cu["root"]
    git(cu["work"], "rm", "-q", "plugins/wiki/sources/old/SOURCE.md")
    git(cu["work"], "commit", "-q", "-m", "drop a type")
    git(cu["work"], "push", "-q", "origin", "main")
    write(root / "git-hooks-off/pre-push", "#!/bin/sh\nexit 0\n")
    write(root / "skills/stale/SKILL.md", "a skill no longer shipped\n")
    write(root / "scripts/__pycache__/x.cpython-311.pyc", b"\0")
    write(root / ".wiki-tools-extra", "kept\n")
    assert hook(run, cu).startswith("wiki plugin updated ")
    assert not (root / "sources").exists()
    assert sorted(p.name for p in (root / "git-hooks-off").iterdir()) == ["README"]
    assert not (root / "skills").exists()
    assert (root / "scripts/__pycache__/x.cpython-311.pyc").is_file()
    assert (root / ".wiki-tools-extra").is_file() and (root / ".wiki-tools-setup").is_file()
    assert (root / "scripts/cloud-update.sh").is_file() and (root / "schema/a.md").is_file()
    assert root.is_dir()


@pytest.mark.parametrize("size", [
    pytest.param("larger", id="cloud-update/self-overwrite-larger"),
    pytest.param("smaller", id="cloud-update/self-overwrite-smaller"),
])
def test_self_overwrite(run, cu, size):
    """The copy overwrites the running script; bash has parsed it all, so
    neither a larger nor a smaller new version changes this run."""
    body = (b"echo BAD\n" * 2000 + SCRIPT) if size == "larger" else b"#!/bin/sh\necho BAD\n"
    new = commit(cu["work"], {"plugins/wiki/scripts/cloud-update.sh": body}, "new script")
    assert hook(run, cu) == "wiki plugin updated %s -> %s\n" % (cu["first"][:7], new[:7])
    assert (cu["root"] / "scripts/cloud-update.sh").read_bytes() == body


@pytest.mark.checks("cloud-update/current")
def test_current(run, cu):
    before = (cu["root"] / "schema/a.md").read_text()
    assert hook(run, cu) == ""
    assert (cu["root"] / "schema/a.md").read_text() == before and ref(cu) == cu["first"] + "\n"


@pytest.mark.parametrize("env", [
    pytest.param({}, id="cloud-update/not-remote"),
    pytest.param({"CLAUDE_CODE_REMOTE": "false"}, id="cloud-update/remote-false"),
])
def test_not_remote(run, cu, env):
    new_commit(cu)
    assert hook(run, cu, env) == ""
    assert ref(cu) == cu["first"] + "\n" and head(cu["clone"]) == cu["first"]


@pytest.mark.parametrize("setup,detach", [
    pytest.param("kind=commit\n", False, id="cloud-update/pinned-record"),
    pytest.param("", True, id="cloud-update/pinned-detached"),
    pytest.param("kind=branch\n", True, id="cloud-update/branch-record-detached"),
    pytest.param("kind=other\n", False, id="cloud-update/unknown-kind"),
])
def test_pinned(run, cu, setup, detach):
    if detach:
        git(cu["clone"], "checkout", "-q", "--detach")
    write(cu["root"] / ".wiki-tools-setup", "clone=%s\n%s" % (posix(cu["clone"]), setup))
    new_commit(cu)
    assert hook(run, cu) == ""
    assert ref(cu) == cu["first"] + "\n" and (cu["root"] / "schema/a.md").read_text() == "old a\n"


@pytest.mark.checks("cloud-update/no-kind-branch")
def test_no_kind_on_branch(run, cu):
    """An environment set up before the record had kind=: the clone's
    branch decides (CRLF line endings read too)."""
    write(cu["root"] / ".wiki-tools-setup", "clone=%s\r\n" % posix(cu["clone"]))
    new = new_commit(cu)
    assert hook(run, cu) == "wiki plugin updated %s -> %s\n" % (cu["first"][:7], new[:7])


@pytest.mark.parametrize("case", [
    pytest.param("missing", id="cloud-update/no-clone"),
    pytest.param("relative", id="cloud-update/relative-clone"),
    pytest.param("no-ref", id="cloud-update/no-wiki-tools-ref"),
    pytest.param("no-record", id="cloud-update/no-record-no-opt"),
])
def test_not_applicable(run, cu, case, tmp_path):
    root = cu["root"]
    if case == "missing":
        write(root / ".wiki-tools-setup", "clone=%s\nkind=branch\n" % posix(tmp_path / "nothing"))
    elif case == "relative":
        write(root / ".wiki-tools-setup", "clone=clone\nkind=branch\n")
    elif case == "no-ref":
        (root / ".wiki-tools-ref").unlink()
    else:
        if os.path.isdir("/opt/wiki-tools"):
            pytest.skip("this machine has /opt/wiki-tools")
        (root / ".wiki-tools-setup").unlink()
    new_commit(cu)
    assert hook(run, cu) == ""
    assert (root / "schema/a.md").read_text() == "old a\n"
    assert head(cu["clone"]) == cu["first"]


@pytest.mark.checks("cloud-update/fetch-fails")
def test_fetch_fails(run, cu, tmp_path):
    git(cu["clone"], "remote", "set-url", "origin", posix(tmp_path / "gone.git"))
    out = hook(run, cu)
    assert out == "wiki plugin: update check failed; this session runs the snapshot's %s\n" % cu["first"][:7]
    assert ref(cu) == cu["first"] + "\n" and (cu["root"] / "schema/a.md").read_text() == "old a\n"


@pytest.mark.checks("cloud-update/no-plugin-upstream")
def test_no_plugin_upstream(run, cu):
    """A branch commit without the plugin's manifest is not copied."""
    git(cu["work"], "rm", "-q", "plugins/wiki/.claude-plugin/plugin.json")
    git(cu["work"], "commit", "-q", "-m", "broken")
    git(cu["work"], "push", "-q", "origin", "main")
    new = head(cu["work"])
    out = hook(run, cu)
    assert out == "wiki plugin: update to %s failed; this session runs the snapshot's %s\n" % (
        new[:7], cu["first"][:7])
    assert ref(cu) == cu["first"] + "\n" and (cu["root"] / ".claude-plugin/plugin.json").is_file()


@pytest.mark.checks("cloud-update/no-git-hooks")
def test_no_git_hooks(run, cu, tmp_path):
    """The clone's own hooks never run (core.hooksPath is the empty folder)."""
    mark = tmp_path / "hook-ran"
    write(cu["clone"] / ".git/hooks/post-checkout", "#!/bin/sh\necho x > '%s'\n" % posix(mark))
    write(cu["clone"] / ".git/hooks/reference-transaction", "#!/bin/sh\necho x > '%s'\n" % posix(mark))
    for h in ("post-checkout", "reference-transaction"):
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
    assert out.startswith("wiki plugin: update check failed")
    assert 10 < took < 19, took


@pytest.mark.checks("cloud-update/copy-fails")
def test_copy_fails(run, cu):
    """A copy that fails (a folder where the commit has a file) says so and
    leaves .wiki-tools-ref and the other files alone."""
    (cu["root"] / "new.md").mkdir()
    write(cu["root"] / "new.md/keep", "x\n")
    new = new_commit(cu)
    assert hook(run, cu) == ("wiki plugin: update to %s failed while copying; files may be mixed "
                             "until the next session\n" % new[:7])
    assert ref(cu) == cu["first"] + "\n"
    assert (cu["root"] / "sources/old/SOURCE.md").is_file()


@pytest.mark.checks("cloud-update/clone-unreadable")
def test_clone_unreadable(run, cu):
    """git can't read the clone (as with dubious ownership): not a silent
    no-op, the check failed."""
    write(cu["clone"] / ".git/HEAD", "not a ref\n")
    new_commit(cu)
    assert hook(run, cu) == ("wiki plugin: update check failed; this session runs the snapshot's %s\n"
                             % cu["first"][:7])
    assert ref(cu) == cu["first"] + "\n"


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
