"""save.sh (save.py): which paths need permission, --allow, merging.

The setup is in save_wiki.py."""

import shlex
import subprocess

import guard
import hookjson
import pytest
import save

from conftest import call_main, git, posix, write
import save_wiki
from save_wiki import CALL, Wiki, call_in, file_url, out, refused, se, so

# save_wiki's fixtures, which pytest looks up in this module.
fakebin, built, wk, ghw = save_wiki.fakebin, save_wiki.built, save_wiki.wk, save_wiki.ghw


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
    refused(wk.save(), ".claude/settings.wiki.json differs from the committed one")


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
def test_shallow(wk, cli):
    """A shallow clone whose merge base lies below its boundary is
    deepened once (the cloud's clones are shallow)."""
    a = wk.head()
    wk.commit("b", "wiki/b.md")
    git(wk.w, "push", "-q", posix(wk.bare), "HEAD:refs/heads/main")
    git(wk.t, "clone", "-q", "--depth", "1", file_url(wk.bare), "shallow")
    s = wk.t / "shallow"
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
