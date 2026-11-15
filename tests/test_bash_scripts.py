"""The scripts that stay bash, end to end: lib-source.sh's helpers (used by
the wrappers and the wikis' local types), ocr.sh and schema.sh, and checks
on the plugin's files (formerly the lib-source, ocr and plugin-schema
sections of run-tests.sh)."""

import re

import pytest

from conftest import HOME_U, PLUGIN, SCRIPTS_P, TESTS, copytree, git, posix, write

# --- lib-source.sh's bash helpers -----------------------------------------


@pytest.fixture(scope="module")
def ls(tmp_path_factory, run):
    d = copytree(TESTS / "sources" / "lib-source", tmp_path_factory.mktemp("lsb") / "ls")
    git(d / "wiki", "init", "-q")
    inst = d / "wiki/.claude/sources/instances"
    write(inst / "crlf.md", (inst / "good.md").read_bytes().replace(b"\n", b"\r\n").replace(b"key: good", b"key: crlf"))

    def lsrun(snippet):
        r = run(["bash", "-c", '. "$1/lib-source.sh"; SRC_PLUGIN=$2; eval "$3"', "_", SCRIPTS_P,
                 posix(d / "plugin"), snippet], cwd=d / "wiki", env={"HOME": HOME_U}, merged=True)
        return r.merged.decode("utf-8", "surrogateescape").rstrip("\n")
    return lsrun


HELPERS = [
    ("field", 'src_field "$SRC_PLUGIN/sources/std/SOURCE.md" title', "Standard test type"),
    ("list", 'src_list "$SRC_PLUGIN/sources/std/SOURCE.md" platforms | paste -sd" " -', "linux windows"),
    ("list-stops", 'src_list "$SRC_PLUGIN/sources/std/SOURCE.md" scripts', "read.sh"),
    ("values-scalar", "src_values .claude/sources/instances/loc1.md labels", "Receipts"),
    ("values-list", 'src_values .claude/sources/instances/good.md roots | paste -sd" " -', "/data/one ~/two"),
    ("crlf-values", 'src_values .claude/sources/instances/crlf.md roots | paste -sd" " -', "/data/one ~/two"),
    ("expand", 'src_expand "~/two/"', "%s/two" % HOME_U),
    ("expand-backslash", 'src_expand "C:\\\\Users\\\\x\\\\"', "C:/Users/x"),
    ("expand-slashes", 'printf "%s %s %s" "$(src_expand "//a//b///c/")" "$(src_expand /)" "$(src_expand //)"',
     "/a/b/c / /"),
    ("match-root", 'printf "/data/one\\n/data/two\\n" | src_match_root /data/one/a/b', "/data/one"),
    ("match-sibling", 'printf "/data/one\\n" | src_match_root /data/one-old >/dev/null; echo $?', "1"),
    ("dots", 'src_has_dots "/a/./b"; echo $?', "0"),
    ("no-dots", 'src_has_dots "/a/.b/c"; echo $?', "1"),
]


@pytest.mark.parametrize("snippet,want", [pytest.param(s, w, id="lib-source/" + n) for n, s, w in HELPERS])
def test_helper(snippet, want, ls):
    assert ls(snippet) == want


# --- ocr.sh with a fake ocrmypdf that writes its arguments into the sidecar

FAKE_OCR = """#!/usr/bin/env bash
while [ $# -gt 0 ]; do
  case "$1" in -l) langs=$2 ;; --sidecar) side=$2 ;; esac
  shift
done
printf 'langs=%s\\n' "$langs" > "$side"
"""


@pytest.fixture(scope="module")
def ocr(tmp_path_factory, run):
    import os
    t = tmp_path_factory.mktemp("ocr")
    write(t / "ocrbin/ocrmypdf", FAKE_OCR).chmod(0o755)
    git(t, "init", "-q", "ocrw")
    write(t / "ocrw/scan.pdf", "pdf")
    path = str(t / "ocrbin") + os.pathsep + os.environ.get("PATH", "")

    def _ocr(*args):
        r = run(["bash", SCRIPTS_P + "/ocr.sh"] + list(args), cwd=t / "ocrw", env={"PATH": path})
        side = t / "ocrw/raw/ocr/scan.txt"
        return r.rc, side.read_text().rstrip("\n") if side.exists() else ""
    return _ocr


@pytest.mark.parametrize("args,want", [
    pytest.param(["scan.pdf"], "langs=eng", id="ocr/default-eng"),
    pytest.param(["scan.pdf", "dan+eng"], "langs=dan+eng", id="ocr/languages"),
])
def test_ocr(args, want, ocr):
    assert ocr(*args) == (0, want)


@pytest.mark.parametrize("args", [pytest.param(["scan.pdf", "dan;rm"], id="ocr/refuse-bad-languages"),
                                  pytest.param(["scan.pdf", "eng", "x"], id="ocr/refuse-extra-args")])
def test_ocr_refused(args, ocr):
    assert ocr(*args)[0] == 1


# --- the plugin's files and schema.sh ---------------------------------------

@pytest.mark.checks("plugin/no-conflict-markers")
def test_no_conflict_markers():
    """The schema and skills reach every wiki session as they are."""
    rx = re.compile(rb"^(<<<<<<< |=======$|>>>>>>> )", re.M)
    bad = [posix(p) for p in PLUGIN.rglob("*") if p.is_file() and "__pycache__" not in p.parts
           and rx.search(p.read_bytes())]
    assert bad == []


def schema(run, name, env=None):
    return run(["bash", SCRIPTS_P + "/schema.sh", name], env=env)


@pytest.mark.checks("schema/conventions", "schema/layout", "schema/root-filled", "schema/refuse-other-name")
def test_schema(run):
    assert "Ask for context, don't guess" in schema(run, "wiki-conventions").out.decode()
    out = schema(run, "wiki-layout").out.decode()
    assert "Data model" in out and "${CLAUDE_PLUGIN_ROOT}" not in out
    assert schema(run, "../README").rc == 1


# Each under the 10,000-character cap on hook context with room to spare,
# even with a long install path (a Windows plugin cache).
@pytest.mark.parametrize("name", [pytest.param(n, id="schema/%s-under-9000-bytes" % n)
                                  for n in ("wiki-conventions", "wiki-layout")])
def test_schema_size(name, run):
    long = "C:/Users/firstname.lastname/.claude/plugins/cache/wiki-tools/wiki/1.0.0"
    assert len(schema(run, name, {"WIKI_SCHEMA_ROOT": long}).out) <= 9000


@pytest.mark.parametrize("name", [pytest.param(p.stem, id="schema/hook-" + p.stem)
                                  for p in sorted((PLUGIN / "schema").glob("*.md"))])
def test_hook_loads_schema(name):
    assert 'schema.sh\\" %s"' % name in (PLUGIN / "hooks/hooks.json").read_text()
