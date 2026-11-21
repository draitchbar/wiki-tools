"""/wiki:bind-reader and the tool-neutral contracts it binds
(docs/plans/reader-binding.md, phase 2): every access: tools contract
has a ## Bind section and sends Check to the skill, and the skill is
model-invocable with only sources.sh pre-allowed."""

import re

import pytest

import contract
from conftest import PLUGIN, posix

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
    assert _tool_neutral() == ["google-drive", "jira", "onenote", "proton-files"]


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
