"""The skills that run save.sh (docs/adr.md, 26): /wiki:save and the
unattended ingest. What they may run is fixed in their allowed-tools, and
the conflict rules live in one place, the save skill."""

import json
import re

import pytest

from conftest import PLUGIN_BASH, TESTS, posix
from test_guard import gbash, gw  # noqa: F401

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
    # Conflicts step 3 aborts a merge: the same exact form as ingest's.
    assert "Bash(git merge --abort)" in _tools(path)
    assert "Bash(git merge --abort)" in _tools(SKILLS / "ingest" / "SKILL.md")


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
    assert "same date: keep the remote's state lines" in rules
    ingest = (SKILLS / "ingest" / "SKILL.md").read_text(encoding="utf-8")
    assert "skills/save/SKILL.md" in ingest and "**Conflicts**" in ingest
    assert "| `raw/sync-log.md` |" not in ingest, "the rule table lives in the save skill only"


@pytest.mark.checks("save-skill/permission")
def test_permission_flow():
    save = (SKILLS / "save" / "SKILL.md").read_text(encoding="utf-8")
    perm = save[save.index("## Permission"):save.index("## Conflicts")]
    assert perm.index("`look:`") < perm.index("`run:` line")
    assert "plain **Yes**" in perm and "don't ask again" in perm
    # The way out where no call can be run: the guard's limits and the
    # word push are named.
    assert "50 paths or 2000 characters" in perm and "the word `push`" in perm
    run = save[save.index("## 1. Run it"):save.index("## Permission")]
    assert "never goes on to the permission call" in run
    assert "fresh `look:` line" in run
    assert "merge it, then delete the branch" in run


@pytest.mark.checks("save-skill/init-lines")
def test_init_writes_save_lines():
    init = (SKILLS / "init" / "SKILL.md").read_text(encoding="utf-8")
    assert "!.claude/settings.wiki-save.json" in init
    assert "wiki/log.md merge=union" in init
    assert "## Turning saving on" in init


def _guard(folder, guard_run, cmd):
    # Forward slashes, as test_guard spells the wiki: a native Windows path
    # put into the JSON text raw would hold invalid \ escapes.
    wiki = posix(folder)
    return guard_run(gbash(cmd).replace("/home/u/wikis/mywiki", wiki), wiki)


@pytest.mark.checks("save-skill/forms-pass-guard")
@pytest.mark.parametrize("skill", ["save", "ingest"])
def test_allowed_forms_pass_guard(skill, gw, guard_run):  # noqa: F811
    """Each save.sh form a skill may run, with the plugin root filled in as
    Claude Code does, passes the guard plainly (no refusal, no "ask")."""
    forms = [t[len("Bash("):-1].replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN_BASH)
             for t in _save_tools(SKILLS / skill / "SKILL.md")]
    assert forms
    for cmd in forms:
        r = _guard(gw, guard_run, cmd)
        assert (r.rc, r.out, r.err) == (0, b"", b""), (cmd, r)


@pytest.mark.checks("save-skill/allow-asks")
def test_allow_call_asks(gw, guard_run):  # noqa: F811
    cmd = "bash %s/scripts/save.sh --allow .claude/settings.wiki-save.json .mcp.json CLAUDE.md" % PLUGIN_BASH
    r = _guard(gw, guard_run, cmd)
    assert r.rc == 0 and r.err == b""
    assert json.loads(r.out)["hookSpecificOutput"]["permissionDecision"] == "ask"


# The diff forms the save skill's Permission step prescribes pass; the
# file forms they replace are refused (protected path, or "push").
@pytest.mark.checks("save-skill/look-forms")
@pytest.mark.parametrize("cmd,rc", [
    ("git diff 1a2b3c4 5d6e7f8 -- .claude", 0),
    ("git log --oneline 1a2b3c4..5d6e7f8 -- .claude", 0),
    ("git diff 1a2b3c4 5d6e7f8 -- .", 0),
    ("git diff 1a2b3c4 5d6e7f8 -- templates", 0),
    ("git diff 1a2b3c4 5d6e7f8 -- .claude/settings.wiki-save.json", 2),
    ("git diff 1a2b3c4 5d6e7f8 -- .mcp.json", 2),
    ("git diff 1a2b3c4 5d6e7f8 -- templates/push-plan.md", 2),
])
def test_look_forms(cmd, rc, gw, guard_run):  # noqa: F811
    assert _guard(gw, guard_run, cmd).rc == rc
