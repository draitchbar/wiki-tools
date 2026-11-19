"""Reader bindings (docs/adr.md, 13): the `operations` of a tool-neutral
contract, an instance's `reader` and `reader_deny` lists, their
validation, and the settings rules check-settings looks for, which may sit
in the user's settings. The guard's side is in test_guard.py (fixtures
*-mcp-reader-*, test_reader_*)."""

import pytest

import contract
import sourcelib
from conftest import PLUGIN, TESTS, copytree, git, home_env, posix, write

JIRA = posix(PLUGIN / "sources" / "jira" / "SOURCE.md")
GMAIL = posix(PLUGIN / "sources" / "gmail" / "SOURCE.md")
T = "mcp__claude_ai_Atlassian_MCP__"
OK = ["search: %ssearchJiraIssuesUsingJql" % T, "read issue: %sgetJiraIssue" % T,
      "list comments: %slistJiraIssueComments" % T]


@pytest.mark.parametrize("item,want", [
    ("search: %sx" % T, ("search", T + "x", "", "")),
    ("find project: %sexecuteRead name=listJiraProjects" % T, ("find project", T + "executeRead", "name", "listJiraProjects")),
    ("read page: Bash(pwsh -NoProfile -File ~/.claude/skills/r/Read.ps1 page *)",
     ("read page", "Bash(pwsh -NoProfile -File ~/.claude/skills/r/Read.ps1 page *)", "", "")),
    ("status: PowerShell(reader status)", ("status", "PowerShell(reader status)", "", "")),
    ("search %sx" % T, None),                       # no ": "
    ("Search: %sx" % T, None),                      # operation in lower case
    ("search: getJiraIssue", None),                 # not an MCP tool or a shell rule
    ("search: %sx name=" % T, None),                # empty limit value
    ("search: %sx name=a b" % T, None),             # one limit only
    ("search: %sx name=a;b" % T, None),             # a limit value is a plain name
    ("search: Bash()", None),
])
def test_reader_item(item, want):
    assert contract.reader_item(item) == want


@pytest.mark.parametrize("item,want", [
    ("search (required)", ("search", "required")),
    ("list remote links (recommended)", ("list remote links", "recommended")),
    ("search", None), ("search (maybe)", None), ("Search (required)", None),
])
def test_operation(item, want):
    assert contract.operation(item) == want


def _inst(tmp_path, typ, reader=(), deny=()):
    lines = ["---", "key: x", "type: " + typ]
    if reader:
        lines += ["reader:"] + ["  - " + r for r in reader]
    if deny:
        lines += ["reader_deny:"] + ["  - " + r for r in deny]
    return posix(write(tmp_path / "x.md", "\n".join(lines + ["---", ""])))


@pytest.mark.parametrize("reader,deny,want", [
    pytest.param((), (), [], id="unbound"),
    pytest.param(OK, ("%sexecuteWrite" % T,), [], id="bound"),
    pytest.param(OK + ["find project: %sexecuteRead name=listJiraProjects" % T,
                       "list remote links: %sexecuteRead name=listJiraIssueRemoteIssueLinks" % T], (), [],
                 id="dispatcher"),
    pytest.param(OK + ["fetch: %sx" % T], (), ["isn't an operation of the contract"], id="unknown-op"),
    pytest.param(OK + ["search: %sy" % T], (), ["binds 'search' twice"], id="twice"),
    pytest.param(OK[:2], (), ["doesn't bind 'list comments', a required operation"], id="required"),
    pytest.param(OK + ["find project: %sexecuteRead name=listJiraProjects" % T, "count: %sexecuteRead" % T], (),
                 ["both with and without a limit"], id="limit-and-free"),
    pytest.param(OK + ["count: oops"], (), ["must be '<operation>: <tool or rule>'"], id="bad-item"),
    pytest.param(OK, ("executeWrite",), ["reader_deny item 'executeWrite' must be"], id="bad-deny"),
    pytest.param(OK, ("%sgetJiraIssue" % T,), ["denies %sgetJiraIssue, which reader binds" % T], id="deny-bound"),
])
def test_reader_errors(reader, deny, want, tmp_path):
    got = sourcelib.reader_errors(_inst(tmp_path, "jira", reader, deny), JIRA)
    assert len(got) == len(want) and all(w in g for w, g in zip(want, got)), got


def test_reader_only_tools(tmp_path):
    f = _inst(tmp_path, "gmail", OK)
    assert sourcelib.reader_errors(f, GMAIL) == [
        "only an access: tools instance has a reader binding ('reader', 'reader_deny')"]


def test_reader_rules(tmp_path):
    f = _inst(tmp_path, "jira", OK + ["find project: %sexecuteRead name=a" % T, "count: %sexecuteRead name=b" % T],
              ("%sexecuteWrite" % T,))
    assert sourcelib.reader_rules(f) == (
        ["allow\t%s\t%s" % (T + t, T + t) for t in
         ("searchJiraIssuesUsingJql", "getJiraIssue", "listJiraIssueComments", "executeRead", "executeRead")]
        + ["deny\t%sexecuteWrite\t%sexecuteWrite" % (T, T)])


# check-settings on the test wiki (tracker is bound): reader rules may be
# met in the user's settings, the contracts' rules only in the wiki's.

@pytest.fixture
def rw(tmp_path, cli):
    w = copytree(TESTS / "guard-wiki", tmp_path / "rw")
    git(w, "init", "-q")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    # A real folder, so HOME too: with --e2e on Windows, Git Bash would
    # otherwise set HOME to the account's own profile (see home_env).
    env = dict(home_env(posix(home)), HOME=posix(home))
    out = cli("sources", "settings", cwd=w, env=env).out.decode()
    sjson = out[out.index("{"):out.index("\n}\n") + 3]
    return w, home, env, sjson


def _check(cli, w, env):
    r = cli("sources", "check-settings", cwd=w, env=env)
    return r.rc, r.out.decode("utf-8", errors="surrogateescape")


def test_check_settings_reader_ok(rw, cli):
    w, home, env, sjson = rw
    write(w / ".claude/settings.json", sjson)
    rc, o = _check(cli, w, env)
    assert rc == 0 and "missing: none" in o and "count in your user settings too" in o, o


def test_check_settings_reader_missing(rw, cli):
    w, home, env, sjson = rw
    write(w / ".claude/settings.json", sjson.replace('      "%sgetJiraIssue",\n' % T, ""))
    rc, o = _check(cli, w, env)
    assert rc == 1 and "  allow: %sgetJiraIssue" % T in o, o


def test_check_settings_reader_in_user(rw, cli):
    w, home, env, sjson = rw
    write(w / ".claude/settings.json", sjson.replace('      "%sgetJiraIssue",\n' % T, "")
          .replace('      "%sexecuteWrite",\n' % T, ""))
    write(home / ".claude/settings.json", '{"permissions": {"allow": ["%sgetJiraIssue"], "deny": ["%sexecuteWrite"]}}\n'
          % (T, T))
    rc, o = _check(cli, w, env)
    assert rc == 0 and "missing: none" in o and "(~/.claude/settings.json, 2 permission rules)" in o, o


def test_check_settings_reader_denied_in_user(rw, cli):
    w, home, env, sjson = rw
    write(w / ".claude/settings.json", sjson)
    write(home / ".claude/settings.json", '{"permissions": {"deny": ["%sgetJiraIssue"]}}\n' % T)
    rc, o = _check(cli, w, env)
    assert rc == 1 and "allow: %sgetJiraIssue (deny: %sgetJiraIssue)" % (T, T) in o, o


def test_check_settings_cache_not_from_user(rw, cli):
    """A contract's cache rule in the user's settings doesn't count: those
    rules are per wiki and instance."""
    w, home, env, sjson = rw
    rule = '"Edit(~/.cache/wiki-sources/rw/code/**)"'
    assert rule in sjson
    write(w / ".claude/settings.json", sjson.replace("      %s,\n" % rule, "").replace("      %s\n" % rule, ""))
    write(home / ".claude/settings.json", '{"permissions": {"allow": [%s]}}\n' % rule)
    rc, o = _check(cli, w, env)
    assert rc == 1 and "allow: Edit(~/.cache/wiki-sources/rw/code/**)" in o, o
