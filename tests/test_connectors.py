"""Connector names per surface (docs/adr.md, 25): the pair table
plugins/wiki/sources/connectors.md, each binding rule under its cloud name
in the settings rules (a tool bound with a limit denied there), the
refusal of a binding that names one connector under both names, a broken
table, and `sources.sh show`'s cloud names. check-settings' cloud-name
lines on the test wiki are in test_reader_binding.py."""

import pytest

import guard
import sources
import sourcelib
import wiki_check
from conftest import (GMAIL_DENY, GMAIL_OPS, GMAIL_T, PLUGIN, SCRIPTS_P, TESTS, call_main, copytree, git, home_env,
                      posix, reset_modules, write)

P = posix(PLUGIN)
GC = "mcp__Gmail__"
AT, AC = "mcp__claude_ai_Atlassian_MCP__", "mcp__Atlassian_MCP__"
GD = "mcp__claude_ai_Google_Drive__"
GMAIL = posix(PLUGIN / "sources/gmail/SOURCE.md")
JIRA_OK = ["search: %ssearchJiraIssuesUsingJql", "read issue: %sgetJiraIssue", "list comments: %slistJiraIssueComments"]
BOTH = "name one connector under both its local name"
SHELL = "Bash(bash ~/.claude/skills/example-drive/drive.sh *)"


@pytest.fixture(autouse=True)
def _fresh():
    reset_modules()
    yield
    reset_modules()


def pairs():
    return sourcelib.connector_pairs(P)


def jira(key, t, extra=(), deny=()):
    """A jira instance file's text, its required operations bound with prefix t."""
    reader = [r % t for r in JIRA_OK] + list(extra)
    return ("---\nkey: %s\ntype: jira\nsite: example.atlassian.net\nscopes:\n  - s | project = ABC\nstate:\n"
            "  - last_checked\nreader:\n%s" % (key, "".join("  - %s\n" % r for r in reader))
            + ("reader_deny:\n" + "".join("  - %s\n" % r for r in deny) if deny else "") + "---\n")


def gmail(prefix, key="gmail"):
    """A gmail instance bound with one prefix (GMAIL_T, or a cloud one)."""
    return ("---\nkey: %s\ntype: gmail\nlabels: Receipts\nstate:\n  - last_checked\nreader:\n" % key
            + "".join("  - %s: %s%s\n" % (o, prefix, t) for o, t in GMAIL_OPS.items())
            + "reader_deny:\n" + "".join("  - %s%s\n" % (prefix, t) for t in GMAIL_DENY) + "---\n")


def wiki(tmp_path, name, files):
    """A wiki folder with these instance files ({key: text}), no git."""
    w = tmp_path / name
    for k, text in files.items():
        write(w / ".claude/sources/instances" / (k + ".md"), text)
    return posix(w)


def gw(tmp_path, name="gw"):
    """A git copy of the test wiki."""
    w = copytree(TESTS / "guard-wiki", tmp_path / name)
    git(w, "init", "-q")
    return w


def empty_home(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    return dict(home_env(posix(home)), HOME=posix(home))


# --- the table ---------------------------------------------------------------

def test_shipped_table():
    assert list(pairs().items()) == [("claude_ai_Gmail", "Gmail"), ("claude_ai_Microsoft_365", "Microsoft_365"),
                                     ("claude_ai_Atlassian_MCP", "Atlassian_MCP")]


def _table(items):
    return "---\nservers:\n" + "".join("  - %s\n" % i for i in items) + "---\n"


@pytest.mark.parametrize("text,want", [
    pytest.param(_table(["local=a"]), "servers item 'local=a' must be 'local=<server> cloud=<server>'", id="bad-item"),
    pytest.param(_table(["local=a__b cloud=c"]), "servers item 'local=a__b cloud=c' must be", id="double-underscore"),
    pytest.param(_table(["local=_a cloud=c"]), "servers item 'local=_a cloud=c' must be", id="leading-underscore"),
    pytest.param(_table(["local=a cloud=b", "local=a cloud=c"]), "server 'a' is listed twice", id="dup-local"),
    pytest.param(_table(["local=a cloud=c", "local=b cloud=c"]), "server 'c' is listed twice", id="dup-cloud"),
    pytest.param(_table(["local=a cloud=b", "local=b cloud=c"]), "server 'b' is listed twice", id="local-and-cloud"),
    pytest.param(None, "missing or has no frontmatter", id="missing"),
    pytest.param("servers:\n  - local=a cloud=b\n", "missing or has no frontmatter", id="no-frontmatter"),
    pytest.param("---\ntitle: x\n---\n", "no 'servers' list", id="no-key"),
    pytest.param("---\nserver:\n  - local=a cloud=b\n---\n", "no 'servers' list", id="misspelled-key"),
    pytest.param("---\nservers:\n---\n", "the 'servers' list is empty", id="empty"),
])
def test_table_errors(text, want, tmp_path):
    p = tmp_path / "plugin"
    (p / "sources").mkdir(parents=True)
    if text is not None:
        write(p / "sources/connectors.md", text)
    with pytest.raises(sourcelib.ConnectorsError) as e:
        sourcelib.connector_pairs(posix(p))
    # The message starts with the table's path as given.
    assert str(e.value).startswith("%s/sources/connectors.md: %s" % (posix(p), want)), str(e.value)


@pytest.mark.parametrize("rule,want", [
    (GMAIL_T + "search_threads", GC + "search_threads"),
    ("mcp__claude_ai_Gmail", "mcp__Gmail"),
    ("mcp__claude_ai_Gmail__*", "mcp__Gmail__*"),
    (AT + "executeRead", AC + "executeRead"),
    ("mcp__claude_ai_GmailX__a", None),           # never a prefix match
    ("mcp__claude_ai_Gmail_x__a", None),
    (GC + "a", None),                             # no cloud -> local
    (GD + "a", None),                             # not paired
    ("Bash(x *)", None),
])
def test_cloud_name(rule, want):
    assert sourcelib.cloud_name(rule, pairs()) == want


# --- the settings rules --------------------------------------------------------

def test_reader_rules_both_names():
    f = posix(TESTS / "guard-wiki/.claude/sources/instances/gmail.md")
    want = []
    for t in GMAIL_OPS.values():
        want += ["allow\t%s%s\t%s%s" % (GMAIL_T, t, GMAIL_T, t), "allow\t%s%s\t%s%s" % (GC, t, GC, t)]
    for t in GMAIL_DENY:
        want += ["deny\t%s%s\t%s%s" % (GMAIL_T, t, GMAIL_T, t), "deny\t%s%s\t%s%s" % (GC, t, GC, t)]
    assert sourcelib.reader_rules(f, pairs()) == want


def test_limited_cloud_denied(tmp_path):
    tracker = (TESTS / "guard-wiki/.claude/sources/instances/tracker.md").read_text(encoding="utf-8")
    got = sourcelib.reader_rules(posix(TESTS / "guard-wiki/.claude/sources/instances/tracker.md"), pairs())
    assert "allow\t%sexecuteRead\t%sexecuteRead" % (AT, AT) in got
    assert "deny\t%sexecuteRead\t%sexecuteRead" % (AC, AC) in got
    assert "allow\t%sexecuteRead\t%sexecuteRead" % (AC, AC) not in got
    assert "allow\t%sgetJiraIssue\t%sgetJiraIssue" % (AC, AC) in got
    # A second instance binding the dispatcher free: free wiki-wide, as the
    # guard treats it, so its cloud name is allowed, never denied.
    free = jira("t2", AT, ["count: %sexecuteRead" % AT])
    for name, t2 in (("valid", free), ("invalid", free.replace("  - list comments: %slistJiraIssueComments\n" % AT, ""))):
        w = wiki(tmp_path, name, {"tracker": tracker, "t2": t2})
        ok, _ = sourcelib.quietly(sourcelib.validate_instance, w, "t2", P)
        assert ok == (name == "valid")
        need = sourcelib.needed_rules(w, P)
        assert "allow\t%sexecuteRead\t%sexecuteRead" % (AC, AC) in need, need
        assert "deny\t%sexecuteRead\t%sexecuteRead" % (AC, AC) not in need, need


def test_server_only_rule(tmp_path):
    f = posix(write(tmp_path / "x.md", "---\nkey: x\ntype: gmail\nreader_deny:\n  - mcp__claude_ai_Gmail\n---\n"))
    assert sourcelib.reader_rules(f, pairs()) == ["deny\tmcp__claude_ai_Gmail\tmcp__claude_ai_Gmail",
                                                 "deny\tmcp__Gmail\tmcp__Gmail"]


def test_unpaired_unchanged(tmp_path):
    f = posix(write(tmp_path / "d.md", "---\nkey: d\ntype: google-drive\nreader:\n  - get item: %sget_file_metadata\n"
                    "reader_deny:\n  - %strash_file\n---\n" % (GD, GD)))
    assert sourcelib.reader_rules(f, pairs()) == sourcelib.reader_rules(f) == [
        "allow\t%sget_file_metadata\t%sget_file_metadata" % (GD, GD), "deny\t%strash_file\t%strash_file" % (GD, GD)]


def test_cloud_binding_literal(tmp_path):
    """A binding in cloud names (the old advice for cloud wikis) validates and
    is taken as it is: one line per rule, all counted only from the wiki's
    settings."""
    w = wiki(tmp_path, "cw", {"gmail": gmail(GC)})
    ok, errs = sourcelib.quietly(sourcelib.validate_instance, w, "gmail", P)
    assert ok, errs
    reader = set()
    need = sourcelib.needed_rules(w, P, reader)
    assert need == (["allow\t%s%s\t%s%s" % (GC, t, GC, t) for t in dict.fromkeys(GMAIL_OPS.values())]
                    + ["deny\t%s%s\t%s%s" % (GC, t, GC, t) for t in GMAIL_DENY])
    assert reader == set()


@pytest.mark.parametrize("reader,deny", [
    pytest.param(["search threads: %ssearch_threads" % GMAIL_T, "read thread: %sget_thread" % GMAIL_T],
                 [GC + "send_message"], id="reader-local-deny-cloud"),
    pytest.param(["search threads: %ssearch_threads" % GMAIL_T, "read thread: %sget_thread" % GC], [],
                 id="reader-local-and-cloud"),
    pytest.param(["search threads: %ssearch_threads" % GC, "read thread: %sget_thread" % GC],
                 [GMAIL_T + "send_message"], id="reader-cloud-deny-local"),
    pytest.param(["search threads: %ssearch_threads" % GC, "read thread: %sget_thread" % GC], [],
                 id="reader-cloud-and-local"),
])
def test_both_forms_refused(reader, deny, tmp_path):
    reader = reader + ["list labels: %slist_labels" % GMAIL_T]
    f = posix(write(tmp_path / "x.md", "---\nkey: x\ntype: gmail\nreader:\n" + "".join("  - %s\n" % r for r in reader)
                    + ("reader_deny:\n" + "".join("  - %s\n" % r for r in deny) if deny else "") + "---\n"))
    got = sourcelib.reader_errors(f, GMAIL, pairs())
    assert got == ["reader and reader_deny %s (mcp__claude_ai_Gmail__…) and its cloud name (mcp__Gmail__…); "
                   "bind the local names only: sources.sh settings adds the cloud names "
                   "(plugins/wiki/sources/connectors.md)" % BOTH], got
    assert sourcelib.reader_errors(f, GMAIL) == []  # without the table: not checked


@pytest.mark.checks("connectors/install-refuses-both-forms")
def test_install_refuses_both_forms(tmp_path, run):
    git(tmp_path, "init", "-q", "iw")
    w = tmp_path / "iw"
    write(w / "CLAUDE.md", "# W\n")
    text = gmail(GMAIL_T).replace("  - %ssend_message\n" % GMAIL_T, "  - %ssend_message\n" % GC)
    r = run(["bash", SCRIPTS_P + "/install-source-file.sh", "instances/gmail.md"], cwd=w, input=text.encode(),
            merged=True, env={"CLAUDECODE": None, "WIKI_INSTALL_ANSWER": "y", "HOME": posix(tmp_path / "home")})
    o = r.merged.decode("utf-8", "surrogateescape")
    assert r.rc == 1 and BOTH in o and not (w / ".claude/sources/instances/gmail.md").exists(), o


def test_mixed_forms_across_wiki(tmp_path, cli):
    """One instance in local names, another in cloud names: refused, since a
    cloud name's allow or deny would depend on which instance wins."""
    w = gw(tmp_path)
    write(w / ".claude/sources/instances/b.md", jira("b", AC))
    write(w / ".claude/settings.json", "{}\n")
    with pytest.raises(sourcelib.BindingMixError) as e:
        sourcelib.needed_rules(posix(w), P)
    msg = ("instances tracker, b %s (mcp__claude_ai_Atlassian_MCP__…) and its cloud name (mcp__Atlassian_MCP__…); "
           "bind every instance with the local names: sources.sh settings adds the cloud names "
           "(plugins/wiki/sources/connectors.md)" % BOTH)
    assert str(e.value) == msg and e.value.key == "b"
    env = empty_home(tmp_path)
    for args in (["settings"], ["settings", "jira", "--key", "tracker"], ["check-settings"]):
        r = cli("sources", *args, cwd=w, env=env)
        assert r.rc == 1 and r.err.decode() == "sources: %s\n" % msg, (args, r)
    o = cli("wiki-check", cwd=w, env=env).merged.decode("utf-8", "surrogateescape")
    assert "- FAIL %s. Fix: bind the instance again locally with /wiki:bind-reader b\n" % msg in o, o
    assert "source `tracker` (type jira) is valid" in o, o  # the later checks still run


# --- a broken table --------------------------------------------------------------

@pytest.fixture
def broken(tmp_path, run, request, pydata):
    """A copy of the plugin whose connectors.md doesn't parse, and a runner
    for its scripts (in-process with --plugin, or its launchers)."""
    p = copytree(PLUGIN, tmp_path / "plugin")
    write(p / "sources/connectors.md", "---\nservers:\n  - local=claude_ai_Gmail\n---\n")
    e2e = request.config.getoption("--e2e")
    mods = {"sources": sources, "wiki-check": wiki_check}

    def _run(name, *args, cwd, env=None):
        if e2e:
            return run(["bash", posix(p / "scripts" / (name + ".sh"))] + list(args), cwd=cwd, env=env)
        return call_main(mods[name].main, ["--plugin", posix(p)] + list(args), cwd=cwd,
                         env=dict(env or {}, CLAUDE_PLUGIN_DATA=pydata))
    return p, _run


def test_broken_table(tmp_path, broken):
    p, prun = broken
    w = gw(tmp_path)
    write(w / ".claude/settings.json", "{}\n")
    env = empty_home(tmp_path)
    bad = "%s/sources/connectors.md: servers item 'local=claude_ai_Gmail' must be" % posix(p)

    def o(r):
        return r.merged.decode("utf-8", "surrogateescape")
    for args in (["settings"], ["check-settings"]):
        r = prun("sources", *args, cwd=w, env=env)
        assert r.rc == 3 and "sources: internal error: ConnectorsError: " + bad in o(r), (args, o(r))
    r = prun("sources", "list", cwd=w, env=env)
    assert r.rc == 0 and "- gmail: type gmail (standard), INVALID (run: sources.sh show gmail)" in o(r), o(r)
    assert "- scans: type local-folder (standard), valid" in o(r), o(r)
    r = prun("sources", "show", "gmail", cwd=w, env=env)
    assert r.rc == 1 and "gmail.md: can't check its connector names: " + bad in o(r), o(r)
    r = prun("sources", "due", cwd=w, env=env)
    assert r.rc == 0 and "- gmail: invalid (sources.sh show gmail)" in o(r), o(r)
    r = prun("wiki-check", cwd=w, env=env)
    assert ("- FAIL source permission rules can't be checked: %s" % bad) in o(r), o(r)
    assert "Fix: update or reinstall the wiki plugin (plugins/wiki/sources/connectors.md)" in o(r), o(r)
    assert "source `scans` (type local-folder) is valid" in o(r), o(r)
    # A wiki whose only binding is a shell reader never reads the table.
    pw = tmp_path / "pw"
    git(tmp_path, "init", "-q", "pw")
    write(pw / ".claude/sources/instances/proton.md", "---\nkey: proton\ntype: proton-files\nroots:\n"
          "  - /my-files/Projects/alpha\nstate:\n  - last_checked\nreader:\n"
          + "".join("  - %s: %s\n" % (op, SHELL) for op in ("changed since", "list folder", "info", "size",
                                                           "download")) + "---\n")
    r = prun("sources", "settings", cwd=pw, env=env)
    assert r.rc == 0 and '"%s"' % SHELL in o(r), o(r)
    r = prun("sources", "show", "proton", cwd=pw, env=env)
    assert r.rc == 0 and "- list folder: %s; cloud: the same" % SHELL in o(r), o(r)


# --- not a source type ---------------------------------------------------------

def test_not_a_type(tmp_path, cli, guard_run):
    w = gw(tmp_path)
    r = cli("sources", "catalog", cwd=w)
    assert r.rc == 0 and "connectors" not in r.out.decode(), r
    r = cli("sources", "contract", "connectors", cwd=w)
    assert r.rc == 1 and "unknown source type 'connectors'" in r.merged.decode(), r
    assert not [f for f in guard.glob_files(P + "/sources", "SOURCE.md") if "connectors" in f]
    assert (PLUGIN / "sources/connectors.md").is_file()
    data = (TESTS / "fixtures/guard/pass-mcp-reader-direct.json").read_text(encoding="utf-8")
    assert guard_run(data, posix(w)).rc == 0


# --- sources.sh show ---------------------------------------------------------------

def test_show_cloud_names(tmp_path, cli):
    w = gw(tmp_path)
    inst = w / ".claude/sources/instances"
    g = "mcp__claude_ai_Google_Drive__"
    write(inst / "drive.md", "---\nkey: drive\ntype: google-drive\nfolders:\n  - Receipts (1AbCdEf)\nstate:\n"
          "  - last_checked\nreader:\n"
          + "".join("  - %s\n" % r for r in ("get item: %sget_file_metadata" % g, "list folder: %ssearch_files" % g,
                                             "search by name: %ssearch_files" % g,
                                             "read file: %sread_file_content" % g,
                                             "download file: %sdownload_file_content" % g))
          + "reader_deny:\n  - %strash_file\n---\n" % g)
    write(inst / "proton.md", "---\nkey: proton\ntype: proton-files\nroots:\n  - /my-files/Projects/alpha\nstate:\n"
          "  - last_checked\nreader:\n" + "".join("  - %s: %s\n" % (op, SHELL) for op in (
              "changed since", "list folder", "info", "size", "download")) + "---\n")
    head = "Reader tools and their cloud names (this session: %s; plugins/wiki/sources/connectors.md):"

    def show(k, remote):
        r = cli("sources", "show", k, cwd=w, env={"CLAUDE_CODE_REMOTE": "true"} if remote else None)
        assert r.rc == 0, r
        return r.out.decode("utf-8", "surrogateescape")
    o = show("gmail", True)
    assert head % "cloud" in o and "- search threads: %ssearch_threads; cloud: %ssearch_threads\n" % (GMAIL_T, GC) in o
    assert o.index(head % "cloud") < o.index("===== Instance file"), o
    assert head % "local" in show("gmail", False)
    o = show("tracker", False)
    assert ("- find project: %sexecuteRead name=listJiraProjects; cloud: denied (%sexecuteRead; the limit holds only "
            "under the bound name)\n" % (AT, AC)) in o, o
    assert "- read issue: %sgetJiraIssue; cloud: %sgetJiraIssue\n" % (AT, AC) in o, o
    o = show("drive", False)
    assert "- get item: %sget_file_metadata; cloud: unknown (no pair in connectors.md)\n" % g in o, o
    o = show("proton", False)
    assert "- list folder: %s; cloud: the same\n" % SHELL in o, o
    assert "Reader tools" not in show("scans", False)
