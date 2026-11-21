"""install-source-file.sh (the user's installer), decode-download.sh and
local-folder/read.sh against throwaway wikis, end to end through bash:
their flow (terminal, prompt, paths) is in the launchers (formerly the
install and install-edge sections of run-tests.sh)."""

import base64
import json
import os
import re
import time

import pytest

from conftest import (PLUGIN, SCRIPTS_P, TESTS, Story, git, norm, posix, recorded, story_assert, write)

ISF = SCRIPTS_P + "/install-source-file.sh"
DDS = SCRIPTS_P + "/decode-download.sh"
LFS = posix(PLUGIN / "sources/local-folder/read.sh")
GM = "---\nkey: gmail\ntype: gmail\nlabels: Projects\n---\n\nNotes.\n"
BK = (TESTS / "guard-wiki/.claude/sources/types/bookish/SOURCE.md").read_text(encoding="utf-8")

# name, text, exit, answer, target, content (None: a step with its own check)
IEXPECT = [
    ("no-frontmatter", 'first line pasted: "key: gmail"', 1, "y", "instances/gmail.md", "key: gmail\ntype: gmail\n"),
    ("key-mismatch", "key 'mail' doesn't match the file name", 1, "y", "instances/gmail.md",
     "---\nkey: mail\ntype: gmail\nlabels: X\n---\n"),
    ("unknown-type", "unknown source type 'nosuch' (looked in", 1, "y", "instances/x.md", "---\nkey: x\ntype: nosuch\n---\n"),
    ("bad-target", "target must be instances/<key>.md", 1, "y", "sources/instances/gmail.md", GM),
    ("dotdot-target", "must be a plain name", 1, "y", "types/bookish/../x.sh", "x\n"),
    ("standard-name", "'gmail' is a standard type", 1, "y", "types/gmail/SOURCE.md", "x\n"),
    ("empty-paste", "nothing pasted", 1, "y", "instances/gmail.md", ""),
    ("answer-no", "Not installed.", 1, "n", "instances/gmail.md", GM),
]
NAMES = (["install/" + n for n, *_ in IEXPECT]
         + ["install/no-frontmatter-not-written", "install/refused-in-claude", "install/gmail-new",
            "install/gmail-rules", "install/present-rule-omitted", "install/codebase-narrow",
            "install/broad-cache-rule-counts", "install/wiki-cache-rule-counts", "install/unchanged",
            "install/diff-shown", "install/crlf", "install/crlf-stripped", "install/crlf-checkout-unchanged",
            "install/crlf-checkout-diff", "install/fs-no-roots", "install/cut-contract",
            "install/cut-contract-not-written", "install/script-first", "install/contract-note",
            "install/script-unlisted", "install/script-ok", "install/local-instance", "install/breaks-other",
            "install/no-git", "install/rules-complete", "install/deny-blocks"])


def settings_with(out, have="{}"):
    """Settings.json have (text) plus every rule the installer's output says is missing."""
    lists = dict({"allow": [], "deny": []}, **json.loads(have).get("permissions", {}))
    cur = None
    for ln in out.splitlines():
        m = re.match(r'  under "permissions" -> "(allow|deny)":$', ln)
        if m:
            cur = m.group(1)
        elif cur and re.match(r'      ".*",$', ln):
            lists[cur].append(json.loads(ln.strip().rstrip(",")))
        else:
            cur = None
    return json.dumps({"permissions": lists}, indent=2) + "\n"


@pytest.fixture(scope="module")
def story(tmp_path_factory, run):
    t = tmp_path_factory.mktemp("inst")
    iw = t / "iw"
    git(t, "init", "-q", "iw")
    write(iw / "CLAUDE.md", "# W\n")
    write(iw / ".claude/settings.json",
          '{\n  "permissions": {\n    "allow": [\n      "mcp__claude_ai_Gmail__search_threads"\n    ]\n  }\n}\n')
    st = Story()

    def inst(answer, target, content, env=None):
        r = run(["bash", ISF, target], cwd=iw, input=content.encode("utf-8"), merged=True,
                env=dict({"CLAUDECODE": None, "WIKI_INSTALL_ANSWER": answer}, **(env or {})))
        return r.merged.decode("utf-8", "surrogateescape"), r.rc

    def iexpect(name, text, code, answer, target, content):
        o, rc = inst(answer, target, content)
        st.check("install/" + name, text in o and rc == code, "rc %d, output:\n%s" % (rc, o))

    gmail = iw / ".claude/sources/instances/gmail.md"
    for i, row in enumerate(IEXPECT):
        iexpect(*row)
        if i == 0:
            st.check("install/no-frontmatter-not-written", not gmail.exists())
    o, rc = inst("y", "instances/gmail.md", GM, env={"CLAUDECODE": "1"})
    st.check("install/refused-in-claude", "outside Claude" in o and rc == 1, o)
    iexpect("gmail-new", "New file .claude/sources/instances/gmail.md", 0, "y", "instances/gmail.md", GM)
    iexpect("gmail-rules", '"mcp__claude_ai_Gmail__send_message",', 0, "y", "instances/gmail.md", GM + "More.\n")
    o, _ = inst("y", "instances/gmail.md", GM + "More.\n")
    st.check("install/present-rule-omitted", '"mcp__claude_ai_Gmail__search_threads"' not in o, o)
    cbi = "---\nkey: code\ntype: codebase\nroots:\n  - %s\n---\n" % posix(iw)
    iexpect("codebase-narrow", '"Edit(~/.cache/wiki-sources/iw/code/**)",', 0, "y", "instances/code.md", cbi)
    settings = iw / ".claude/settings.json"
    write(settings, settings.read_text().replace('"mcp__claude_ai_Gmail__search_threads"',
                                                 '"mcp__claude_ai_Gmail__search_threads", "Edit(~/.cache/wiki-sources/**)"'))
    o, _ = inst("y", "instances/code.md", cbi + "Notes.\n")
    st.check("install/broad-cache-rule-counts", '"Edit(~/.cache/wiki-sources/iw/code/**)"' not in o, o)
    write(settings, settings.read_text().replace('"Edit(~/.cache/wiki-sources/**)"', '"Edit(~/.cache/wiki-sources/iw/**)"'))
    o, _ = inst("y", "instances/code.md", cbi + "More notes.\n")
    st.check("install/wiki-cache-rule-counts", '"Edit(~/.cache/wiki-sources/iw/code/**)"' not in o, o)
    saved = settings.read_text()
    write(settings, settings_with(o, saved))
    o, _ = inst("y", "instances/code.md", cbi + "Last notes.\n")
    st.check("install/rules-complete", "has every rule these sources need" in o and "still lacks" not in o, o)
    # A deny rule covering a needed allow rule blocks it: deny wins.
    write(settings, settings.read_text().replace('"deny": [', '"deny": ["Edit(~/.cache/wiki-sources/**)",', 1))
    o, _ = inst("y", "instances/code.md", cbi + "Denied notes.\n")
    blocks = '"Edit(~/.cache/wiki-sources/**)" blocks "Edit(~/.cache/wiki-sources/iw/code/**)"'
    st.check("install/deny-blocks", blocks in o and "has every rule" not in o, o)
    write(settings, saved)
    (iw / ".claude/sources/instances/code.md").unlink()
    iexpect("unchanged", "already exactly this", 0, "y", "instances/gmail.md", GM + "More.\n")
    iexpect("diff-shown", "+Changed.", 0, "y", "instances/gmail.md", GM + "Changed.\n")
    iexpect("crlf", "Installed", 0, "y", "instances/gmail.md", "---\r\nkey: gmail\r\ntype: gmail\r\nlabels: Y\r\n---\r\n")
    st.check("install/crlf-stripped", b"\r" not in gmail.read_bytes())
    # A CRLF checkout (core.autocrlf) without a final newline is the same file.
    write(gmail, "---\r\nkey: gmail\r\ntype: gmail\r\nlabels: Y\r\n---")
    iexpect("crlf-checkout-unchanged", "already exactly this", 0, "n", "instances/gmail.md",
            "---\nkey: gmail\ntype: gmail\nlabels: Y\n---\n")
    o, rc = inst("n", "instances/gmail.md", "---\nkey: gmail\ntype: gmail\nlabels: Z\n---\n")
    st.check("install/crlf-checkout-diff", "-key: gmail" not in o and rc == 1
             and re.search(r"-labels: Y.*\+labels: Z.*Not installed\.", o, re.S), o)
    iexpect("fs-no-roots", "required parameter 'roots' is empty", 1, "y", "instances/scans.md",
            "---\nkey: scans\ntype: local-folder\n---\n")
    iexpect("cut-contract", "missing section '## Resolve citation'", 1, "y", "types/bookish/SOURCE.md",
            BK[:BK.index("## Resolve citation")])
    st.check("install/cut-contract-not-written", not (iw / ".claude/sources/types/bookish/SOURCE.md").exists())
    iexpect("script-first", "SOURCE.md doesn't exist yet", 1, "y", "types/bookish/fetch.sh", "#!/bin/bash\n")
    iexpect("contract-note", "script 'fetch.sh' is listed but missing (install it next)", 0, "y",
            "types/bookish/SOURCE.md", BK)
    iexpect("script-unlisted", "other.sh isn't listed under scripts", 1, "y", "types/bookish/other.sh", "#!/bin/bash\n")
    iexpect("script-ok", "Installed .claude/sources/types/bookish/fetch.sh", 0, "y", "types/bookish/fetch.sh",
            "#!/bin/bash\necho hi\n")
    iexpect("local-instance", "Installed .claude/sources/instances/books.md", 0, "y", "instances/books.md",
            "---\nkey: books\ntype: bookish\nshelf: Byg\n---\n")
    iexpect("breaks-other", "required parameter 'colour' is empty", 1, "y", "types/bookish/SOURCE.md",
            BK.replace("  - shelf (required): shelf name\n",
                       "  - shelf (required): shelf name\n  - colour (required): x\n", 1))
    import subprocess
    st_out = subprocess.run(["git", "-C", str(iw), "status", "--porcelain", "--", ".claude/sources"],
                            stdout=subprocess.PIPE).stdout.decode()
    st.check("install/no-git", not [ln for ln in st_out.splitlines() if not ln.startswith("??")], st_out)
    return st, t


@pytest.mark.parametrize("name", [pytest.param(n, id=n) for n in NAMES])
def test_install(name, story):
    story_assert(story[0], name)


@pytest.mark.checks("install/every-check-run")
def test_every_check_run(story):
    assert sorted(story[0].results) == sorted(NAMES)


# --- decode-download.sh against the installer's wiki (instance gmail exists)

WANT = '<mxfile>\n  <diagram name="Plan"/>\n</mxfile>\n'
B64 = base64.b64encode(WANT.encode()).decode()


def _wrapped(s, n=76):
    return "".join(s[i:i + n] + "\n" for i in range(0, len(s), n))


INPUTS = {
    "plain.b64": _wrapped(B64),  # wrapped base64, as written with Write
    "saved.json": '{"content":"%s","mimeType":"application/xml"}' % B64.replace("/", "\\/"),
    "nested.json": json.dumps([{"type": "text", "text": json.dumps({"content": B64}, separators=(",", ":"))}],
                              separators=(",", ":")),
    # decode_download.py parses JSON, so base64 wrapped with \n inside a
    # "content" string decodes; the longest "content" wins; a cut-off saved
    # result, missing = padding and CRLF plain base64 decode too.
    "wrapped.json": '{"content":"%s\\n%s"}' % (B64[:20], B64[20:]),
    "two.json": '{"content":"%s","x":{"content":"QQ=="}}' % B64,
    "cut.json": '{"content":"%s' % B64,
    "nopad.b64": B64.rstrip("="),
    "crlf.b64": B64 + "\r\n",
}


@pytest.fixture(scope="module")
def dd(story, run):
    _, t = story
    d = t / "dd"
    for n, text in INPUTS.items():
        write(d / n, text)
    write(d / "bad.txt", "not base64 at all!\n")
    write(d / "nocontent.json", '{"other":"x"}')
    write(d / "stray.b64", "QUJDR")

    def _dd(*args, env=None):
        r = run(["bash", DDS] + list(args), cwd=t / "iw", merged=True,
                env=dict({"HOME": posix(t / "home")}, **(env or {})))
        return norm(r.merged, t), r.rc
    out = t / "home/.cache/wiki-sources/iw/gmail/Projects/plan.drawio"
    return _dd, d, out


@pytest.mark.parametrize("name", [pytest.param(n, id="decode-download/" + n) for n in INPUTS])
def test_decode(name, dd):
    _dd, d, out = dd
    if out.exists():
        out.unlink()
    o, rc = _dd("gmail", posix(d / name), "Projects/plan.drawio")
    assert rc == 0 and "wrote @TMP@/home/.cache/wiki-sources/iw/gmail/Projects/plan.drawio" in o, o
    assert out.read_text() == WANT


@pytest.mark.parametrize("args", [
    pytest.param(["gmail", "plain.b64", "../../x.drawio"], id="decode-download/refuse-dotdot"),
    pytest.param(["gmail", "plain.b64", "/tmp/x.drawio"], id="decode-download/refuse-absolute"),
    pytest.param(["nosuch", "plain.b64", "a.drawio"], id="decode-download/refuse-no-key"),
    pytest.param(["gmail", "bad.txt", "a.drawio"], id="decode-download/refuse-not-b64"),
    pytest.param(["gmail", "plain.b64"], id="decode-download/refuse-args"),
])
def test_decode_refused(args, dd):
    _dd, d, _ = dd
    args = [args[0], posix(d / args[1])] + args[2:]
    assert _dd(*args)[1] == 1


@pytest.mark.checks("decode-download/refuse-no-content")
def test_decode_no_content(dd):
    _dd, d, _ = dd
    o, rc = _dd("gmail", posix(d / "nocontent.json"), "a.drawio")
    assert rc == 1 and "no base64 content found" in o


@pytest.mark.checks("decode-download/refuse-bad-length")
def test_decode_bad_length(dd):
    _dd, d, out = dd
    write(out, "x\n")
    o, rc = _dd("gmail", posix(d / "stray.b64"), "Projects/plan.drawio")
    assert rc == 1 and "decoding failed" in o and not out.exists()


@pytest.fixture(scope="module")
def nopy(tmp_path_factory):
    t = tmp_path_factory.mktemp("nopy-i")
    for c in ("python", "python3", "py"):
        write(t / "bin" / c, "#!/bin/sh\nexit 1\n").chmod(0o755)
    return {"CLAUDE_PLUGIN_DATA": posix(t / "data"), "CLAUDE_CONFIG_DIR": posix(t / "cfg"),
            "PATH": str(t / "bin") + os.pathsep + os.environ.get("PATH", "")}


@pytest.mark.checks("decode-download/no-python")
def test_decode_no_python(dd, nopy):
    _dd, d, _ = dd
    o, rc = _dd("gmail", posix(d / "plain.b64"), "a.drawio", env=nopy)
    assert rc == 1 and o.startswith("decode-download: no Python 3.11 or later found")


# --- local-folder/read.sh against a throwaway wiki and folder --------------

def _mtime(path, day):
    t = time.mktime(time.strptime(day, "%Y-%m-%d"))
    os.utime(path, (t, t))


@pytest.fixture(scope="module")
def lf(tmp_path_factory, run):
    t = tmp_path_factory.mktemp("lf")
    w = t / "lfw"
    git(t, "init", "-q", "lfw")
    T = posix(t)
    write(w / ".claude/sources/instances/scans.md",
          "---\nkey: scans\ntype: local-folder\nroots:\n  - %s/scans\n  - %s/other/one.pdf\n---\n" % (T, T))
    write(w / ".claude/sources/instances/notafolder.md", "---\nkey: notafolder\ntype: gmail\nlabels: X\n---\n")
    _mtime(write(t / "scans/2026/old.pdf", "old\n"), "2026-01-01")
    _mtime(write(t / "scans/2026/sub/new file.pdf", "new\n"), "2026-10-10")
    _mtime(write(t / "other/one.pdf", "one\n"), "2026-09-01")
    write(t / "scans-old/x.pdf", "x\n")

    def _lf(*args, cwd=w):
        r = run(["bash", LFS] + list(args), cwd=cwd, merged=True, env={"HOME": posix(t / "home")})
        return norm(r.merged, t).rstrip("\n"), r.rc
    return _lf, t, T


@pytest.mark.parametrize("args", [
    pytest.param(["scans", "delete", "@T/scans/2026/old.pdf"], id="local-folder/refuse-unknown-op"),
    pytest.param(["scans", "list", "@T/scans", "--force"], id="local-folder/refuse-extra-args"),
    pytest.param(["nosuch", "list", "@T/scans"], id="local-folder/refuse-no-instance"),
    pytest.param(["../x", "list", "@T/scans"], id="local-folder/refuse-bad-key"),
    pytest.param(["notafolder", "list", "@T/scans"], id="local-folder/refuse-wrong-type"),
    pytest.param(["scans", "list", "@T"], id="local-folder/refuse-outside"),
    pytest.param(["scans", "list", "@T/scans-old"], id="local-folder/refuse-sibling"),
    pytest.param(["scans", "list", "@T/scans/../scans-old"], id="local-folder/refuse-dotdot"),
    pytest.param(["scans", "list", "scans"], id="local-folder/refuse-relative"),
    pytest.param(["scans", "new", "yesterday"], id="local-folder/refuse-bad-date"),
    pytest.param(["scans", "copy", "@T/scans/2026"], id="local-folder/refuse-copy-folder"),
])
def test_lf_refused(args, lf):
    _lf, _, T = lf
    assert _lf(*[a.replace("@T", T) for a in args])[1] == 1


@pytest.mark.checks("local-folder/refuse-outside-git")
def test_lf_outside_git(lf):
    _lf, t, T = lf
    assert _lf("scans", "list", T + "/scans", cwd=t)[1] == 1


@pytest.mark.checks("local-folder/list", "local-folder/new-since", "local-folder/new-never", "local-folder/copy",
                    "local-folder/copy-content", "local-folder/copy-file-root", "local-folder/source-untouched")
def test_lf_reads(lf):
    _lf, t, T = lf
    o, _ = _lf("scans", "list", T + "/scans/2026")
    assert " ".join("%s %s" % (ln.split()[0], ln.split()[-1]) for ln in o.split("\n")) == \
        "f @TMP@/scans/2026/old.pdf d @TMP@/scans/2026/sub"
    o, _ = _lf("scans", "new", "2026-10-01")
    assert re.sub(r"^.* [0-9]* ", "", o) == "@TMP@/scans/2026/sub/new file.pdf"
    o, _ = _lf("scans", "new", "never")
    assert len(o.split("\n")) == 3
    o, _ = _lf("scans", "copy", T + "/scans/2026/sub/new file.pdf")
    assert o == "local-folder: copied to @TMP@/home/.cache/wiki-sources/lfw/scans/2026/sub/new file.pdf"
    assert (t / "home/.cache/wiki-sources/lfw/scans/2026/sub/new file.pdf").read_text() == "new\n"
    o, _ = _lf("scans", "copy", T + "/other/one.pdf")
    assert o == "local-folder: copied to @TMP@/home/.cache/wiki-sources/lfw/scans/one.pdf"
    assert (t / "scans/2026/old.pdf").read_text() == "old\n"


# --- install-edge: recorded against the bash version ----------------------

@pytest.mark.checks("install-edge/same", "install-edge/cases")
def test_install_edge(tmp_path, run, request):
    t = tmp_path
    cases = []

    def ie(name, d, answer, target, content):
        r = run(["bash", ISF, target], cwd=d, input=content.encode("utf-8"),
                env={"CLAUDECODE": None, "WIKI_INSTALL_ANSWER": answer})
        block = "rc=%d\n-- out\n%s-- err\n%s" % (r.rc, r.out.decode("utf-8", "surrogateescape"),
                                                 r.err.decode("utf-8", "surrogateescape"))
        cases.append("== %s\n%s\n" % (name, norm(block.rstrip("\n"), t)))
        return r.out.decode("utf-8", "surrogateescape")

    (t / "ie-plain").mkdir()
    ie("no-git", t / "ie-plain", "y", "instances/a.md", "---\n")
    git(t, "init", "-q", "ie-nocm")
    ie("no-claude-md", t / "ie-nocm", "y", "instances/a.md", "---\n")
    w = t / "iew"
    git(t, "init", "-q", "iew")
    write(w / "CLAUDE.md", "# W\n")
    (w / "sub").mkdir()
    gm = "---\nkey: gmail\ntype: gmail\nlabels: X\n---\n"
    ie("dot-prefix", w, "y", "./instances/gmail.md", gm)
    ie("claude-prefix", w / "sub", "y", ".claude/sources/instances/gmail.md", gm + "x\n")
    ie("nested-type", w, "y", "types/a/b/c.sh", "x\n")
    ie("empty-type", w, "y", "types//c.sh", "x\n")
    ie("bare-instances", w, "y", "instances/.md", "x\n")
    ie("upper-key", w, "y", "instances/Gmail.md", gm)
    ie("only-cr", w, "y", "instances/gmail.md", "\r\r")
    ie("no-final-newline", w, "n", "instances/gmail.md", "---\nkey: gmail\ntype: gmail\nlabels: Y\n---")
    ie("utf8-first-line", w, "y", "instances/x.md", "æøå" * 21 + "\n")
    write(w / ".claude/settings.json", '{"permissions": {"allow": [,]}}')
    ie("bad-json", w, "y", "instances/gmail.md", gm + "y\n")
    write(w / ".claude/settings.json", '{"permissions": {"allow": [], "deny": []}}')
    ie("codebase-all-rules", w, "y", "instances/code.md", "---\nkey: code\ntype: codebase\nroots:\n  - /x\n---\n")
    lc = ie("local-contract", w, "y", "types/bookish/SOURCE.md", BK.rstrip("\n") + "\n")
    ie("local-contract-again", w, "y", "types/bookish/SOURCE.md", BK.rstrip("\n") + "\n")
    ie("local-bad-instance", w, "y", "instances/bk.md", "---\nkey: bk\ntype: bookish\nshelf: TODO\n---\n")
    write(w / ".claude/settings.json", settings_with(lc))
    ie("no-rules-missing", w, "y", "instances/gmail.md", gm + "z\n")
    out = "".join(cases)
    assert len(cases) == 17
    recorded(request, TESTS / "fixtures/install/edge.out", out)
