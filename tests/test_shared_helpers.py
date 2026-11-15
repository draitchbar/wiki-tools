"""The helpers the scripts share: lower() in hookjson.py (the
guard's lean import), read_text(), git(), git_out() and toplevel() in
sourcelib.py; and a check that no script defines its own copy again."""

import ast
import os
import subprocess

import pytest

import hookjson
import install_source
import lint
import sourcelib
from conftest import SCRIPTS, git, posix, write


@pytest.fixture
def outside(tmp_path, monkeypatch):
    """A folder git won't find a work tree above."""
    d = tmp_path / "plain"
    d.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return d


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    git(d, "init", "-q")
    return d


@pytest.mark.checks("shared/lower")
def test_lower():
    assert hookjson.lower("ABC xyz Æ Å İ") == "abc xyz Æ Å İ"
    assert lint.lower is hookjson.lower


@pytest.mark.checks("shared/read-text")
def test_read_text(tmp_path):
    p = tmp_path / "f.md"
    p.write_bytes(b"a\r\nb\xff\n")
    t = sourcelib.read_text(str(p))
    assert t == "a\r\nb\udcff\n"
    assert t.encode("utf-8", "surrogateescape") == b"a\r\nb\xff\n"
    assert sourcelib.read_text(str(tmp_path / "missing")) == ""
    assert sourcelib.read_text(str(tmp_path)) == ""


@pytest.mark.checks("shared/git")
def test_git(repo, outside, monkeypatch):
    rc, o = sourcelib.git(posix(repo), "rev-parse", "--show-toplevel")
    assert rc == 0 and o.endswith("\n") and os.path.samefile(o.rstrip("\n"), repo)
    rc, o = sourcelib.git(posix(outside), "rev-parse", "--show-toplevel")
    assert rc != 0 and o == ""
    # No -C for an empty or missing root: git runs in the current folder.
    monkeypatch.chdir(repo)
    for root in (None, ""):
        rc, o = sourcelib.git(root, "rev-parse", "--show-toplevel")
        assert rc == 0 and os.path.samefile(o.rstrip("\n"), repo)


@pytest.mark.checks("shared/git-missing")
def test_git_missing(repo, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", boom)
    assert sourcelib.git(posix(repo), "status") == (1, "")
    assert sourcelib.git_out(posix(repo), "status") is None
    assert sourcelib.toplevel(posix(repo)) == ""


@pytest.mark.checks("shared/git-out")
def test_git_out(repo, outside):
    write(repo / "a", "x\n")
    git(repo, "add", "a")
    git(repo, "commit", "-qm", "one\n\n")
    assert sourcelib.git_out(posix(repo), "log", "-1", "--format=%B") == "one"
    assert sourcelib.git_out(posix(repo), "status", "--porcelain") == ""
    assert sourcelib.git_out(posix(outside), "status", "--porcelain") is None


@pytest.mark.checks("shared/toplevel")
def test_toplevel(repo, outside, monkeypatch):
    (repo / "sub").mkdir()
    assert os.path.samefile(sourcelib.toplevel(posix(repo / "sub")), repo)
    assert sourcelib.toplevel(posix(outside)) == ""
    monkeypatch.chdir(repo / "sub")
    assert os.path.samefile(sourcelib.toplevel(None), repo)
    monkeypatch.chdir(outside)
    assert sourcelib.toplevel(None) == ""


@pytest.mark.checks("shared/wiki-root")
def test_wiki_root(repo, outside, monkeypatch):
    """Two callers, two messages: lint needs a work tree, install-source-file
    one with a CLAUDE.md."""
    monkeypatch.chdir(outside)
    with pytest.raises(lint.Die, match="not inside a git repo; run from a wiki."):
        lint.wiki_root()
    with pytest.raises(install_source.Die, match="not inside a git repo; run it from the wiki."):
        install_source.wiki_root()
    monkeypatch.chdir(repo)
    assert os.path.samefile(lint.wiki_root(), repo)
    with pytest.raises(install_source.Die, match="has no CLAUDE.md"):
        install_source.wiki_root()
    write(repo / "CLAUDE.md", "x\n")
    assert os.path.samefile(install_source.wiki_root(), repo)


@pytest.mark.checks("shared/no-copies")
def test_no_copies():
    """The shared helpers are defined once; the guard stays off sourcelib."""
    own = {"hookjson.py": {"lower"}, "sourcelib.py": {"read_text", "git", "git_out", "toplevel"}}
    shared = {"lower", "_text", "read_text", "git", "git_out", "toplevel"}
    for f in sorted(SCRIPTS.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        defs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        assert defs & shared == own.get(f.name, set()), f.name
    guard = ast.parse((SCRIPTS / "guard.py").read_text(encoding="utf-8"))
    mods = {a.name for n in ast.walk(guard) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module for n in ast.walk(guard) if isinstance(n, ast.ImportFrom)}
    assert "sourcelib" not in mods and not {"lint", "sources", "sync_status"} & mods
