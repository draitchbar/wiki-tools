"""The files coding agents read (docs/adr.md, 10): rules and skills are
written once for Claude Code and Copilot CLI. CLAUDE.md only imports
AGENTS.md, which imports CONTRIBUTING.md; no instruction or skill files only
one agent reads; skills in .claude/skills/ have the frontmatter both need,
and a manual-only skill carries the guard line Copilot needs."""

import subprocess

import pytest

from conftest import TESTS

REPO = TESTS.parent
SKILLS = sorted((REPO / ".claude" / "skills").glob("*/SKILL.md"))
ONE_AGENT_ONLY = [".github/copilot-instructions.md", ".github/instructions", ".github/skills",
                  ".agents", "GEMINI.md", ".claude/CLAUDE.md"]


def frontmatter(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    assert lines[0] == "---", path
    end = lines.index("---", 1)
    fm = {}
    for line in lines[1:end]:
        k, sep, v = line.partition(":")
        if sep and not k.startswith(" "):
            fm[k.strip()] = v.strip()
    return fm, "\n".join(lines[end + 1:])


@pytest.mark.checks("agents/claude-imports-agents")
def test_claude_md_is_the_import():
    assert (REPO / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"


@pytest.mark.checks("agents/agents-imports-contributing")
def test_agents_md_imports_contributing():
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "@CONTRIBUTING.md" in agents.split("\n")
    size = len(agents.encode()) + (REPO / "CONTRIBUTING.md").stat().st_size
    assert size < 8192, "AGENTS.md with CONTRIBUTING.md is %d bytes; keep the rules short" % size


@pytest.mark.checks("agents/policy-once")
@pytest.mark.parametrize("phrase", ["core.hooksPath", "noreply", "--no-verify"])
def test_policy_lives_in_contributing(phrase):
    assert phrase in (REPO / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert phrase not in (REPO / "AGENTS.md").read_text(encoding="utf-8")


@pytest.mark.checks("agents/no-one-agent-files")
def test_no_one_agent_files():
    assert [p for p in ONE_AGENT_ONLY if (REPO / p).exists()] == []


@pytest.mark.checks("agents/no-symlinks")
def test_no_symlinks():
    out = subprocess.run(["git", "ls-files", "-s"], cwd=REPO, capture_output=True, check=True).stdout
    assert [ln for ln in out.decode().split("\n") if ln.startswith("120000 ")] == []


@pytest.mark.checks("agents/skills")
def test_skills():
    assert SKILLS
    for path in SKILLS:
        fm, body = frontmatter(path)
        name = path.parent.name
        assert fm.get("name") == name, path
        assert fm.get("description"), path
        if fm.get("disable-model-invocation") == "true":
            assert "Run only when the user typed `/%s`" % name in body, \
                "%s: manual-only, but no guard line (AGENTS.md, Agents)" % path
