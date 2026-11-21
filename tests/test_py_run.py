"""py-run.sh (docs/adr.md, 4): the launcher for scripts and the bridge
lib-source.sh calls (formerly the py-run section of run-tests.sh). End to
end by nature: a copy of py-run.sh beside a test script that echoes what it
got, and lib-source.sh's bridge through bash. Also the argument round trip
from Python to bash (step 6's first Windows check)."""

import os
import re
import shutil
import sys

import pytest

from conftest import CACHE, FLOOR, IS_WIN, SCRIPTS, SCRIPTS_P, TESTS, copytree, git, posix, write

ECHO_ARGS = r'''import sys
sys.stdout.buffer.write(("exe=%s\n" % sys.executable.replace("\\", "/")).encode())
for a in sys.argv[1:]:
    sys.stdout.buffer.write(("arg=%s\n" % a).encode("utf-8", "surrogateescape"))
sys.stdout.buffer.write(("stdin=%s\n" % sys.stdin.read()).encode())
sys.exit(int(sys.argv[1]) if sys.argv[1:] and sys.argv[1].isdigit() else 0)
'''


@pytest.fixture(scope="module")
def prt(tmp_path_factory):
    d = tmp_path_factory.mktemp("prt")
    shutil.copy(SCRIPTS / "py-run.sh", d / "py-run.sh")
    write(d / "echo_args.py", ECHO_ARGS)
    return posix(d)


def prx(run, prt, *args, env=None, input=b""):
    return run(["bash", prt + "/py-run.sh"] + list(args), env=env, input=input, merged=True)


ODD = ["a b", "æøå", "/c/x", "C:/y", "/tmp/z", "*", "lib/*", "@p.txt", "-e @x", '"q"', "back\\",
       "", "two\nlines", "$HOME", "'s'"]


@pytest.mark.checks("argv/round-trip")
def test_argv_round_trip(run, tmp_path):
    """Arguments from Python reach bash unchanged (on Windows, Git Bash
    parses its own command line: wildcards, @file, quotes). A file p.txt
    and a folder lib/ with a file exist, so an expansion would show."""
    write(tmp_path / "p.txt", "x\n")
    write(tmp_path / "lib" / "a.txt", "x\n")
    r = run(["bash", "-c", 'for a; do printf "%s\\0" "$a"; done', "_"] + ODD, cwd=tmp_path)
    assert r.rc == 0, r
    assert r.out.decode("utf-8").split("\0")[:-1] == ODD


@pytest.mark.checks("py-run/arguments-unchanged")
def test_arguments_unchanged(run, prt):
    r = prx(run, prt, "echo_args", "0", "a b", "æøå", "/c/x", "C:/y", "/tmp/z")
    assert r.rc == 0
    assert "arg=a b\narg=æøå\narg=/c/x\narg=C:/y\narg=/tmp/z\n" in r.merged.decode("utf-8")


@pytest.mark.parametrize("code", [pytest.param(1, id="py-run/exit-1"), pytest.param(3, id="py-run/exit-3")])
def test_exit_code(code, run, prt):
    assert prx(run, prt, "echo_args", str(code)).rc == code


@pytest.mark.checks("py-run/stdin")
def test_stdin(run, prt):
    assert b"stdin=hello\n" in prx(run, prt, "echo_args", input=b"hello").merged


@pytest.mark.parametrize("name", [pytest.param("../echo_args", id="py-run/bad-name"),
                                  pytest.param("nosuch", id="py-run/missing-script")])
def test_bad_script(name, run, prt):
    assert prx(run, prt, name).rc == 2


# The interpreter: CLAUDE_PLUGIN_DATA's cache first, then the hooks' cache
# under CLAUDE_CONFIG_DIR, each only if it names an executable python*.
@pytest.fixture
def caches(tmp_path):
    fake = write(tmp_path / "fakepy" / "python3.11", "#!/bin/sh\necho fake-python\n")
    fake.chmod(0o755)
    data, cfg = tmp_path / "prdata", tmp_path / "prcfg" / "plugins" / "data" / "wiki-wiki-tools"
    data.mkdir()
    cfg.mkdir(parents=True)
    return posix(fake), data, cfg, posix(tmp_path / "prcfg")


@pytest.mark.checks("py-run/cache-plugin-data", "py-run/cache-config-dir", "py-run/cache-rejected-probes",
                    "py-run/writes-no-cache")
def test_caches(run, prt, caches):
    fake, data, cfg, cfgdir = caches
    write(data / CACHE, fake + "\n")
    assert prx(run, prt, "echo_args", env={"CLAUDE_PLUGIN_DATA": posix(data)}).merged == b"fake-python\n"
    write(cfg / CACHE, fake + "\n")
    r = prx(run, prt, "echo_args", env={"CLAUDE_PLUGIN_DATA": None, "CLAUDE_CONFIG_DIR": cfgdir})
    assert r.merged == b"fake-python\n"
    write(data / CACHE, "/bin/sh\n")
    write(cfg / CACHE, "relative/python\n")
    r = prx(run, prt, "echo_args", env={"CLAUDE_PLUGIN_DATA": posix(data), "CLAUDE_CONFIG_DIR": cfgdir})
    assert re.match(rb"exe=.*python", r.merged.split(b"\n")[0])
    assert (data / CACHE).read_bytes() == b"/bin/sh\n"


@pytest.mark.checks("py-run/old-cache-never-read")
def test_old_cache_never_read(run, prt, caches):
    """A cache from before the floor rose (the old name, `python`) is never
    read, in either place: the probe finds the real Python."""
    fake, data, cfg, cfgdir = caches
    write(data / "python", fake + "\n")
    write(cfg / "python", fake + "\n")
    r = prx(run, prt, "echo_args", env={"CLAUDE_PLUGIN_DATA": posix(data), "CLAUDE_CONFIG_DIR": cfgdir})
    assert r.rc == 0 and b"fake-python" not in r.merged
    assert re.match(rb"exe=.*python", r.merged.split(b"\n")[0])


@pytest.mark.checks("py-run/below-floor-rejected")
def test_below_floor_rejected(run, prt, tmp_path):
    """The probe's floor: the real Python with its version set back to just
    under the floor is rejected, as in py-launch.sh."""
    for c in ("python3", "py"):
        write(tmp_path / "bin" / c, "#!/bin/sh\nexit 1\n").chmod(0o755)
    write(tmp_path / "bin" / "python", '#!/bin/sh\nexec "%s" -I -S -c "import sys; sys.version_info = '
          '(3, 10, 0, \'final\', 0); exec(sys.argv[1])" "$4"\n' % posix(sys.executable)).chmod(0o755)
    env = {"CLAUDE_PLUGIN_DATA": posix(tmp_path / "data"), "CLAUDE_CONFIG_DIR": posix(tmp_path / "cfg"),
           "PATH": str(tmp_path / "bin") + os.pathsep + os.environ.get("PATH", "")}
    r = prx(run, prt, "echo_args", env=env)
    assert r.rc == 1 and r.merged.startswith(b"echo_args: no Python 3.11 or later found"), r.merged


@pytest.fixture(scope="module")
def nopy(tmp_path_factory):
    """No Python: every candidate fails, nothing cached."""
    t = tmp_path_factory.mktemp("nopy")
    for c in ("python", "python3", "py"):
        write(t / "bin" / c, "#!/bin/sh\nexit 1\n").chmod(0o755)
    return {"CLAUDE_PLUGIN_DATA": posix(t / "data"), "CLAUDE_CONFIG_DIR": posix(t / "cfg"),
            "PATH": str(t / "bin") + os.pathsep + os.environ.get("PATH", "")}


@pytest.mark.checks("py-run/no-python")
def test_no_python(run, prt, nopy):
    r = prx(run, prt, "echo_args", env=nopy)
    assert r.rc == 1
    assert r.merged.startswith(b"echo_args: no Python 3.11 or later found")


@pytest.mark.checks("py-run/same-candidates", "py-run/same-floor")
def test_same_candidates():
    """The same probe as py-launch.sh: same candidates, same order, the same
    floor (and the one the tests and wiki_check.py's cache name assume)."""
    pl, pr = (SCRIPTS / "py-launch.sh").read_text(), (SCRIPTS / "py-run.sh").read_text()
    a = re.search(r"^ *for _pl_c in (.*); do$", pl, re.M).group(1)
    b = re.search(r"^ *for c in (.*); do$", pr, re.M).group(1)
    assert a == b
    fa = re.findall(r"^_pl_floor=(.*)$", pl, re.M)
    fb = re.findall(r"^_pr_floor=(.*)$", pr, re.M)
    assert fa == fb == [FLOOR]
    assert '"/plugins/data/wiki-wiki-tools/%s"' % CACHE in (SCRIPTS / "wiki_check.py").read_text()
    assert "sys.version_info < (%s)" % FLOOR.replace(".", ", ") in (SCRIPTS / "guard.py").read_text()


# The bridge: lib-source.sh sources py-run.sh lazily, safe under set -u.
@pytest.fixture(scope="module")
def ls(tmp_path_factory):
    d = copytree(TESTS / "sources" / "lib-source", tmp_path_factory.mktemp("ls") / "ls")
    git(d / "wiki", "init", "-q")
    (d / "wiki" / "sub").mkdir()
    return d


@pytest.mark.checks("py-run/bridge-lazy-set-u")
def test_bridge_lazy(run, ls):
    script = ('. "$1/lib-source.sh"; declare -F _pr_call >/dev/null && echo early; SRC_PLUGIN=$2\n'
              'src_validate_instance "$3" good && echo valid; declare -F _pr_call >/dev/null && echo loaded;'
              ' echo "conv=${MSYS2_ARG_CONV_EXCL-unset}"')
    r = run(["bash", "-uc", script, "_", SCRIPTS_P, posix(ls / "plugin"), posix(ls / "wiki")],
            cwd=ls / "wiki", merged=True)
    assert r.merged.split() == [b"valid", b"loaded", b"conv=unset"]


@pytest.mark.checks("py-run/bridge-relative-root")
def test_bridge_relative_root(run, ls):
    r = run(["bash", "-c", '. "$1/lib-source.sh"; SRC_PLUGIN=$2; src_validate_instance .. wrong-key', "_",
             SCRIPTS_P, posix(ls / "plugin")], cwd=ls / "wiki" / "sub", merged=True)
    assert (r.rc, r.merged) == (1, b"../.claude/sources/instances/wrong-key.md: key 'other' doesn't match the file name\n")


@pytest.mark.checks("py-run/bridge-internal-error")
def test_bridge_internal_error(run, tmp_path):
    r = run(["bash", "-c", '. "$1/lib-source.sh"; _src_py settings-rules "$2"', "_", SCRIPTS_P,
             posix(tmp_path / "no" / "such" / "settings.json")], merged=True)
    assert r.rc == 3 and r.merged.startswith(b"sourcelib: internal error")


@pytest.mark.checks("py-run/bridge-no-python")
def test_bridge_no_python(run, ls, nopy):
    r = run(["bash", "-c", '. "$1/lib-source.sh"; SRC_PLUGIN=$2; src_validate_instance "$3" good', "_",
             SCRIPTS_P, posix(ls / "plugin"), posix(ls / "wiki")], cwd=ls / "wiki", env=nopy, merged=True)
    assert r.rc == 1 and r.merged.startswith(b"sourcelib: no Python 3.11 or later found")


@pytest.mark.checks("py-run/wrapper-no-python")
def test_wrapper_no_python(run, tmp_path, nopy):
    """Through a wrapper, which hides the bridge's stderr: "doesn't validate"."""
    w, scans = tmp_path / "prw", tmp_path / "prw-scans"
    scans.mkdir()
    write(w / ".claude/sources/instances/scans.md",
          "---\nkey: scans\ntype: local-folder\nroots:\n  - %s\n---\n" % posix(scans))
    git(w, "init", "-q")
    r = run(["bash", SCRIPTS_P + "/../sources/local-folder/read.sh", "scans", "list", posix(scans)],
            cwd=w, env=nopy, merged=True)
    assert r.rc == 1 and b"doesn't validate; run /wiki:init" in r.merged


@pytest.mark.skipif(not IS_WIN, reason="Windows only: Git Bash mount paths")
@pytest.mark.checks("py-run/windows-mount-path-refused")
def test_windows_mount_path_refused(run, ls):
    """A Git Bash mount path (/tmp/...) is refused, not reported missing."""
    script = ('d=$(mktemp -d); cp -r "$2" "$d/w"; . "$1/lib-source.sh"; src_validate_instance "$d/w" good;'
              ' rc=$?; rm -rf "$d"; exit $rc')
    r = run(["bash", "-c", script, "_", SCRIPTS_P, posix(ls / "wiki")], merged=True)
    assert r.rc == 3 and b"is a Git Bash path, which Python on Windows can't use" in r.merged
