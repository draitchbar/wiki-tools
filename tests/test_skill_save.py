"""The skills that run save.sh (docs/adr.md, 26): /wiki:save and the
unattended ingest. What they may run is fixed in their allowed-tools, and
the conflict rules live in one place, the save skill."""

import re

import pytest

from conftest import TESTS

PLUGIN = TESTS.parent / "plugins" / "wiki"
SKILLS = PLUGIN / "skills"
SAVE = "Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/save.sh"


def _frontmatter(path):
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    assert m, "frontmatter"
    return m.group(1)


def _tools(path):
    return re.findall(r"^  - (.*)$", _frontmatter(path).split("allowed-tools:", 1)[1], re.M)


def _save_tools(path):
    return [t for t in _tools(path) if t.startswith(SAVE)]


@pytest.mark.checks("save-skill/frontmatter")
def test_save_skill_frontmatter():
    path = SKILLS / "save" / "SKILL.md"
    fm = _frontmatter(path)
    assert re.search(r"^name: save$", fm, re.M)
    assert "disable-model-invocation" not in fm, "model-invocable: an ingest offers it"
    # Exact forms only: --allow is never pre-approved (the guard asks),
    # and the unattended forms belong to ingest.
    assert _save_tools(path) == [SAVE + ")", SAVE + " --check)"]
    assert "Bash(git push" not in fm


@pytest.mark.checks("save-skill/ingest-forms")
def test_ingest_save_forms():
    path = SKILLS / "ingest" / "SKILL.md"
    assert _save_tools(path) == [SAVE + " --update --unattended)", SAVE + " --unattended)"]
    text = path.read_text(encoding="utf-8")
    assert "save.sh --update --unattended" in text and "save.sh --unattended" in text
    assert "--allow" not in text, "an unattended run can't answer a prompt"


@pytest.mark.checks("save-skill/no-other-skill")
def test_only_save_and_ingest_run_save():
    users = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md")
                   if "scripts/save.sh" in p.read_text(encoding="utf-8"))
    assert users == ["ingest", "save"]


@pytest.mark.checks("save-skill/conflict-rules-once")
def test_conflict_rules_in_one_place():
    save = (SKILLS / "save" / "SKILL.md").read_text(encoding="utf-8")
    rules = save[save.index("## Conflicts"):]
    for f in ("`raw/sync-log.md`", "`open-questions.md`", "`wiki/index.md`", "Anything else"):
        assert "| %s" % f in rules or "| Pages under `wiki/`, %s" % f in rules, f
    assert "| merge |" in rules and "git commit --no-edit" in rules
    ingest = (SKILLS / "ingest" / "SKILL.md").read_text(encoding="utf-8")
    assert "skills/save/SKILL.md" in ingest and "**Conflicts**" in ingest
    assert "| `raw/sync-log.md` |" not in ingest, "the rule table lives in the save skill only"


@pytest.mark.checks("save-skill/permission")
def test_permission_flow():
    save = (SKILLS / "save" / "SKILL.md").read_text(encoding="utf-8")
    perm = save[save.index("## Permission"):save.index("## Conflicts")]
    assert perm.index("`look:`") < perm.index("`run:` line")
    assert "plain **Yes**" in perm and "don't ask again" in perm


@pytest.mark.checks("save-skill/init-lines")
def test_init_writes_save_lines():
    init = (SKILLS / "init" / "SKILL.md").read_text(encoding="utf-8")
    assert "!.claude/settings.wiki-save.json" in init
    assert "wiki/log.md merge=union" in init
    assert "## Turning saving on" in init
