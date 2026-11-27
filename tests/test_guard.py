"""The guard (guard.py): every hook fixture, the hooks.json command, and the
guard failing closed on broken source files (formerly the guard-fixtures and
guard-broken sections of run-tests.sh).

Fixtures live in tests/fixtures/<group>/<pass|block|ask>-<case>.json (group
push or guard). "pass" expects exit 0 and no output, "block" 2, "ask" exit 0
and the "ask" reply on stdout (hookjson.ask); a <case>.msg beside it holds
the exact message (for "ask", the reply's reason) (@PLUGIN@ the plugin folder as bash prints it,
@PLUGIN_DRIVE@ as Claude Code substitutes it on Windows, C:/...; @WIKI@ the
test wiki). They run on a copy of tests/guard-wiki with HOME=/home/u, the
home the fixtures use; in-process, or with --e2e through hooks.json's
command and py-launch.sh.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import guard
import hookjson
import pytest

from conftest import (BASH, IS_WIN, PLUGIN, PLUGIN_BASH, PLUGIN_P, SCRIPTS, TESTS, call_main,
                      copytree, home_env, hooks_guard_command, norm, posix, write)

FIXTURES = TESTS / "fixtures"
GUARD_WIKI = TESTS / "guard-wiki"


def subst(text, wiki):
    return (text.replace("@PLUGIN_DRIVE@", PLUGIN_P).replace("@PLUGIN@", PLUGIN_BASH)
            .replace("@WIKI@", wiki))


@pytest.fixture
def gw(tmp_path):
    return copytree(GUARD_WIKI, tmp_path / "gw")


def _fixture_params():
    out = []
    for f in sorted(FIXTURES.glob("*/*.json")):
        case = f.stem
        if case.startswith(("pass-", "block-", "ask-")):
            out.append(pytest.param(f, id="%s/%s" % (f.parent.name, case)))
    return out


def _message(r, wiki):
    return norm(r.err.decode("utf-8", errors="surrogateescape").rstrip("\n"), wiki)


@pytest.mark.parametrize("fixture", _fixture_params())
def test_fixture(fixture, gw, guard_run):
    wiki = str(gw).replace("\\", "/")
    data = subst(fixture.read_bytes().decode("utf-8"), wiki)
    r = guard_run(data, wiki)
    assert r.rc == (2 if fixture.stem.startswith("block-") else 0), r
    got = _message(r, wiki)
    if r.rc == 0:
        # A pass prints nothing; an ask prints only its reply.
        assert r.err == b"", r
        if fixture.stem.startswith("ask-"):
            got = _ask_reason(r)
        else:
            assert r.out == b"", r
    # The message, when a <case>.msg is beside it: same guard run.
    msg = fixture.with_suffix(".msg")
    if msg.is_file():
        want = subst(msg.read_bytes().decode("utf-8"), wiki).rstrip("\n")
        assert norm(got, wiki) == norm(want, wiki)


def _ask_reason(r):
    """The reason of the "ask" reply on r's stdout, which holds nothing else."""
    reply = json.loads(r.out)
    reason = reply["hookSpecificOutput"].pop("permissionDecisionReason")
    assert reply == {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask"}}
    return reason


@pytest.mark.parametrize("msg", [pytest.param(m, id="fixtures/%s has a fixture" % m.name)
                                 for m in sorted(FIXTURES.glob("*/*.msg"))])
def test_message_has_fixture(msg):
    """Every message is checked (test_fixture): a pass-, block- or ask- fixture beside it."""
    assert msg.with_suffix(".json").is_file() and msg.stem.startswith(("pass-", "block-", "ask-"))


# --- the checks: an ordered list, each one tested -------------------------

@pytest.mark.checks("guard/no-push-first")
def test_no_push_first():
    """git push is checked before anything else can decide."""
    assert guard.CHECKS[0] is guard.no_push


# Saving on (.claude/settings.wiki.json in the working tree, "save":
# {"enabled": true}): the push refusals name /wiki:save; only the wording changes. Any
# other content, or a file that can't be read, keeps the old message. The
# gh refusal never changes.
SAVE_ON = b'{"save": {"enabled": true, "url": "https://example.com/wiki.git", "base": "main"}}'
SAVE_HINT = [
    ("git-push", "push/block-git-push", True),
    ("mcp-github", "push/block-mcp-github-push-files", True),
    ("gh-api", "guard/block-gh-api-put", False),
]
SAVE_CONFIGS = [
    ("on", SAVE_ON, True),
    ("absent", None, False),
    ("other-sections", b'{"later": {"x": 1}, "save": {"enabled": true}}', True),
    ("off", b'{"save": {"enabled": false, "url": "https://example.com/wiki.git"}}', False),
    ("enabled-string", b'{"save": {"enabled": "true"}}', False),
    ("not-object", b'[{"save": {"enabled": true}}]', False),
    ("save-not-object", b'{"save": [{"enabled": true}]}', False),
    # The old, flat format: saving is off, so is the hint.
    ("flat", b'{"enabled": true, "url": "https://example.com/wiki.git", "base": "main"}', False),
    ("truncated", SAVE_ON[:20], False),
    ("not-utf8", b'{"save": {"enabled": true}, "x": "\xff"}', False),
    ("deep", b"[" * 5000 + b"]" * 5000, False),
    ("folder", "folder", False),
    # A FIFO, which open() would wait on (the guard checks for a regular file).
    ("fifo", "fifo", False),
]


@pytest.mark.parametrize("fixture,named,config", [
    pytest.param(f, named and on, config, id="guard/save-hint-%s-%s" % (case, cname))
    for case, f, named in SAVE_HINT for cname, config, on in SAVE_CONFIGS])
def test_save_hint(fixture, named, config, gw, guard_run):
    wiki = str(gw).replace("\\", "/")
    path = gw / ".claude" / "settings.wiki.json"
    if config == "folder":
        path.mkdir(parents=True)
    elif config == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("no FIFOs here")
        path.parent.mkdir(parents=True, exist_ok=True)
        os.mkfifo(path)
    elif config is not None:
        write(path, config)
    r = guard_run(subst((FIXTURES / (fixture + ".json")).read_text(encoding="utf-8"), wiki), wiki)
    assert r.rc == 2
    want = (FIXTURES / (fixture + ".msg")).read_text(encoding="utf-8").rstrip("\n")
    assert _message(r, wiki) == norm(want + (" Or run /wiki:save." if named else ""), wiki)


def _deciding_check(data, wiki):
    """The name of the check that refuses the hook input data, "" if none
    (in-process, on the test wiki, with HOME=/home/u as the fixtures)."""
    got = []

    def run():
        call = hookjson.parse(data.encode("utf-8"))
        if call is not None:
            check = guard.decide(call)[0]
            got.append(check.__name__ if check else "")
    call_main(run, None, env={"HOME": "/home/u", "USERPROFILE": None, "CLAUDE_PROJECT_DIR": wiki})
    return got[0] if got else ""


@pytest.mark.checks("guard/every-check-has-a-fixture")
def test_every_check_has_a_fixture(gw):
    """Each check in CHECKS refuses at least one block- fixture (the broken
    source files of test_fail_closed for broken_sources), so a removed or
    reordered check shows in the fixtures."""
    wiki = str(gw).replace("\\", "/")
    hit = {_deciding_check(subst(f.read_text(encoding="utf-8"), wiki), wiki)
           for f in sorted(FIXTURES.glob("*/block-*.json"))}
    BROKEN["instance-no-frontmatter"](gw)
    hit.add(_deciding_check(ORDINARY, wiki))
    missing = [c.__name__ for c in guard.CHECKS if c.__name__ not in hit]
    assert not missing


def _parsed(path):
    call = hookjson.parse((FIXTURES / path).read_bytes())
    return {k: getattr(call, k) for k in hookjson.HookCall.__slots__}


@pytest.mark.parametrize("path,want", [
    pytest.param("guard/pass-ordinary-bash.json", dict(
        kind="shell", shell="bash", command="pdftotext -layout contract.pdf /tmp/c.txt", paths=(),
        contents=("", ""), pattern=" ", subagent="", cwd="/home/u/wikis/mywiki", tool="Bash", inputs={}),
        id="hookjson/parse-bash"),
    pytest.param("guard/block-powershell-multiline.json", dict(
        kind="shell", shell="powershell", command="Get-Date;proton-drive ls", paths=(),
        contents=("", ""), pattern=" ", subagent="", cwd="C:\\Users\\u\\wikis\\mywiki",
        tool="PowerShell", inputs={}),
        id="hookjson/parse-powershell"),
    pytest.param("guard/block-edit-helper-content.json", dict(
        kind="write", shell="", command="", paths=("/home/u/wikis/mywiki/tool.py",),
        contents=("", "", 'os.system("proton-drive fs trash /x")'), pattern=" ", subagent="",
        cwd="/home/u/wikis/mywiki", tool="Edit", inputs={}),
        id="hookjson/parse-edit"),
    pytest.param("guard/block-write-no-path.json", dict(
        kind="write", shell="", command="", paths=(), contents=("x", "", ""), pattern=" ",
        subagent="", cwd="/home/u/wikis/mywiki", tool="Write", inputs={}),
        id="hookjson/parse-write-no-path"),
    pytest.param("guard/block-codebase-grep-main.json", dict(
        kind="read", shell="", command="", paths=("/home/u/src/components",), contents=("", ""),
        pattern="foo ", subagent="", cwd="/home/u/wikis/mywiki", tool="Grep", inputs={}),
        id="hookjson/parse-grep"),
    pytest.param("guard/pass-codebase-read-agent.json", dict(
        kind="read", shell="", command="", paths=("/home/u/src/components/app/A.java",),
        contents=("", ""), pattern=" ", subagent="a1", cwd="/home/u/wikis/mywiki", tool="Read", inputs={}),
        id="hookjson/parse-read-subagent"),
    # An MCP call: only its top-level string inputs, for the reader limits.
    pytest.param("guard/block-mcp-reader-dispatch-other.json", dict(
        kind="mcp", shell="", command="", paths=(), contents=(), pattern=" ", subagent="",
        cwd="/home/u/wikis/mywiki", tool="mcp__claude_ai_Atlassian_MCP__executeRead",
        inputs={"name": "getConfluencePage", "cloudId": "c1"}),
        id="hookjson/parse-mcp"),
])
def test_parse(path, want):
    assert _parsed(path) == want


@pytest.mark.checks("hookjson/parse-multiedit")
def test_parse_multiedit():
    data = _bash_input("MultiEdit", {"file_path": "/home/u/wikis/mywiki/a.py", "edits": [
        {"old_string": "a", "new_string": "b\tc"}, {"old_string": "d", "new_string": "e\nf"}]})
    call = hookjson.parse(data.encode("utf-8"))
    assert (call.kind, call.paths, call.contents) == ("write", ("/home/u/wikis/mywiki/a.py",),
                                                      ("", "", "", "b c", "e;f"))


@pytest.mark.parametrize("path", [pytest.param(p, id="hookjson/parse-none-" + p.split("/")[1][:-5])
                                  for p in ("push/block-non-string-command.json",
                                            "push/block-malformed.json")])
def test_parse_none(path):
    assert hookjson.parse((FIXTURES / path).read_bytes()) is None


@pytest.mark.parametrize("tool,ti,want", [
    pytest.param("WebFetch", {"url": "https://example.com"}, ("harmless", "", ""),
                 id="hookjson/parse-harmless"),
    pytest.param("mcp__example__search", {"query": "x"}, ("mcp", "", ""), id="hookjson/parse-kind-mcp"),
    pytest.param("LSP", {"file_path": "/home/u/src/components/A.java"}, ("unknown", "", ""),
                 id="hookjson/parse-unknown"),
    pytest.param("Monitor", {"command": "tail -f log.txt", "timeout_ms": 1000},
                 ("shell", "bash", "tail -f log.txt"), id="hookjson/parse-monitor"),
    pytest.param("Monitor", {"ws": {"url": "wss://example.com/x", "protocols": ["a"]}},
                 ("harmless", "", ""), id="hookjson/parse-monitor-ws"),
    pytest.param("Monitor", {"description": "x"}, ("shell", "bash", ""),
                 id="hookjson/parse-monitor-neither"),
])
def test_parse_kind(tool, ti, want):
    call = hookjson.parse(_bash_input(tool, ti).encode())
    assert (call.kind, call.shell, call.command) == want


@pytest.mark.checks("hookjson/parse-notebook-edit")
def test_parse_notebook_edit():
    call = hookjson.parse(_bash_input("NotebookEdit", {
        "notebook_path": "/home/u/wikis/mywiki/a.ipynb", "new_source": "x = 1", "cell_id": "c1",
        "cell_type": "code", "edit_mode": "replace"}).encode())
    assert (call.kind, call.paths, call.contents) == ("write", ("/home/u/wikis/mywiki/a.ipynb",),
                                                      ("", "x = 1", ""))


# Tools the guard doesn't check may carry any JSON under the keys it reads
# for the others; tools it checks may not.
ODD_INPUT = {"content": [{"type": "text", "text": "x"}], "path": 3, "command": {"a": 1},
             "pattern": None, "new_string": ["x"]}


@pytest.mark.parametrize("tool,parsed", [
    pytest.param("mcp__example__write_page", True, id="hookjson/parse-mcp-non-string"),
    pytest.param("TodoWrite", True, id="hookjson/parse-harmless-non-string"),
    pytest.param("NoSuchTool", True, id="hookjson/parse-unknown-non-string"),
    pytest.param("Bash", False, id="hookjson/parse-shell-non-string"),
    pytest.param("Write", False, id="hookjson/parse-write-non-string"),
    pytest.param("Grep", False, id="hookjson/parse-read-non-string"),
])
def test_parse_non_string(tool, parsed):
    assert (hookjson.parse(_bash_input(tool, ODD_INPUT).encode()) is not None) == parsed


@pytest.mark.parametrize("tool,want", [
    pytest.param("mcp__example__write_page", 0, id="guard/mcp-non-string-input"),
    pytest.param("TodoWrite", 0, id="guard/harmless-non-string-input"),
    pytest.param("NoSuchTool", 2, id="guard/unknown-non-string-input"),
])
def test_non_string_input(tool, want, gw, guard_run):
    assert guard_run(_bash_input(tool, ODD_INPUT), str(gw)).rc == want


@pytest.mark.checks("hookjson/harmless-list")
def test_harmless_list():
    """No tool that runs commands, writes or reads files is on the list."""
    assert not hookjson.HARMLESS & {"Bash", "PowerShell", "Monitor", "Write", "Edit", "MultiEdit",
                                    "NotebookEdit", "Read", "Grep", "Glob", "LSP"}


@pytest.mark.checks("hookjson/harmless-names")
def test_harmless_names():
    """The built-in tools a wiki session uses stay allowed, current names and
    legacy ones. One payload of each kind runs through the guard as a
    fixture: pass-harmless-tool, pass-real-agent, pass-task-legacy-agent."""
    assert {"Agent", "Skill", "TaskCreate", "ToolSearch", "EnterWorktree", "ExitWorktree", "TodoWrite",
            "Task", "BashOutput", "KillShell"} <= hookjson.HARMLESS


# --- hooks.json: one guard command, run as Claude Code runs it ------------

HOOKS = (PLUGIN / "hooks" / "hooks.json").read_text()


@pytest.mark.checks("py-launch/hooks-json-guard")
def test_hooks_json_guard():
    assert hooks_guard_command()


@pytest.mark.checks("py-launch/hooks-json-matcher")
def test_hooks_json_matcher():
    matchers = [h["matcher"] for h in json.loads(HOOKS)["hooks"]["PreToolUse"]]
    assert matchers == ["*"]


@pytest.mark.checks("hooks-json/sync-status-matcher")
def test_hooks_json_sync_status_matcher():
    """The sync status (and its open-questions reminder) runs at startup and
    after /clear, not on resume or compaction."""
    groups = [g for g in json.loads(HOOKS)["hooks"]["SessionStart"]
              if any("sync-status.sh" in h["command"] for h in g["hooks"])]
    assert [g.get("matcher") for g in groups] == ["startup|clear"]


@pytest.mark.parametrize("tool,ti,want", [
    pytest.param("Monitor", {"command": "git push"}, 2, id="py-launch/hooks-json-monitor-push"),
    pytest.param("Monitor", {"ws": {"url": "wss://example.com/x"}}, 0, id="py-launch/hooks-json-monitor-ws"),
    pytest.param("NotebookEdit", {"notebook_path": "/home/u/Scans/a.ipynb", "new_source": "x"}, 2,
                 id="py-launch/hooks-json-notebook-edit-root"),
    pytest.param("mcp__example__search", {"query": ["x"]}, 0, id="py-launch/hooks-json-mcp"),
    pytest.param("WebSearch", {"query": "x"}, 0, id="py-launch/hooks-json-harmless"),
    pytest.param("LSP", {"file_path": "/home/u/src/components/A.java"}, 2,
                 id="py-launch/hooks-json-unknown"),
])
def test_hooks_json_every_tool(tool, ti, want, gw, guard_run):
    """The matcher sends every tool to the guard; through hooks.json's
    command, whatever --e2e says."""
    assert guard_run(_bash_input(tool, ti), str(gw), e2e_only=True).rc == want


@pytest.mark.checks("py-launch/hooks-json-guard-once")
def test_hooks_json_guard_once():
    assert sum("py-launch" in ln for ln in HOOKS.splitlines()) == 1


def _shell(name):
    """sh, bash or dash as Claude Code would find it, or None."""
    if IS_WIN:
        p = Path(BASH).parent / (name + ".exe")
        return str(p) if p.is_file() else None
    return shutil.which(name)


# Claude Code runs hook commands with sh, which on Linux is often dash: its
# "." ignores arguments, so the command sources the launcher only under bash
# and otherwise runs it with bash (found 2026-11-07 in a real session).
@pytest.mark.parametrize("sh,cmd,want", [
    pytest.param(sh, cmd, want, id="py-launch/hooks-json-under-%s-%s" % (sh, kind))
    for sh in ("sh", "bash", "dash")
    for kind, cmd, want in (("push", "git push", 2), ("pass", "ls", 0))])
def test_hooks_json_under_shell(sh, cmd, want, run, gw, tmp_path):
    exe = _shell(sh)
    if not exe:
        pytest.skip("no %s" % sh)
    data = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/tmp"})
    r = run([exe, "-c", hooks_guard_command()], input=data.encode(), merged=True,
            env={"CLAUDE_PLUGIN_ROOT": PLUGIN_BASH, "CLAUDE_PLUGIN_DATA": str(tmp_path / "pdata"),
                 "CLAUDE_PROJECT_DIR": str(gw)})
    assert r.rc == want, r
    if want == 2:
        assert r.merged.startswith(b"wiki guard: git push is not allowed")
    else:
        assert r.merged == b""


@pytest.mark.checks("guard/crash-blocks")
def test_crash_blocks(run, gw, tmp_path):
    """guard.py's last resort: an exception blocks (exit 2), never passes.
    A copy of the plugin whose hookjson.parse raises."""
    plug = copytree(PLUGIN, tmp_path / "plug")
    hj = plug / "scripts" / "hookjson.py"
    write(hj, hj.read_text() + "\n\ndef parse(data):\n    raise RuntimeError('boom')\n")
    r = run(["bash", "-c", hooks_guard_command()], merged=True, input=b'{"tool_name":"Bash"}',
            env={"CLAUDE_PLUGIN_ROOT": str(plug).replace("\\", "/"),
                 "CLAUDE_PLUGIN_DATA": str(tmp_path / "pdata"), "CLAUDE_PROJECT_DIR": str(gw)})
    assert r.rc == 2
    assert b"guard.py failed (RuntimeError); refusing (fail closed)." in r.merged


# --- a plugin that runs from a git clone (the cloud setup script's) --------

def _clone_cases():
    """(id, git clone?, tool, input with @TOP@ the clone, want). Reads of the
    clone follow the plugin root's rules: refused in a shell command (its
    text names a protected path), allowed through Read."""
    top, plug = "@TOP@", "@TOP@/plugins/wiki"
    return [
        ("checkout", True, "Bash", {"command": "git -C %s checkout x" % top}, 2),
        ("git-dir", True, "Bash", {"command": "git --git-dir=%s/.git reset --hard x" % top}, 2),
        ("rev-parse", True, "Bash", {"command": "git -C %s rev-parse --short HEAD" % top}, 2),
        ("tilde", True, "Bash", {"command": "git -C ~/clone checkout x"}, 2),
        ("write-git", True, "Write", {"file_path": top + "/.git/HEAD", "content": "x"}, 2),
        ("write-top", True, "Edit", {"file_path": top + "/README.md", "old_string": "a",
                                     "new_string": "b"}, 2),
        ("read-git-head", True, "Read", {"file_path": top + "/.git/HEAD"}, 0),
        ("ordinary", True, "Bash", {"command": "git status"}, 0),
        ("core-script", True, "Bash", {"command": "bash %s/scripts/sources.sh list" % plug}, 0),
        ("no-git", False, "Bash", {"command": "git -C %s checkout x" % top}, 0),
    ]


@pytest.mark.parametrize("git_clone,tool,ti,want", [
    pytest.param(*c[1:], marks=pytest.mark.checks("guard/clone-" + c[0]), id=c[0])
    for c in _clone_cases()])
def test_plugin_clone(git_clone, tool, ti, want, run, gw, tmp_path):
    """The guard of a plugin at <top>/plugins/wiki, <top> a git clone (it
    has .git): <top> is protected as the plugin folder is, so a session
    can't check out another commit or edit .git/ to change its own guard.
    Run through hooks.json's command from a copy of the plugin."""
    top = tmp_path / "clone"
    plug = copytree(PLUGIN, top / "plugins" / "wiki")
    if git_clone:
        (top / ".git").mkdir()
    data = json.dumps({"session_id": "t", "cwd": posix(gw), "hook_event_name": "PreToolUse",
                       "tool_name": tool, "tool_use_id": "x",
                       "tool_input": json.loads(json.dumps(ti).replace("@TOP@", posix(top)))})
    env = dict(home_env(posix(tmp_path)), CLAUDE_PLUGIN_ROOT=posix(plug),
               CLAUDE_PLUGIN_DATA=str(tmp_path / "pdata"), CLAUDE_PROJECT_DIR=posix(gw))
    cmd = ("unset HOME; " if IS_WIN else "") + hooks_guard_command()
    r = run(["bash", "-c", cmd], env=env, input=data.encode("utf-8"))
    assert r.rc == want, r
    if want:
        assert b"protected" in r.err


@pytest.mark.checks("guard/no-typing-at-run-time")
def test_no_typing_at_run_time():
    """AGENTS.md's run-time rule: the guard's modules import `typing` only
    under TYPE_CHECKING, so a hook never pays for it. Imported as
    py-launch.sh runs the guard (-I -S -X utf8)."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import guard; "
            "sys.exit(1 if 'typing' in sys.modules else 0)")
    r = subprocess.run([sys.executable, "-I", "-S", "-X", "utf8", "-c", code, str(SCRIPTS)],
                       capture_output=True)
    assert (r.returncode, r.stderr) == (0, b"")


# --- guard-broken: fails closed on source files it can't use --------------

def _bash_input(tool, tool_input, cwd="/home/u/wikis/mywiki", extra=None):
    d = {"session_id": "t", "cwd": cwd, "hook_event_name": "PreToolUse"}
    d.update(extra or {})
    d.update(tool_name=tool, tool_input=tool_input, tool_use_id="x")
    return json.dumps(d, ensure_ascii=False)


def gbash(cmd):
    return _bash_input("Bash", {"command": cmd})


ORDINARY = (FIXTURES / "guard" / "pass-ordinary-bash.json").read_text()
INST = Path(".claude/sources/instances")


def inst(wiki, key, typ, *lines):
    write(wiki / INST / (key + ".md"),
          "---\nkey: %s\ntype: %s\n%sstate:\n  - last_checked\n---\n"
          % (key, typ, "".join(ln + "\n" for ln in lines)))


def _shadow(w):
    (w / ".claude/sources/types/gmail").mkdir(parents=True)
    shutil.copy(w / ".claude/sources/types/bookish/SOURCE.md", w / ".claude/sources/types/gmail/")


BROKEN = {
    "instance-no-frontmatter": lambda w: write(w / INST / "x.md", "key: x\n"),
    "instance-unknown-type": lambda w: write(w / INST / "x.md", "---\nkey: x\ntype: nosuch\n---\n"),
    "local-type-shadows": _shadow,
    "contract-no-frontmatter": lambda w: write(w / ".claude/sources/types/bookish/SOURCE.md", "# no fm\n"),
    "filesystem-no-roots": lambda w: write(w / INST / "x.md", "---\nkey: x\ntype: local-folder\n---\n"),
    "first-of-two": lambda w: (write(w / INST / "a-x.md", "key: a\n"), write(w / INST / "b-x.md", "key: b\n")),
    "reader-item": lambda w: inst(w, "x", "jira", "reader:", "  - search mcp__claude_ai_Atlassian_MCP__x"),
}


# A reader binding that doesn't parse: the MCP tools it names are refused
# too (their limits are unknown); other MCP tools pass. (guard-wiki's gmail
# instance binds the Gmail connector's read tools, so the other tool is one
# that no reader list names.)
def _mcp(tool, **ti):
    return _bash_input(tool, ti)


@pytest.mark.parametrize("item,tool,want", [
    pytest.param("  - find project mcp__claude_ai_Atlassian_MCP__executeRead name=listJiraProjects",
                 "mcp__claude_ai_Atlassian_MCP__executeRead", 2, id="guard/reader-broken-named"),
    pytest.param("  - find project: mcp__claude_ai_Atlassian_MCP__executeRead name=",
                 "mcp__claude_ai_Atlassian_MCP__executeRead", 2, id="guard/reader-broken-limit"),
    pytest.param("  - find project mcp__claude_ai_Atlassian_MCP__executeRead name=listJiraProjects",
                 "mcp__claude_ai_Google_Calendar__list_events", 0, id="guard/reader-broken-other-tool"),
])
def test_reader_broken(item, tool, want, gw, guard_run):
    inst(gw, "x", "jira", "reader:", item)
    assert guard_run(_mcp(tool, name="listJiraProjects"), str(gw)).rc == want


@pytest.mark.parametrize("lines,ti,agent,want", [
    # Another instance binds the dispatcher without a limit: no limit applies.
    pytest.param(("reader:", "  - search: mcp__claude_ai_Atlassian_MCP__executeRead"),
                 {"name": "getConfluencePage"}, "", 0, id="guard/reader-free-elsewhere"),
    # Another instance's limit adds its value.
    pytest.param(("reader:", "  - search: mcp__claude_ai_Atlassian_MCP__executeRead name=searchJira"),
                 {"name": "searchJira"}, "", 0, id="guard/reader-limit-union"),
    # Values compare exactly.
    pytest.param((), {"name": "listjiraprojects"}, "", 2, id="guard/reader-limit-case"),
    # A subagent is held to the binding too.
    pytest.param((), {"name": "getConfluencePage"}, "a1", 2, id="guard/reader-limit-subagent"),
])
def test_reader_limits(lines, ti, agent, want, gw, guard_run):
    if lines:
        inst(gw, "y", "jira", *lines)
    data = _bash_input("mcp__claude_ai_Atlassian_MCP__executeRead", ti, extra={"agent_id": agent} if agent else None)
    assert guard_run(data, str(gw)).rc == want


@pytest.mark.checks("guard/reader-outside-wiki")
def test_reader_outside_wiki(tmp_path, guard_run):
    """Outside a wiki no binding applies."""
    data = _mcp("mcp__claude_ai_Atlassian_MCP__executeRead", name="getConfluencePage")
    assert guard_run(data, str(tmp_path)).rc == 0


@pytest.mark.parametrize("name", [pytest.param(n, id="guard/fail-closed-%s" % n) for n in BROKEN])
def test_fail_closed(name, gw, guard_run):
    BROKEN[name](gw)
    assert guard_run(ORDINARY, str(gw)).rc == 2


@pytest.mark.checks("guard/fail-closed-first-of-two (message)")
def test_fail_closed_first_of_two_message(gw, guard_run):
    BROKEN["first-of-two"](gw)
    assert "/instances/a-x.md" in _message(guard_run(ORDINARY, str(gw)), str(gw))


# While broken: read-only diagnostics pass, everything else is refused.
P = PLUGIN_BASH
DIAG = [
    ("git-status", 0, "Bash", {"command": "git status"}),
    ("git-diff-sources", 0, "Bash", {"command": "git diff .claude/sources/instances/x.md"}),
    ("git-log", 0, "Bash", {"command": "git log --oneline -5 -- .claude/sources"}),
    ("git-show", 0, "Bash", {"command": "git show HEAD:.claude/sources/instances/x.md"}),
    ("sources-show", 0, "Bash", {"command": "bash %s/scripts/sources.sh show x" % P}),
    ("sources-list", 0, "Bash", {"command": "bash %s/scripts/sources.sh list" % P}),
    ("sources-contract", 0, "Bash", {"command": "bash %s/scripts/sources.sh contract gmail" % P}),
    ("sources-contract-chain", 2, "Bash", {"command": "bash %s/scripts/sources.sh contract gmail && rm -rf wiki" % P}),
    ("sources-list-other-clone", 2, "Bash", {"command": "bash ~/src/wiki-tools/plugins/wiki/scripts/sources.sh list"}),
    ("sources-settings", 2, "Bash", {"command": "bash %s/scripts/sources.sh settings" % P}),
    ("lint", 2, "Bash", {"command": "bash %s/scripts/lint.sh" % P}),
    ("git-diff-output", 2, "Bash", {"command": "git diff --output=/tmp/x"}),
    ("git-status-chain", 2, "Bash", {"command": "git status && rm -rf wiki"}),
    ("git-status-redir", 2, "Bash", {"command": "git status > wiki/x.md"}),
    ("git-commit", 2, "Bash", {"command": "git commit -m x"}),
    ("write-md", 2, "Write", {"file_path": "/home/u/wikis/mywiki/wiki/a.md", "content": "x"}),
]


@pytest.fixture
def gb(tmp_path):
    w = copytree(GUARD_WIKI, tmp_path / "gb")
    write(w / INST / "x.md", "key: x\n")
    return w


@pytest.mark.parametrize("name,want,tool,ti", [pytest.param(*d, id="guard/broken-%s" % d[0]) for d in DIAG])
def test_broken_diagnostics(name, want, tool, ti, gb, guard_run):
    assert guard_run(_bash_input(tool, ti), str(gb)).rc == want


@pytest.mark.checks("guard/broken-message", "guard/broken-message (message)")
def test_broken_message(gb, guard_run):
    r = guard_run(_bash_input("Bash", {"command": "ls"}, cwd="/x"), str(gb))
    assert r.rc == 2
    m = _message(r, str(gb))
    assert 'its first line is "key: x"' in m and "Read still works" in m


WIN_WRITE = _bash_input("Write", {"file_path": "C:\\Users\\u\\Pictures\\Receipts\\a.txt", "content": "x"},
                        cwd="C:\\Users\\u\\wikis\\mywiki")


@pytest.mark.parametrize("home", [pytest.param("/c/Users/u", id="guard/windows-drive-root"),
                                  pytest.param("C:\\Users\\u", id="guard/windows-drive-root-native-home")])
def test_windows_drive_root(home, gw, guard_run):
    assert guard_run(WIN_WRITE, str(gw), home=home).rc == 2


@pytest.fixture
def gc(tmp_path):
    """An agent_only root written with ~, read by the main session as C:\\..."""
    w = copytree(GUARD_WIKI, tmp_path / "gc")
    p = w / INST / "code.md"
    p.write_bytes(p.read_bytes().replace(b"  - /home/u/src/components", b"  - ~/src/components"))
    return w


def _win_read(path, agent=None):
    return _bash_input("Read", {"file_path": path}, cwd="C:\\Users\\u\\wikis\\mywiki",
                       extra={"agent_id": agent} if agent else None)


A_JAVA = "C:\\Users\\u\\src\\components\\app\\A.java"


@pytest.mark.parametrize("data,home,want", [
    pytest.param(_win_read(A_JAVA), "/c/Users/u", 2, id="guard/codebase-read-windows-main"),
    pytest.param(_win_read(A_JAVA, "a1"), "/c/Users/u", 0, id="guard/codebase-read-windows-agent"),
    # ".." at the drive root stays there: C:\..\Users is C:/Users.
    pytest.param(_win_read("C:\\..\\Users\\u\\src\\components\\A.java"), "/c/Users/u", 2,
                 id="guard/codebase-read-windows-dotdot"),
    # A real Windows session hands Python HOME as C:\Users\u.
    pytest.param(_win_read(A_JAVA), "C:\\Users\\u", 2, id="guard/codebase-read-windows-native-home"),
])
def test_codebase_windows(data, home, want, gc, guard_run):
    assert guard_run(data, str(gc), home=home).rc == want


def _win_bash(cmd, tool="Bash"):
    return _bash_input(tool, {"command": cmd}, cwd="C:\\Users\\u\\wikis\\mywiki")


# The user's ~/.claude/skills in every home spelling passes (a skill's
# reader script); the wiki's own .claude/skills stays protected.
@pytest.mark.parametrize("data,home,want", [
    pytest.param(_win_bash("bash /c/Users/u/.claude/skills/x/read.sh list"), "C:\\Users\\u", 0,
                 id="guard/user-skill-slash-form"),
    pytest.param(_win_bash("bash C:/Users/u/.claude/skills/x/read.sh list"), "/c/Users/u", 0,
                 id="guard/user-skill-drive-form"),
    pytest.param(_win_bash("& C:\\Users\\u\\.claude\\skills\\x\\Read.ps1 sections", "PowerShell"),
                 "C:\\Users\\u", 0, id="guard/user-skill-native-form"),
    pytest.param(_win_bash("pwsh -File $HOME/.claude/skills/x/Read.ps1 sections"), "C:\\Users\\u", 0,
                 id="guard/user-skill-home-var"),
    pytest.param(_win_bash("cp x C:/Users/u/wikis/mywiki/.claude/skills/y"), "C:\\Users\\u", 2,
                 id="guard/wiki-skill-under-home"),
    pytest.param(_bash_input("Write", {"file_path": "C:\\Users\\u\\.claude\\skills\\x\\SKILL.md",
                                       "content": "x"}, cwd="C:\\Users\\u\\wikis\\mywiki"),
                 "C:\\Users\\u", 0, id="guard/user-skill-write-native"),
    pytest.param(_bash_input("Write", {"file_path": ".claude\\skills\\x\\SKILL.md", "content": "x"},
                             cwd="C:\\Users\\u\\wikis\\mywiki"),
                 "C:\\Users\\u", 2, id="guard/wiki-skill-write-relative"),
])
def test_user_skills_windows(data, home, want, gw, guard_run):
    assert guard_run(data, str(gw), home=home).rc == want


# Edge cases (most from the review of guard.py), each on a fresh copy.
EM = "\u2003"
KELVIN = "\u212a"
READ_CB = _bash_input("Read", {"file_path": "/home/u/src/components/A.java"})


def _cb_type(w):
    src = (PLUGIN / "sources/codebase/SOURCE.md").read_text(encoding="utf-8")
    src = src.replace("type: codebase", "type: cb", 1).replace("agent_only: yes", "agent_only: yes" + EM, 1)
    write(w / ".claude/sources/types/cb/SOURCE.md", src)
    inst(w, "cb", "cb", "roots:", "  - /home/u/cbsrc")


def _two_types(w):
    for t in ("a-x", "ab"):
        write(w / ".claude/sources/types" / t / "SOURCE.md", "# x\n")


def _copy_inst(src, dst):
    return lambda w: shutil.copy(w / INST / src, w / INST / dst)


CASES = [
    # Unicode whitespace around a contract value is stripped.
    ("unicode-space-root", 2, lambda w: inst(w, "uni", "local-folder", "roots: /home/u/Uni" + EM),
     gbash("cat /home/u/Uni/x"), None),
    ("unicode-space-agent-only", 2, _cb_type,
     _bash_input("Read", {"file_path": "/home/u/cbsrc/A.java"}), None),
    # Unicode whitespace in a command: the guard takes ASCII whitespace only.
    ("unicode-space-command", 2, None, gbash("bash" + EM + PLUGIN_BASH + "/scripts/lint.sh"), None),
    # Lowercasing is ASCII only: messages keep non-ASCII letters, and the
    # Kelvin sign is not a k.
    ("non-ascii-root", 2, lambda w: inst(w, "ae", "local-folder", "roots:", "  - /home/u/Æble"),
     gbash("cat /home/u/Æble/x"), "/home/u/Æble"),
    ("kelvin-sign", 0, None, gbash("boo%sish-cli list" % KELVIN), None),
    # JSON null is an absent field.
    ("null-path", 0, None, _bash_input("Grep", {"pattern": "x", "path": None, "glob": None}), None),
    ("null-agent-id", 2, None, _bash_input("Read", {"file_path": "/home/u/src/components/A.java"},
                                           extra={"agent_id": None}), None),
    # Two broken local types: the first in byte order is named.
    ("first-of-two-types", 2, _two_types, gbash("ls"), "/types/a-x/SOURCE.md"),
    # Instance file names that aren't keys.
    ("instance-key-space", 2, _copy_inst("gmail.md", "gmail scans.md"), gbash("ls"), None),
    ("instance-key-copy", 2, _copy_inst("scans.md", "scans - Copy.md"), gbash("ls"), None),
    # A main-session wrapper call whose key or operation isn't a plain word.
    ("main-op-quoted", 2, None, gbash('bash %s/sources/codebase/git.sh code" "status grep x' % PLUGIN_BASH), None),
    ("main-op-backslash", 2, None, gbash("bash %s/sources/codebase/git.sh code\\ status grep x" % PLUGIN_BASH), None),
]


def _case_params():
    out = []
    for name, want, setup, data, msg in CASES:
        names = ["guard/" + name] + (["guard/%s (message)" % name] if msg else [])
        out.append(pytest.param(want, setup, data, msg, marks=pytest.mark.checks(*names), id=name))
    return out


@pytest.mark.parametrize("want,setup,data,msg", _case_params())
def test_case(want, setup, data, msg, tmp_path, guard_run):
    w = copytree(GUARD_WIKI, tmp_path / "gk")
    if setup:
        setup(w)
    r = guard_run(data, str(w))
    assert r.rc == want, r
    if msg:
        assert msg in _message(r, str(w))


@pytest.mark.checks("guard/wiki-path-space-read")
def test_wiki_path_space(tmp_path, guard_run):
    w = copytree(GUARD_WIKI, tmp_path / "sp ace" / "gw")
    assert guard_run(READ_CB, str(w)).rc == 2


@pytest.mark.checks("guard/unreadable-instances")
def test_unreadable_instances(tmp_path, guard_run):
    """A source folder that can't be listed (not testable as root or on Windows)."""
    w = copytree(GUARD_WIKI, tmp_path / "gu")
    d = w / INST
    os.chmod(d, 0)
    try:
        try:
            os.listdir(d)
            pytest.skip("the folder stays readable here")
        except OSError:
            pass
        assert guard_run(gbash("cat /home/u/Scans/x"), str(w)).rc == 2
    finally:
        os.chmod(d, 0o755)
