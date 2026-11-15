"""py-launch.sh, the hooks' launcher: interpreter cache, probe, fail-closed
exits, end to end through bash with fake interpreters (formerly the
py-launch section of run-tests.sh). Plus two guard cases about how the
plugin folder is written (in-process, with the other guard tests' helpers)."""

import json
import re

import pytest

from conftest import PLUGIN, PLUGIN_BASH, PLUGIN_P, TESTS, copytree, hooks_guard_command, posix, write

PUSH = '{"tool_name":"Bash","tool_input":{"command":"git push"}}'
LS = '{"tool_name":"Bash","tool_input":{"command":"ls"}}'


@pytest.fixture(scope="module")
def pl(tmp_path_factory, run):
    t = tmp_path_factory.mktemp("pl")
    gw = copytree(TESTS / "guard-wiki", t / "gw")
    pdata = t / "pdata"

    def hook(data, root=PLUGIN_BASH, path=None, data_dir=None, extra=None):
        env = {"CLAUDE_PLUGIN_ROOT": root, "CLAUDE_PLUGIN_DATA": posix(pdata) if data_dir is None else data_dir,
               "CLAUDE_PROJECT_DIR": posix(gw), "HOME": "/home/u"}
        if path is not None:
            env["PATH"] = path
        env.update(extra or {})
        return run(["bash", "-c", hooks_guard_command()], env=env, input=data.encode())

    def fk(name, prog, body):
        f = write(t / "fk" / name / prog, "#!/bin/sh\n%s\n" % body)
        f.chmod(0o755)
        return posix(t / "fk" / name)

    def setcache(value, newline=True):
        write(pdata / "python", value + ("\n" if newline else ""))

    return t, hook, fk, setcache, pdata


@pytest.mark.checks("py-launch/probe-and-run", "py-launch/cache-written", "py-launch/cache-trailing-newline",
                    "py-launch/warm-cache-pass", "py-launch/warm-cache-push", "py-launch/cache-no-newline",
                    "py-launch/stale-cache", "py-launch/stale-cache-rewritten", "py-launch/relative-cache",
                    "py-launch/relative-cache-rewritten", "py-launch/non-python-cache-push",
                    "py-launch/exit1-pass-blocked", "py-launch/exit1-message", "py-launch/exit127-pass-blocked",
                    "py-launch/store-alias-only", "py-launch/store-alias-message", "py-launch/old-python-only",
                    "py-launch/py-only-pass", "py-launch/py-only-push", "py-launch/none",
                    "py-launch/order-python-first", "py-launch/order-python3-not-run", "py-launch/no-plugin-data",
                    "py-launch/empty-stdin", "py-launch/timing-log")
def test_launcher(pl, run):
    """One story, as the old section: each step leaves the cache the next expects."""
    t, hook, fk, setcache, pdata = pl
    assert hook(LS).rc == 0
    realpy = (pdata / "python").read_text().rstrip("\n")
    assert re.fullmatch(r"(/|[A-Za-z]:/).*/python[^/]*", realpy), realpy
    assert (pdata / "python").read_text().count("\n") == 1
    none = posix(t / "fk/none")
    (t / "fk/none").mkdir(parents=True)
    # A warm cache, used with no python on PATH at all.
    setcache(realpy)
    assert hook(LS, path=none).rc == 0
    assert hook(PUSH, path=none).rc == 2
    setcache(realpy, newline=False)
    assert hook(LS, path=none).rc == 0
    # Stale, relative or non-python cache entries: ignored, probed again, rewritten.
    setcache(posix(t / "gone/python3"))
    assert hook(LS).rc == 0
    assert (pdata / "python").read_text().rstrip("\n") == realpy
    setcache("python3")
    assert hook(LS).rc == 0
    assert (pdata / "python").read_text().rstrip("\n") == realpy
    setcache(run(["bash", "-c", "command -v true"]).out.decode().strip())
    assert hook(PUSH).rc == 2
    # A cached interpreter that fails: blocked, whatever the call.
    setcache(fk("exit1", "python", 'echo "Traceback (most recent call last):" >&2; '
                                   'echo "SyntaxError: invalid syntax" >&2; exit 1') + "/python")
    r = hook(LS)
    assert r.rc == 2 and b"guard.py failed (exit 1)" in r.err
    setcache(fk("exit127", "python", "exit 127") + "/python")
    assert hook(LS).rc == 2
    # Probing: the Store alias, an old Python, `py -3` only, nothing.
    (pdata / "python").unlink(missing_ok=True)
    store = fk("store", "python3", 'echo "Python was not found; run without arguments to install from the '
                                   'Microsoft Store." >&2; exit 9009')
    r = hook(LS, path=store)
    assert r.rc == 2 and b"no Python 3.9 or later found" in r.err
    assert hook(LS, path=fk("old", "python3", 'echo "old $0"')).rc == 2
    pyonly = fk("pyonly", "py", '[ "$1" = -3 ] && shift; exec "%s" "$@"' % realpy)
    assert hook(LS, path=pyonly).rc == 0
    (pdata / "python").unlink(missing_ok=True)
    assert hook(PUSH, path=pyonly).rc == 2
    # No cache and no Python: blocked. (The call before may have cached the
    # interpreter: on Windows Git's bin/bash.exe puts its own folders before
    # the test's PATH, so mkdir and mv are found; the old runner's bash didn't.)
    (pdata / "python").unlink(missing_ok=True)
    assert hook(LS, path=none).rc == 2
    # Probe order: python before python3 (on Windows python3 is usually the
    # Store alias, slow to fail). A working python means python3 never runs.
    fk("order", "python", 'exec "%s" "$@"' % realpy)
    order = fk("order", "python3", ': > "%s"; exit 9009' % posix(t / "python3-ran"))
    if (pdata / "python").exists():
        (pdata / "python").unlink(missing_ok=True)
    assert hook(LS, path=order).rc == 0
    assert not (t / "python3-ran").exists()
    # No CLAUDE_PLUGIN_DATA: probes every time, caches nothing.
    assert hook(LS, data_dir="").rc == 0
    # Empty stdin.
    assert hook("").rc == 2
    # WIKI_HOOK_TIMING=1 logs one line per call.
    setcache(realpy)
    hook(PUSH, extra={"WIKI_HOOK_TIMING": "1"})
    assert re.match(r"guard [0-9]+ rc=2 %s " % re.escape(realpy), (pdata / "hook-timing.log").read_text())


@pytest.mark.parametrize("name", [pytest.param("../guard", id="py-launch/bad-name"),
                                  pytest.param("no_such_hook", id="py-launch/missing-script")])
def test_bad_script(name, run):
    r = run(["bash", "-c", '. "$1/scripts/py-launch.sh" "$2"', "_", PLUGIN_BASH, name], input=LS.encode())
    assert r.rc == 2


@pytest.mark.checks("py-launch/space-in-root-push", "py-launch/space-in-root-pass")
def test_space_in_root(pl, tmp_path):
    _, hook, _, setcache, _ = pl
    plug = copytree(PLUGIN, tmp_path / "plug in" / "wiki")
    assert hook(PUSH, root=posix(plug)).rc == 2
    assert hook(LS, root=posix(plug)).rc == 0


# How the plugin folder is written in a command: with ~ when it is under
# HOME, and with Windows backslashes (JSON-escaped).
@pytest.mark.checks("guard/pass-lint-tilde-form")
def test_tilde_form(guard_run, tmp_path):
    gw = copytree(TESTS / "guard-wiki", tmp_path / "gw")
    cmd = json.dumps({"tool_name": "Bash", "tool_input": {"command": "bash ~/%s/scripts/lint.sh" % PLUGIN.name}})
    assert guard_run(cmd, str(gw), home=posix(PLUGIN.parent)).rc == 0


@pytest.mark.checks("guard/pass-lint-backslash-form")
def test_backslash_form(guard_run, tmp_path):
    gw = copytree(TESTS / "guard-wiki", tmp_path / "gw")
    cmd = json.dumps({"tool_name": "Bash",
                      "tool_input": {"command": "bash %s\\scripts\\lint.sh" % PLUGIN_P.replace("/", "\\")}})
    assert guard_run(cmd, str(gw)).rc == 0
