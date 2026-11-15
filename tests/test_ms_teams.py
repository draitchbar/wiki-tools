"""ms-teams/snapshot.sh (snapshot.py) against a
throwaway wiki and cache, through its launcher (formerly the ms-teams
section of run-tests.sh). One story: each walk builds on the snapshot the
step before saved."""

import pytest

from conftest import PLUGIN, git, norm, posix, write

MTS = posix(PLUGIN / "sources/ms-teams/snapshot.sh")


@pytest.fixture(scope="module")
def mt(tmp_path_factory, run):
    t = tmp_path_factory.mktemp("mt")
    git(t, "init", "-q", "mtw")
    w = t / "mtw"
    write(w / ".claude/sources/instances/teams.md",
          "---\nkey: teams\ntype: ms-teams\nfolders:\n  - Files | file:///b!d/\n---\n")
    write(w / ".claude/sources/instances/mail.md", "---\nkey: mail\ntype: gmail\nlabels: X\n---\n")
    cache = t / "mthome/.cache/wiki-sources/mtw/teams"
    cache.mkdir(parents=True)

    def mts(*args, cwd=w):
        r = run(["bash", MTS] + list(args), cwd=cwd, env={"HOME": posix(t / "mthome")}, merged=True)
        return norm(r.merged, t), r.rc
    return t, cache, mts


@pytest.mark.parametrize("args", [
    pytest.param(["teams", "delete"], id="ms-teams/refuse-unknown-op"),
    pytest.param(["teams", "compare", "--force"], id="ms-teams/refuse-extra-args"),
    pytest.param(["nosuch", "compare"], id="ms-teams/refuse-no-instance"),
    pytest.param(["../x", "compare"], id="ms-teams/refuse-bad-key"),
    pytest.param(["mail", "compare"], id="ms-teams/refuse-wrong-type"),
])
def test_refused(args, mt):
    assert mt[2](*args)[1] == 1


@pytest.mark.checks("ms-teams/refuse-outside-git")
def test_outside_git(mt):
    t, _, mts = mt
    assert mts("teams", "compare", cwd=t)[1] == 1


NAMES = ["ms-teams/refuse-no-walk", "ms-teams/refuse-two-fields", "ms-teams/refuse-bad-size",
         "ms-teams/refuse-duplicate-uri", "ms-teams/first-run-note", "ms-teams/first-run-new",
         "ms-teams/crlf-path-spaces", "ms-teams/compare-no-write", "ms-teams/save", "ms-teams/save-removes-walk",
         "ms-teams/save-strips-cr", "ms-teams/new", "ms-teams/changed", "ms-teams/removed", "ms-teams/summary",
         "ms-teams/moved", "ms-teams/unchanged-silent", "ms-teams/empty-walk-warns", "ms-teams/empty-walk-removed",
         "ms-teams/refuse-bad-snapshot"]


@pytest.mark.checks(*NAMES)
def test_story(mt):
    t, cache, mts = mt

    def walk(text):
        write(cache / "walk.tsv", text)

    def lines(out, prefix):
        return [ln for ln in out.split("\n") if ln.startswith(prefix)]

    assert mts("teams", "compare")[1] == 1  # no walk yet
    walk("file:///b!d/1\tFiles/a.pdf\t10\nfile:///b!d/2\tFiles/b.docx\n")
    assert mts("teams", "compare")[1] == 1
    walk("file:///b!d/1\tFiles/a.pdf\tten\n")
    assert mts("teams", "compare")[1] == 1
    walk("file:///b!d/1\tFiles/a.pdf\t10\nfile:///b!d/1\tFiles/copy.pdf\t10\n")
    assert "repeats URI file:///b!d/1" in mts("teams", "compare")[0]
    walk("file:///b!d/1\tFiles/a.pdf\t10\r\nfile:///b!d/2\tFiles/AP/plan 2026.pptx\t20\r\n\r\n")
    out, _ = mts("teams", "compare")
    assert "no files.tsv yet" in out
    assert len(lines(out, "new\t")) == 2
    assert [ln for ln in out.split("\n") if "plan" in ln] == ["new\tFiles/AP/plan 2026.pptx\t20"]
    assert not (cache / "files.tsv").exists()
    out, _ = mts("teams", "save")
    assert out.rstrip("\n") == "ms-teams snapshot: saved 2 files to @TMP@/mthome/.cache/wiki-sources/mtw/teams/files.tsv"
    assert not (cache / "walk.tsv").exists()
    assert b"\r" not in (cache / "files.tsv").read_bytes()
    walk("file:///b!d/2\tFiles/AP/plan 2026.pptx\t25\nfile:///b!d/3\tFiles/new.md\t5\n")
    out, _ = mts("teams", "compare")
    assert lines(out, "new") == ["new\tFiles/new.md\t5"]
    assert lines(out, "changed") == ["changed\tFiles/AP/plan 2026.pptx\t25 (was 20)"]
    assert lines(out, "removed") == ["removed\tFiles/a.pdf\t10"]
    assert [ln for ln in out.split("\n") if "summary" in ln] == [
        "ms-teams snapshot: summary: 1 new, 1 changed, 0 moved, 1 removed, 0 unchanged"]
    walk("file:///b!d/1\tFiles/Archive/a.pdf\t10\nfile:///b!d/2\tFiles/AP/plan 2026.pptx\t20\n")
    out, _ = mts("teams", "compare")
    assert lines(out, "moved") == ["moved\tFiles/Archive/a.pdf\tfrom Files/a.pdf"]
    assert "plan 2026" not in out
    walk("")
    out, _ = mts("teams", "compare")
    assert "WARNING: walk.tsv is empty" in out
    assert len(lines(out, "removed")) == 2
    write(cache / "files.tsv", "garbage\n")
    walk("file:///b!d/1\tFiles/a.pdf\t10\n")
    assert mts("teams", "compare")[1] == 1
