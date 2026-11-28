"""scripts/file-snapshot.sh (file_snapshot.py) against a throwaway wiki and
cache. Every case runs in-process through file_snapshot.main, in both
modes (docs/adr.md, 6). One story: each walk builds on the snapshot the
step before saved. Then the types it accepts (any access: tools type,
standard or local) and refuses. A few chosen cases (BOUNDARY, and the
missing Python) run through the launcher, in both modes."""

import os
import re

import file_snapshot
import pytest

from conftest import PLUGIN, call_main, git, norm, posix, write

FSS = posix(PLUGIN / "scripts/file-snapshot.sh")


def _local_type(w, name, access):
    """A local type in w copied from the standard onenote contract, renamed
    and given `access`; a non-tools type also drops its operations."""
    src = (PLUGIN / "sources/onenote/SOURCE.md").read_text(encoding="utf-8")
    src = src.replace("type: onenote\n", "type: %s\n" % name, 1)
    if access != "tools":
        src = src.replace("access: tools\n", "access: %s\n" % access, 1)
        src = re.sub(r"operations:\n(  - .*\n)+", "operations:\n", src, count=1)
    write(w / (".claude/sources/types/%s/SOURCE.md" % name), src)


@pytest.fixture(scope="module")
def fs(tmp_path_factory, run):
    t = tmp_path_factory.mktemp("fs")
    git(t, "init", "-q", "fsw")
    w = t / "fsw"
    inst = w / ".claude/sources/instances"
    write(inst / "teams.md", "---\nkey: teams\ntype: google-drive\nfolders:\n  - Files (1AbC)\n---\n")
    # gmail is tool-neutral now (docs/adr.md 10); the MCP type refused is local.
    write(inst / "mail.md", "---\nkey: mail\ntype: notes-mcp\nsections:\n  - Book > Section\n---\n")
    write(inst / "tickets.md", "---\nkey: tickets\ntype: jira\nsite: example.atlassian.net\n"
                               "scopes:\n  - mine | project = X\n---\n")
    write(inst / "chats.md", "---\nkey: chats\ntype: ms-teams\nfolders:\n  - Files | file:///b!d/\n---\n")
    write(inst / "notes.md", "---\nkey: notes\ntype: onenote\nsections:\n  - Book > Section\n---\n")
    write(inst / "local-notes.md", "---\nkey: local-notes\ntype: notes-tool\nsections:\n  - Book > Section\n---\n")
    write(inst / "ghost.md", "---\nkey: ghost\ntype: no-such-type\n---\n")
    _local_type(w, "notes-tool", "tools")
    _local_type(w, "notes-mcp", "mcp")
    home = t / "fshome"
    cache = home / ".cache/wiki-sources/fsw/teams"
    cache.mkdir(parents=True)

    def fss(*args, cwd=w, env=None, launcher=False):
        """Result: file_snapshot.main in-process, or with launcher=True
        through bash file-snapshot.sh."""
        env = dict({"HOME": posix(home)}, **(env or {}))
        if launcher:
            return run(["bash", FSS] + list(args), cwd=cwd, env=env)
        return call_main(file_snapshot.main, list(args), cwd=cwd, env=env)

    def merged(*args, **kw):
        r = fss(*args, **kw)
        return norm(r.merged, t), r.rc
    return t, cache, merged, fss


@pytest.mark.parametrize("args", [
    pytest.param(["teams", "delete"], id="file-snapshot/refuse-unknown-op"),
    pytest.param(["teams", "compare", "--force"], id="file-snapshot/refuse-extra-args"),
    pytest.param(["teams"], id="file-snapshot/refuse-no-op"),
    pytest.param(["nosuch", "compare"], id="file-snapshot/refuse-no-instance"),
    pytest.param(["../x", "compare"], id="file-snapshot/refuse-bad-key"),
])
def test_refused(args, fs):
    assert fs[2](*args)[1] == 1


@pytest.mark.parametrize("key,want", [
    pytest.param("mail", "instance 'mail' is not of a tool-neutral type (access: tools).",
                 id="file-snapshot/refuse-mcp-type"),
    pytest.param("ghost", "unknown source type 'no-such-type'", id="file-snapshot/refuse-unknown-type"),
])
def test_refused_type(key, want, fs):
    out, rc = fs[2](key, "compare")
    assert rc == 1 and out.startswith("file-snapshot: ") and want in out, out


@pytest.mark.parametrize("key", [
    pytest.param("tickets", id="file-snapshot/accepts-tools-type-standard"),
    pytest.param("local-notes", id="file-snapshot/accepts-tools-type-local"),
])
def test_accepts_tools_type(key, fs):
    t, _, fss, _ = fs
    d = t / "fshome/.cache/wiki-sources/fsw" / key
    write(d / "walk.tsv", "u1\tF/a.pdf\t1\n")
    out, rc = fss(key, "compare")
    assert rc == 0, out
    assert out.split("\n")[:2] == ["file-snapshot: no files.tsv yet; every file is new.", "new\tF/a.pdf\t1"]
    assert not (d / "files.tsv").exists()


@pytest.mark.checks("file-snapshot/refuse-outside-git")
def test_outside_git(fs):
    t, _, fss, _ = fs
    assert fss("teams", "compare", cwd=t)[1] == 1


# The cases that also cross the process boundary (bash, file-snapshot.sh,
# py-run.sh, Python's stdout and stderr), in both modes: each covers
# something the boundary can break that the in-process run can't see.
BOUNDARY = [
    # A refusal: exit 1, the message on stderr, nothing on stdout.
    ("refusal", "teams", "delete", None, 1, "err", "file-snapshot: operation 'delete' is not allowed"),
    # Success, with non-ASCII text and a space in a path: stdout's encoding.
    ("non-ascii", "notes", "compare", "u1\tFiles/Økonomi plan.pdf\t7\n", 0, "out",
     "new\tFiles/Økonomi plan.pdf\t7\n"),
    # HOME passed through bash, and the cache path in the message spelled
    # as Python spells it (Windows: C:/..., not Git Bash's /c/...).
    ("home-path", "chats", "compare", None, 1, "err",
     "file-snapshot: no walk file @TMP@/fshome/.cache/wiki-sources/fsw/chats/walk.tsv;"),
]


@pytest.mark.parametrize("key,op,walk,rc,stream,text", [pytest.param(*b[1:], id="file-snapshot/boundary-" + b[0])
                                                         for b in BOUNDARY])
def test_boundary(key, op, walk, rc, stream, text, fs):
    """Through file-snapshot.sh, whatever --e2e says: the exit code, the
    text on its stream and nothing on the other; the same as in-process."""
    t, _, _, fss = fs
    if walk is not None:
        write(t / "fshome/.cache/wiki-sources/fsw" / key / "walk.tsv", walk)
    want, got = fss(key, op), fss(key, op, launcher=True)
    streams = {"out": norm(got.out, t), "err": norm(got.err, t)}
    assert got.rc == rc and text in streams.pop(stream) and list(streams.values()) == [""], got
    assert (got.rc, norm(got.out, t), norm(got.err, t)) == (want.rc, norm(want.out, t), norm(want.err, t)), got


@pytest.mark.checks("file-snapshot/no-python")
def test_no_python(fs, tmp_path):
    """The launcher's own refusal (py-run.sh): a boundary case by nature."""
    for c in ("python", "python3", "py"):
        write(tmp_path / "bin" / c, "#!/bin/sh\nexit 1\n").chmod(0o755)
    env = {"CLAUDE_PLUGIN_DATA": posix(tmp_path / "data"), "CLAUDE_CONFIG_DIR": posix(tmp_path / "cfg"),
           "PATH": str(tmp_path / "bin") + os.pathsep + os.environ.get("PATH", "")}
    out, rc = fs[2]("teams", "compare", env=env, launcher=True)
    assert rc == 1 and out.startswith("file-snapshot: no Python 3.11 or later found"), out


NAMES = ["file-snapshot/refuse-no-walk", "file-snapshot/refuse-two-fields", "file-snapshot/refuse-bad-size",
         "file-snapshot/refuse-duplicate-uri", "file-snapshot/first-run-note", "file-snapshot/first-run-new",
         "file-snapshot/crlf-path-spaces", "file-snapshot/compare-no-write", "file-snapshot/save",
         "file-snapshot/save-removes-walk", "file-snapshot/save-strips-cr", "file-snapshot/new",
         "file-snapshot/changed", "file-snapshot/removed", "file-snapshot/summary", "file-snapshot/moved",
         "file-snapshot/unchanged-silent", "file-snapshot/empty-walk-warns", "file-snapshot/empty-walk-removed",
         "file-snapshot/refuse-bad-snapshot"]


@pytest.mark.checks(*NAMES)
def test_story(fs):
    t, cache, fss, _ = fs

    def walk(text):
        write(cache / "walk.tsv", text)

    def lines(out, prefix):
        return [ln for ln in out.split("\n") if ln.startswith(prefix)]

    assert fss("teams", "compare")[1] == 1  # no walk yet
    walk("file:///b!d/1\tFiles/a.pdf\t10\nfile:///b!d/2\tFiles/b.docx\n")
    assert fss("teams", "compare")[1] == 1
    walk("file:///b!d/1\tFiles/a.pdf\tten\n")
    assert fss("teams", "compare")[1] == 1
    walk("file:///b!d/1\tFiles/a.pdf\t10\nfile:///b!d/1\tFiles/copy.pdf\t10\n")
    assert "repeats URI file:///b!d/1" in fss("teams", "compare")[0]
    walk("file:///b!d/1\tFiles/a.pdf\t10\r\nfile:///b!d/2\tFiles/AP/plan 2026.pptx\t20\r\n\r\n")
    out, _ = fss("teams", "compare")
    assert "no files.tsv yet" in out
    assert len(lines(out, "new\t")) == 2
    assert [ln for ln in out.split("\n") if "plan" in ln] == ["new\tFiles/AP/plan 2026.pptx\t20"]
    assert not (cache / "files.tsv").exists()
    out, _ = fss("teams", "save")
    assert out.rstrip("\n") == "file-snapshot: saved 2 files to @TMP@/fshome/.cache/wiki-sources/fsw/teams/files.tsv"
    assert not (cache / "walk.tsv").exists()
    assert b"\r" not in (cache / "files.tsv").read_bytes()
    walk("file:///b!d/2\tFiles/AP/plan 2026.pptx\t25\nfile:///b!d/3\tFiles/new.md\t5\n")
    out, _ = fss("teams", "compare")
    assert lines(out, "new") == ["new\tFiles/new.md\t5"]
    assert lines(out, "changed") == ["changed\tFiles/AP/plan 2026.pptx\t25 (was 20)"]
    assert lines(out, "removed") == ["removed\tFiles/a.pdf\t10"]
    assert [ln for ln in out.split("\n") if "summary" in ln] == [
        "file-snapshot: summary: 1 new, 1 changed, 0 moved, 1 removed, 0 unchanged"]
    walk("file:///b!d/1\tFiles/Archive/a.pdf\t10\nfile:///b!d/2\tFiles/AP/plan 2026.pptx\t20\n")
    out, _ = fss("teams", "compare")
    assert lines(out, "moved") == ["moved\tFiles/Archive/a.pdf\tfrom Files/a.pdf"]
    assert "plan 2026" not in out
    walk("")
    out, _ = fss("teams", "compare")
    assert "WARNING: walk.tsv is empty" in out
    assert len(lines(out, "removed")) == 2
    write(cache / "files.tsv", "garbage\n")
    walk("file:///b!d/1\tFiles/a.pdf\t10\n")
    assert fss("teams", "compare")[1] == 1
