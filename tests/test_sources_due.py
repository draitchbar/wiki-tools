"""sources.sh due: what /wiki:ingest all ingests (issue #37), on a copy of
guard-wiki with one source per reason. Dates in the state are fixed and
long past, except "checked today", so only that line depends on today."""

import datetime
import re
import sys

import pytest

from conftest import TESTS, copytree, git, write

HOST = {"linux": "linux", "darwin": "macos"}.get(sys.platform, "windows")
OTHER = "macos" if HOST == "linux" else "linux"
TODAY = datetime.date.today().isoformat()


@pytest.fixture
def wiki(tmp_path):
    w = copytree(TESTS / "guard-wiki", tmp_path / "dw")
    git(w, "init", "-q")
    bk = w / ".claude/sources/types/bookish/SOURCE.md"
    text = re.sub(r"(?m)^  - (linux|macos|windows)\n", "", bk.read_text())
    write(bk, text.replace("platforms:\n", "platforms:\n  - %s\n" % OTHER, 1))
    write(w / ".claude/sources/instances/all.md", "---\nkey: all\ntype: gmail\n---\n")
    write(w / "raw/sync-log.md",
          "last_checked_gmail: 2026-10-02\n"
          "last_checked_scans:   2026-10-01  \n"   # spaces, as sync-status reads it
          "last_checked_raw: 2026-10-05\n"
          "last_checked_tracker: %s\n"
          "last_checked_proton: 2026-10-01\n"     # access: tools, no reader binding
          "last_checked_code: 2026-10-01\n"       # research
          "last_checked_books: 2026-10-01\n"      # only the other platform
          "last_checked_all: 2026-10-01\n"
          "last_checked_teams: soon\n"
          "last_checked_web: 2026-10-01\n" % TODAY)  # manual
    git(w, "add", "-A")
    git(w, "commit", "-qm", "init", date="2026-10-01T10:00:00")
    return w


def due(cli, w, *args):
    r = cli("sources", "due", *args, cwd=w)
    return r.rc, r.merged.decode("utf-8", "surrogateescape").replace("\r", "")


def expected(due_rows, quiet_rows, skipped_rows):
    out = ["Due for ingest (today %s), oldest first:" % TODAY] + due_rows
    out += ["Not due:"] + quiet_rows + ["Skipped (need the user or another skill):"] + skipped_rows
    return "\n".join(out) + "\n"


SKIPPED = [
    "- all: invalid (sources.sh show all)",
    "- books: not available on %s (only %s)" % (HOST, OTHER),
    '- code: research (/wiki:research code "<question>")',
    "- proton: Check needed (/wiki:ingest proton)",
    "- teams: unreadable date 'soon'",
    "- web: manual key (enters via raw/ or user statements)",
]


def test_due_reasons(cli, wiki):
    rc, out = due(cli, wiki)
    assert rc == 0
    assert out == expected(
        ["- scans: last checked 2026-10-01", "- gmail: last checked 2026-10-02"],
        ["- raw: nothing new in raw/ since 2026-10-05", "- tracker: checked today"],
        SKIPPED)


def test_due_raw_and_check_needed(cli, wiki):
    """Something new in raw/ makes raw due (before gmail: older); an
    uncommitted instance file makes gmail Check needed."""
    write(wiki / "raw/new.txt", "new\n")
    write(wiki / "raw/sync-log.md",
          (wiki / "raw/sync-log.md").read_text().replace("last_checked_raw: 2026-10-05", "last_checked_raw: 2026-10-01"))
    gm = wiki / ".claude/sources/instances/gmail.md"
    write(gm, gm.read_bytes() + b"\nNotes.\n")
    rc, out = due(cli, wiki)
    assert rc == 0
    assert out == expected(
        ["- raw: last checked 2026-10-01", "- scans: last checked 2026-10-01"],
        ["- tracker: checked today"],
        SKIPPED[:3] + ["- gmail: Check needed (/wiki:ingest gmail)"] + SKIPPED[3:])


def show(cli, w, key):
    r = cli("sources", "show", key, cwd=w)
    return r.merged.decode("utf-8", "surrogateescape").replace("\r", "")


def test_check_needed_same_day_ingest(cli, wiki):
    """A second ingest on the day of the first leaves last_checked_<key> as
    it is, so its commit is found by its history row (issue #45). A row of
    another key, also one this key is a part of, is no ingest of this one."""
    log = wiki / "raw/sync-log.md"
    gm = wiki / ".claude/sources/instances/gmail.md"

    def commit(date, msg):
        git(wiki, "add", "-A")
        git(wiki, "commit", "-qm", msg, date=date)

    def gmail_skipped():
        rc, out = due(cli, wiki)
        assert rc == 0
        return "- gmail: Check needed (/wiki:ingest gmail)\n" in out

    write(log, log.read_text().replace("last_checked_gmail: 2026-10-02", "last_checked_gmail: 2026-10-03")
          + "cursor_gmail: 2026-10-03T08:00:00Z\n\n## History\n| Date | Source | What |\n|---|---|---|\n"
          "| 2026-10-03 | gmail | 3 threads |\n")
    commit("2026-10-03T09:00:00", "Ingest gmail")
    assert "Check needed" not in show(cli, wiki, "gmail")
    assert not gmail_skipped()

    write(gm, gm.read_bytes() + b"\nNotes.\n")
    commit("2026-10-03T12:00:00", "Edit the gmail instance")
    needed = "Check needed: the instance file changed (2026-10-03) since the last ingest (2026-10-03).\n"
    assert needed in show(cli, wiki, "gmail")
    assert gmail_skipped()

    write(log, log.read_text() + "| 2026-10-03 | gmail-archive | nothing new |\n| 2026-10-03 | my-gmail | 1 thread |\n")
    commit("2026-10-03T13:00:00", "Ingest other sources")
    assert needed in show(cli, wiki, "gmail")
    assert gmail_skipped()

    write(log, log.read_text().replace("cursor_gmail: 2026-10-03T08:00:00Z", "cursor_gmail: 2026-10-03T14:00:00Z")
          + "| 2026-10-03 | gmail | nothing new |\n")
    commit("2026-10-03T15:00:00", "Ingest gmail: nothing new")
    assert "Check needed" not in show(cli, wiki, "gmail")
    rc, out = due(cli, wiki)
    assert rc == 0
    assert "- gmail: last checked 2026-10-03\n" in out.split("Not due:")[0]


def test_thread_ids_row_is_ingest(cli, wiki):
    """gmail's history row ends with the thread IDs it read (`; thread IDs:
    <id>, <id>`, docs/adr.md 10); it is still this key's ingest row, found
    on a second ingest the same day as in test_check_needed_same_day_ingest."""
    log = wiki / "raw/sync-log.md"
    gm = wiki / ".claude/sources/instances/gmail.md"

    def commit(date, msg):
        git(wiki, "add", "-A")
        git(wiki, "commit", "-qm", msg, date=date)

    write(log, log.read_text().replace("last_checked_gmail: 2026-10-02", "last_checked_gmail: 2026-10-03")
          + "\n## History\n| Date | Source | What |\n|---|---|---|\n"
          "| 2026-10-03 | gmail | 1 thread ingested; thread IDs: 18f0a1b2c3d4e5f6 |\n")
    commit("2026-10-03T09:00:00", "Ingest gmail")
    write(gm, gm.read_bytes() + b"\nNotes.\n")
    commit("2026-10-03T12:00:00", "Edit the gmail instance")
    assert "Check needed: the instance file changed" in show(cli, wiki, "gmail")
    write(log, log.read_text() + "| 2026-10-03 | gmail | 2 threads ingested, 1 skipped; thread IDs: "
          "18f0a1b2c3d4e5f7, 18f0a1b2c3d4e5f8, 18f0a1b2c3d4e5f9 |\n")
    commit("2026-10-03T15:00:00", "Ingest gmail again")
    assert "Check needed" not in show(cli, wiki, "gmail")


def test_due_nothing(cli, tmp_path):
    w = copytree(TESTS / "guard-wiki", tmp_path / "dw")
    git(w, "init", "-q")
    rc, out = due(cli, w)
    assert rc == 0
    assert out.startswith("Due for ingest (today %s), oldest first:\n- none\nNot due:\n- none\n" % TODAY)
    assert "- raw: never checked (first ingest: /wiki:ingest raw)" in out


def test_due_usage(cli, wiki):
    rc, out = due(cli, wiki, "extra")
    assert rc == 1
    assert out == "sources: usage: sources.sh due\n"
