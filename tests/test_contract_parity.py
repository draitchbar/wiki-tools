"""contract.py (speed plan, step 2b) against lib-source.sh's frontmatter
parsers, which stay bash for the wrappers and the wikis' local types:
has-fm and the values of every frontmatter key (and one absent key) must
match byte for byte, for every instance file in the tests (and the local
types' contracts beside them), a CRLF copy of one, and edge cases. The
plugin's contracts aren't compared: only contract.py reads them; the bash
readers read instances (local-folder/read.sh, a local type's wrapper).
Then contract.py's lookups and path helpers (formerly the contract-parity
section of run-tests.sh).

The bash side runs once, in one bash process over every file; contract.py
is called in-process."""


import pytest

import contract
from conftest import SCRIPTS_P, TESTS, call_main, copytree, posix, write

EDGE = {
    "no-close.md": b"---\ntype: x\n  - y\n",
    "empty.md": b"",
    "bom.md": b"\xef\xbb\xbf---\ntype: x\n---\n",
    "spaces.md": (b"--- \t\ntitle:   padded value \t \nkey:value\ntab:\tx\nempty:\nlist:\n  - a\n\t- tabbed\n"
                  b"  -nospace\n  - \n    - nested\n  -  trailing  \n- notindented\nFoo:\n  - upper\n"
                  b"foo bar: not a key\n  - under-foo\nother: x\n  - after-scalar\n----\n---\nbody: ignored\n"),
    "bare-cr.md": b"---\ntitle: a\rb\nlist:\n  - c\r\r\n---\n",
    "non-utf8.md": b"---\ntitle: caf\xe9\nlist:\n  - \xff\xfe\n  - ok\n---\n",
    "dup-keys.md": b"---\ntitle: first\ntitle: second\nlist:\n  - a\nlist:\n  - b\n---\n",
    "no-final-newline.md": b"---\ntitle: x\n---",
    "open-no-newline.md": b"---\ntitle: y",
    "no-fence.md": b"title: no fence\n---\n",
}
EDGE["crlf.md"] = EDGE["spaces.md"].replace(b"\n", b"\r\n")

# For each file: its keys (from src_fm, as before), then src_has_fm and
# src_values per key, NUL-separated.
BASH_SIDE = r'''. "$1/lib-source.sh"; shift
for f; do
  keys=$(src_fm "$f" | sed -n 's/^\([A-Za-z_]\{1,\}\):.*/\1/p' | LC_ALL=C sort -u)
  printf '%s\n' $keys nosuch_key | paste -sd' ' -
  (src_has_fm "$f"; echo "has_fm $?"
   for k in $keys nosuch_key; do echo "-- $k"; src_values "$f" "$k"; done) 2>&1
  printf '\0'
done'''


@pytest.fixture(scope="module")
def tree(tmp_path_factory, run):
    """The files, as named in the check names (relative to tests/ or to the
    temp folder), and the bash side's output per file."""
    t = tmp_path_factory.mktemp("cp")
    # The lib-source fixture as the lib-source section leaves it: a CRLF
    # copy of an instance.
    ls = copytree(TESTS / "sources" / "lib-source", t / "ls")
    inst = ls / "wiki/.claude/sources/instances"
    write(inst / "crlf.md", (inst / "good.md").read_bytes().replace(b"\n", b"\r\n")
          .replace(b"key: good", b"key: crlf"))
    for n, data in EDGE.items():
        write(t / "cp-edge" / n, data)
    found = [p for p in TESTS.rglob("*.md") if "/.claude/sources/" in posix(p)]
    files = sorted(found, key=lambda p: posix(p).encode()) + [inst / "crlf.md"]
    files += sorted((t / "cp-edge").glob("*.md"))
    r = run(["bash", "-c", BASH_SIDE, "_", SCRIPTS_P] + [posix(f) for f in files])
    assert r.rc == 0, r
    chunks = r.out.split(b"\0")[:-1]
    assert len(chunks) == len(files)
    out = {}
    for f, c in zip(files, chunks):
        name = posix(f)
        for pre in (posix(TESTS) + "/", posix(t) + "/"):
            if name.startswith(pre):
                name = name[len(pre):]
                break
        keys, _, rest = c.partition(b"\n")
        out[name] = (posix(f), keys.decode("utf-8", "surrogateescape").split(), rest)
    return t, out


def _python_side(path, keys):
    lines = ["has_fm %d" % (0 if contract.has_fm(path) else 1)]
    for k in keys:
        lines.append("-- " + k)
        lines.extend(contract.values(path, k))
    return b"".join(s.encode("utf-8", errors="surrogateescape") + b"\n" for s in lines)


def _names():
    # Collected before the tree exists: the same walk, names only.
    found = [p for p in TESTS.rglob("*.md") if "/.claude/sources/" in posix(p)]
    names = [posix(p.relative_to(TESTS)) for p in found]
    names += ["ls/wiki/.claude/sources/instances/crlf.md"] + ["cp-edge/" + n for n in sorted(EDGE)]
    return sorted(set(names))


@pytest.mark.parametrize("name", [pytest.param(n, id="contract-parity/" + n) for n in _names()])
def test_parity(name, tree):
    _, out = tree
    path, keys, bash = out[name]
    contract._cache.clear()
    assert _python_side(path, keys) == bash


@pytest.mark.checks("contract-parity/every-file-checked")
def test_every_file_checked(tree):
    assert sorted(tree[1]) == _names()


# Lookups: contract.py only since lib-source.sh's src_contract and
# src_instances went; expectations as bash had them.
@pytest.fixture
def lsw(tmp_path):
    ls = copytree(TESTS / "sources" / "lib-source", tmp_path / "ls")
    inst = ls / "wiki/.claude/sources/instances"
    write(inst / "crlf.md", (inst / "good.md").read_bytes().replace(b"\n", b"\r\n")
          .replace(b"key: good", b"key: crlf"))
    return posix(ls / "wiki"), posix(ls / "plugin")


def _contract(w, t, plugin):
    try:
        return contract.contract(w, t, plugin), 0
    except contract.ContractError as e:
        return str(e), 1


@pytest.mark.checks("contract-py/contract-std", "contract-py/contract-local", "contract-py/contract-unknown",
                    "contract-py/contract-badname", "contract-py/contract-empty", "contract-py/contract-shadow")
def test_contract_lookup(lsw, tmp_path):
    w, plug = lsw
    assert _contract(w, "std", plug) == (plug + "/sources/std/SOURCE.md", 0)
    assert _contract(w, "loc", plug) == (w + "/.claude/sources/types/loc/SOURCE.md", 0)
    assert _contract(w, "nosuch", plug) == (
        "unknown source type 'nosuch' (looked in %s/sources/nosuch/SOURCE.md and "
        "%s/.claude/sources/types/nosuch/SOURCE.md)" % (plug, w), 1)
    assert _contract(w, "../std", plug) == ("invalid source type name '../std'", 1)
    assert _contract(w, "", plug) == ("invalid source type name ''", 1)
    write(w + "/.claude/sources/types/std/SOURCE.md", (tmp_path / "ls/plugin/sources/std/SOURCE.md").read_bytes())
    msg, rc = _contract(w, "std", plug)
    assert rc == 1 and msg.startswith("local type 'std' (%s/.claude/sources/types/std/SOURCE.md) shadows" % w)
    assert msg.endswith("Otherwise rename the local type")


@pytest.mark.checks("contract-py/instances", "contract-py/instances-none")
def test_instances(lsw):
    w, _ = lsw
    d = w + "/.claude/sources/instances"
    import os
    os.mkdir(d + "/dir.md")
    for n in (".hidden.md", "Upper.md", "notes.txt"):
        write(d + "/" + n, "")
    assert contract.instances(w) == ["Upper", "bad-root", "crlf", "good", "loc1", "missing-param",
                                     "unknown-type", "uses-broken", "wrong-key"]
    assert contract.instances(w + "/nosuch") == []


PATHS = ["~/two/", "~\\two", "C:\\Users\\x\\", "//a//b//", "/", "rel/x/", "~", "~/", "a/./b", "/a/../b",
         "/a/.b/c", "c:/x", "C:x", "..", ".", "", "x/.."]


@pytest.fixture(scope="module")
def bash_paths(run):
    """src_expand, src_is_abs and src_has_dots for every path, one bash."""
    script = ('. "$1/lib-source.sh"; shift; HOME=/home/u\n'
              'for p; do for op in expand is_abs has_dots; do src_$op "$p"; echo " rc=$?"; done; done')
    r = run(["bash", "-c", script, "_", SCRIPTS_P] + PATHS)
    assert r.rc == 0, r
    lines = r.out.decode("utf-8").split("\n")[:-1]
    return {(p, op): lines[3 * i + j] for i, p in enumerate(PATHS)
            for j, op in enumerate(("expand", "is_abs", "has_dots"))}


def _py_path(op, p):
    def fn():
        if op == "expand":
            import sys
            sys.stdout.buffer.write(contract.expand(p).encode())
            return 0
        return 0 if getattr(contract, op)(p) else 1
    r = call_main(fn, None, env={"HOME": "/home/u"})
    return r.out.decode() + " rc=%d" % r.rc


@pytest.mark.parametrize("op,p", [pytest.param(op, p, id="contract-py/%s-%d" % (op, i + 1))
                                  for i, p in enumerate(PATHS) for op in ("expand", "is_abs", "has_dots")])
def test_path_helpers(op, p, bash_paths):
    assert _py_path(op, p) == bash_paths[(p, op)]


@pytest.mark.parametrize("env,want", [
    pytest.param({"HOME": "C:\\h", "USERPROFILE": "C:\\p"}, "C:/h/a", id="contract-py/home-prefers-HOME"),
    pytest.param({"HOME": None, "USERPROFILE": "C:\\p"}, "C:/p/a", id="contract-py/home-falls-back-to-USERPROFILE"),
])
def test_home(env, want):
    r = call_main(lambda: __import__("sys").stdout.write(contract.expand("~/a")) and 0, None, env=env)
    assert r.out.decode() == want
