"""The core is source- and reader-neutral (docs/adr.md, 2): its code holds
no standard type's name and no claude.ai connector's server name. Skills
and the schema are prose, where an "e.g." example is fine; the review
checks those. The allowlist names each known deviation and why."""

import re

import pytest

from conftest import TESTS

REPO = TESTS.parent
PLUGIN = REPO / "plugins" / "wiki"
TYPES = sorted(p.name for p in (PLUGIN / "sources").iterdir() if (p / "SOURCE.md").is_file())
SERVERS = ["claude_ai_", "Atlassian", "Microsoft_365"]
CORE = sorted([*(PLUGIN / "scripts").glob("*.py"), *(PLUGIN / "scripts").glob("*.sh"),
               *(PLUGIN / "hooks").iterdir(), PLUGIN / "templates" / "project-settings.json"])

# file -> names it may contain, each with its reason.
ALLOWED = {
    # an "e.g." in the agent_only docstring; onenote's reader as the example of
    # a script a session must run
    "guard.py": {"codebase", "onenote"},
    # codebase-instance: the codebase wrappers' instance reader in core
    # (a deviation; it belongs with the codebase type)
    # and, in its docstring, a connector's names as the example of a pair
    # from sources/connectors.md (docs/adr.md, 2 and 17)
    "sourcelib.py": {"codebase", "claude_ai_"},
    "lib-source.sh": {"codebase", "local-folder"},
}


def names_in(text):
    found = {t for t in TYPES if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(t), text, re.I)}
    return found | {s for s in SERVERS if s.lower() in text.lower()}


def test_core_list_is_not_empty():
    assert TYPES and len(CORE) > 10


@pytest.mark.parametrize("path", CORE, ids=lambda p: p.name)
def test_core_names_no_source(path):
    extra = names_in(path.read_text(encoding="utf-8")) - ALLOWED.get(path.name, set())
    assert not extra, "%s names %s: source details belong in SOURCE.md (docs/adr.md, 2)" % (
        path.relative_to(REPO), ", ".join(sorted(extra)))


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_allowlist_is_current(name):
    path = PLUGIN / "scripts" / name
    assert ALLOWED[name] <= names_in(path.read_text(encoding="utf-8")), (
        "%s no longer names all of %s; shrink the allowlist" % (name, sorted(ALLOWED[name])))
