"""The validation and lookups behind lib-source.sh's bridge (sourcelib.py,
contract.py), in-process, against the fixture plugin and wiki in
tests/sources/lib-source (formerly the bridged half of run-tests.sh's
lib-source section; its bash helpers, src_field ... src_match_root, stay
end to end in test_bash_scripts.py)."""

import re

import pytest

import contract
import sourcelib
from conftest import TESTS, copytree, git, posix, write


@pytest.fixture
def ls(tmp_path):
    d = copytree(TESTS / "sources" / "lib-source", tmp_path / "ls")
    git(d / "wiki", "init", "-q")
    return posix(d / "wiki"), posix(d / "plugin")


def vc(path):
    """src_validate_contract: (errors as text, exit code)."""
    contract._cache.clear()
    ok, lines = sourcelib.quietly(sourcelib.validate_contract, path)
    return "\n".join(lines), 0 if ok else 1


def vi(w, key, plug):
    contract._cache.clear()
    ok, lines = sourcelib.quietly(sourcelib.validate_instance, w, key, plug)
    return "\n".join(lines), 0 if ok else 1


@pytest.mark.checks("lib-source/instances")
def test_instances(ls):
    w, _ = ls
    assert contract.instances(w) == ["bad-root", "good", "loc1", "missing-param", "unknown-type",
                                     "uses-broken", "wrong-key"]


@pytest.mark.checks("lib-source/contract-std", "lib-source/contract-local", "lib-source/contract-unknown",
                    "lib-source/contract-badname")
def test_contract(ls):
    w, plug = ls
    assert contract.contract(w, "std", plug) == plug + "/sources/std/SOURCE.md"
    assert contract.contract(w, "loc", plug) == w + "/.claude/sources/types/loc/SOURCE.md"
    for t in ("nosuch", "../std"):
        with pytest.raises(contract.ContractError):
            contract.contract(w, t, plug)


@pytest.mark.checks("lib-source/valid-std", "lib-source/cut-body")
def test_validate_contract(ls, tmp_path):
    _, plug = ls
    assert vc(plug + "/sources/std/SOURCE.md") == ("", 0)
    std = (tmp_path / "ls/plugin/sources/std/SOURCE.md").read_text()
    cut = write(tmp_path / "cut/std/SOURCE.md", std[:std.index("## Fetch\n")])
    write(tmp_path / "cut/std/read.sh", "")
    msg, rc = vc(posix(cut))
    assert rc == 1 and "missing section '## Fetch'" in msg and "missing section '## Caveats'" in msg


BAD = [  # name, key, text
    ("missing-param", "missing-param", "required parameter 'roots' is empty"),
    ("relative-root", "bad-root", "root 'relative/path' isn't an absolute path"),
    ("dotdot-root", "bad-root", "root '/data/../etc' contains '.' or '..'"),
    ("wrong-key", "wrong-key", "key 'other' doesn't match the file name"),
    ("unknown-type", "unknown-type", "unknown source type 'nosuch'"),
    ("broken-folder", "uses-broken", "type 'other' doesn't match its folder 'broken'"),
    ("broken-access", "uses-broken", "access must be mcp, script, filesystem or tools"),
    ("broken-platform", "uses-broken", "unknown platform 'beos'"),
    ("broken-state", "uses-broken", "state must include last_checked"),
    ("broken-prefix", "uses-broken", "missing 'cite_prefix'"),
    ("broken-script", "uses-broken", "script name '../evil.sh' must be a plain <name>.sh"),
    ("missing-script", "uses-broken", "script 'missing.sh' is listed but missing"),
]


@pytest.mark.parametrize("key", [pytest.param(k, id="lib-source/valid-" + k) for k in ("good", "loc1")])
def test_valid_instance(key, ls):
    assert vi(*ls[:1], key, ls[1]) == ("", 0)


@pytest.mark.parametrize("key,text", [pytest.param(k, t, id="lib-source/" + n) for n, k, t in BAD])
def test_bad_instance(key, text, ls):
    msg, rc = vi(ls[0], key, ls[1])
    assert rc == 1 and text in msg


@pytest.mark.checks("lib-source/shadowing")
def test_shadowing(ls, tmp_path):
    w, plug = ls
    write(w + "/.claude/sources/types/std/SOURCE.md", (tmp_path / "ls/plugin/sources/std/SOURCE.md").read_bytes())
    msg, rc = vi(w, "good", plug)
    assert rc == 1 and "shadows the standard type" in msg


@pytest.mark.checks("lib-source/crlf")
def test_crlf_instance(ls):
    w, plug = ls
    inst = w + "/.claude/sources/instances/"
    data = open(inst + "good.md", "rb").read().replace(b"\n", b"\r\n").replace(b"key: good", b"key: crlf")
    write(inst + "crlf.md", data)
    assert vi(w, "crlf", plug) == ("", 0)


# Contract keys for research types.
def _variant(tmp_path, name, fm_add, body_add=None):
    std = (tmp_path / "ls/plugin/sources/std/SOURCE.md").read_text()
    text = re.sub(r"(?m)^cite_prefix:", fm_add + "\ncite_prefix:", std, count=1)
    text = re.sub(r"(?m)^type: .*$", "type: " + name, text, count=1)
    if body_add:
        text += "\n## Research\n%s\n" % body_add
    f = write(tmp_path / "rk" / name / "SOURCE.md", text)
    m = re.search(r"(?ms)^scripts:\n((?:  - .*\n)*)", text)
    for s in re.findall(r"  - (.*)", m.group(1)) if m else []:
        write(tmp_path / "rk" / name / s, "")
    return posix(f)


LSC = [
    ("research-ok", "mode: research\nmain_ops:\n  - status", None, "How to research."),
    ("agent-only-fs", "agent_only: yes", "agent_only: yes needs access: filesystem", None),
    ("research-nobody", "mode: research", "mode: research needs a '## Research' section", None),
    ("bad-mode", "mode: sometimes", "mode must be ingest or research", None),
    ("bad-agent-only", "agent_only: maybe", "agent_only must be yes or no", None),
    ("bad-main-op", "main_ops:\n  - rm -rf", "main_ops item '-rf' must be a plain operation name", None),
]


@pytest.mark.parametrize("name,fm_add,text,body", [pytest.param(*c, id="lib-source/" + c[0]) for c in LSC])
def test_research_keys(name, fm_add, text, body, ls, tmp_path):
    msg, rc = vc(_variant(tmp_path, name, fm_add, body))
    if text is None:
        assert (msg, rc) == ("", 0)
    else:
        assert rc == 1 and text in msg


# access: tools names no tools: no scripts or bookkeeping tools, but it may
# deny and guard a CLI its reader wraps (proton-files: its reader wraps proton-drive).
@pytest.fixture
def tools_out(ls, tmp_path):
    std = (tmp_path / "ls/plugin/sources/std/SOURCE.md").read_text()
    text = std.replace("type: std", "type: tl", 1).replace("access: script", "access: tools", 1)
    write(tmp_path / "at/tl/read.sh", "")
    return vc(posix(write(tmp_path / "at/tl/SOURCE.md", text)))


@pytest.mark.checks("lib-source/tools-scripts", "lib-source/tools-forbidden_tools-allowed",
                    "lib-source/tools-guard_words-allowed", "lib-source/tools-read_tools",
                    "lib-source/tools-empty-ok")
def test_tools_rules(tools_out):
    msg, rc = tools_out
    assert rc == 1
    assert "access: tools names no tools, so 'scripts' must be empty" in msg
    assert "so 'forbidden_tools' must be empty" not in msg
    assert "so 'guard_words' must be empty" not in msg
    assert "'read_tools' may hold only Read/Edit rules on ~/.cache/wiki-sources/" in msg
    assert "'bookkeeping_tools' must be empty" not in msg


@pytest.mark.checks("lib-source/tools-valid", "lib-source/tools-cache-rules")
def test_tools_valid(ls, tmp_path):
    std = (tmp_path / "ls/plugin/sources/std/SOURCE.md").read_text()
    out, skip = [], False
    for ln in std.split("\n"):
        if re.match(r"(read_tools|forbidden_tools|guard_words|scripts):", ln):
            out.append(ln)
            skip = True
            continue
        if skip and ln.startswith("  - "):
            continue
        skip = False
        out.append(ln)
    text = "\n".join(out).replace("type: std", "type: tl", 1).replace("access: script", "access: tools", 1)
    f = write(tmp_path / "at/tl/SOURCE.md", text)
    # access: tools lists its operations (docs/adr.md, 13).
    assert "access: tools needs 'operations'" in vc(posix(f))[0]
    text = text.replace("read_tools:", "operations:\n  - read (required)\n  - count (optional)\nread_tools:", 1)
    write(f, text)
    assert vc(posix(f)) == ("", 0)
    write(f, text.replace("read_tools:", "read_tools:\n  - Read(~/.cache/wiki-sources/*/*/**)\n"
                                         "  - Edit(~/.cache/wiki-sources/*/*/**)", 1))
    assert vc(posix(f)) == ("", 0)


@pytest.mark.checks("lib-source/proton-files-contract")
def test_proton_files_contract():
    from conftest import PLUGIN
    assert vc(posix(PLUGIN / "sources/proton-files/SOURCE.md")) == ("", 0)


# --- open-questions.md (sourcelib.open_questions) --------------------------

Q_TEXT = ("# Open questions\r\n\r\nWhat /wiki:clarify answers.\r\n\r\n"
          "### q-2026-11-20-offer-vat-basis\r\n- raised: 2026-11-20, gmail\r\n- kind: unclear\r\n"
          "- pages: [[supplier-x]], [[budget]]\r\n- question: Incl. VAT?\r\n- kind: conflict\r\n\r\n"
          "### q-2026-10-01-old\n- kind: filing\n- raised: soon, raw\n\n"
          "### Not an id\n- kind: unclear\n\n"
          "## Notes\n- kind: conflict\n\n"
          "### q-2026-10-01-old\n- raised: 2026-02-30")


@pytest.mark.checks("open-questions/parse")
def test_open_questions_parse():
    qs, conflict = sourcelib.open_questions(Q_TEXT)
    assert not conflict
    assert [(q.id, q.valid, q.kind, q.raised) for q in qs] == [
        ("q-2026-11-20-offer-vat-basis", True, "unclear", "2026-11-20, gmail"),
        ("q-2026-10-01-old", True, "filing", "soon, raw"),
        ("Not an id", False, "unclear", ""),
        ("q-2026-10-01-old", True, "", "2026-02-30")]
    assert qs[0].raised_date.isoformat() == "2026-11-20"
    assert qs[0].pages == "[[supplier-x]], [[budget]]"
    assert qs[1].raised_date is None and qs[3].raised_date is None


@pytest.mark.parametrize("line,want", [
    pytest.param("<<<<<<< HEAD", True, id="open-questions/conflict-ours"),
    pytest.param("=======", True, id="open-questions/conflict-sep"),
    pytest.param(">>>>>>> main", True, id="open-questions/conflict-theirs"),
    pytest.param(" =======", False, id="open-questions/no-conflict-indented"),
    pytest.param("||||||| base", True, id="open-questions/conflict-diff3"),
    pytest.param("==========", False, id="open-questions/no-conflict-setext"),
])
def test_open_questions_conflict(line, want):
    assert sourcelib.open_questions("### q-2026-01-01-a\n%s\n- kind: unclear\n" % line)[1] is want


@pytest.mark.checks("open-questions/marker")
def test_open_questions_marker():
    t = "A *note* ^[open: q-2026-11-20-a-b] and ^[open: q-2026-11-2-x] and ^[open: Q-2026-11-20-a]"
    assert [m.group(1) for m in sourcelib.MARKER.finditer(t)] == ["q-2026-11-20-a-b"]
    assert sourcelib.QID.fullmatch("q-2026-11-20-" + "a" * 40)
    assert not sourcelib.QID.fullmatch("q-2026-11-20-" + "a" * 41)


@pytest.mark.checks("open-questions/read")
def test_read_questions(tmp_path):
    assert sourcelib.read_questions(posix(tmp_path)) is None
    write(tmp_path / "open-questions.md", "### q-2026-01-01-a\n- kind: unclear")
    qs, _ = sourcelib.read_questions(posix(tmp_path))
    assert [q.kind for q in qs] == ["unclear"]


@pytest.mark.checks("open-questions/fenced-example")
def test_open_questions_fenced():
    t = "### q-2026-01-01-a\n- kind: unclear\n```markdown\n### q-2026-01-02-example\n- kind: filing\n```\n"
    qs, _ = sourcelib.open_questions(t)
    assert [(q.id, q.kind) for q in qs] == [("q-2026-01-01-a", "unclear")]
