"""The repo's dev environment (docs/adr.md, 15): scripts/dev-env.sh, which
run-tests.sh and dev-lint.sh source to use .venv (made by `uv sync --locked`
from uv.lock) and to stop when it is missing or stale; and the policy in
pyproject.toml. End to end through bash, on a copy of the scripts with a
fake uv first on PATH and fake tools in .venv; the real install is CI's
own `uv sync --locked`."""

import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from conftest import BASH, CACHE, FLOOR, TESTS, git, msys, posix, write

REPO = TESTS.parent
COPY = ["scripts/dev-env.sh", "scripts/dev-lint.sh", "tests/run-tests.sh", "plugins/wiki/scripts/py-run.sh"]

# A fake uv: logs "<cwd>|<UV_PYTHON_DOWNLOADS>|<args>", says FAKE_UV_ERR on
# stderr, exits FAKE_UV_RC.
FAKE_UV = r'''#!/usr/bin/env bash
printf '%s|%s|%s\n' "$(pwd)" "${UV_PYTHON_DOWNLOADS-}" "$*" >> "$FAKE_UV_LOG"
[ -n "${FAKE_UV_ERR:-}" ] && printf '%s\n' "$FAKE_UV_ERR" >&2
exit "${FAKE_UV_RC:-0}"
'''
# A fake tool (python, ruff, mypy, shellcheck): logs "<name> <args>", fails
# when FAKE_FAIL names it, else exits 0 (so `python -c 'import xdist'` works).
FAKE_TOOL = r'''#!/usr/bin/env bash
printf '%s %s\n' "${0##*/}" "$*" >> "$FAKE_LOG"
[ "${FAKE_FAIL:-}" = "${0##*/}" ] && exit 1
exit 0
'''
OUTDATED = "error: The environment is outdated; run `uv sync`"
LOCK_STALE = ("error: The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.\n"
              "hint: run `uv lock`")


def exe(path, body):
    p = write(path, body)
    p.chmod(0o755)
    return p


@pytest.fixture
def dev(tmp_path):
    """A copy of the scripts at r/, the fake uv in uvbin/, logs beside them.
    Returns (root, env) for the `run` fixture."""
    root = tmp_path / "r"
    for f in COPY:
        write(root / f, (REPO / f).read_bytes())
    exe(tmp_path / "uvbin" / "uv", FAKE_UV)
    env = {"PATH": str(tmp_path / "uvbin") + os.pathsep + os.environ.get("PATH", ""),
           "FAKE_UV_LOG": posix(tmp_path / "uv.log"), "FAKE_LOG": posix(tmp_path / "tools.log"),
           "CI": "1"}
    return root, env


def venv(root):
    """A fake .venv/bin/python (the .venv/bin layout on both platforms)."""
    exe(root / ".venv" / "bin" / "python", FAKE_TOOL)


def log(tmp_path, name):
    p = tmp_path / name
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def pytest_cmd(root, args=""):
    """As run-tests.sh starts pytest with CI set (dev's env): parallel, the
    slowest tests' times after the summary."""
    return ("python -X utf8 -m pytest %s -n auto --dist loadfile --durations=20%s"
            % (msys(posix(root / "tests")), args))


@pytest.mark.checks("dev-env/current")
def test_current(run, dev, tmp_path):
    """A current .venv: its Python runs pytest, in parallel, with the given
    arguments; uv only checked, in the repo root, also when run-tests.sh is
    started from another folder."""
    root, env = dev
    venv(root)
    r = run(["bash", root / "tests" / "run-tests.sh", "-k", "x y"], cwd=tmp_path, env=env)
    assert r.rc == 0, r
    assert log(tmp_path, "tools.log") == ["python -c import xdist", pytest_cmd(root, " -k x y")]
    assert log(tmp_path, "uv.log") == ["%s|never|sync --locked --check -q" % msys(posix(root))]


@pytest.mark.parametrize("err", [pytest.param(OUTDATED, id="dev-env/stale"),
                                 pytest.param(LOCK_STALE, id="dev-env/lock-stale")])
def test_stale(err, run, dev, tmp_path):
    root, env = dev
    venv(root)
    r = run(["bash", root / "tests" / "run-tests.sh"], env=dict(env, FAKE_UV_RC="1", FAKE_UV_ERR=err))
    assert r.rc == 1, r
    assert err.encode() in r.err
    assert b"run-tests: .venv is missing or out of date with uv.lock. Run: uv sync --locked\n" in r.err
    assert log(tmp_path, "tools.log") == []


@pytest.mark.checks("dev-env/missing")
def test_missing(run, dev, tmp_path):
    """uv content, but no .venv to run."""
    root, env = dev
    r = run(["bash", root / "tests" / "run-tests.sh"], env=env)
    assert r.rc == 1, r
    assert b"out of date with uv.lock. Run: uv sync --locked" in r.err


@pytest.mark.checks("dev-env/no-uv")
def test_no_uv(run, dev, tmp_path):
    root, env = dev
    venv(root)
    os.remove(tmp_path / "uvbin" / "uv")
    env = dict(env, PATH=str(tmp_path / "uvbin") + os.pathsep + str(Path(BASH).parent))
    if run(["bash", "-c", "command -v uv"], env=env).rc == 0:
        pytest.skip("a uv beside bash")
    r = run(["bash", root / "tests" / "run-tests.sh"], env=env)
    assert r.rc == 1, r
    assert b"run-tests: uv not found. Install uv 0.13.7 or later" in r.err
    assert b"then run: uv sync --locked" in r.err
    assert log(tmp_path, "tools.log") == []


@pytest.mark.checks("dev-env/uv-project-environment")
def test_uv_project_environment(run, dev, tmp_path):
    root, env = dev
    venv(root)
    r = run(["bash", root / "tests" / "run-tests.sh"], env=dict(env, UV_PROJECT_ENVIRONMENT="x"))
    assert r.rc == 1, r
    assert b"run-tests: UV_PROJECT_ENVIRONMENT is set; these scripts use .venv. Unset it.\n" in r.err
    assert log(tmp_path, "uv.log") == []


@pytest.mark.checks("dev-env/downloads-never")
def test_downloads_never(run, dev, tmp_path):
    """A caller's UV_PYTHON_DOWNLOADS would override pyproject.toml's."""
    root, env = dev
    venv(root)
    r = run(["bash", root / "tests" / "run-tests.sh"], env=dict(env, UV_PYTHON_DOWNLOADS="automatic"))
    assert r.rc == 0, r
    assert [x.split("|")[1] for x in log(tmp_path, "uv.log")] == ["never"]


@pytest.mark.checks("dev-env/uv-could-not-check")
def test_uv_exit_2(run, dev, tmp_path):
    root, env = dev
    venv(root)
    r = run(["bash", root / "tests" / "run-tests.sh"],
            env=dict(env, FAKE_UV_RC="2", FAKE_UV_ERR="error: No interpreter found"))
    assert r.rc == 1, r
    assert b"error: No interpreter found\nrun-tests: uv could not check .venv (its message is above)\n" in r.err
    assert b"out of date" not in r.err


@pytest.mark.checks("dev-env/override")
def test_override(run, dev, tmp_path):
    """WIKI_TOOLS_DEV_VENV=off: uv never asked; pytest from the Python
    py-run.sh finds (here the plugin-data cache's)."""
    root, env = dev
    fake = exe(tmp_path / "ovr" / "python", FAKE_TOOL)
    write(tmp_path / "data" / CACHE, posix(fake) + "\n")
    r = run(["bash", root / "tests" / "run-tests.sh", "-x"],
            env=dict(env, WIKI_TOOLS_DEV_VENV="off", CLAUDE_PLUGIN_DATA=posix(tmp_path / "data")))
    assert r.rc == 0, r
    assert b"run-tests: WIKI_TOOLS_DEV_VENV=off: tools from PATH, outside uv.lock\n" in r.err
    assert log(tmp_path, "uv.log") == []
    assert log(tmp_path, "tools.log") == ["python -c import pytest", "python -c import xdist",
                                          pytest_cmd(root, " -x")]


@pytest.mark.checks("dev-env/override-bad-value")
def test_override_bad_value(run, dev, tmp_path):
    root, env = dev
    venv(root)
    r = run(["bash", root / "tests" / "run-tests.sh"], env=dict(env, WIKI_TOOLS_DEV_VENV="1"))
    assert r.rc == 1, r
    assert b"run-tests: WIKI_TOOLS_DEV_VENV must be off or unset\n" in r.err
    assert log(tmp_path, "uv.log") == [] and log(tmp_path, "tools.log") == []


LAYOUT = 'set -u; . "$1/scripts/dev-env.sh"; _de_venv t; echo "rc=$? bin=$_de_bin py=$_de_py"; echo still here\n'


@pytest.mark.parametrize("unix", [pytest.param(True, id="dev-env/layout-bin"),
                                  pytest.param(False, id="dev-env/layout-scripts")])
def test_layout(unix, run, dev, tmp_path):
    """.venv/bin/python, else .venv/Scripts/python.exe (Windows); sourcing
    and failing never exit."""
    root, env = dev
    r0 = msys(posix(root))
    if unix:
        venv(root)
        exe(root / ".venv" / "Scripts" / "python.exe", "")
        want = "rc=0 bin=%s/.venv/bin py=%s/.venv/bin/python" % (r0, r0)
    else:
        exe(root / ".venv" / "Scripts" / "python.exe", "")
        want = "rc=0 bin=%s/.venv/Scripts py=%s/.venv/Scripts/python.exe" % (r0, r0)
    r = run(["bash", "-c", LAYOUT, "_", posix(root)], env=env)
    assert r.out.decode().splitlines() == [want, "still here"], r
    r = run(["bash", "-c", LAYOUT, "_", posix(root)], env=dict(env, FAKE_UV_RC="1"))
    assert r.out.decode().splitlines() == ["rc=1 bin= py=", "still here"], r


# --- dev-lint.sh ------------------------------------------------------------

@pytest.fixture
def lint(dev, tmp_path):
    """The copy as a git repo, with fake tools in .venv/bin, two tracked
    .sh files and one untracked."""
    root, env = dev
    venv(root)
    for t in ("ruff", "mypy", "shellcheck"):
        exe(root / ".venv" / "bin" / t, FAKE_TOOL)
    write(root / ".gitignore", ".venv/\n")
    write(root / "x" / "a b.sh", "echo a\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    write(root / "untracked.sh", "echo u\n")
    git(root, "commit", "-q", "-m", "c")
    return root, env


def lint_run(run, root, env, **extra):
    return run(["bash", root / "scripts" / "dev-lint.sh"], cwd=root / "tests", env=dict(env, **extra))


def tracked_sh(root):
    out = subprocess.run(["git", "-C", str(root), "ls-files", "*.sh"], stdout=subprocess.PIPE,
                         check=True).stdout.decode()
    return out.split("\n")[:-1]


@pytest.mark.checks("dev-env/lint-clean")
def test_lint_clean(run, lint, tmp_path):
    root, env = lint
    r = lint_run(run, root, env, GITHUB_ACTIONS="")
    assert r.rc == 0, r
    assert r.out.decode().splitlines()[-1] == "dev-lint: clean"
    sh = tracked_sh(root)
    assert "untracked.sh" not in sh and "x/a b.sh" in sh
    tools = log(tmp_path, "tools.log")
    assert tools[0] == "ruff check ."
    assert tools[1] == "mypy "
    assert tools[2] == "shellcheck -S warning " + " ".join(sh)
    assert len(tools) == 3


@pytest.mark.checks("dev-env/lint-github")
def test_lint_github(run, lint, tmp_path):
    root, env = lint
    r = lint_run(run, root, env, GITHUB_ACTIONS="true")
    assert r.rc == 0, r
    assert log(tmp_path, "tools.log")[0] == "ruff check --output-format=github ."


@pytest.mark.parametrize("tool", [pytest.param(t, id="dev-env/lint-fails-" + t)
                                  for t in ("ruff", "mypy", "shellcheck")])
def test_lint_one_fails(tool, run, lint, tmp_path):
    """One step failing: the others still run; it is named at the end."""
    root, env = lint
    r = lint_run(run, root, env, FAKE_FAIL=tool)
    assert r.rc == 1, r
    assert r.err.decode().splitlines()[-1] == "dev-lint: failed: %s" % tool
    assert [x.split(" ")[0] for x in log(tmp_path, "tools.log")] == ["ruff", "mypy", "shellcheck"]
    assert r.out.decode().count("== ") == 4


@pytest.mark.checks("dev-env/lint-crlf")
def test_lint_crlf(run, lint, tmp_path):
    """Committed CRLF or mixed endings fail, named; a binary file with a CR
    doesn't. Git's view of the index, not grep (Git Bash's can miss a CR)."""
    root, env = lint
    write(root / "c r l f.txt", b"a\r\nb\r\n")
    write(root / "mixed.txt", b"a\r\nb\n")
    write(root / "bin.dat", b"\0\r\n")
    git(root, "add", "c r l f.txt", "mixed.txt", "bin.dat")
    git(root, "commit", "-q", "-m", "crlf")
    r = lint_run(run, root, env, GITHUB_ACTIONS="true")
    assert r.rc == 1, r
    out = r.out.decode().splitlines()
    i = out.index("== LF line endings")
    assert out[i + 1:] == ["c r l f.txt", "mixed.txt", "::error::CRLF line endings in the files above"]
    assert r.err.decode().splitlines()[-1] == "dev-lint: failed: LF"


@pytest.mark.checks("dev-env/lint-crlf-work-tree-only")
def test_lint_crlf_work_tree_only(run, lint, tmp_path):
    """CRs only in the work tree (a Windows checkout's core.autocrlf) are
    never committed: clean."""
    root, env = lint
    write(root / "x" / "a b.sh", b"echo a\r\n")
    r = lint_run(run, root, env)
    assert r.rc == 0, r


@pytest.mark.checks("dev-env/lint-stale")
def test_lint_stale(run, lint, tmp_path):
    root, env = lint
    r = lint_run(run, root, env, FAKE_UV_RC="1")
    assert r.rc == 1, r
    assert b"dev-lint: .venv is missing or out of date with uv.lock. Run: uv sync --locked\n" in r.err
    assert log(tmp_path, "tools.log") == []


@pytest.mark.checks("dev-env/lint-override-missing-tool")
def test_lint_override_missing_tool(run, lint, tmp_path):
    """Under the override the tools come from PATH; one not there fails
    its step, never passes."""
    root, env = lint
    for t in ("ruff", "mypy"):
        exe(tmp_path / "tools" / t, FAKE_TOOL)
    env = dict(env, WIKI_TOOLS_DEV_VENV="off",
               PATH=str(tmp_path / "tools") + os.pathsep + str(Path(BASH).parent))
    if run(["bash", "-c", "command -v shellcheck"], env=env).rc == 0:
        pytest.skip("a shellcheck beside bash")
    r = lint_run(run, root, env)
    assert r.rc == 1, r
    assert b"dev-lint: WIKI_TOOLS_DEV_VENV=off: tools from PATH, outside uv.lock\n" in r.err
    assert b"dev-lint: shellcheck is not installed\n" in r.err
    assert r.err.decode().splitlines()[-1] == "dev-lint: failed: shellcheck"
    assert log(tmp_path, "uv.log") == []
    assert [x.split(" ")[0] for x in log(tmp_path, "tools.log")] == ["ruff", "mypy"]


# --- the policy in pyproject.toml and uv.lock --------------------------------

def toml(name):
    with open(REPO / name, "rb") as f:
        return tomllib.load(f)


@pytest.mark.checks("dev-env/config-python-floor")
def test_config_floor():
    """pyproject.toml and uv.lock state the plugin's floor (conftest.FLOOR)."""
    assert toml("pyproject.toml")["project"]["requires-python"] == ">=" + FLOOR
    assert toml("uv.lock")["requires-python"] == ">=" + FLOOR


@pytest.mark.checks("dev-env/config-uv")
def test_config_uv():
    """No package build, no uv-managed Python downloads, wheels only."""
    uv = toml("pyproject.toml")["tool"]["uv"]
    assert uv["package"] is False
    assert uv["python-downloads"] == "never"
    assert uv["no-build"] is True
    assert re.fullmatch(r">=\d+\.\d+\.\d+", uv["required-version"])


@pytest.mark.checks("dev-env/config-no-uv-run")
def test_config_no_uv_run():
    """No script, workflow or hook runs `uv run` (it syncs implicitly)."""
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "*.sh", ".github/workflows/",
                          ".githooks/"], stdout=subprocess.PIPE, check=True).stdout.decode()
    files = [f for f in out.split("\0") if f]
    assert "tests/run-tests.sh" in files
    bad = [f for f in files if re.search(r"\buv\s+run\b", (REPO / f).read_text(encoding="utf-8"))]
    assert bad == []


@pytest.mark.checks("dev-env/config-ci-uv")
def test_config_ci_uv():
    """CI's setup-uv: pinned by commit SHA, installing the uv that
    pyproject.toml's required-version names, in every job."""
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    steps = re.findall(r"uses: astral-sh/setup-uv@(\S+)(.*?)(?=\n      - |\Z)", ci, re.S)
    assert len(steps) == 2, steps   # lint, test
    want = toml("pyproject.toml")["tool"]["uv"]["required-version"][2:]
    for ref, body in steps:
        assert re.fullmatch(r"[0-9a-f]{40}", ref), ref
        assert re.search(r'^\s+version: "%s"' % re.escape(want), body, re.M), body
        assert "python-version" not in body
