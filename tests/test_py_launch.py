"""py-launch.sh, the hooks' launcher: interpreter cache, probe, fail-closed
exits, end to end through bash with fake interpreters (formerly the
py-launch section of run-tests.sh)."""

import re
import sys

import pytest

from conftest import CACHE, PLUGIN, PLUGIN_BASH, TESTS, copytree, hooks_guard_command, posix, write

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
        write(pdata / CACHE, value + ("\n" if newline else ""))

    return t, hook, fk, setcache, pdata


@pytest.mark.checks("py-launch/probe-and-run", "py-launch/cache-written", "py-launch/cache-trailing-newline",
                    "py-launch/warm-cache-pass", "py-launch/warm-cache-push", "py-launch/cache-no-newline",
                    "py-launch/stale-cache", "py-launch/stale-cache-rewritten", "py-launch/relative-cache",
                    "py-launch/relative-cache-rewritten", "py-launch/non-python-cache-push",
                    "py-launch/exit1-pass-blocked", "py-launch/exit1-message",
                    "py-launch/store-alias-only", "py-launch/store-alias-message",
                    "py-launch/py-only-pass", "py-launch/py-only-push", "py-launch/none",
                    "py-launch/order-python-first", "py-launch/order-python3-not-run", "py-launch/no-plugin-data",
                    "py-launch/empty-stdin", "py-launch/timing-log", "py-launch/old-cache-never-read",
                    "py-launch/below-floor-rejected", "py-launch/at-floor-used")
def test_launcher(pl, run):
    """One story, as the old section: each step leaves the cache the next expects."""
    t, hook, fk, setcache, pdata = pl
    assert hook(LS).rc == 0
    realpy = (pdata / CACHE).read_text().rstrip("\n")
    assert re.fullmatch(r"(/|[A-Za-z]:/).*/python[^/]*", realpy), realpy
    assert (pdata / CACHE).read_text().count("\n") == 1
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
    assert (pdata / CACHE).read_text().rstrip("\n") == realpy
    setcache("python3")
    assert hook(LS).rc == 0
    assert (pdata / CACHE).read_text().rstrip("\n") == realpy
    setcache(run(["bash", "-c", "command -v true"]).out.decode().strip())
    assert hook(PUSH).rc == 2
    # A cache from before the floor rose (the old file name, `python`) is
    # never read: its interpreter doesn't run, the new cache is written.
    (pdata / CACHE).unlink(missing_ok=True)
    write(pdata / "python", fk("oldcache", "python", ': > "%s"; exit 0' % posix(t / "oldcache-ran")) + "/python\n")
    assert hook(PUSH).rc == 2
    assert not (t / "oldcache-ran").exists()
    assert (pdata / CACHE).read_text().rstrip("\n") == realpy
    # A cached interpreter that fails: blocked, whatever the call.
    setcache(fk("exit1", "python", 'echo "Traceback (most recent call last):" >&2; '
                                   'echo "SyntaxError: invalid syntax" >&2; exit 1') + "/python")
    r = hook(LS)
    assert r.rc == 2 and b"guard.py failed (exit 1)" in r.err
    # Probing: the Store alias, an old Python, `py -3` only, nothing.
    (pdata / CACHE).unlink(missing_ok=True)
    store = fk("store", "python3", 'echo "Python was not found; run without arguments to install from the '
                                   'Microsoft Store." >&2; exit 9009')
    r = hook(LS, path=store)
    assert r.rc == 2 and b"no Python 3.11 or later found" in r.err
    # The probe's floor: the real Python with its version set back to just
    # under the floor is rejected; set to the floor, it is used.
    (pdata / CACHE).unlink(missing_ok=True)
    r = hook(LS, path=aged(fk, realpy, "v310", (3, 10)))
    assert r.rc == 2 and b"no Python 3.11 or later found" in r.err
    assert not (pdata / CACHE).exists()
    assert hook(LS, path=aged(fk, realpy, "v311", (3, 11))).rc == 0
    pyonly = fk("pyonly", "py", '[ "$1" = -3 ] && shift; exec "%s" "$@"' % realpy)
    assert hook(LS, path=pyonly).rc == 0
    (pdata / CACHE).unlink(missing_ok=True)
    assert hook(PUSH, path=pyonly).rc == 2
    # No cache and no Python: blocked. (The call before may have cached the
    # interpreter: on Windows Git's bin/bash.exe puts its own folders before
    # the test's PATH, so mkdir and mv are found; the old runner's bash didn't.)
    (pdata / CACHE).unlink(missing_ok=True)
    assert hook(LS, path=none).rc == 2
    # Probe order: python before python3 (on Windows python3 is usually the
    # Store alias, slow to fail). A working python means python3 never runs.
    fk("order", "python", 'exec "%s" "$@"' % realpy)
    order = fk("order", "python3", ': > "%s"; exit 9009' % posix(t / "python3-ran"))
    if (pdata / CACHE).exists():
        (pdata / CACHE).unlink(missing_ok=True)
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


def aged(fk, realpy, name, version):
    """A fake `python` folder: the real Python, with sys.version_info set to
    VERSION before the probe (its fourth argument, after -I -S -c) runs."""
    return fk(name, "python", 'exec "%s" -I -S -c "import sys; sys.version_info = (%d, %d, 0, \'final\', 0); '
                              'exec(sys.argv[1])" "$4"' % ((realpy,) + version))


# The guard's own version check, before any sibling import: exit 2 with a
# message, which py-launch.sh passes on (not "guard.py failed (exit 1)").
GUARD_AT_310 = ("import runpy, sys; sys.version_info = (3, 10, 0, 'final', 0); "
                "runpy.run_path(sys.argv[1], run_name='__main__')")
GUARD_MSG = rb"^wiki guard: Python 3\.11 or later is needed, .+ is 3\.10\. Install it \(Windows: from python\.org\), " \
            rb"then start Claude again; refusing \(fail closed\)\.\r?\n$"


@pytest.mark.checks("py-launch/guard-version-check")
def test_guard_version_check_launched(pl):
    """Through py-launch.sh: a cached interpreter that runs guard.py as 3.10."""
    t, hook, fk, _, _ = pl
    realpy = posix(sys.executable)
    old = fk("guard310", "python", 'exec "%s" -I -S -c "%s" "$5"' % (realpy, GUARD_AT_310))
    data = t / "pdata-guard310"
    write(data / CACHE, old + "/python\n")
    r = hook(LS, data_dir=posix(data))
    assert r.rc == 2 and re.match(GUARD_MSG, r.err), r.err


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
