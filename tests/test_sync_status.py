"""sync-status.sh (formerly the sync-status section of run-tests.sh):
in-process for the report, in both modes; the plugin-working-tree note end
to end, on copies of the scripts (the note is about the folder the script
runs from), and the cases in BOUNDARY through sync-status.sh, in both
modes (docs/adr.md, 6)."""

import datetime
import shutil

import pytest

from conftest import SCRIPTS, git, posix, rerun, write

ENV = {"CLAUDE_PROJECT_DIR": ""}
SS_FILES = ("sync-status.sh", "sync_status.py", "py-run.sh", "sourcelib.py", "contract.py")


def text(r):
    return r.merged.decode("utf-8", errors="surrogateescape")


@pytest.fixture(scope="module")
def ss(tmp_path_factory, cli):
    """The wiki the old section built step by step, and the output after each step."""
    t = tmp_path_factory.mktemp("ss")
    w = t / "ss"
    git(t, "init", "-q", "ss")
    write(w / "raw/sync-log.md", "last_checked_gmail: never\nlast_checked_proton: 2026-10-01\nlast_checked_web: soon\n")
    out = {"plain": text(cli("sync-status", cwd=w, env=ENV))}
    inst = w / ".claude/sources/instances"
    write(inst / "scans.md", "---\nkey: scans\ntype: local-folder\nroots:\n  - /x\n---\n")
    out["instances"] = text(cli("sync-status", cwd=w, env=ENV))
    # A research instance (mode: research) is left out, line or no line.
    write(inst / "code.md", "---\nkey: code\ntype: codebase\nroots:\n  - /x\n---\n")
    write(inst / "repo.md", "---\nkey: repo\ntype: codebase\nroots:\n  - /y\n---\n")
    log = w / "raw/sync-log.md"
    write(log, log.read_bytes() + b"last_checked_code: 2026-01-01\n")
    out["research"] = text(cli("sync-status", cwd=w, env=ENV))
    return t, w, out


@pytest.mark.parametrize("step,want", [
    pytest.param("plain", "- gmail: never checked", id="sync-status/never"),
    pytest.param("plain", "- proton: last checked 2026-10-01", id="sync-status/date-still-works"),
    pytest.param("plain", "- web: unreadable date 'soon'", id="sync-status/unreadable"),
    pytest.param("instances", "- scans: no last_checked_scans line yet", id="sync-status/instance-without-line"),
    pytest.param("instances", "- gmail: never checked (manual key: enters via raw/ or user statements)",
                 id="sync-status/manual-never"),
    pytest.param("instances", "days ago) (manual key", id="sync-status/manual-dated"),
])
def test_report(step, want, ss):
    assert want in ss[2][step]


@pytest.mark.checks("sync-status/research-skipped")
def test_research_skipped(ss):
    out = ss[2]["research"]
    assert "- code:" not in out and "- repo:" not in out and "- scans:" in out


# The plugin running from a git working tree: a note only when it has
# uncommitted plugin changes (the plugin cache is no git repo: no note).
@pytest.mark.checks("sync-status/plugin-clean", "sync-status/plugin-dirty", "sync-status/plugin-cache")
def test_plugin_note(ss, run):
    t, w, _ = ss
    pt = t / "pt" / "plugins" / "wiki" / "scripts"
    pt.mkdir(parents=True)
    for f in SS_FILES:
        shutil.copy(SCRIPTS / f, pt / f)
    write(t / "pt/.gitignore", "__pycache__/\n")  # as wiki-tools' own
    git(t / "pt", "init", "-q")
    git(t / "pt", "add", "-A")
    git(t / "pt", "commit", "-qm", "init")

    def note(script, env=None):
        r = run(["bash", posix(script)], cwd=w, env=dict(ENV, **(env or {})), merged=True)
        return text(r)

    o = note(pt / "sync-status.sh")
    assert "runs from the working tree" not in o and "Wiki sync status" in o
    write(pt / "sourcelib.py", (pt / "sourcelib.py").read_bytes() + b"\n")
    o = note(pt / "sync-status.sh")
    assert o.index("runs from the working tree") < o.index("sourcelib.py") < o.index("Wiki sync status")
    pc = t / "pc" / "scripts"
    pc.mkdir(parents=True)
    for f in SS_FILES:
        shutil.copy(SCRIPTS / f, pc / f)
    assert "runs from the working tree" not in note(pc / "sync-status.sh", {"GIT_CEILING_DIRECTORIES": posix(t)})


# Dates are real YYYY-MM-DD dates, counted in
# calendar days; a last line without a newline isn't read (as bash's
# `while read`); a CR line ending is dropped; a local research type is left out.
@pytest.fixture(scope="module")
def ss2(tmp_path_factory, cli):
    t = tmp_path_factory.mktemp("ss2")
    w = t / "ss2"
    git(t, "init", "-q", "ss2")
    d3 = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    write(w / "raw/sync-log.md", "last_checked_three: %s\r\nlast_checked_short: 2026-1-1\nlast_checked_empty:\n"
          "last_checked_word: yesterday\nlast_checked_notes: 2026-01-01\nlast_checked_tail: never" % d3)
    write(w / ".claude/sources/types/notes/SOURCE.md", "---\ntype: notes\nmode: research\n---\n")
    write(w / ".claude/sources/instances/notes.md", "---\nkey: notes\ntype: notes\n---\n")
    return w, d3, text(cli("sync-status", cwd=w, env=ENV))


@pytest.mark.checks("sync-status/calendar-days-crlf")
def test_calendar_days(ss2):
    _, d3, out = ss2
    assert "- three: last checked %s (3 days ago) (manual key" % d3 in out


@pytest.mark.checks("sync-status/strict-date")
def test_strict_date(ss2):
    for v in ("short: unreadable date '2026-1-1'", "empty: unreadable date ''",
              "word: unreadable date 'yesterday'"):
        assert "- " + v in ss2[2], v


@pytest.mark.checks("sync-status/unterminated-and-local-research")
def test_unterminated(ss2):
    out = ss2[2]
    assert "- tail" not in out and "- notes" not in out


@pytest.mark.checks("sync-status/python-missing")
def test_python_missing(ss2, run, tmp_path):
    """No Python: one line on stdout (session context), exit 0, as a hook must."""
    import os
    for c in ("python", "python3", "py"):
        write(tmp_path / "bin" / c, "#!/bin/sh\nexit 1\n").chmod(0o755)
    r = run(["bash", posix(SCRIPTS / "sync-status.sh")], cwd=ss2[0],
            env={"CLAUDE_PROJECT_DIR": "", "CLAUDE_PLUGIN_DATA": None, "CLAUDE_CONFIG_DIR": posix(tmp_path / "cfg"),
                 "PATH": str(tmp_path / "bin") + os.pathsep + os.environ.get("PATH", "")})
    assert r.rc == 0
    assert r.out.startswith(b"sync-status: no Python 3.11 or later found (tried python, python3, py -3). Install it")


# The raw line says "nothing new in raw/" when git shows no change under
# raw/ since last_checked_raw but raw/sync-log.md: committed that day or
# later, staged, modified, untracked, or ignored and modified or created
# since that day.
@pytest.fixture(scope="module")
def ss_raw(tmp_path_factory, cli):
    t = tmp_path_factory.mktemp("ssraw")
    w = t / "w"
    git(t, "init", "-q", "w")
    log = w / "raw/sync-log.md"

    def status():
        return text(cli("sync-status", cwd=w, env=ENV))

    write(w / "raw/old.md", "old\n")
    write(log, "last_checked_raw: 2026-10-18\n")
    git(w, "add", "-A")
    git(w, "commit", "-qm", "old", date="2026-10-01T12:00:00")
    write(log, "last_checked_raw: 2026-10-18\nlast_checked_gmail: 2026-10-18\n")
    git(w, "commit", "-qam", "sync-log only", date="2026-10-20T12:00:00")
    write(w / "notes.md", "outside raw/\n")
    out = {"quiet": status()}
    write(w / "raw/new.md", "new\n")
    out["untracked"] = status()
    git(w, "add", "-A")
    out["staged"] = status()
    git(w, "commit", "-qm", "new", date="2026-10-20T12:00:00")
    out["committed"] = status()
    write(log, "last_checked_raw: 2026-10-20\n")
    out["same-day"] = status()
    write(log, "last_checked_raw: 2026-10-21\n")
    out["before"] = status()
    write(w / ".gitignore", "*.pdf\n")
    git(w, "add", "-A")
    git(w, "commit", "-qm", "ignore", date="2026-10-01T12:00:00")
    write(w / "raw/scan.pdf", "pdf\n")
    out["ignored"] = status()
    # An ignored file older than the check day (its times are now, so the
    # check day is tomorrow) is not new: raw/ PDFs are ignored in wikis.
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    write(log, "last_checked_raw: %s\n" % tomorrow.isoformat())
    out["ignored-old"] = status()
    write(w / "raw/scans/a.pdf", "pdf\n")
    out["ignored-dir-old"] = status()
    write(log, "last_checked_raw: 2026-10-21\n")
    (w / "raw/scan.pdf").unlink()
    out["ignored-dir"] = status()
    (w / "raw/scans/a.pdf").unlink()
    write(w / "raw/old.md", "changed\n")
    out["modified"] = status()
    write(log, "last_checked_raw: never\n")
    out["never"] = status()
    return out


@pytest.mark.parametrize("step,quiet", [
    pytest.param("quiet", True, id="sync-status/raw-sync-log-only"),
    pytest.param("untracked", False, id="sync-status/raw-untracked"),
    pytest.param("staged", False, id="sync-status/raw-staged"),
    pytest.param("committed", False, id="sync-status/raw-committed"),
    pytest.param("same-day", False, id="sync-status/raw-committed-same-day"),
    pytest.param("before", True, id="sync-status/raw-committed-before"),
    pytest.param("ignored", False, id="sync-status/raw-ignored"),
    pytest.param("ignored-old", True, id="sync-status/raw-ignored-old"),
    pytest.param("ignored-dir-old", True, id="sync-status/raw-ignored-dir-old"),
    pytest.param("ignored-dir", False, id="sync-status/raw-ignored-dir"),
    pytest.param("modified", False, id="sync-status/raw-modified"),
])
def test_raw_nothing_new(step, quiet, ss_raw):
    lines = ss_raw[step].split("\n")
    raw = [ln for ln in lines if ln.startswith("- raw: last checked ")]
    assert len(raw) == 1 and raw[0].endswith(", nothing new in raw/") == quiet
    assert not any("nothing new" in ln for ln in lines if not ln.startswith("- raw:"))


@pytest.mark.checks("sync-status/raw-never")
def test_raw_never(ss_raw):
    assert "- raw: never checked" in ss_raw["never"] and "nothing new" not in ss_raw["never"]


# --- open questions (open-questions.md) ------------------------------------

def _qwiki(tmp_path, questions=None, synclog=True):
    w = tmp_path / "qw"
    git(tmp_path, "init", "-q", "qw")
    if synclog:
        write(w / "raw/sync-log.md", "last_checked_raw: never\n")
    if questions is not None:
        write(w / "open-questions.md", questions)
    return w


@pytest.mark.checks("sync-status/questions-none")
def test_questions_none(tmp_path, cli):
    w = _qwiki(tmp_path)
    assert "Open questions" not in text(cli("sync-status", cwd=w, env=ENV))
    write(w / "open-questions.md", "# Open questions\n\nNone yet.\n")
    assert "Open questions" not in text(cli("sync-status", cwd=w, env=ENV))


@pytest.mark.checks("sync-status/questions-oldest")
def test_questions_oldest(tmp_path, cli):
    d = datetime.date.today()
    d5, d40 = ((d - datetime.timedelta(days=n)).isoformat() for n in (5, 40))
    w = _qwiki(tmp_path, "# Open questions\n\n### q-%s-new\n- kind: unclear\n- raised: %s, gmail\n\n"
                         "### q-2026-01-01-bad\n- raised: someday\n\n"
                         "### q-%s-old\n- kind: conflict\n- raised: %s, raw\n" % (d5, d5, d40, d40))
    out = text(cli("sync-status", cwd=w, env=ENV))
    assert ("- raw: never checked (first ingest asks for a starting point)\nOpen questions (open-questions.md): 3, "
            "oldest q-%s-old (raised %s, 40 days ago). Answer them with /wiki:clarify.\n" % (d40, d40)) in out


@pytest.mark.checks("sync-status/questions-undated")
def test_questions_undated(tmp_path, cli):
    w = _qwiki(tmp_path, "### q-2026-01-01-x\n- raised: someday\n")
    assert "Open questions (open-questions.md): 1. Answer them with /wiki:clarify." in \
        text(cli("sync-status", cwd=w, env=ENV))


@pytest.mark.checks("sync-status/questions-no-sync-log")
def test_questions_no_sync_log(tmp_path, cli):
    w = _qwiki(tmp_path, "### q-2026-01-01-x\n- raised: 2026-01-01, raw\n", synclog=False)
    assert "Open questions" not in text(cli("sync-status", cwd=w, env=ENV))


@pytest.mark.checks("sync-status/questions-future")
def test_questions_future(tmp_path, cli):
    w = _qwiki(tmp_path, "### q-2026-01-01-x\n- raised: 2999-01-01, raw\n")
    assert "Open questions (open-questions.md): 1. Answer them with /wiki:clarify." in \
        text(cli("sync-status", cwd=w, env=ENV))


# --- the boundary -------------------------------------------------------------

# The cases that also run through sync-status.sh (bash, py-run.sh, Python's
# stdout and stderr), in both modes: each covers something the boundary can
# break that the in-process run can't see. test_plugin_note (the folder the
# launcher runs from) and test_python_missing (the launcher's own message)
# always run bash.
BOUNDARY = [
    # Success: the report with its open-questions line, dates counted from today.
    ("questions", test_questions_oldest),
]


@pytest.mark.parametrize("test", [pytest.param(t, id="sync-status/boundary-" + n) for n, t in BOUNDARY])
def test_boundary(test, request, cli):
    """The chosen cases through sync-status.sh, whatever --e2e says: same
    assertions as in-process, and, as a SessionStart hook must, exit 0 and
    nothing on stderr."""
    def launched(*args, **kw):
        r = cli(*args, launcher=True, **kw)
        assert r.rc == 0 and r.err == b"", r
        return r
    rerun(request, test, cli=launched)
