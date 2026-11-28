"""Reader bindings (docs/adr.md, 11): the `operations` of a tool-neutral
contract, an instance's `reader`, `reader_deny` and `reader_allow` lists, their
validation, and the settings rules check-settings looks for, which may sit
in the user's settings. The guard's side is in test_guard.py (fixtures
*-mcp-reader-*, test_reader_*)."""

import json

import pytest

import contract
import sourcelib
from conftest import GMAIL_DENY, GMAIL_OPS, GMAIL_T, PLUGIN, TESTS, copytree, git, home_env, posix, write

JIRA = posix(PLUGIN / "sources" / "jira" / "SOURCE.md")
GMAIL = posix(PLUGIN / "sources" / "gmail" / "SOURCE.md")
CODEBASE = posix(PLUGIN / "sources" / "codebase" / "SOURCE.md")
GDRIVE = posix(PLUGIN / "sources" / "google-drive" / "SOURCE.md")
T = "mcp__claude_ai_Atlassian_MCP__"
C = "mcp__Atlassian_MCP__"  # its cloud name (docs/adr.md, 17)
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


def _inst(tmp_path, typ, reader=(), deny=(), allow=()):
    lines = ["---", "key: x", "type: " + typ]
    if reader:
        lines += ["reader:"] + ["  - " + r for r in reader]
    if deny:
        lines += ["reader_deny:"] + ["  - " + r for r in deny]
    if allow:
        lines += ["reader_allow:"] + ["  - " + r for r in allow]
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
    pytest.param(['"%s"' % OK[0]] + OK[1:], (), ["is in quotes; write it without them"], id="quoted-item"),
    pytest.param(OK, ("'%sexecuteWrite'" % T,), ["reader_deny item '%sexecuteWrite' is in quotes" % T],
                 id="quoted-deny"),
    pytest.param(OK, ("%sgetJiraIssue" % T,), ["denies %sgetJiraIssue, which reader binds" % T], id="deny-bound"),
])
def test_reader_errors(reader, deny, want, tmp_path):
    got = sourcelib.reader_errors(_inst(tmp_path, "jira", reader, deny), JIRA)
    assert len(got) == len(want) and all(w in g for w, g in zip(want, got, strict=True)), got


def test_reader_only_tools(tmp_path):
    """A contract that isn't access: tools (codebase; gmail was the example
    until it became tool-neutral, docs/adr.md 10) takes no binding."""
    f = _inst(tmp_path, "codebase", OK)
    assert sourcelib.reader_errors(f, CODEBASE) == [
        "only an access: tools instance has a reader binding ('reader', 'reader_deny', 'reader_allow')"]
    f = _inst(tmp_path, "codebase", allow=("Bash(bash */scripts/file-snapshot.sh *)",))
    assert sourcelib.reader_errors(f, CODEBASE) == [
        "only an access: tools instance has a reader binding ('reader', 'reader_deny', 'reader_allow')"]


def test_one_tool_two_operations(tmp_path):
    """One tool may do two operations, both unlimited (the Google Drive
    connector's search_files: list folder and search by name). It validates,
    and the wiki's settings allow it once."""
    g = "mcp__claude_ai_Google_Drive__"
    reader = ["get item: %sget_file_metadata" % g, "list folder: %ssearch_files" % g,
              "search by name: %ssearch_files" % g, "read file: %sread_file_content" % g,
              "download file: %sdownload_file_content" % g]
    w = tmp_path / "w"
    (w / ".claude/sources/instances").mkdir(parents=True)
    f = posix(write(w / ".claude/sources/instances/drive.md",
                    "\n".join(["---", "key: drive", "type: google-drive", "reader:"] + ["  - " + r for r in reader]
                              + ["reader_deny:", "  - %strash_file" % g, "---", ""])))
    assert sourcelib.reader_errors(f, GDRIVE) == []
    need = sourcelib.needed_rules(posix(w), posix(PLUGIN))
    assert [ln for ln in need if ln.startswith("allow\t%ssearch_files\t" % g)] == [
        "allow\t%ssearch_files\t%ssearch_files" % (g, g)], need
    assert "deny\t%strash_file\t%strash_file" % (g, g) in need, need


def test_reader_rules(tmp_path):
    f = _inst(tmp_path, "jira", OK + ["find project: %sexecuteRead name=a" % T, "count: %sexecuteRead name=b" % T],
              ("%sexecuteWrite" % T,))
    # Without the pair table: the bound names only.
    assert sourcelib.reader_rules(f) == (
        ["allow\t%s\t%s" % (T + t, T + t) for t in
         ("searchJiraIssuesUsingJql", "getJiraIssue", "listJiraIssueComments", "executeRead", "executeRead")]
        + ["deny\t%sexecuteWrite\t%sexecuteWrite" % (T, T)])
    # With it (docs/adr.md, 17): each line followed by its cloud name's; the
    # dispatcher bound only with limits is denied under its cloud name.
    assert sourcelib.reader_rules(f, sourcelib.connector_pairs(posix(PLUGIN))) == (
        ["allow\t%s\t%s" % (p + t, p + t) for t in ("searchJiraIssuesUsingJql", "getJiraIssue", "listJiraIssueComments")
         for p in (T, C)]
        + ["allow\t%sexecuteRead\t%sexecuteRead" % (T, T), "deny\t%sexecuteRead\t%sexecuteRead" % (C, C)] * 2
        + ["deny\t%sexecuteWrite\t%sexecuteWrite" % (T, T), "deny\t%sexecuteWrite\t%sexecuteWrite" % (C, C)])
    # A reader_allow item adds no line here (allow_rules gives it).
    (tmp_path / "a").mkdir()
    g = _inst(tmp_path / "a", "jira", OK, allow=("Bash(bash */scripts/file-snapshot.sh *)",))
    assert sourcelib.reader_rules(g) == ["allow\t%s\t%s" % (p, p) for p in (r.split(": ", 1)[1] for r in OK)]


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
    assert ("(~/.claude/settings.json, 0 permission rules), except their cloud names "
            "(the plugin's sources/connectors.md), which count only here\n") in o, o


def test_check_settings_reader_missing(rw, cli):
    w, home, env, sjson = rw
    write(w / ".claude/settings.json", sjson.replace('      "%sgetJiraIssue",\n' % T, ""))
    rc, o = _check(cli, w, env)
    assert rc == 1 and "  allow: %sgetJiraIssue" % T in o, o


def test_check_settings_reader_in_user(rw, cli):
    """Still met: only the local names moved to the user's settings; their
    cloud names stay in the wiki's (the cloud-name tests below)."""
    w, home, env, sjson = rw
    write(w / ".claude/settings.json", sjson.replace('      "%sgetJiraIssue",\n' % T, "")
          .replace('      "%sexecuteWrite",\n' % T, ""))
    write(home / ".claude/settings.json", '{"permissions": {"allow": ["%sgetJiraIssue"], "deny": ["%sexecuteWrite"]}}\n'
          % (T, T))
    rc, o = _check(cli, w, env)
    assert rc == 0 and "missing: none" in o and "(~/.claude/settings.json, 2 permission rules)" in o, o


# The cloud names (docs/adr.md, 17) count only from the wiki's settings.

def _drop(sjson, rule):
    q = '"%s"' % rule
    assert q in sjson
    return sjson.replace("      %s,\n" % q, "").replace("      %s\n" % q, "")


def test_check_settings_cloud_missing(rw, cli):
    w, home, env, sjson = rw
    write(w / ".claude/settings.json", _drop(sjson, C + "getJiraIssue"))
    rc, o = _check(cli, w, env)
    assert rc == 1 and "  allow: %sgetJiraIssue (cloud name)\n" % C in o, o


def test_check_settings_cloud_only_in_user(rw, cli):
    w, home, env, sjson = rw
    write(w / ".claude/settings.json", _drop(sjson, C + "getJiraIssue"))
    write(home / ".claude/settings.json", '{"permissions": {"allow": ["%sgetJiraIssue"]}}\n' % C)
    rc, o = _check(cli, w, env)
    assert rc == 1 and ("  allow: %sgetJiraIssue (cloud name; only in ~/.claude/settings.json, which a cloud "
                        "session doesn't read)\n" % C) in o, o


def test_check_settings_limited_cloud_deny_missing(rw, cli):
    w, home, env, sjson = rw
    deny = sjson.index('"deny"')
    write(w / ".claude/settings.json", sjson[:deny] + _drop(sjson[deny:], C + "executeRead"))
    rc, o = _check(cli, w, env)
    assert rc == 1 and "  deny: %sexecuteRead (cloud name)\n" % C in o, o


def test_check_settings_local_in_user_cloud_in_wiki(rw, cli):
    """Every local reader name in the user's settings, the cloud names in
    the wiki's: all met."""
    w, home, env, sjson = rw
    perms = json.loads(sjson)["permissions"]
    local = {k: [r for r in v if r.startswith("mcp__claude_ai_")] for k, v in perms.items()}
    rest = {k: [r for r in v if not r.startswith("mcp__claude_ai_")] for k, v in perms.items()}
    assert local["allow"] and local["deny"] and any(r.startswith(C) for r in rest["deny"])
    write(w / ".claude/settings.json", json.dumps({"permissions": rest}, indent=2) + "\n")
    write(home / ".claude/settings.json", json.dumps({"permissions": local}) + "\n")
    rc, o = _check(cli, w, env)
    assert rc == 0 and "missing: none" in o, o


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


# ms-teams (access: tools, docs/adr.md 10): no required operation, so a
# binding is valid whatever it binds; its Check asks for each parameter's
# operations. The connector binding is guard-wiki's teams.md.

TEAMS = posix(PLUGIN / "sources" / "ms-teams" / "SOURCE.md")
M = "mcp__claude_ai_Microsoft_365__"


def test_teams_connector_binding_valid():
    assert sourcelib.reader_errors(posix(TESTS / "guard-wiki/.claude/sources/instances/teams.md"), TEAMS) == []


def test_teams_one_operation_valid(tmp_path):
    """No operation is required: one recommended operation alone validates
    (Check, not validation, catches a parameter's missing operations)."""
    assert sourcelib.reader_errors(_inst(tmp_path, "ms-teams", ["read file: %sread_resource" % M]), TEAMS) == []


# reader_allow (docs/adr.md, 11): a binding's extra allow rules, only in
# named shapes.

SNAP = "Bash(bash */scripts/file-snapshot.sh *)"
SHAPE = "must be Bash(bash */scripts/<script>.sh *) with <script> file-snapshot, decode-download or ocr"


@pytest.mark.parametrize("allow,want", [
    pytest.param((SNAP,), [], id="allow-snapshot"),
    pytest.param(("Bash(bash */scripts/decode-download.sh *)",), [], id="allow-decode"),
    pytest.param(("Bash(bash */scripts/ocr.sh *)",), [], id="allow-ocr"),
    pytest.param(("Edit(~/.cache/wiki-sources/**)",), [], id="allow-cache-all"),
    pytest.param(("Edit(~/.cache/wiki-sources/*/*/notes/*.json)",), [], id="allow-cache-path"),
    pytest.param(("Bash(bash */scripts/save.sh *)",), [SHAPE], id="allow-core-script"),
    pytest.param(("Bash(bash */scripts/sources.sh *)",), [SHAPE], id="allow-sources-sh"),
    pytest.param(("Bash(curl *)",), [SHAPE], id="allow-any-bash"),
    pytest.param(("Read(~/.cache/wiki-sources/**)",), [SHAPE], id="allow-read-cache"),
    pytest.param(("Edit(~/.cache/other/**)",), [SHAPE], id="allow-other-cache"),
    pytest.param(("Edit(~/.cache/wiki-sources/*/*/../x)",), [SHAPE], id="allow-dotdot"),
    pytest.param(("Edit(~/.cache/wiki-sources/*/*/./x)",), [SHAPE], id="allow-dot"),
    pytest.param(("Edit(~/.cache/wiki-sources/*/*/..*/x)",), [SHAPE], id="allow-dotstar"),
    pytest.param(("Edit(~/.cache/wiki-sources/*/*/.*)",), [SHAPE], id="allow-dot-star"),
    pytest.param(("Edit(~/.cache/wiki-sources/*/*/a//b)",), [SHAPE], id="allow-empty-seg"),
    pytest.param(("Edit(~/.cache/wiki-sources/*/*/a b)",), [SHAPE], id="allow-space"),
    pytest.param(("%sread_resource" % M,), [SHAPE], id="allow-mcp"),
    pytest.param(("Skill(wiki:ingest)",), [SHAPE], id="allow-skill"),
    pytest.param(('"%s"' % SNAP,), ["reader_allow item \"%s\" is in quotes; write it without them" % SNAP],
                 id="allow-quoted"),
    pytest.param((SNAP, SNAP), ["reader_allow lists %s twice" % SNAP], id="allow-twice"),
])
def test_reader_allow_errors(allow, want, tmp_path):
    got = sourcelib.reader_errors(_inst(tmp_path, "ms-teams", ["read file: %sread_resource" % M], allow=allow), TEAMS)
    assert len(got) == len(want) and all(w in g for w, g in zip(want, got, strict=True)), got


def test_reader_allow_denied(tmp_path):
    f = _inst(tmp_path, "ms-teams", ["read file: %sread_resource" % M], ("'%s'" % SNAP,), (SNAP,))
    got = sourcelib.reader_errors(f, TEAMS)
    assert got[-1] == "reader_allow allows %s, which reader_deny denies" % SNAP, got


def test_reader_allow_only_unbound(tmp_path):
    """reader_allow alone binds no operation: no required-operation error."""
    assert sourcelib.reader_errors(_inst(tmp_path, "jira", allow=(SNAP,)), JIRA) == []


def _allow_wiki(tmp_path, allow):
    w = tmp_path / "w"
    (w / ".claude/sources/instances").mkdir(parents=True)
    write(w / ".claude/sources/instances/x.md",
          "\n".join(["---", "key: x", "type: ms-teams", "reader:", "  - read file: %sread_resource" % M,
                     "reader_allow:"] + ["  - " + r for r in allow] + ["---", ""]))
    reader, aux = set(), set()
    need = sourcelib.needed_rules(posix(w), posix(PLUGIN), reader, aux)
    return need, reader, aux


def test_reader_allow_needed_rules(tmp_path):
    need, reader, aux = _allow_wiki(tmp_path, [SNAP, "Edit(~/.cache/wiki-sources/*/*/notes/**)",
                                               "Edit(~/.cache/wiki-sources/**)", '"Bash(bash */scripts/ocr.sh *)"',
                                               "Bash(curl *)"])
    want = ["allow\t%s\t%s" % (SNAP, SNAP),
            "allow\tEdit(~/.cache/wiki-sources/w/x/notes/**)\tEdit(~/.cache/wiki-sources/*/*/notes/**)",
            "allow\tEdit(~/.cache/wiki-sources/w/x/**)\tEdit(~/.cache/wiki-sources/**)"]
    for ln in want:
        assert ln in need and ln in reader and ln in aux, (ln, need)
    walk = "allow\tEdit(~/.cache/wiki-sources/w/x/walk.tsv)\tEdit(~/.cache/wiki-sources/*/*/walk.tsv)"
    assert walk in need and walk not in reader and walk not in aux, need
    assert not [ln for ln in need if "ocr.sh" in ln or "curl" in ln], need
    assert aux == set(want), aux


def test_reader_allow_same_narrowed(tmp_path):
    """Two spellings that narrow to one rule give one line, the first's."""
    need, reader, aux = _allow_wiki(tmp_path, ["Edit(~/.cache/wiki-sources/**)", "Edit(~/.cache/wiki-sources/*/*/**)"])
    got = [ln for ln in need if ln.startswith("allow\tEdit(~/.cache/wiki-sources/w/x/**)\t")]
    assert got == ["allow\tEdit(~/.cache/wiki-sources/w/x/**)\tEdit(~/.cache/wiki-sources/**)"], need
    assert aux == set(got), aux


def test_reader_allow_dup_of_contract(tmp_path):
    """A copy of the contract's own cache rule is still the contract's: it
    counts only from the wiki's settings."""
    need, reader, aux = _allow_wiki(tmp_path, ["Edit(~/.cache/wiki-sources/*/*/walk.tsv)"])
    walk = "allow\tEdit(~/.cache/wiki-sources/w/x/walk.tsv)\tEdit(~/.cache/wiki-sources/*/*/walk.tsv)"
    assert need.count(walk) == 1 and walk not in reader and walk not in aux, need


@pytest.fixture
def rwa(rw):
    """rw with the Teams instance's folder snapshot in reader_allow."""
    w, home, env, _ = rw
    f = w / ".claude/sources/instances/teams.md"
    text = f.read_text(encoding="utf-8")
    end = text.index("\n---\n") + 1
    write(f, text[:end] + "reader_allow:\n  - %s\n" % SNAP + text[end:])
    return w, home, env


def _settings(cli, w, env, *args):
    return cli("sources", "settings", *args, cwd=w, env=env).out.decode()


def _sjson(o):
    return o[o.index("{"):o.index("\n}\n") + 3]


LOCAL = ("only in your user settings (enough locally; a cloud session or routine reads only this wiki's "
         ".claude/settings.json):\n")


def test_check_settings_allow_ok(rwa, cli):
    w, home, env = rwa
    sjson = _sjson(_settings(cli, w, env))
    assert '"%s"' % SNAP in sjson
    write(w / ".claude/settings.json", sjson)
    rc, o = _check(cli, w, env)
    assert rc == 0 and "missing: none" in o and "stale: none" in o and "only in your user settings" not in o, o


def test_check_settings_allow_missing(rwa, cli):
    w, home, env = rwa
    write(w / ".claude/settings.json", _drop(_sjson(_settings(cli, w, env)), SNAP))
    rc, o = _check(cli, w, env)
    assert rc == 1 and "  allow: %s\n" % SNAP in o, o


def test_check_settings_allow_only_in_user(rwa, cli):
    w, home, env = rwa
    write(w / ".claude/settings.json", _drop(_sjson(_settings(cli, w, env)), SNAP))
    write(home / ".claude/settings.json", '{"permissions": {"allow": ["%s"]}}\n' % SNAP)
    rc, o = _check(cli, w, env)
    assert rc == 0 and "missing: none" in o and LOCAL + "  allow: %s\n" % SNAP in o, o


def test_check_settings_allow_removed_stale(rw, cli):
    """The last binding that needs the helper rule is gone: it is stale."""
    w, home, env, sjson = rw
    assert SNAP not in sjson
    write(w / ".claude/settings.json", sjson.replace('"allow": [', '"allow": [\n      "%s",' % SNAP, 1))
    rc, o = _check(cli, w, env)
    assert rc == 0 and "\n  allow: %s\n" % SNAP in o[o.index("stale"):], o


def test_check_settings_allow_narrowed_contract_rule(rw, cli):
    """A reader_allow item spelled differently from the contract's rule but
    narrowing to it stays the contract's rule: missing from the wiki's
    settings even though the user's settings cover it, reported once."""
    w, home, env, _ = rw
    write(w / ".claude/sources/instances/n.md", "---\nkey: n\ntype: onenote\nreader_allow:\n"
          "  - Edit(~/.cache/wiki-sources/**)\nstate:\n  - last_checked\n---\n")
    rule = "Edit(~/.cache/wiki-sources/rw/n/**)"
    sjson = _sjson(_settings(cli, w, env))
    assert sjson.count('"%s"' % rule) == 1, sjson
    write(w / ".claude/settings.json", _drop(sjson, rule))
    write(home / ".claude/settings.json", '{"permissions": {"allow": ["Edit(~/.cache/wiki-sources/**)"]}}\n')
    rc, o = _check(cli, w, env)
    assert rc == 1 and o.count("  allow: %s\n" % rule) == 1 and "only in your user settings" not in o, o


def test_check_settings_allow_cache_only_in_user(rwa, cli):
    """A reader_allow cache rule, narrowed, met by a broader rule in the
    user's settings: enough locally, reported."""
    w, home, env = rwa
    f = w / ".claude/sources/instances/teams.md"
    write(f, f.read_text(encoding="utf-8").replace(
        "reader_allow:\n", "reader_allow:\n  - Edit(~/.cache/wiki-sources/*/*/notes/**)\n", 1))
    rule = "Edit(~/.cache/wiki-sources/rw/teams/notes/**)"
    write(w / ".claude/settings.json", _drop(_sjson(_settings(cli, w, env)), rule))
    write(home / ".claude/settings.json", '{"permissions": {"allow": ["Edit(~/.cache/wiki-sources/**)"]}}\n')
    rc, o = _check(cli, w, env)
    assert rc == 0 and "missing: none" in o and LOCAL + "  allow: %s\n" % rule in o, o


def test_settings_key_allow(rwa, cli):
    w, home, env = rwa
    assert '"%s"' % SNAP in _settings(cli, w, env, "ms-teams", "--key", "teams")
    assert SNAP not in _settings(cli, w, env, "ms-teams")
    f = w / ".claude/sources/instances/teams.md"
    write(f, f.read_text(encoding="utf-8").replace(
        "reader_allow:\n", "reader_allow:\n  - Edit(~/.cache/wiki-sources/*/*/notes/**)\n", 1))
    o = _settings(cli, w, env, "ms-teams", "--key", "teams")
    assert '"Edit(~/.cache/wiki-sources/rw/teams/notes/**)"' in o, o
    assert "Cache rules are narrowed to this wiki and instance" in o, o


def test_contract_without_required_valid(tmp_path, capsys):
    """A tools contract whose operations are all recommended or optional
    validates."""
    text = (PLUGIN / "sources" / "jira" / "SOURCE.md").read_text(encoding="utf-8")
    text = text.replace("(required)", "(recommended)")
    assert "(required)" not in text
    c = write(tmp_path / "jira" / "SOURCE.md", text)
    assert sourcelib.validate_contract(posix(c)) is True
    assert capsys.readouterr().err == ""


def test_check_settings_teams_outlook_deny_missing(rw, cli):
    w, home, env, sjson = rw
    rule = '"%soutlook_email_search"' % M
    assert rule in sjson
    write(w / ".claude/settings.json", sjson.replace("      %s,\n" % rule, "").replace("      %s\n" % rule, ""))
    rc, o = _check(cli, w, env)
    assert rc == 1 and "deny: %soutlook_email_search" % M in o, o


def test_show_teams_unbound(tmp_path, cli):
    """Without its reader binding, the Teams instance asks for Check."""
    w = copytree(TESTS / "guard-wiki", tmp_path / "uw")
    git(w, "init", "-q")
    f = w / ".claude/sources/instances/teams.md"
    lines = f.read_text(encoding="utf-8").split("\n")
    out, skip = [], False
    for ln in lines:
        if ln in ("reader:", "reader_deny:"):
            skip = True
            continue
        if skip and ln.startswith("  - "):
            continue
        skip = False
        out.append(ln)
    write(f, "\n".join(out).split("\n## Reader")[0])
    o = cli("sources", "show", "teams", cwd=w).merged.decode("utf-8", errors="surrogateescape")
    assert ("Check needed: ms-teams names no tools (access: tools) and this instance has no reader binding yet; "
            "/wiki:bind-reader teams drafts it.") in o, o


def test_teams_all_operations_bound(tmp_path, cli):
    """Every operation bound to the connector's tools: it validates, and
    `settings ms-teams --key` allows the tools only that binding adds."""
    tools = {"show scope": "get_granted_scopes", "list channels": "teams_list_channels",
             "list channel posts": "teams_list_channel_messages", "list replies": "teams_list_channel_messages",
             "read message": "read_resource", "list chats": "teams_list_chats", "list chat messages": "read_resource",
             "search chat messages": "chat_message_search", "list folder": "read_resource",
             "read file": "read_resource", "search files by name": "sharepoint_search"}
    ops = [contract.operation(o)[0] for o in contract.list_(TEAMS, "operations")]
    assert sorted(ops) == sorted(tools)
    w = copytree(TESTS / "guard-wiki", tmp_path / "aw")
    git(w, "init", "-q")
    f = w / ".claude/sources/instances/teams.md"
    text = f.read_text(encoding="utf-8")
    head, rest = text.split("reader:\n", 1)
    rest = rest[rest.index("reader_deny:\n"):]
    write(f, head + "reader:\n" + "".join("  - %s: %s%s\n" % (o, M, t) for o, t in tools.items()) + rest)
    assert sourcelib.reader_errors(posix(f), TEAMS) == []
    o = cli("sources", "settings", "ms-teams", "--key", "teams", cwd=w).out.decode()
    for t in ("teams_list_chats", "chat_message_search", "sharepoint_search"):
        assert '"%s%s"' % (M, t) in o, o


# gmail (access: tools, docs/adr.md 10): the contract names no tools; the
# connector binding is guard-wiki's gmail.md. Gmail is read-only: the
# binding denies the label writes the old contract allowed, and the draft
# reads.

GW_GMAIL = TESTS / "guard-wiki/.claude/sources/instances/gmail.md"


def test_gmail_connector_binding_valid():
    assert sourcelib.reader_errors(posix(GW_GMAIL), GMAIL) == []


def test_gmail_operations_match_connector():
    """The contract's operations are the connector's (show scope aside:
    it has none), and the shared binding covers all the others."""
    ops = [contract.operation(o)[0] for o in contract.list_(GMAIL, "operations")]
    assert sorted(ops) == sorted([*GMAIL_OPS, "show scope"])
    assert contract.list_(GMAIL, "read_tools") == contract.list_(GMAIL, "bookkeeping_tools") == []
    assert contract.list_(GMAIL, "forbidden_tools") == []


def test_gmail_required_missing(tmp_path):
    reader = ["%s: %s%s" % (o, GMAIL_T, t) for o, t in GMAIL_OPS.items() if o != "read thread"]
    got = sourcelib.reader_errors(_inst(tmp_path, "gmail", reader), GMAIL)
    assert len(got) == 1 and "doesn't bind 'read thread', a required operation" in got[0], got


def test_gmail_thread_dates_recommended(tmp_path):
    """thread dates is recommended: a binding without it (as bound before
    it existed) stays valid; List new then takes dates from read thread."""
    reader = ["%s: %s%s" % (o, GMAIL_T, t) for o, t in GMAIL_OPS.items() if o != "thread dates"]
    assert sourcelib.reader_errors(_inst(tmp_path, "gmail", reader), GMAIL) == []


def test_gmail_settings_key(tmp_path, cli):
    """`settings gmail --key gmail` allows the bound read tools and denies
    the write tools and draft reads; it never allows a label write."""
    w = copytree(TESTS / "guard-wiki", tmp_path / "gw")
    git(w, "init", "-q")
    o = cli("sources", "settings", "gmail", "--key", "gmail", cwd=w).out.decode()
    allow = o[o.index('"allow"'):o.index('"deny"')]
    deny = o[o.index('"deny"'):]
    for t in GMAIL_OPS.values():
        assert '"%s%s"' % (GMAIL_T, t) in allow, o
    for t in GMAIL_DENY:
        assert '"%s%s"' % (GMAIL_T, t) in deny, (t, o)
    for t in ("create_label", "label_thread", "list_drafts", "get_draft"):
        assert '"%s%s"' % (GMAIL_T, t) not in allow, (t, o)


def test_check_settings_gmail_label_deny_missing(rw, cli):
    w, home, env, sjson = rw
    rule = '"%slabel_thread"' % GMAIL_T
    assert rule in sjson
    write(w / ".claude/settings.json", sjson.replace("      %s,\n" % rule, "").replace("      %s\n" % rule, ""))
    rc, o = _check(cli, w, env)
    assert rc == 1 and "deny: %slabel_thread" % GMAIL_T in o, o


def test_check_settings_gmail_old_label_allow(rw, cli):
    """A wiki moving from the old contract still allows label_thread: it
    is now also denied, which check-settings reports until it is removed."""
    w, home, env, sjson = rw
    write(w / ".claude/settings.json", sjson.replace('"allow": [', '"allow": [\n      "%slabel_thread",' % GMAIL_T, 1))
    rc, o = _check(cli, w, env)
    assert rc == 1 and "in both allow and deny" in o and "%slabel_thread" % GMAIL_T in o, o


def test_show_gmail_unbound(tmp_path, cli):
    """Without its reader binding, the gmail instance asks for Check."""
    w = copytree(TESTS / "guard-wiki", tmp_path / "ug")
    git(w, "init", "-q")
    write(w / ".claude/sources/instances/gmail.md", "---\nkey: gmail\ntype: gmail\nlabels: Receipts\nstate:\n"
          "  - last_checked\n---\n")
    o = cli("sources", "show", "gmail", cwd=w).merged.decode("utf-8", errors="surrogateescape")
    assert ("Check needed: gmail names no tools (access: tools) and this instance has no reader binding yet; "
            "/wiki:bind-reader gmail drafts it.") in o, o
