"""/wiki:bind-reader and the tool-neutral contracts it binds
(docs/plans/reader-binding.md, phase 2): every access: tools contract
has a ## Bind section and sends Check to the skill, and the skill is
model-invocable with only sources.sh pre-allowed."""

import re

import pytest

import contract
import sourcelib
from conftest import GMAIL_DENY, PLUGIN, TESTS, copytree, git, posix, write

SOURCES = PLUGIN / "sources"
SKILL = PLUGIN / "skills" / "bind-reader" / "SKILL.md"


def _tool_neutral():
    return sorted(p.parent.name for p in SOURCES.glob("*/SOURCE.md")
                  if re.search(r"^access: tools$", p.read_text(encoding="utf-8"), re.M))


def _section(text, name):
    m = re.search(r"^## %s\n(.*?)(?=^## |\Z)" % re.escape(name), text, re.M | re.S)
    return m.group(1) if m else ""


@pytest.mark.checks("bind-reader/tool-neutral-types")
def test_tool_neutral_types():
    assert _tool_neutral() == ["gmail", "google-drive", "jira", "ms-teams", "onenote", "proton-files"]


@pytest.mark.parametrize("t", _tool_neutral())
def test_bind_section(t):
    text = (SOURCES / t / "SOURCE.md").read_text(encoding="utf-8")
    bind = _section(text, "Bind")
    assert "/wiki:bind-reader" in bind
    assert re.search(r"^1\. ", bind, re.M), "the Bind tests are a numbered list"
    assert "safe" in bind


@pytest.mark.parametrize("t", _tool_neutral())
def test_check_starts_binding(t):
    check = _section((SOURCES / t / "SOURCE.md").read_text(encoding="utf-8"), "Check")
    first = check.strip().split("\n")[0]
    assert "no `reader` list" in first and "/wiki:bind-reader <key>" in first


@pytest.mark.parametrize("t", _tool_neutral())
def test_operations_named_in_body(t):
    """Each operation the frontmatter lists (what a binding names) is
    one the body describes, in bold."""
    text = (SOURCES / t / "SOURCE.md").read_text(encoding="utf-8")
    body = text.split("\n---\n", 1)[1]
    ops = [contract.operation(o)[0] for o in contract.list_(posix(SOURCES / t / "SOURCE.md"), "operations")]
    assert ops and all("**%s**" % o in body for o in ops), ops


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "frontmatter"
    return m.group(1)


@pytest.mark.checks("bind-reader/frontmatter")
def test_skill_frontmatter():
    fm = _frontmatter(SKILL)
    assert re.search(r"^name: bind-reader$", fm, re.M)
    assert "disable-model-invocation" not in fm, "Check starts it (phase 1: no prompt)"
    tools = re.findall(r"^  - (.*)$", fm.split("allowed-tools:", 1)[1], re.M)
    assert tools == ["Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/sources.sh *)"]


@pytest.mark.checks("bind-reader/skill-rules")
def test_skill_rules():
    text = SKILL.read_text(encoding="utf-8")
    deny = text.index("## 4. Deny the write tools first")
    test = text.index("## 5. Test each operation")
    assert deny < test, "write tools are denied before any test call"
    assert "check-settings" in text[deny:test]
    assert "plain Yes" in text
    assert "**stops**" in text


@pytest.mark.checks("bind-reader/live-run-fixes")
def test_skill_live_run_fixes():
    """The first live run (2026-11-19): a missed allow line, a reader
    already named in prose, a safe item that can't serve every test."""
    text = SKILL.read_text(encoding="utf-8")
    hand = text[text.index("## 6. Hand over"):]
    assert "check-settings" in hand and "not allowed" in hand
    assert "**Already named in prose.**" in text
    assert "second safe item" in text


@pytest.mark.checks("bind-reader/contract-live-run-fixes")
def test_contract_live_run_fixes():
    jira = (SOURCES / "jira" / "SOURCE.md").read_text(encoding="utf-8")
    assert "**Moved issues.**" in _section(jira, "List new")
    assert "same scope name" in _section(jira, "Check")
    assert "does not exist for the field" in _section(jira, "Check")
    onenote = (SOURCES / "onenote" / "SOURCE.md").read_text(encoding="utf-8")
    assert _section(onenote, "List new").count("diff -B -w") == 2


@pytest.mark.checks("bind-reader/ms-teams-contract")
def test_ms_teams_contract():
    """ms-teams (docs/adr.md 10): Check stops for a parameter's unbound
    operation; Bind names the connector's denies (write, Outlook, people)
    and hands over the snapshot script's allow."""
    text = (SOURCES / "ms-teams" / "SOURCE.md").read_text(encoding="utf-8")
    check, bind = _section(text, "Check"), _section(text, "Bind")
    assert "every operation it needs (the table above) must be bound" in check
    for tool in ("teams_send_channel_message", "teams_reply_channel_message", "teams_send_chat_message",
                 "teams_create_chat", "outlook_create_event", "outlook_email_search", "outlook_calendar_search",
                 "outlook_find_available_time", "find_meeting_availability", "search_people", "get_me"):
        assert "`%s`" % tool in bind, tool
    assert "`Bash(bash */scripts/file-snapshot.sh *)`" in bind
    assert "reader_allow" in bind
    assert "can't verify" not in text
    assert "**Stop**" in bind
    assert "sources/ms-teams/snapshot" not in text
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/file-snapshot.sh <key> compare" in _section(text, "List new")
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/file-snapshot.sh <key> save" in _section(text, "Mark ingested")


@pytest.mark.checks("bind-reader/gmail-contract")
def test_gmail_contract():
    """gmail (docs/adr.md 10): read-only, no Gmail write at all; Bind names
    the connector's denies (writes, label writes, draft reads) on both
    surfaces; List new searches a 7-day overlap with no old-label
    exclusion (issue #87: it hid new replies in threads labelled before the
    move) and drops threads by the thread IDs in the sync-log history, which
    Mark ingested writes in the same form, or, for a thread read before the
    move, by the dates pages' sources: cite."""
    text = (SOURCES / "gmail" / "SOURCE.md").read_text(encoding="utf-8")
    check, bind = _section(text, "Check"), _section(text, "Bind")
    new, mark = _section(text, "List new"), _section(text, "Mark ingested")
    for tool in GMAIL_DENY:
        assert "`%s`" % tool in bind, tool
    assert "`mcp__claude_ai_Gmail__`" in bind and "`mcp__Gmail__`" in bind
    assert "THREAD_VIEW_SUMMARY" in bind and "**Stop**" in bind
    assert "**search threads**, **read thread** or **list labels**" in check
    # The connector's search gives no message dates in any view: List new
    # takes an already-read thread's newest date from thread dates (a
    # metadata-only get_thread), or read thread where nothing can.
    assert "No view gives a message `date`" in bind
    assert "**thread dates**: `get_thread` with `threadId` and `messageFormat: METADATA_ONLY`" in bind
    assert "**thread dates** on the safe thread's ID" in bind
    assert "A thread that no row names needs no date" in new
    assert "otherwise with **thread dates**" in new and "**read thread** where no tool can" in new
    assert "If none can **thread dates**" in check
    # Nor a next-page field: one page, so a full page may have dropped
    # threads; List new splits it by date, then by term, and stops if a
    # one-day term search is still full. Its message-count estimate is unused.
    assert "**no next-page field**" in bind and "`resultCountEstimate` counts messages" in bind
    assert "is noted, not a stop" in bind
    assert "**Full pages.**" in new and "halve its date range" in new
    assert "one search per label, sender and recipient" in new and "stop and tell the user" in new
    assert "Merge the results by thread ID" in new
    assert "thread count from **list labels**" in check and '"<page size> or more"' in check
    # Its bodies come as plain text only with messageFormat given; its
    # attachment IDs change on every read; its downloads keep their extension.
    assert "`get_thread` with `threadId` and `messageFormat: PLAIN_TEXT`, given explicitly" in bind
    assert "`get_message` with `messageId` and `messageFormat: PLAIN_TEXT`" in bind
    assert "attachment IDs change on every read" in bind
    fetch = _section(text, "Fetch")
    assert "by an attachment ID from a **read thread** or **read message** made just before" in fetch
    assert "in the attachment's own extension" in fetch
    form = "`; thread IDs: <id>, <id>`"
    assert form in text.split("## Bind", 1)[0]
    assert "Nothing is written at Gmail" in mark and form in mark and "`raw/sync-log.md`" in mark
    # Every thread read is listed, re-reads with nothing new too, or a thread
    # ingested on its newest message's day comes back for the whole window.
    assert "thread IDs of **every** thread the run read" in text
    assert "read again under **List new**'s same-day rule with nothing new" in text
    assert "IDs of every thread it read" in mark and "read again with nothing new" in mark
    resolve = _section(text, "Resolve citation")
    assert "dated on or after the cited message date" in resolve and "subject matches" in resolve
    assert "7 days before `last_checked_<key>`" in new and "8 days before `last_checked_<key>`" in new
    assert "after:2026/08/29" in new and "-label:wiki-ingested" not in new
    assert "`; thread IDs: …`" in new and "**later than**" in new
    # A thread read before the move (no recorded ID, maybe still labelled)
    # counts as ingested up to the dates pages' sources: cite; its newest
    # message date comes from thread dates, so a new reply in it is found.
    assert "counts as ingested up to the cited dates" in new
    # Cited dates are days: a reply later on the cited day is read too.
    assert "on the newest cited date or later" in new
    assert "come back once" not in text
    for name in ("Check", "List new", "Fetch", "Mark ingested", "Cite", "Resolve citation"):
        assert "mcp__" not in _section(text, name), name
    assert "label_thread" not in text.split("## Bind", 1)[0] and "create_label" not in mark


@pytest.mark.checks("bind-reader/bind-extras")
def test_skill_carries_bind_extras():
    """A contract's `## Bind` may add denies, `## Reader` lines and settings
    lines (ms-teams: Outlook and people tools, the folder mode, the
    snapshot allow); the skill carries them, in words that name no source."""
    text = SKILL.read_text(encoding="utf-8")
    deny = text[text.index("## 4. Deny the write tools first"):text.index("## 5. Test each operation")]
    hand = text[text.index("## 6. Hand over"):]
    assert "any other tools the contract's `## Bind` section says to deny" in deny
    assert "plus any the `## Bind` section says to deny" in hand
    assert "plus any lines the `## Bind` section says to record" in hand
    assert "plus any settings lines the `## Bind` section names" in hand
    body = text.split("\n---\n", 1)[1]
    assert not re.search(r"teams|outlook|Microsoft", body, re.I)


def _check(t):
    return _section((SOURCES / t / "SOURCE.md").read_text(encoding="utf-8"), "Check")


TOOL_NAMED = ["gmail", "jira", "ms-teams", "google-drive"]
# What a contract or the skill quotes from `sources.sh show`, with the contracts that quote it.
QUOTED = {
    "this session: cloud": TOOL_NAMED,
    "Reader tools and their cloud names": TOOL_NAMED,
    "cloud: denied": TOOL_NAMED,
    "cloud: unknown": TOOL_NAMED,
    "cloud rules missing from .claude/settings.json": TOOL_NAMED,
}


def _show_cloud(tmp_path):
    """`sources.sh show` of a gmail, a jira and a google-drive instance in a cloud session."""
    w = copytree(TESTS / "guard-wiki", tmp_path / "gw")
    git(w, "init", "-q")
    g = "mcp__claude_ai_Google_Drive__"
    write(w / ".claude/sources/instances/drive.md",
          "---\nkey: drive\ntype: google-drive\nfolders:\n  - Receipts (1AbCdEf)\nstate:\n  - last_checked\nreader:\n"
          + "".join("  - %s\n" % r for r in ("get item: %sget_file_metadata" % g, "list folder: %ssearch_files" % g,
                                             "search by name: %ssearch_files" % g,
                                             "read file: %sread_file_content" % g,
                                             "download file: %sdownload_file_content" % g))
          + "reader_deny:\n  - %strash_file\n---\n" % g)
    return w


def test_contracts_quote_show_output(tmp_path, cli):
    """Each string the contracts and the skill quote from `sources.sh show`
    in a cloud session is in its real output, and in the contracts."""
    w = _show_cloud(tmp_path)
    out, heads = "", []
    # proton is unbound: the session line comes for it too.
    for k in ("gmail", "tracker", "drive", "proton"):
        r = cli("sources", "show", k, cwd=w, env={"CLAUDE_CODE_REMOTE": "true"})
        assert r.rc == 0, r
        out += r.out.decode("utf-8", "surrogateescape")
        heads.append(r.out.decode("utf-8", "surrogateescape").split("=====")[0])
    assert len(heads) == 4 and all("this session: cloud" in h for h in heads), heads
    assert "bind it in a local session" in heads[3], heads
    skill = SKILL.read_text(encoding="utf-8")
    assert "this session: cloud" in skill
    for quoted, types in QUOTED.items():
        assert quoted in out, quoted
        for t in types:
            assert quoted in (SOURCES / t / "SOURCE.md").read_text(encoding="utf-8"), (t, quoted)


@pytest.mark.parametrize("t", TOOL_NAMED)
def test_name_rule_outside_check(t):
    """The cloud-name rule is in the contract's intro, which every ingest
    follows (Check runs only on a first ingest), and Check refers to it."""
    text = (SOURCES / t / "SOURCE.md").read_text(encoding="utf-8")
    outside = text.replace(_section(text, "Check"), "")
    assert "call each bound tool under its bound name" in outside
    assert "this session: cloud" in outside and "cloud: unknown" in outside
    assert "this session: cloud" in _section(text, "Check")


def test_jira_denied_in_fetch():
    text = (SOURCES / "jira" / "SOURCE.md").read_text(encoding="utf-8")
    assert "cloud: denied" in _section(text, "Fetch") and "cloud: denied" in _section(text, "Check")


# Google Drive's cloud name hasn't been seen, so it is not in connectors.md.
UNPAIRED = {"claude_ai_Google_Drive"}
_SERVER = re.compile(r"mcp__([A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)*)__")


def _bind_notes():
    return {t: _section((SOURCES / t / "SOURCE.md").read_text(encoding="utf-8"), "Bind")
            for t in _tool_neutral()}


def test_connector_pairs_in_bind_notes():
    """Each pair's local and cloud server appear, backticked, in some
    tool-neutral contract's ## Bind."""
    notes = " ".join(_bind_notes().values())
    for local, cloud in sourcelib.connector_pairs(posix(PLUGIN)).items():
        assert "`mcp__%s__`" % local in notes, local
        assert "`mcp__%s__`" % cloud in notes, cloud


def test_bind_servers_paired():
    pairs = sourcelib.connector_pairs(posix(PLUGIN))
    known = set(pairs) | set(pairs.values())
    assert not UNPAIRED & known, "a connector in connectors.md is no longer unpaired"
    for t, bind in _bind_notes().items():
        for srv in _SERVER.findall(bind.replace("mcp__<server>__", "")):
            assert srv in known | UNPAIRED, (t, srv)
