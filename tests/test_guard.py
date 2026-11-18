"""The guard (guard.py): every hook fixture, the hooks.json command, and the
guard failing closed on broken source files (formerly the guard-fixtures and
guard-broken sections of run-tests.sh).

Fixtures live in tests/fixtures/<group>/<pass|block>-<case>.json (group push
or guard). "pass" expects exit 0, "block" 2; a <case>.msg beside it holds
the exact message (@PLUGIN@ the plugin folder as bash prints it,
@PLUGIN_DRIVE@ as Claude Code substitutes it on Windows, C:/...; @WIKI@ the
test wiki). They run on a copy of tests/guard-wiki with HOME=/home/u, the
home the fixtures use; in-process, or with --e2e through hooks.json's
command and py-launch.sh.
"""

import json
import os
import shutil
from pathlib import Path

import guard
import hookjson
import pytest

from conftest import (BASH, IS_WIN, PLUGIN, PLUGIN_BASH, PLUGIN_P, TESTS, call_main, copytree,
                      hooks_guard_command, norm, write)

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
        if case.startswith(("pass-", "block-")):
            out.append(pytest.param(f, id="%s/%s" % (f.parent.name, case)))
    return out


def _message(r, wiki):
    return norm(r.err.decode("utf-8", errors="surrogateescape").rstrip("\n"), wiki)


@pytest.mark.parametrize("fixture", _fixture_params())
def test_fixture(fixture, gw, guard_run):
    wiki = str(gw).replace("\\", "/")
    data = subst(fixture.read_bytes().decode("utf-8"), wiki)
    r = guard_run(data, wiki)
    assert r.rc == (0 if fixture.stem.startswith("pass-") else 2), r


@pytest.mark.parametrize("fixture", [pytest.param(f, id="%s/%s (message)" % (f.parent.name, f.stem))
                                     for f in sorted(FIXTURES.glob("*/*.json"))
                                     if f.with_suffix(".msg").is_file()])
def test_fixture_message(fixture, gw, guard_run):
    wiki = str(gw).replace("\\", "/")
    r = guard_run(subst(fixture.read_bytes().decode("utf-8"), wiki), wiki)
    want = subst(fixture.with_suffix(".msg").read_bytes().decode("utf-8"), wiki).rstrip("\n")
    assert _message(r, wiki) == norm(want, wiki)


@pytest.mark.parametrize("msg", [pytest.param(m, id="fixtures/%s has a fixture" % m.name)
                                 for m in sorted(FIXTURES.glob("*/*.msg"))])
def test_message_has_fixture(msg):
    assert msg.with_suffix(".json").is_file()


# --- the checks: an ordered list, each one tested -------------------------

@pytest.mark.checks("guard/no-push-first")
def test_no_push_first():
    """git push is checked before anything else can decide."""
    assert guard.CHECKS[0] is guard.no_push


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
        contents=("", ""), pattern=" ", subagent="", cwd="/home/u/wikis/mywiki", tool="Bash"),
        id="hookjson/parse-bash"),
    pytest.param("guard/block-powershell-multiline.json", dict(
        kind="shell", shell="powershell", command="Get-Date;proton-drive ls", paths=(),
        contents=("", ""), pattern=" ", subagent="", cwd="C:\\Users\\u\\wikis\\mywiki",
        tool="PowerShell"),
        id="hookjson/parse-powershell"),
    pytest.param("guard/block-edit-helper-content.json", dict(
        kind="write", shell="", command="", paths=("/home/u/wikis/mywiki/tool.py",),
        contents=("", 'os.system("proton-drive fs trash /x")'), pattern=" ", subagent="",
        cwd="/home/u/wikis/mywiki", tool="Edit"),
        id="hookjson/parse-edit"),
    pytest.param("guard/block-write-no-path.json", dict(
        kind="write", shell="", command="", paths=(), contents=("x", ""), pattern=" ",
        subagent="", cwd="/home/u/wikis/mywiki", tool="Write"),
        id="hookjson/parse-write-no-path"),
    pytest.param("guard/block-codebase-grep-main.json", dict(
        kind="read", shell="", command="", paths=("/home/u/src/components",), contents=("", ""),
        pattern="foo ", subagent="", cwd="/home/u/wikis/mywiki", tool="Grep"),
        id="hookjson/parse-grep"),
    pytest.param("guard/pass-codebase-read-agent.json", dict(
        kind="read", shell="", command="", paths=("/home/u/src/components/app/A.java",),
        contents=("", ""), pattern=" ", subagent="a1", cwd="/home/u/wikis/mywiki", tool="Read"),
        id="hookjson/parse-read-subagent"),
])
def test_parse(path, want):
    assert _parsed(path) == want


@pytest.mark.checks("hookjson/parse-multiedit")
def test_parse_multiedit():
    data = _bash_input("MultiEdit", {"file_path": "/home/u/wikis/mywiki/a.py", "edits": [
        {"old_string": "a", "new_string": "b\tc"}, {"old_string": "d", "new_string": "e\nf"}]})
    call = hookjson.parse(data.encode("utf-8"))
    assert (call.kind, call.paths, call.contents) == ("write", ("/home/u/wikis/mywiki/a.py",),
                                                      ("", "", "b c", "e;f"))


@pytest.mark.parametrize("path", [pytest.param(p, id="hookjson/parse-none-" + p.split("/")[1][:-5])
                                  for p in ("push/block-non-string-command.json",
                                            "push/block-malformed.json")])
def test_parse_none(path):
    assert hookjson.parse((FIXTURES / path).read_bytes()) is None


@pytest.mark.checks("hookjson/parse-other-tool")
def test_parse_other_tool():
    call = hookjson.parse(_bash_input("WebFetch", {"url": "https://example.com"}).encode())
    assert (call.kind, call.shell, call.paths) == ("", "", ())


# --- hooks.json: one guard command, run as Claude Code runs it ------------

HOOKS = (PLUGIN / "hooks" / "hooks.json").read_text()


@pytest.mark.checks("py-launch/hooks-json-guard")
def test_hooks_json_guard():
    assert hooks_guard_command()


@pytest.mark.checks("py-launch/hooks-json-matcher")
def test_hooks_json_matcher():
    matchers = [h["matcher"] for h in json.loads(HOOKS)["hooks"]["PreToolUse"]]
    assert matchers == ["Bash|PowerShell|Write|Edit|MultiEdit|Read|Grep|Glob"]


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
}


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
    ("kelvin-sign", 0, None, gbash("cat x/hoo%ss.json" % KELVIN), None),
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
