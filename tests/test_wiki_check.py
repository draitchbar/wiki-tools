"""wiki-check.sh: a freshly initialised wiki passes; each planted fault
fails (formerly the wiki-check section of run-tests.sh). The good wiki is
built once; each fault gets its own copy."""

import datetime
import os
import re
import shutil

import pytest

from conftest import PLUGIN, SCRIPTS, copytree, git, posix, write


def text(r):
    return r.merged.decode("utf-8", errors="surrogateescape")


def _rules(out, lst):
    """The quoted rules in sources.sh settings' "<lst>": [ ... ] block."""
    m = re.search(r'"%s": \[\n(.*?)\n\s*\]' % lst, out, re.S)
    return re.findall(r'"[^"]+"', m.group(1)) if m else []


@pytest.fixture(scope="module")
def good(tmp_path_factory, cli):
    t = tmp_path_factory.mktemp("wc")
    w = t / "good"
    git(t, "init", "-q", "good")
    write(w / "CLAUDE.md", "# Test wiki\n\n## Purpose\n\nTesting.\n")
    write(w / ".gitignore", ".obsidian/\n.claude/*\n!.claude/settings.json\n!.claude/sources/\n")
    write(w / "raw/sync-log.md", "# Sync Log\n\nlast_checked_raw: never\nlast_checked_gmail: never\nlast_checked_scans: never\n")
    write(w / ".claude/sources/instances/gmail.md", "---\nkey: gmail\ntype: gmail\nlabels: Test\nstate:\n  - last_checked\n---\n")
    write(w / ".claude/sources/instances/scans.md",
          "---\nkey: scans\ntype: local-folder\nroots:\n  - /x/scans\nstate:\n  - last_checked\n---\n")
    write(w / "wiki/index.md", "# Index\n\n## Notes\n\n| Page | Summary |\n|---|---|\n")
    write(w / "wiki/log.md", "# Log\n\n## 2026-10-16 | init | Wiki created\n")
    write(w / "templates/entity.md", "---\ntitle: Name\ntype: entity\nsources: []\nrelated: []\n"
          "created: YYYY-MM-DD\nupdated: YYYY-MM-DD\n---\n")
    write(w / "outputs/.gitkeep", "")
    write(w / "wiki/notes/.gitkeep", "")
    # Template plus the rules of the two source types, in its allow and deny lists.
    rules = text(cli("sources", "settings", cwd=w))
    al, dn = ",".join(_rules(rules, "allow")), ",".join(_rules(rules, "deny"))
    tpl = (PLUGIN / "templates/project-settings.json").read_text()
    tpl = tpl.replace('"allow": [', '"allow": [' + (al + "," if al else ""), 1)
    tpl = tpl.replace('"deny": [', '"deny": [' + (dn + "," if dn else ""), 1)
    write(w / ".claude/settings.json", tpl)
    git(w, "add", "-A")
    git(w, "commit", "-qm", "init")
    return t, w


@pytest.fixture
def mk(good, tmp_path):
    """A fresh copy of the good wiki (named f<n> as the old fixtures were)."""
    def _mk(name):
        return copytree(good[1], tmp_path / name)
    return _mk


def wc(cli, w, env=None):
    return cli("wiki-check", cwd=w, env=env)


@pytest.mark.checks("wiki-check/good-wiki-passes", "wiki-check/good-summary", "wiki-check/python-found",
                    "wiki-check/no-import")
def test_good(good, cli):
    r = wc(cli, good[1])
    out = text(r)
    assert r.rc == 0, out
    assert "Failures: 0." in out
    assert "PASS the guard hooks and the source scripts find Python 3." in out
    assert "PASS CLAUDE.md has no schema imports" in out
    assert "outside the wiki layout" not in out


@pytest.mark.checks("wiki-check/python-cached", "wiki-check/python-not-cached")
def test_python_cache(good, cli, tmp_path):
    write(tmp_path / "cfg/plugins/data/wiki-wiki-tools/python", "/opt/py/python3\n")
    assert "INFO the guard hooks have cached `/opt/py/python3`" in text(
        wc(cli, good[1], {"CLAUDE_CONFIG_DIR": posix(tmp_path / "cfg")}))
    assert "INFO no interpreter cached yet" in text(wc(cli, good[1], {"CLAUDE_CONFIG_DIR": posix(tmp_path / "none")}))


@pytest.mark.checks("wiki-check/python-missing")
def test_python_missing(good, run, tmp_path):
    """Without Python the launcher's message is the report (step 4)."""
    for c in ("python", "python3", "py"):
        write(tmp_path / "bin" / c, "#!/bin/sh\nexit 1\n").chmod(0o755)
    r = run(["bash", posix(SCRIPTS / "wiki-check.sh")], cwd=good[1], merged=True,
            env={"CLAUDE_PLUGIN_DATA": None, "CLAUDE_CONFIG_DIR": posix(tmp_path / "cfg"),
                 "PATH": str(tmp_path / "bin") + os.pathsep + os.environ.get("PATH", "")})
    assert r.rc == 1
    assert r.merged.startswith(b"wiki-check: no Python 3.9 or later found (tried python, python3, py -3). Install it")


def _append(rel, data):
    return lambda w: write(w / rel, (w / rel).read_bytes() + data.encode())


def _edit(rel, fn):
    return lambda w: write(w / rel, fn((w / rel).read_text()))


def _drop_line(rel, needle):
    return _edit(rel, lambda s: "".join(ln for ln in s.splitlines(True) if needle not in ln))


def _untrack(rel):
    return lambda w: git(w, "rm", "-q", "--cached", rel)


def _code_rules(w, cli=None):
    write(w / ".claude/sources/instances/code.md", "---\nkey: code\ntype: codebase\nroots:\n  - /x/code\n---\n")


SETTINGS = ".claude/settings.json"
FAULTS = [  # name, change, text
    ("old-import", _append("CLAUDE.md", "@~/src/wiki-tools/schema/wiki-layout.md\n"),
     "FAIL CLAUDE.md still imports the schema by path: @~/src/wiki-tools/schema/wiki-layout.md"),
    ("bad-sync-value", _append("raw/sync-log.md", "last_checked_web: soon\n"), "FAIL `last_checked_web: soon` in raw/sync-log.md"),
    ("missing-permission", _drop_line(SETTINGS, "Bash(git push *)"),
     'FAIL permission rules missing from .claude/settings.json: "Bash(git push *)"'),
    ("plugin-disabled", _edit(SETTINGS, lambda s: s.replace('"wiki@wiki-tools": true', '"wiki@wiki-tools": false')),
     "FAIL plugin `wiki@wiki-tools` is not enabled"),
    ("settings-uncommitted", _untrack(SETTINGS), "FAIL `.claude/settings.json` isn't committed"),
    ("roots-relative", _edit(".claude/sources/instances/scans.md", lambda s: s.replace("  - /x/scans", "  - relative/path")),
     "root 'relative/path' isn't an absolute path"),
    ("no-templates", lambda w: shutil.rmtree(w / "templates"),
     "FAIL folder `templates/` is missing"),
    ("uncommitted-setup", _append("CLAUDE.md", "extra\n"), "FAIL uncommitted setup files: CLAUDE.md"),
    ("lint-error", lambda w: write(w / "wiki/notes/x.md", "---\ntitle: X\ntype: entity\nsources: []\n"
                                   "created: 2026-10-16\nupdated: 2026-10-16\n---\nSee [[nowhere]].\n"),
     "FAIL lint finds 1 structural error(s)"),
    ("instance-uncommitted", _untrack(".claude/sources/instances/scans.md"),
     "FAIL `.claude/sources/instances/scans.md` isn't committed"),
    ("instance-no-sync-line", _drop_line("raw/sync-log.md", "last_checked_scans"),
     "FAIL source `scans` has no `last_checked_scans` line"),
    ("source-rule-missing", _edit(SETTINGS, lambda s: s.replace('"mcp__claude_ai_Gmail__send_message",', "", 1)),
     'FAIL source permission rules missing from .claude/settings.json: "mcp__claude_ai_Gmail__send_message"'),
    ("settings-not-json", _edit(SETTINGS, lambda s: s.replace('"allow": [', '"allow": [,', 1)),
     'FAIL `.claude/settings.json` is not valid JSON: unexpected ","'),
    ("gitignore-sources", _drop_line(".gitignore", "!.claude/sources"), "FAIL `.gitignore` lacks `!.claude/sources/`"),
    ("instance-invalid", lambda w: write(w / ".claude/sources/instances/bad.md", "---\nkey: bad\ntype: nosuch\n---\n"),
     "FAIL source `bad` doesn't validate: unknown source type 'nosuch'"),
    ("instance-dirty", _append(".claude/sources/instances/scans.md", "\nNotes.\n"),
     "FAIL `.claude/sources/instances/scans.md` has uncommitted changes"),
    ("settings-dirty", _edit(SETTINGS, lambda s: s.replace('"wiki@wiki-tools": true', '"wiki@wiki-tools": true ')),
     "FAIL `.claude/settings.json` has uncommitted changes"),
    ("no-raw-line", _drop_line("raw/sync-log.md", "last_checked_raw"), "FAIL raw/sync-log.md has no `last_checked_raw` line"),
]


@pytest.mark.parametrize("change,want", [pytest.param(c, t, id="wiki-check/" + n) for n, c, t in FAULTS])
def test_fault(change, want, mk, cli):
    w = mk("f")
    change(w)
    out = text(wc(cli, w))
    assert want in out, out


@pytest.mark.checks("wiki-check/fault-exits-1")
def test_fault_exit(mk, cli):
    w = mk("f1")
    FAULTS[0][1](w)
    assert wc(cli, w).rc == 1


@pytest.mark.checks("wiki-check/broad-cache-rules")
def test_broad_cache_rules(mk, cli):
    """Broader settings rules count."""
    w = mk("f21")
    _code_rules(w)
    dn = _rules(text(cli("sources", "settings", "codebase", cwd=w)), "deny")
    s = (w / SETTINGS).read_text()
    s = s.replace('"allow": [', '"allow": ["Read(~/.cache/wiki-sources/**)", "Edit(~/.cache/wiki-sources/f21/**)", '
                  '"Bash(bash */sources/codebase/git.sh *)", "Bash(bash */sources/codebase/gh.sh *)",', 1)
    s = s.replace('"deny": [', '"deny": [' + ",".join(dn) + ",", 1)
    write(w / SETTINGS, s)
    git(w, "add", "-A")
    git(w, "commit", "-qm", "code")
    assert "PASS all permission rules of the sources' types are present" in text(wc(cli, w))


@pytest.mark.checks("wiki-check/log-history-not-failure", "wiki-check/log-history-info",
                    "wiki-check/log-uncommitted-counts")
def test_log_history(mk, cli):
    """A past commit that rewrote wiki/log.md isn't a setup failure, only an
    INFO line with its age-out date; an uncommitted rewrite still counts."""
    w = mk("f22")
    log = w / "wiki/log.md"
    when = datetime.date.today() - datetime.timedelta(days=5)
    write(log, log.read_text().replace("Wiki created", "Wiki made"))
    git(w, "commit", "-qam", "Rewrite log", date=when.isoformat() + "T12:00:00")
    r = wc(cli, w)
    out = text(r)
    assert r.rc == 0, out
    assert "PASS lint finds no structural errors" in out
    assert ("INFO lint flags 1 past commit(s) that rewrote `wiki/log.md`; not a setup failure, "
            "restoring the lines won't clear it, the last ages out on %s"
            % (when + datetime.timedelta(days=30)).isoformat()) in out, out
    write(log, log.read_text().replace("Wiki made", "Wiki made again"))
    out = text(wc(cli, w))
    assert "FAIL lint finds 1 structural error(s). Fix: run /wiki:lint" in out, out
    assert "INFO lint flags 1 past commit(s)" in out


@pytest.mark.parametrize("deny", ["Edit(~/.cache/wiki-sources/**)", "Edit(~/.cache/wiki-sources/f23/code/**)"],
                         ids=["wiki-check/deny-broad", "wiki-check/deny-exact"])
def test_deny_blocks(mk, cli, deny):
    """A deny rule covering a needed allow rule fails: deny wins."""
    w = mk("f23")
    _code_rules(w)
    rules = text(cli("sources", "settings", "codebase", "--key", "code", cwd=w))
    s = (w / SETTINGS).read_text()
    s = s.replace('"allow": [', '"allow": [' + ",".join(_rules(rules, "allow")) + ",", 1)
    s = s.replace('"deny": [', '"deny": ["%s",' % deny + ",".join(_rules(rules, "deny")) + ",", 1)
    write(w / SETTINGS, s)
    git(w, "add", "-A")
    git(w, "commit", "-qm", "deny")
    r = wc(cli, w)
    assert "PASS all permission rules of the sources' types are present" in text(r)
    assert r.rc == 1
    assert ('FAIL source permission rules blocked by a deny rule in .claude/settings.json: '
            '"Edit(~/.cache/wiki-sources/f23/code/**)" (deny "%s")' % deny) in text(r)


@pytest.mark.checks("wiki-check/stray-markdown", "wiki-check/stray-markdown-not-failure")
def test_stray_markdown(mk, cli):
    """Tracked Markdown outside the layout is listed as INFO, not a failure;
    the layout's folders, work/, dot folders and dot files, untracked files
    and the root's CLAUDE.md and README.md aren't."""
    w = mk("f24")
    for rel in ("draft.md", "notes/mail.MD", "notes/CLAUDE.md", "README.md", "work/deck.md", "raw/note.md",
                "outputs/r.md", ".hidden.md", "notes/.drafts/x.md", "notes/a.txt"):
        write(w / rel, "Draft.\n")
    git(w, "add", "-A")
    git(w, "commit", "-qm", "more")
    write(w / "untracked.md", "x\n")
    r = wc(cli, w)
    out = text(r)
    assert r.rc == 0, out
    assert ("INFO 3 Markdown file(s) outside the wiki layout: `draft.md` `notes/CLAUDE.md` `notes/mail.MD`. "
            "Move each to `work/` (drafts) or `raw/` (source material), or delete it") in out, out
    assert "Failures: 0." in out


@pytest.mark.checks("wiki-check/outside-git")
def test_outside_git(cli, tmp_path):
    (tmp_path / "plain").mkdir()
    r = wc(cli, tmp_path / "plain", {"GIT_CEILING_DIRECTORIES": posix(tmp_path)})
    assert r.rc == 1
    assert text(r) == "wiki-check: not inside a git repo; run from a wiki.\n"


@pytest.mark.checks("wiki-check/outside-git-plugin-enabled", "wiki-check/outside-git-plugin-disabled")
def test_outside_git_not_initialised(cli, tmp_path):
    """No repo yet, but the folder's settings enable the plugin: point to /wiki:init."""
    w = tmp_path / "new"
    env = {"GIT_CEILING_DIRECTORIES": posix(tmp_path)}
    write(w / SETTINGS, '{"enabledPlugins": {"wiki@wiki-tools": true}}\n')
    r = wc(cli, w, env)
    assert r.rc == 1
    assert text(r) == ("wiki-check: not inside a git repo, but `.claude/settings.json` here enables the wiki "
                       "plugin: this wiki isn't initialised yet. Run (or finish) `/wiki:init`.\n")
    write(w / SETTINGS, '{"enabledPlugins": {"wiki@wiki-tools": false}}\n')
    assert text(wc(cli, w, env)) == "wiki-check: not inside a git repo; run from a wiki.\n"
