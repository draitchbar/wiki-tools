"""Connector names per surface (docs/adr.md, 17): the pair table
plugins/wiki/sources/connectors.md, each binding rule under its cloud name
in the settings rules (a tool bound with a limit denied there), the
refusal of a binding that names one connector under both names, a broken
table, and `sources.sh show`'s cloud names. check-settings' cloud-name
lines on the test wiki are in test_reader_binding.py. Every case runs
in-process in both modes; the cases in BOUNDARY, test_boundary_internal_error
and the install tests run through the launchers in both modes (docs/adr.md, 6)."""

import functools

import pytest

import sources
import sourcelib
import wiki_check
from conftest import (GMAIL_DENY, GMAIL_OPS, GMAIL_T, PLUGIN, SCRIPTS_P, TESTS, call_main, copytree, git, home_env,
                      msys, posix, rerun, reset_modules, write)

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
    pytest.param(_table(["local=a"]), "servers item 'local=a' must be 'local=<server> cloud=<server>'", id="connectors/bad-item"),
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
    # One instance alone, its limited dispatcher denied under the cloud name:
    # test_reader_binding.py's test_reader_rules.
    tracker = (TESTS / "guard-wiki/.claude/sources/instances/tracker.md").read_text(encoding="utf-8")
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
                   "(the plugin's sources/connectors.md)" % BOTH], got
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


def _mix_msg(who):
    return ("%s one connector under both its local name (mcp__claude_ai_Atlassian_MCP__…) and its cloud name "
            "(mcp__Atlassian_MCP__…); bind every instance with the local names: sources.sh settings adds the cloud "
            "names (the plugin's sources/connectors.md)" % who)


@pytest.mark.parametrize("case", ["across", "one-instance"])
def test_mixed_forms_across_wiki(case, tmp_path, cli):
    """One instance in local names, another in cloud names, or one instance
    with both: refused, since a cloud name's allow or deny would depend on
    which binding wins (one instance alone is invalid too, but its rules
    would still be printed)."""
    w = gw(tmp_path)
    inst = w / ".claude/sources/instances"
    if case == "across":
        write(inst / "b.md", jira("b", AC))
        msg, later = _mix_msg("instances tracker, b name"), "source `tracker` (type jira) is valid"
    else:
        (inst / "tracker.md").unlink()
        write(inst / "b.md", jira("b", AT, ["find project: %sexecuteRead name=x" % AT, "count: %sexecuteRead" % AC]))
        msg, later = _mix_msg("instance b names"), "source `gmail` (type gmail) is valid"
    write(w / ".claude/settings.json", "{}\n")
    with pytest.raises(sourcelib.BindingMixError) as e:
        sourcelib.needed_rules(posix(w), P)
    assert str(e.value) == msg and e.value.key == "b"
    env = empty_home(tmp_path)
    for args in (["settings"], ["settings", "jira", "--key", "b"], ["check-settings"]):
        r = cli("sources", *args, cwd=w, env=env)
        assert r.rc == 1 and r.err.decode() == "sources: %s\n" % msg, (args, r)
    # The bridge's commands: a user error (exit 1), not an internal one.
    for args in (["needed-rules", posix(w)], ["missing-rules", posix(w), posix(w / ".claude/settings.json")]):
        r = cli("sourcelib", *args, cwd=w, env=env)
        assert r.rc == 1 and r.err.decode() == "sourcelib: %s\n" % msg, (args, r)
    o = cli("wiki-check", cwd=w, env=env).merged.decode("utf-8", "surrogateescape")
    assert "- FAIL %s. Fix: bind the instance again locally with /wiki:bind-reader b\n" % msg in o, o
    assert later in o, o  # the later checks still run


@pytest.mark.checks("connectors/install-mixed-forms")
def test_install_mixed_forms(tmp_path, run):
    """An instance valid alone, in cloud names, beside one in local names:
    installed, then the settings rules can't be given; the message is the
    user's to act on, not an internal error, and the exit is 1."""
    git(tmp_path, "init", "-q", "iw")
    w = tmp_path / "iw"
    write(w / "CLAUDE.md", "# W\n")
    write(w / ".claude/sources/instances/tracker.md", jira("tracker", AT))
    r = run(["bash", SCRIPTS_P + "/install-source-file.sh", "instances/b.md"], cwd=w, input=jira("b", AC).encode(),
            env={"CLAUDECODE": None, "WIKI_INSTALL_ANSWER": "y", "HOME": posix(tmp_path / "home")})
    err = r.err.decode("utf-8", "surrogateescape")
    assert r.rc == 1 and (w / ".claude/sources/instances/b.md").is_file(), r
    assert err == "install-source-file: %s\n" % _mix_msg("instances tracker, b name"), err
    assert "Installed .claude/sources/instances/b.md." in r.out.decode(), r


# --- a broken table --------------------------------------------------------------

@pytest.fixture
def broken(tmp_path, run, pydata):
    """A copy of the plugin whose connectors.md doesn't parse, and a runner
    for its scripts (in-process with --plugin in both modes, or with
    launcher=True its launchers in both modes)."""
    p = copytree(PLUGIN, tmp_path / "plugin")
    write(p / "sources/connectors.md", "---\nservers:\n  - local=claude_ai_Gmail\n---\n")
    mods = {"sources": sources, "wiki-check": wiki_check}

    def _run(name, *args, cwd, env=None, launcher=False):
        if launcher:
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
        # Through the launcher on Windows, the plugin path keeps Git Bash's
        # spelling (/c/...), as messages give paths as they came in.
        return r.merged.decode("utf-8", "surrogateescape").replace(msys(posix(p)), posix(p))
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
    assert "Fix: update or reinstall the wiki plugin (its sources/connectors.md)" in o(r), o(r)
    assert "source `scans` (type local-folder) is valid" in o(r), o(r)
    # The instance's own line points at the plugin too, not only at the file.
    assert ("can't check its connector names: %s" % bad) in o(r), o(r)
    assert ("Fix: update or reinstall the wiki plugin (its sources/connectors.md); for any other error listed, "
            "correct `.claude/sources/instances/gmail.md` (you, not Claude)") in o(r), o(r)
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
    head = "Reader tools and their cloud names (the plugin's sources/connectors.md):"
    surface = "Reader surface (this session: %s): "

    def show(k, remote):
        r = cli("sources", "show", k, cwd=w, env={"CLAUDE_CODE_REMOTE": "true"} if remote else None)
        assert r.rc == 0, r
        return r.out.decode("utf-8", "surrogateescape")
    o = show("gmail", True)
    assert surface % "cloud" in o and head in o, o
    assert "- search threads: %ssearch_threads; cloud: %ssearch_threads\n" % (GMAIL_T, GC) in o, o
    assert o.index(surface % "cloud") < o.index(head) < o.index("===== Instance file"), o
    assert surface % "local" in show("gmail", False)
    o = show("tracker", False)
    assert ("- find project: %sexecuteRead name=listJiraProjects; cloud: denied (%sexecuteRead; the limit holds only "
            "under the bound name)\n" % (AT, AC)) in o, o
    assert "- read issue: %sgetJiraIssue; cloud: %sgetJiraIssue\n" % (AT, AC) in o, o
    o = show("drive", False)
    assert "- get item: %sget_file_metadata; cloud: unknown (no pair in the plugin's sources/connectors.md)\n" % g in o, o
    o = show("proton", False)
    assert "- list folder: %s; cloud: the same\n" % SHELL in o, o
    o = show("scans", True)
    assert "Reader tools" not in o and "this session:" not in o, o


def test_show_unbound_cloud(tmp_path, cli):
    """The session line comes for an unbound instance too, and in a cloud
    session the hint is to bind locally, not /wiki:bind-reader."""
    w = gw(tmp_path)
    for remote, surface, hint in ((True, "cloud", "this instance has no reader binding yet; bind it in a local "
                                                  "session.\n"),
                                  (False, "local", "this instance has no reader binding yet; /wiki:bind-reader proton "
                                                   "drafts it.\n")):
        r = cli("sources", "show", "proton", cwd=w, env={"CLAUDE_CODE_REMOTE": "true"} if remote else None)
        o = r.out.decode("utf-8", "surrogateescape")
        assert r.rc == 0 and "Reader surface (this session: %s): " % surface in o and hint in o, o
        assert o.index("this session:") < o.index("Check needed: proton-files names no tools"), o
        assert ("/wiki:bind-reader" in o.split("=====")[0]) != remote, o


# --- the cloud rules must be in the wiki's settings before a cloud ingest -------

MISSING = "Check needed: cloud rules missing from .claude/settings.json:"


@pytest.fixture
def gated(tmp_path, cli):
    """A committed test wiki with gmail last checked 2026-10-01, and the
    settings `sources.sh settings` prints (not committed: no matter here)."""
    w = gw(tmp_path)
    write(w / "raw/sync-log.md", "last_checked_gmail: 2026-10-01\n")
    git(w, "add", "-A")
    git(w, "commit", "-qm", "init")
    o = cli("sources", "settings", cwd=w).out.decode()
    return w, o[o.index("{"):o.index("\n}\n") + 3]


def _show_due(cli, w, remote=True):
    env = {"CLAUDE_CODE_REMOTE": "true"} if remote else None
    r1, r2 = cli("sources", "show", "gmail", cwd=w, env=env), cli("sources", "due", cwd=w, env=env)
    assert r1.rc == 0 and r2.rc == 0, (r1, r2)
    # show's status lines, before the instance file and the contract (which quotes them).
    return r1.out.decode("utf-8", "surrogateescape").split("=====")[0], r2.out.decode("utf-8", "surrogateescape")


def test_cloud_rules_present(gated, cli):
    w, sjson = gated
    write(w / ".claude/settings.json", sjson)
    show, due = _show_due(cli, w)
    assert "cloud rules missing" not in show and "Check needed" not in show, show
    assert "- gmail: last checked 2026-10-01\n" in due, due


@pytest.mark.parametrize("case", ["one-missing", "no-settings"])
def test_cloud_rules_missing(case, gated, cli):
    """In a cloud session a bound instance whose cloud-name rules the wiki's
    settings lack is stopped (fail closed): show's Check needed line, which
    the unattended ingest refuses and Check stops at, and due skips it.
    Locally nothing changes: the local names are what the session has."""
    w, sjson = gated
    if case == "one-missing":
        write(w / ".claude/settings.json", sjson.replace('      "%ssend_message",\n' % GC, ""))
        rules = ' "%ssend_message"' % GC
    else:
        rules = ' "%ssearch_threads" "%sget_thread"' % (GC, GC)
    show, due = _show_due(cli, w)
    assert MISSING + rules in show, show
    assert ("; run sources.sh settings in a local session, paste the lines and commit .claude/settings.json; this "
            "source can't run in a cloud session until then.\n") in show, show
    assert ("- gmail: Check needed: cloud rules missing from .claude/settings.json (sources.sh show gmail)\n"
            in due), due
    show, due = _show_due(cli, w, remote=False)
    assert "cloud rules missing" not in show + due and "- gmail: last checked 2026-10-01\n" in due, due


# --- the boundary ------------------------------------------------------------------

# The cases that also run through sources.sh, lib-source.sh's bridge and
# wiki-check.sh (bash, py-run.sh, Python's stdout and stderr), in both
# modes: each covers something the boundary can break that the in-process
# run can't see. test_install_refuses_both_forms and test_install_mixed_forms
# always run install-source-file.sh (stdin, an answer from the environment).
BOUNDARY = [
    # Success: exit 0, CLAUDE_CODE_REMOTE passed through bash picks the surface.
    ("show-surface", test_show_unbound_cloud, {}),
    # A user's error: exit 1, its one line on stderr only, from sources.sh and the bridge.
    ("refusal", test_mixed_forms_across_wiki, {"case": "across"}),
]


@pytest.mark.parametrize("test,given", [pytest.param(t, g, id="connectors/boundary-" + n) for n, t, g in BOUNDARY])
def test_boundary(test, given, request, cli):
    """The chosen cases through the launchers, whatever --e2e says: same
    assertions as in-process."""
    rerun(request, test, cli=functools.partial(cli, launcher=True), **given)


@pytest.mark.checks("connectors/boundary-internal-error")
def test_boundary_internal_error(tmp_path, broken):
    """An internal error through a copied plugin's own sources.sh: exit 3,
    the message on stderr only, the copy's path as the launcher found it."""
    p, prun = broken
    w = gw(tmp_path)
    write(w / ".claude/settings.json", "{}\n")
    r = prun("sources", "settings", cwd=w, env=empty_home(tmp_path), launcher=True)
    err = r.err.decode("utf-8", "surrogateescape").replace(msys(posix(p)), posix(p))
    assert r.rc == 3 and r.out == b"", r
    assert err.startswith("sources: internal error: ConnectorsError: %s/sources/connectors.md: servers item "
                          "'local=claude_ai_Gmail' must be" % posix(p)), err
