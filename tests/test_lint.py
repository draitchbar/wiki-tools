"""lint.sh against the fixture wiki in tests/lint-wiki (one planted problem
per check), and the recorded edge cases of lint.sh and wiki-check.sh
(formerly the lint and lint-edge sections of run-tests.sh). Every case
runs in-process in both modes; the edge cases in BOUNDARY also run through
lint.sh, in both modes (docs/adr.md, 6)."""

import datetime
import re

import pytest

from conftest import GMAIL_READER, TESTS, copytree, git, home_env, norm, posix, recorded, write

TODAY = {"WIKI_LINT_TODAY": "2026-10-16"}


def text(r):
    return r.merged.decode("utf-8", errors="surrogateescape")


@pytest.fixture(scope="module")
def lw(tmp_path_factory):
    w = copytree(TESTS / "lint-wiki", tmp_path_factory.mktemp("lint") / "lw")
    git(w, "init", "-q")
    return w


@pytest.fixture(scope="module")
def lint_out(lw, cli):
    return text(cli("lint", cwd=lw, env=TODAY))


FOUND = [
    ("summary", "Pages: 6. Errors: 4. Warnings: 10. Info: 1."),
    ("no-frontmatter", "`topics/no-frontmatter.md`: no YAML frontmatter"),
    ("missing-fields", "`tasks/missing-fields.md`: missing title sources"),
    ("broken-alias", "`[[missing-page]]` (no such page) linked from `people/broken-person.md`"),
    ("broken-path-anchor", "`[[also-missing]]` (no such page)"),
    ("orphan", "`topics/no-frontmatter.md`: no inbound links from other pages"),
    ("not-in-index", "`tasks/missing-fields.md`: not listed in index.md"),
    ("no-sources", "`notes/no-sources.md`: `sources:` is empty"),
    ("future-date", "`updated: 2027-01-01` is in the future"),
    ("invalid-date", "`updated: 2026-31-12` is not a YYYY-MM-DD date"),
    ("updated-before", "updated (2026-08-01) is before created (2026-09-01)"),
    # Calendar days.
    ("stale-words", "`decisions/stale-decision.md`: updated 284 days ago and still says: awaiting,pending"),
    ("stale-status", "status_as_of 2026-01-01 is 288 days old"),
    ("no-status", "`decisions/stale-decision.md` (decision): no `status_as_of`"),
    ("clusters", "- **decisions**: `decisions/good-decision.md`, `decisions/stale-decision.md`"),
]


@pytest.mark.parametrize("want", [pytest.param(t, id="lint/" + n) for n, t in FOUND])
def test_found(want, lint_out):
    assert want in lint_out


def _findings(out):
    return out.split("## Clusters")[0]


ABSENT = [
    ("clean-page-not-flagged", "good-decision.md", True),
    ("case-insensitive-links", "broken-person]]", True),
    ("no-prefix-check-without-instances", "matches no source", False),
    # status_as_of: required only for types whose template has it.
    ("status-not-required-by-template", "broken-person.md` (person): no `status_as_of`", False),
    # log.md's links aren't checked (old entries keep renamed pages' names).
    ("log-links-not-checked", "ghost-from-log", False),
]


@pytest.mark.parametrize("needle,findings_only", [pytest.param(t, f, id="lint/" + n) for n, t, f in ABSENT])
def test_absent(needle, findings_only, lint_out):
    assert needle not in (_findings(lint_out) if findings_only else lint_out)


@pytest.mark.checks("lint/status-type-from-template")
def test_status_type_from_template(tmp_path, cli):
    w = copytree(TESTS / "lint-wiki", tmp_path / "lw")
    git(w, "init", "-q")
    (w / "templates" / "decision.md").unlink()
    assert "no `status_as_of`" not in text(cli("lint", cwd=w, env=TODAY))


@pytest.fixture(scope="module")
def lw2(tmp_path_factory):
    """The same wiki with a gmail instance: citations must match a source."""
    w = copytree(TESTS / "lint-wiki", tmp_path_factory.mktemp("lint2") / "lw2")
    git(w, "init", "-q")
    write(w / ".claude/sources/instances/gmail.md", "---\nkey: gmail\ntype: gmail\nlabels: X\n---\n")
    write(w / "raw/sync-log.md", "last_checked_raw: never\nlast_checked_web: never\n")
    write(w / "wiki/cites.md", '---\ntitle: Cites\ntype: note\nsources:\n  - "Gmail: A (2026-09-01)"\n'
          '  - "Proton: x.pdf, p. 1"\n  - raw/a.pdf\n  - "raw: b.pdf, p. 2"\n'
          '  - "web: example.com, buyer guide"\n  - "User statement (2026-10-01)"\n'
          '  - https://example.com\nrelated: []\ncreated: 2026-10-01\nupdated: 2026-10-01\n---\n')
    return w


@pytest.mark.checks("lint/unknown-source-prefix", "lint/known-prefixes-pass")
def test_source_prefixes(lw2, cli):
    out = text(cli("lint", cwd=lw2, env=TODAY))
    assert "`cites.md`: source `Proton: x.pdf, p. 1` matches no source of this wiki" in out
    # cites.md Proton + broken-person.md "Proton Drive"
    assert sum("matches no source" in ln for ln in out.splitlines()) == 2


@pytest.mark.checks("lint/source-yaml-unescape")
def test_source_yaml_unescape(tmp_path, cli):
    """A double-quoted source shows \\" and \\\\ unescaped; a
    single-quoted or bare one is shown as written."""
    w = copytree(TESTS / "lint-wiki", tmp_path / "lw")
    git(w, "init", "-q")
    write(w / ".claude/sources/instances/gmail.md", "---\nkey: gmail\ntype: gmail\nlabels: X\n---\n")
    write(w / "raw/sync-log.md", "last_checked_raw: never\nlast_checked_web: never\n")
    write(w / "wiki/esc.md", '---\ntitle: Esc\ntype: note\nsources:\n'
          '  - "Brave folder \\"garden\\" C:\\\\x (read 2026-09-06)"\n'
          "  - 'Brave single \\\"kept\\\"'\n  - Brave bare \\\"kept\\\" x\n"
          "related: []\ncreated: 2026-10-01\nupdated: 2026-10-01\n---\n")
    out = text(cli("lint", cwd=w, env=TODAY))
    assert '`esc.md`: source `Brave folder "garden" C:\\x (read 2026-09-06)` matches' in out
    assert '`esc.md`: source `Brave single \\"kept\\"` matches' in out
    assert '`esc.md`: source `Brave bare \\"kept\\" x` matches' in out


@pytest.fixture(scope="module")
def lint3(lw2, cli):
    """Case-insensitive prefixes, "Local file: raw/", and as_of pages."""
    write(lw2 / "wiki/cites2.md", '---\ntitle: Cites2\ntype: note\nsources:\n  - "Web: example.com"\n'
          '  - "gmail: B (2026-09-02)"\n  - "Local file: raw/a.pdf"\nrelated: []\n'
          'created: 2026-10-01\nupdated: 2026-10-01\n---\n[[cites]]\n')
    write(lw2 / "wiki/old-analysis.md", "---\ntitle: Old analysis\ntype: research\nsources:\n  - raw/a.pdf\n"
          "related: []\ncreated: 2026-01-01\nupdated: 2026-01-01\nstatus_as_of: 2026-01-01\n"
          "as_of: 2026-01-01\n---\nThe offer is still pending.\n")
    write(lw2 / "wiki/old-note.md", "---\ntitle: Old note\ntype: research\nsources:\n  - raw/a.pdf\n"
          "related: []\ncreated: 2026-01-01\nupdated: 2026-01-01\nas_of: soon\n---\n"
          "The offer is still pending.\n")
    return text(cli("lint", cwd=lw2, env=TODAY))


@pytest.mark.parametrize("needle,present", [
    pytest.param("cites2.md`: source", False, id="lint/prefix-case-and-local-file"),
    pytest.param("old-analysis.md`: updated", False, id="lint/as-of-not-stale"),
    pytest.param("old-analysis.md` (research): status_as_of", False, id="lint/as-of-status-not-stale"),
    pytest.param("old-note.md`: `as_of: soon` is not a YYYY-MM-DD date", True, id="lint/as-of-bad-date"),
])
def test_lint3(needle, present, lint3):
    assert (needle in lint3) == present


@pytest.mark.checks("lint/log-append-ok", "lint/log-uncommitted-edit", "lint/log-committed-edit",
                    "lint/log-append-commit-ok", "lint/log-committed-ages-out")
def test_log_append_only(tmp_path, cli):
    """Removed or changed lines in log.md are errors, appended entries not."""
    w = copytree(TESTS / "lint-wiki", tmp_path / "lw")
    git(w, "init", "-q")
    git(w, "add", "-A")
    git(w, "commit", "-qm", "init")

    def log_section():
        out = text(cli("lint", cwd=w, env=TODAY))
        m = re.search(r"^### ERROR: wiki/log\.md.*?(?=^###|\Z)", out, re.S | re.M)
        return m.group(0) if m else ""

    log = w / "wiki/log.md"
    write(log, "# Log\n## 2026-10-16 | ingest | new\n## 2026-01-01 | init | [[ghost-from-log]]\n")
    assert log_section() == ""
    git(w, "commit", "-qam", "append")
    write(log, log.read_text().replace("| init |", "| init (edited) |"))
    assert "uncommitted changes remove or rewrite 1 line(s)" in log_section()
    # Committed 5 days ago (the window is the real clock): the error names
    # the date it ages out, 30 days after the commit.
    when = datetime.date.today() - datetime.timedelta(days=5)
    git(w, "commit", "-qam", "Rewrite log", date=when.isoformat() + "T12:00:00")
    sec = log_section()
    out = (when + datetime.timedelta(days=30)).isoformat()
    assert re.search(r"commit .*Rewrite log\) removes or rewrites 1 line\(s\) "
                     r"\(ages out on %s\)" % out, sec), sec
    assert sum(ln.startswith("- commit") for ln in sec.splitlines()) == 1


@pytest.mark.checks("lint/no-wiki-folder")
def test_no_wiki_folder(tmp_path, cli):
    w = tmp_path / "nowiki"
    w.mkdir()
    git(w, "init", "-q")
    assert "no wiki/ folder" in text(cli("lint", cwd=w))


# --- lint-edge ------------------------------------------------------------
# Edge cases of lint.sh and wiki-check.sh, checked against the bash versions
# when they moved to Python, and kept as recorded
# output in fixtures/lint/edge.out (exit code, stdout, stderr). --record
# rewrites it.

def _lfm(title, updated="2026-10-01"):
    return ("---\ntitle: %s\ntype: note\nsources:\n  - raw/x.pdf\ncreated: 2026-01-01\n"
            "updated: %s\n---\n" % (title, updated))


_HASH = re.compile(r"commit [0-9a-f]{7,} \([0-9-]{10}, ")
_AGES = re.compile(r"ages out on [0-9-]{10}")
_PY = re.compile(r"find Python 3[^ \n]* [^ \n]*$", re.M)


@pytest.fixture(scope="module")
def edge(tmp_path_factory, cli):
    """The recorded edge cases, run in order on one wiki: their text, the
    wiki, and {name: (in-process block, launcher block)} for BOUNDARY."""
    t = tmp_path_factory.mktemp("edge")
    w = t / "ew"
    w.mkdir()
    git(w, "init", "-q")
    cases, through = [], {}

    def block(name, d, script, env, launcher=False):
        r = cli(script, cwd=d, env=env, launcher=launcher)
        b = "rc=%d\n-- out\n%s-- err\n%s" % (
            r.rc, r.out.decode("utf-8", "surrogateescape"), r.err.decode("utf-8", "surrogateescape"))
        b = norm(b.rstrip("\n"), t)
        b = _PY.sub("find Python @V@", _AGES.sub("ages out on @D@", _HASH.sub("commit @H@ (@D@, ", b)))
        return "== %s\n%s\n" % (name, b)

    def case(name, d, script, env=None):
        cases.append(block(name, d, script, env))
        if name in dict(BOUNDARY):
            through[name] = cases[-1], block(name, d, script, env, launcher=True)

    write(w / "wiki/index.md", "# Index\n[[ok]] [[A-B]] [[b]] [[Økonomi-X]] [[crlf]] [[bom]]\n")
    write(w / "wiki/log.md", "# Log\n## 2026-01-01 | init | [[ghost]]\n")
    write(w / "wiki/ok.md", _lfm("ok") + "Links: [[a-b]] [[ghost-page|alias]] [[folder/target#heading]] "
          "[[  spaced  ]]\n| x | [[a\\|b]] |\n|---|---|\n")
    write(w / "wiki/a-b.md", _lfm("dash"))
    write(w / "wiki/a/b.md", _lfm("slash"))
    write(w / "wiki/crlf.md", "---\r\ntitle: CRLF\r\ntype: note\r\nsources:\r\n  - raw/x.pdf\r\n"
          "created: 2026-01-01\r\nupdated: 2026-10-01\r\n---\r\nText [[ok]]\r\n")
    write(w / "wiki/bom.md", "\ufeff---\ntitle: BOM\ntype: note\nsources: []\ncreated: 2026-01-01\n"
          "updated: 2026-10-01\n---\n")
    write(w / "wiki/latin1.md", _lfm("latin1").encode() + b"Caf\xe9 [[ok]] currently\n")
    write(w / "wiki/dates.md", "---\ntitle: \"Quoted\"\ntype: 'note'\nsources: [a, b]\ncreated: 2026-02-30\n"
          "updated: 2026-10-01 # comment\nstatus_as_of: 2027-01-01\nas_of: 2026-1-1\n---\n")
    write(w / "wiki/stale.md", "---\ntitle: Stale\ntype: decision\nsources:\nas-of: x\n"
          "  - counted under sources\ncreated: 2025-01-01\nupdated: 2025-01-01\n---\n"
          "Currently PENDING. Venter PÅ svar, venter på svar, afventer.\n---|---\nLatest pending\n")
    write(w / "wiki/sub/index.md", "---\ntitle: Twice\ntitle: Again\ntype: decision\nsources: \n"
          "created: 2026-01-01\nupdated: 2025-12-31\n---\n")
    write(w / "wiki/.hidden/h.md", _lfm("hidden"))
    write(w / "wiki/top.md", "no frontmatter [[Økonomi-x]]\n")
    write(w / "wiki/unclosed.md", "---\ntitle: open\ntype: note\n")
    write(w / "wiki/empty.md", "")
    write(w / "templates/decision.md", "---\r\ntitle: T\r\nstatus_as_of: YYYY-MM-DD\r\n---\r\n")
    write(w / "templates/note.md", "status_as_of: x\n---\n")
    (w / "raw").mkdir()
    case("lint-before-commit", w, "lint", TODAY)

    log = w / "wiki/log.md"
    git(w, "commit", "-q", "--allow-empty", "-m", "empty")
    git(w, "add", "-A")
    git(w, "commit", "-q", "-m", "init")
    write(log, log.read_text() + "## 2026-10-16 | x | appended\n")
    git(w, "commit", "-q", "-am", "append")
    git(w, "checkout", "-q", "-b", "side")
    write(log, log.read_text().replace("| init |", "| init (side) |"))
    git(w, "commit", "-q", "-am", "side edit")
    git(w, "checkout", "-q", "main")
    write(log, log.read_text() + "## more\n")
    git(w, "commit", "-q", "-am", "more")
    try:
        git(w, "merge", "-q", "--no-edit", "side")
    except Exception:
        git(w, "checkout", "-q", "--theirs", "wiki/log.md")
        git(w, "add", "-A")
        git(w, "commit", "-q", "-m", "merge")
    write(log, log.read_text().replace("appended", "rewritten"))
    git(w, "commit", "-q", "-am", "rewrite")
    write(log, "".join(log.read_text().splitlines(True)[1:]) + "x\n")
    case("lint", w, "lint", TODAY)
    case("lint-bad-today", w, "lint", {"WIKI_LINT_TODAY": "16-10-2026"})

    # Bound (gmail is access: tools, docs/adr.md 10), so wiki-check below
    # still finds its permission rules missing.
    write(w / ".claude/sources/instances/gmail.md", "---\nkey: gmail\ntype: gmail\nlabels: X\n" + GMAIL_READER
          + "---\n")
    write(w / ".claude/sources/instances/bad.md", "---\nkey: bad\ntype: nosuch\n---\n")
    write(w / "raw/sync-log.md", "last_checked_raw: never\nlast_checked_web: 2026-01-01\n"
          "last_checked_gmail: soon\r\nlast_checked_bad: 2026-02-30\nlast_checked_x:\nlast_checked_tail: never")
    write(w / "wiki/cites.md", _lfm("cites"))
    write(w / "wiki/cites2.md", "---\ntitle: C\ntype: note\nsources:\n  - \"Gmail: a\"\n  - 'web: b'\n"
          "  - \"Proton: c\"\n  - \"''\"\n  - Local file: raw/a\n  - local File: raw/b\n"
          "  - User statement x\n  - https://e\n  - RAW/x\n---\n")
    case("lint-prefixes", w, "lint", TODAY)

    write(w / "CLAUDE.md", "@~/x/schema/wiki-layout.md\r\n@y/schema/wiki-conventions.md\n")
    write(w / ".gitignore", ".obsidian/\r\n.claude/*\n")
    write(w / ".claude/settings.json", '{"permissions": {"allow": ["Read(~/.cache/wiki-sources/**)"]}, '
          '"enabledPlugins": {"wiki@wiki-tools" : true}}')
    write(w / ".claude/sources/types/zz-local/SOURCE.md", "---\ntype: zz-local\n---\n")
    write(w / ".claude/sources/types/a-local/SOURCE.md", "---\ntype: a-local\nscripts:\n  - r.sh other.sh\n---\n")
    (w / "templates/dir.md").mkdir()
    write(w / "templates/with space.md", "x\n")
    git(w, "add", "CLAUDE.md")
    write(w / "CLAUDE.md", (w / "CLAUDE.md").read_bytes() + b"y\n")
    # An empty HOME too: reader rules in the user's settings would count.
    (t / "home-none").mkdir()
    cfg = dict(home_env(posix(t / "home-none")), HOME=posix(t / "home-none"), CLAUDE_CONFIG_DIR=str(t / "cfg-none"))
    case("wiki-check", w, "wiki-check", dict(TODAY, **cfg))
    case("wiki-check-bad-today", w, "wiki-check", dict(cfg, WIKI_LINT_TODAY="bad"))
    write(w / ".claude/settings.json", '{"permissions": {"allow": [,]}}')
    case("wiki-check-bad-json", w, "wiki-check", dict(TODAY, **cfg))

    e = t / "ew-empty"
    (e / "wiki").mkdir(parents=True)
    git(e, "init", "-q")
    case("lint-no-commits", e, "lint", TODAY)
    case("wiki-check-bare", e, "wiki-check", cfg)
    (t / "ew-plain").mkdir()
    case("lint-no-git", t / "ew-plain", "lint")
    return "".join(cases), w, through


# The edge cases that also run through their launcher (bash, py-run.sh,
# Python's stdout and stderr), at their point in the sequence, in both
# modes: each covers something the boundary can break that the in-process
# run can't see. wiki-check.sh's are in test_wiki_check.py.
BOUNDARY = [
    # Success: exit 0, a report with non-ASCII (Økonomi) on stdout, after git history reads.
    ("lint", "success-non-ascii"),
    # A refusal: exit 1, its line on stderr only, an env value passed through bash.
    ("lint-bad-today", "refusal"),
    # Outside a git repo: exit 1 before any check.
    ("lint-no-git", "outside-git"),
]


@pytest.mark.parametrize("name", [pytest.param(n, id="lint-edge/boundary-" + b) for n, b in BOUNDARY])
def test_edge_boundary(name, edge):
    """The chosen edge cases through lint.sh, whatever --e2e says: the
    same block as in-process."""
    inproc, launched = edge[2][name]
    assert launched == inproc


@pytest.mark.checks("lint-edge/same", "lint-edge/cases")
def test_edge_recorded(edge, request):
    out, *_ = edge
    assert out.count("\n== ") + out.startswith("== ") == 10
    recorded(request, TESTS / "fixtures/lint/edge.out", out)


@pytest.mark.parametrize("needle,present", [
    pytest.param("PASS `.gitignore` has `.obsidian/`", True, id="lint-edge/crlf-gitignore"),
    pytest.param("crlf.md`: `created", False, id="lint-edge/crlf-dates"),
])
def test_edge_contains(needle, present):
    assert (needle in (TESTS / "fixtures/lint/edge.out").read_text(encoding="utf-8")) == present


@pytest.mark.checks("lint-edge/symlink-skipped")
def test_symlink_skipped(edge, cli):
    """A symlinked page is not a page (find -type f); only where one can be made."""
    _, w, _ = edge
    try:
        (w / "wiki/link.md").symlink_to("ok.md")
    except OSError:
        pytest.skip("no symlinks here")
    assert "link.md" not in cli("lint", cwd=w, env=TODAY).out.decode("utf-8", "surrogateescape")


# --- index.md Updated dates -------------------------------------------------
# Only the table format /wiki:init writes is checked: header
# `| Page | Summary | Updated |`, Page one [[link]], Updated YYYY-MM-DD.

@pytest.fixture(scope="module")
def idx_out(tmp_path_factory, cli):
    w = tmp_path_factory.mktemp("idx") / "iw"
    w.mkdir()
    git(w, "init", "-q")
    for name in ("same", "stale", "newer", "nodate", "other", "free", "crlf"):
        write(w / ("wiki/n/%s.md" % name), _lfm(name))
    write(w / "wiki/index.md",
          "# Index\n\n## Notes\n\n| Page | Summary | Updated |\n|---|---|---|\n"
          "| [[same]] | Matches | 2026-10-01 |\n"
          "| [[Stale]] | Older than the page | 2026-09-01 |\n"
          "| [[newer]] | Newer than the page | 2026-10-05 |\n"
          "| [[nodate]] | No date | |\n"
          "| [[ghost]] | No such page | 2026-01-01 |\n"
          "| [[same]] and [[stale]] | Two links | 2026-01-01 |\n"
          "\n## Other\n\n| Page | Notes | Date |\n|---|---|---|\n"
          "| [[other]] | Not the fixed format | 2026-01-01 |\n"
          "\n| Page | Summary | Updated |\r\n|---|---|---|\r\n"
          "| [[crlf]] | CRLF row | 2026-02-02 |\r\n"
          "\nFree text after a table: [[free]] 2026-01-01\n"
          "| [[free]] | Not under a header | 2026-01-01 |\n")
    return text(cli("lint", cwd=w, env=TODAY))


@pytest.mark.parametrize("needle,present", [
    pytest.param("`n/same.md`: index.md", False, id="lint/index-date-match"),
    pytest.param("- `n/stale.md`: index.md says Updated 2026-09-01, the page says `updated: 2026-10-01`",
                 True, id="lint/index-date-older"),
    pytest.param("- `n/newer.md`: index.md says Updated 2026-10-05, the page says `updated: 2026-10-01`",
                 True, id="lint/index-date-newer"),
    pytest.param("`n/nodate.md`: index.md", False, id="lint/index-row-without-date"),
    pytest.param("`n/other.md`: index.md", False, id="lint/index-other-table-skipped"),
    pytest.param("`n/free.md`: index.md", False, id="lint/index-row-without-header-skipped"),
    pytest.param("- `n/crlf.md`: index.md says Updated 2026-02-02", True, id="lint/index-date-crlf"),
    pytest.param("### WARN: index.md Updated date differs from the page (3)", True, id="lint/index-date-count"),
])
def test_index_dates(needle, present, idx_out):
    assert (needle in idx_out) == present


# --- open questions (open-questions.md and ^[open: <id>] markers) ---------

Q_OK = "q-2026-09-01-vat-basis"


@pytest.fixture(scope="module")
def q_out(tmp_path_factory, cli):
    """A wiki with one question of each problem; lint on 2026-10-16."""
    w = tmp_path_factory.mktemp("lq") / "qw"
    write(w / "wiki/index.md", "# Index\n\n[[a]] [[b]]\n")
    write(w / "wiki/log.md", "# Log\n\n## 2026-10-01 | clarify | ^[open: q-2026-01-01-in-log]\n")
    write(w / "wiki/a.md", _lfm("A") + "\n[[b]] *VAT basis not stated* ^[open: %s]\n"
          "*Old* ^[open: q-2026-09-15-boundary] ^[open: q-2026-09-16-fresh]\n" % Q_OK)
    write(w / "wiki/b.md", _lfm("B") + "\n[[a]] ^[open: q-2026-10-01-orphan-marker]\n")
    write(w / "open-questions.md", "# Open questions\n\n"
          "### q-2026-10-02-unmarked\n- kind: conflict\n- raised: 2026-10-02, raw\n- pages: [[a]]\n\n"
          "### q-2026-10-03-planted\n- kind: suspicious\n- raised: 2026-10-03, raw\n- items: raw/x.md\n\n"
          "### q-2026-10-04-planted-empty\n- kind: suspicious\n- raised: 2026-10-04, raw\n- items: raw/y.md\n- pages:\n\n"
          "### q-2026-09-16-fresh\n- kind: unclear\n- raised: 2026-09-16, raw\n- pages: [[a]]\n\n"
          "### q-2026-09-15-boundary\n- kind: unclear\n- raised: 2026-09-15, raw\n- pages: [[a]]\n\n"
          "### %s\n- kind: unclear\n- raised: 2026-09-01, gmail\n- pages: [[a]], [[gone]]\n\n"
          "### %s\n- kind: guess\n- raised: soon\n\n"
          "### Bad heading\n- raised: 2026-10-01, raw\n- kind: filing\n" % (Q_OK, Q_OK))
    git(w, "init", "-q")
    return text(cli("lint", cwd=w, env=TODAY))


@pytest.mark.parametrize("want", [pytest.param(t, id="lint/questions-" + n) for n, t in [
    ("old", "### WARN: open questions older than 30 days (2)\n\n"
            "- `q-2026-09-15-boundary` raised 2026-09-15 (31 days ago)\n"
            "- `q-2026-09-01-vat-basis` raised 2026-09-01 (45 days ago)\n"),
    ("markers", "### WARN: open question markers that don't match (2)\n\n"
                "- `b.md`: marker q-2026-10-01-orphan-marker has no question in open-questions.md\n"
                "- `q-2026-10-02-unmarked`: no page carries its marker\n"),
    ("malformed", "### WARN: open-questions.md malformed (3)\n\n"
                  "- `q-2026-09-01-vat-basis`: pages links to [[gone]], no such page\n"
                  "- `q-2026-09-01-vat-basis`: duplicate ID; kind `guess` is not one of unclear, conflict, filing, suspicious; "
                  "raised `soon` has no YYYY-MM-DD date\n"
                  "- `Bad heading`: not a question ID (q-YYYY-MM-DD-<slug>)\n"),
    ("summary", "Errors: 0. Warnings: 7. Info: 0."),
]])
def test_questions(want, q_out):
    assert want in q_out


def test_suspicious_kind_needs_no_marker(q_out):
    assert "q-2026-10-03-planted" not in q_out
    assert "q-2026-10-04-planted-empty" not in q_out


@pytest.mark.checks("lint/questions-fresh-and-log-ignored")
def test_questions_ignored(q_out):
    assert "q-2026-09-16-fresh" not in q_out and "in-log" not in q_out


@pytest.mark.checks("lint/questions-conflict-lines")
def test_questions_conflict(tmp_path, cli):
    w = tmp_path / "qc"
    write(w / "wiki/index.md", "# Index\n")
    write(w / "open-questions.md", "<<<<<<< HEAD\n=======\n>>>>>>> other\n")
    git(w, "init", "-q")
    out = text(cli("lint", cwd=w, env=TODAY))
    assert "### WARN: open-questions.md malformed (1)\n\n- merge conflict lines" in out


@pytest.mark.checks("lint/questions-absent")
def test_questions_absent(lint_out):
    assert "open question" not in lint_out and "open-questions" not in lint_out


@pytest.mark.checks("lint/questions-more")
def test_questions_more(tmp_path, cli):
    """A marker in index.md counts; a malformed marker is named; a future
    raised date is malformed; pages: [[index]] is no page; an unmarked
    duplicate is reported once; markers with no open-questions.md at all."""
    w = tmp_path / "qm"
    write(w / "wiki/index.md", "# Index\n\n[[a]] ^[open: q-2026-10-01-in-index]\n")
    write(w / "wiki/a.md", _lfm("A") + "\n^[open: q-2026-10-1-bad] ^[open: q-2026-10-05-later]\n")
    git(w, "init", "-q")
    out = text(cli("lint", cwd=w, env=TODAY))
    assert "- `index.md`: marker q-2026-10-01-in-index has no question in open-questions.md\n" in out
    assert "- `a.md`: marker q-2026-10-05-later has no question in open-questions.md\n" in out
    assert "- `a.md`: marker `^[open: q-2026-10-1-bad]` is not a question ID (q-YYYY-MM-DD-<slug>)" in out
    write(w / "open-questions.md",
          "### q-2026-10-01-in-index\n- kind: unclear\n- raised: 2026-10-01, raw\n- pages: [[index]]\n\n"
          "### q-2026-10-05-later\n- kind: unclear\n- raised: 2026-12-01, raw\n- pages: [[a]]\n\n"
          "### q-2026-10-09-dup\n- kind: unclear\n- raised: 2026-10-09, raw\n\n"
          "### q-2026-10-09-dup\n- kind: unclear\n- raised: 2026-10-09, raw\n")
    out = text(cli("lint", cwd=w, env=TODAY))
    assert "- `q-2026-10-01-in-index`: pages links to [[index]], no such page" in out
    assert "- `q-2026-10-05-later`: raised 2026-12-01 is in the future" in out
    assert out.count("`q-2026-10-09-dup`: no page carries its marker") == 1
    assert "has no question" not in out
