"""Shared pytest setup for the wiki plugin's tests (docs/adr.md, 7).

Two layers:
- in-process: a script's Python module is called through its main(argv),
  the CLI contract its .sh launcher runs, with stdout and stderr captured
  in write order (`cli`, `guard_run`);
- end to end: the .sh launchers and the scripts that are still bash, run by
  a real bash (Git Bash on Windows) (`run`, `bash_argv`).
`--e2e` runs the in-process tests through the launchers instead, so the same
tests prove both paths give the same result.

Paths: every test works in pytest's tmp_path, written with forward slashes,
on both platforms; `norm` maps the spellings a path can come back in
(native, forward slashes, Git Bash's /c/...) to @TMP@ and @PLUGIN@.

Each test carries a check name of the form <area>/<case>, as its
parametrize id or in a `checks` marker; `--check-names` prints them.
"""

import io
import os
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
PLUGIN = (TESTS.parent / "plugins" / "wiki").resolve()
SCRIPTS = PLUGIN / "scripts"
IS_WIN = os.name == "nt"
# The Python floor, as the launchers' _pl_floor and _pr_floor (a test checks
# they agree), and the interpreter cache named after it.
FLOOR = "3.11"
CACHE = "python-" + FLOOR

sys.path.insert(0, str(SCRIPTS))

import contract  # noqa: E402
import sourcelib  # noqa: E402


def posix(p):
    """A path with forward slashes, as tests hand it to scripts."""
    return str(p).replace("\\", "/")


def msys(p):
    """Git Bash's spelling of a Windows path (C:/x -> /c/x); unchanged elsewhere."""
    p = posix(p)
    m = re.match(r"([A-Za-z]):/", p)
    return "/%s/%s" % (m.group(1).lower(), p[3:]) if m else p


PLUGIN_P = posix(PLUGIN)          # as Python spells it
HOME_U = "/home/u"                # the home the fixtures use
PLUGIN_BASH = msys(PLUGIN_P)      # as bash's `pwd` prints it
SCRIPTS_P = posix(SCRIPTS)

# A gmail instance's reader binding to the claude.ai Gmail connector
# (docs/adr.md, 23), as frontmatter lines: gmail is access: tools, so its
# settings rules come from these lists, not from the contract.
GMAIL_T = "mcp__claude_ai_Gmail__"
GMAIL_DENY = ("send_message", "reply", "forward", "create_draft", "update_draft", "delete_draft",
              "trash_message", "trash_thread", "untrash_message", "untrash_thread",
              "mark_message_spam", "mark_thread_spam", "unmark_message_spam", "unmark_thread_spam",
              "create_label", "delete_label", "update_label", "label_message", "label_thread",
              "unlabel_message", "unlabel_thread", "update_message_labels",
              "apply_sensitive_message_label", "apply_sensitive_thread_label", "list_drafts", "get_draft")
GMAIL_OPS = {"search threads": "search_threads", "read thread": "get_thread", "list labels": "list_labels",
             "thread dates": "get_thread", "read message": "get_message", "download attachment": "download_gmail_attachment"}
GMAIL_READER = ("reader:\n" + "".join("  - %s: %s%s\n" % (o, GMAIL_T, t) for o, t in GMAIL_OPS.items())
                + "reader_deny:\n" + "".join("  - %s%s\n" % (GMAIL_T, t) for t in GMAIL_DENY))


# --- options and markers -------------------------------------------------

def pytest_addoption(parser):
    parser.addoption("--e2e", action="store_true",
                     help="run the in-process tests through the .sh launchers instead")
    parser.addoption("--record", action="store_true",
                     help="rewrite recorded outputs (tests/fixtures/*/*.out) instead of comparing")
    parser.addoption("--check-names", action="store_true",
                     help="print the bash check names the collected tests carry, one per line")


def pytest_configure(config):
    config.addinivalue_line("markers", "checks(*names): the bash runner's check names this test replaces")


# Parallel runs (run-tests.sh: -n auto --dist loadfile, docs/adr.md, 15):
# a module runs on one worker, so its module fixtures and its story run
# once; except the modules in SPREAD, whose tests stand alone: each is
# split into one part per worker, which go to any worker. They come last,
# to fill in around the long modules (#115).
SPREAD = {"test_guard.py", "test_save.py", "test_pii_check.py", "test_connectors.py",
          "test_dev_env.py", "test_sources_due.py"}


def _spread(nodeid):
    return nodeid.split("::")[0].rsplit("/", 1)[-1] in SPREAD


def pytest_collection_modifyitems(items):
    items.sort(key=lambda i: _spread(i.nodeid))


@pytest.hookimpl(optionalhook=True)  # xdist's hooks: unknown without it
def pytest_xdist_make_scheduler(config, log):
    if config.getvalue("dist") != "loadfile":
        return None
    from xdist.scheduler import LoadScopeScheduling

    class ByModule(LoadScopeScheduling):
        def _split_scope(self, nodeid):
            mod = nodeid.split("::")[0]
            if not _spread(nodeid):
                return mod
            return "%s#%d" % (mod, zlib.crc32(nodeid.encode()) % self.numnodes)
    return ByModule(config, log)


def check_names(item):
    m = item.get_closest_marker("checks")
    if m:
        return list(m.args)
    cs = getattr(item, "callspec", None)
    if cs is not None:
        return [cs.id]
    return [item.name]


# Each module's time, setup to teardown, summed over its tests: a module
# that isn't `spread` runs on one worker, so the slowest one bounds the run
# (docs/adr.md, 15). Shown with --durations, which CI sets (#115).
_MODULE_TIME: dict = {}


def pytest_runtest_logreport(report):
    m = report.nodeid.split("::")[0]
    _MODULE_TIME[m] = _MODULE_TIME.get(m, 0.0) + report.duration


def pytest_terminal_summary(terminalreporter, config):
    if config.getoption("durations") is None or not _MODULE_TIME:
        return
    terminalreporter.write_sep("=", "time per module (its tests' setup, call and teardown)")
    for m, t in sorted(_MODULE_TIME.items(), key=lambda x: -x[1])[:15]:
        terminalreporter.write_line("%8.2fs %s" % (t, m))


def pytest_collection_finish(session):
    if session.config.getoption("--check-names"):
        for item in session.items:
            for n in check_names(item):
                print("name " + n)


# --- processes ------------------------------------------------------------

class Result:
    def __init__(self, rc, out=b"", err=b"", merged=None):
        self.rc, self.out, self.err = rc, out, err
        self.merged = out + err if merged is None else merged

    def __repr__(self):
        return "Result(rc=%r, out=%r, err=%r)" % (self.rc, self.out, self.err)


def _find_bash():
    if not IS_WIN:
        b = shutil.which("bash")
        if not b:
            pytest.exit("no bash on PATH", 3)
        return b
    for b in (os.environ.get("CLAUDE_CODE_GIT_BASH_PATH"), os.environ.get("WIKI_TEST_BASH")):
        if b and os.path.isfile(b):
            return b
    # Git Bash beside git: <git>/mingw64/libexec/git-core -> <git>/bin/bash.exe
    # (bin/, which sets up PATH; never WSL's System32\bash.exe).
    try:
        ex = subprocess.run(["git", "--exec-path"], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, check=True).stdout.decode().strip()
        b = Path(ex).parents[2] / "bin" / "bash.exe"
        if b.is_file():
            return str(b)
    except (OSError, subprocess.CalledProcessError, IndexError):
        pass
    pytest.exit("Git Bash not found: set CLAUDE_CODE_GIT_BASH_PATH or WIKI_TEST_BASH", 3)


BASH = _find_bash()

# Variables a developer's or a Claude session's environment may carry that
# would change what the scripts do.
_DROP = ("CLAUDECODE", "CLAUDE_PLUGIN_DATA", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR",
         "CLAUDE_CONFIG_DIR", "WIKI_LINT_TODAY", "WIKI_CHECK_TEMPLATE", "WIKI_INSTALL_ANSWER",
         "WIKI_HOOK_TIMING", "MSYS2_ARG_CONV_EXCL", "MSYS2_ENV_CONV_EXCL", "GIT_DIR",
         "GIT_WORK_TREE", "WIKI_TOOLS_DEV_VENV", "UV_PROJECT_ENVIRONMENT", "UV_PYTHON_DOWNLOADS",
         "CLAUDE_CODE_REMOTE", "WIKI_SAVE_TEST_FILE_URLS", "FAKE_GH_MODE", "FAKE_GH_LOG")


@pytest.fixture(scope="session")
def pydata(tmp_path_factory):
    """A CLAUDE_PLUGIN_DATA whose interpreter cache names the Python running
    the tests, so launchers run the same one (py-run.sh, py-launch.sh)."""
    d = tmp_path_factory.mktemp("pydata")
    (d / CACHE).write_bytes((posix(sys.executable) + "\n").encode())
    return posix(d)


@pytest.fixture(scope="session")
def base_env(pydata):
    env = {k: v for k, v in os.environ.items() if k not in _DROP}
    # The test repos have no .gitattributes; keep a user's core.autocrlf
    # (Windows) from converting their files.
    env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.autocrlf",
               GIT_CONFIG_VALUE_0="false", CLAUDE_PLUGIN_DATA=pydata)
    return env


def _env(base, extra):
    env = dict(base)
    for k, v in (extra or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return env


# Git Bash started from a native program parses its own command line
# (found on Windows 2026-11-14 by test_py_run's argv round trip): unquoted
# wildcards are globbed, @file is read as a response file, and \" outside
# quotes throws the quoting out of step. So on Windows the arguments of an
# MSYS program (bash, sh, dash) go through a NUL-separated file that this
# fixed driver reads; it then starts the program from bash, as the old
# runner always did, where arguments pass unchanged. (Windows check: all of
# test_py_run's awkward arguments arrive, 2026-11-14.)
_DRIVER = 'mapfile -d "" -t a < "$1"; rm -f "$1"; exec "${a[@]}"\n'
_MSYS = ("bash.exe", "sh.exe", "dash.exe")


@pytest.fixture(scope="session")
def run(base_env, tmp_path_factory):
    """run(argv, cwd=None, env=None, input=b"", merged=False) -> Result.
    argv[0] "bash" means the test bash. merged=True: one stream, in order."""
    d = tmp_path_factory.mktemp("argv")
    driver = d / "driver.sh"
    driver.write_bytes(_DRIVER.encode())
    n = [0]

    def _wrap(argv):
        if not IS_WIN or Path(argv[0]).name.lower() not in _MSYS:
            return argv
        n[0] += 1
        f = d / ("a%d" % n[0])
        # <git>/bin/bash.exe (and sh.exe) are Git's native launchers, which
        # parse the command line again; the driver starts the MSYS program
        # itself, <git>/usr/bin/<name>, which inherits the launcher's PATH.
        p = Path(argv[0])
        if p.parent == Path(BASH).parent:
            u = p.parent.parent / "usr" / "bin" / p.name
            if u.is_file():
                p = u
        argv = [posix(p)] + argv[1:]
        f.write_bytes(b"".join(a.encode("utf-8", errors="surrogateescape") + b"\0" for a in argv))
        return [BASH, posix(driver), posix(f)]

    def _run(argv, cwd=None, env=None, input=b"", merged=False):
        argv = _wrap([BASH if argv[0] == "bash" else str(argv[0])] + [str(a) for a in argv[1:]])
        e = _env(base_env, env)
        if merged:
            r = subprocess.run(argv, cwd=cwd, env=e, input=input,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            return Result(r.returncode, merged=r.stdout)
        r = subprocess.run(argv, cwd=cwd, env=e, input=input,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return Result(r.returncode, r.stdout, r.stderr)
    return _run


def git(cwd, *args, date=None, check=True):
    """git with a test identity (and, with date, that commit date); output
    dropped; failure raises unless check=False."""
    env = dict(os.environ, GIT_COMMITTER_DATE=date, GIT_AUTHOR_DATE=date) if date else None
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                           "-c", "core.autocrlf=false", "-c", "init.defaultBranch=main"] + list(args),
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, check=check, env=env).returncode


class Story:
    """Checks of a section that replays a sequence of steps on one wiki, in
    order, as the bash runner did: each step records its checks by name;
    the tests then assert them one by one (`story_params`)."""

    def __init__(self):
        self.results = {}

    def check(self, name, ok, detail=""):
        assert name not in self.results, "duplicate check name " + name
        self.results[name] = (bool(ok), detail)

    def found(self, name, text, out):
        self.check(name, text in out, "%r missing in:\n%s" % (text, out))

    def eq(self, name, want, got):
        self.check(name, want == got, "expected %r, got %r" % (want, got))


def story_assert(story, name):
    ok, detail = story.results[name]
    assert ok, detail


# --- in-process -----------------------------------------------------------

class _Stream:
    """sys.stdout/sys.stderr stand-in: bytes to its own buffer and to the
    shared merged one, in write order; text written as UTF-8."""

    def __init__(self, own, merged):
        self.own, self.merged, self.buffer = own, merged, self

    def write(self, s):
        b = s.encode("utf-8", errors="surrogateescape") if isinstance(s, str) else bytes(s)
        self.own.write(b)
        self.merged.write(b)
        return len(s)

    def flush(self):
        pass


class _Stdin:
    def __init__(self, data):
        self.buffer = io.BytesIO(data)

    def read(self):
        return self.buffer.read().decode("utf-8", errors="surrogateescape")


def reset_modules():
    """Module state that would leak between in-process calls."""
    contract._cache.clear()
    sourcelib._shown.clear()
    sourcelib._pairs.clear()
    sourcelib._sink = None


def call_main(fn, argv, cwd=None, env=None, input=b""):
    """fn(argv) (or fn() when argv is None) with env, cwd and stdin set and
    stdout/stderr captured: Result. SystemExit is the exit code."""
    out, err, merged = io.BytesIO(), io.BytesIO(), io.BytesIO()
    saved_env, saved_cwd = dict(os.environ), os.getcwd()
    saved = sys.stdin, sys.stdout, sys.stderr
    reset_modules()
    try:
        for k in _DROP:
            os.environ.pop(k, None)
        os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.autocrlf",
                          GIT_CONFIG_VALUE_0="false")
        for k, v in (env or {}).items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if cwd is not None:
            os.chdir(cwd)
        sys.stdin = _Stdin(input)
        sys.stdout, sys.stderr = _Stream(out, merged), _Stream(err, merged)
        try:
            rc = fn(argv) if argv is not None else fn()
        except SystemExit as e:
            rc = e.code
        rc = 0 if rc is None else rc
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved
        os.chdir(saved_cwd)
        os.environ.clear()
        os.environ.update(saved_env)
        reset_modules()
    return Result(rc, out.getvalue(), err.getvalue(), merged.getvalue())


# Each script: its module and how its launcher calls main().
def _launcher_args(name, args):
    if name in ("wiki-check", "sources", "sourcelib", "save"):
        return ["--plugin", PLUGIN_BASH] + list(args)
    return list(args)


_MODULES = {"lint": "lint", "wiki-check": "wiki_check", "sync-status": "sync_status",
            "sources": "sources", "sourcelib": "sourcelib", "save": "save"}
# The bridge as the wrappers call it: lib-source.sh's _src_py, SRC_PLUGIN the
# plugin as bash spells it.
_BRIDGE = '. "$1/lib-source.sh"; SRC_PLUGIN=$2; shift 2; _src_py "$@"'



@pytest.fixture(scope="session")
def cli(request, run, pydata):
    """cli(name, *args, cwd=..., env=None, input=b"") -> Result: the script
    `name` (lint, wiki-check, ...) in-process through its module's main, or
    with --e2e through bash <plugin>/scripts/<name>.sh."""
    e2e = request.config.getoption("--e2e")

    def _cli(name, *args, cwd, env=None, input=b"", both=False):
        """both: separate streams and the real merged order (e2e runs a
        second time for it, when both streams have output; with one empty
        the merged order is the other stream)."""
        if e2e:
            if name == "sourcelib":
                argv = ["bash", "-c", _BRIDGE, "_", SCRIPTS_P, PLUGIN_BASH] + list(args)
            else:
                argv = ["bash", SCRIPTS_P + "/%s.sh" % name] + list(args)
            r = run(argv, cwd=cwd, env=env, input=input)
            if both and r.out and r.err:
                r.merged = run(argv, cwd=cwd, env=env, input=input, merged=True).merged
            return r
        mod = __import__(_MODULES[name])
        env = dict(env or {}, CLAUDE_PLUGIN_DATA=pydata)
        return call_main(mod.main, _launcher_args(name, args), cwd=cwd, env=env, input=input)
    return _cli


# The guard as hooks.json runs it, for --e2e and the end-to-end tests.
def hooks_guard_command():
    text = (PLUGIN / "hooks" / "hooks.json").read_text()
    m = re.search(r'"command": "(.*py-launch\.sh\\" guard.*?)"\s*$', text, re.M)
    return m.group(1).replace('\\"', '"')


def home_env(home):
    """HOME for a Python started by Git Bash: Git Bash rewrites HOME=/home/u
    into its own install folder, so on Windows the home goes in as
    USERPROFILE (contract._home's fallback), protected from conversion."""
    if IS_WIN:
        return {"HOME": None, "USERPROFILE": home, "MSYS2_ENV_CONV_EXCL": "USERPROFILE"}
    return {"HOME": home}


@pytest.fixture(scope="session")
def guard_run(request, run, pydata):
    """guard_run(input_bytes, project_dir, home) -> Result: guard.py's
    decision, in-process or (--e2e) through the hooks.json command."""
    e2e = request.config.getoption("--e2e")
    import guard

    def _g(data, project, home="/home/u", e2e_only=False):
        project = posix(project)
        if isinstance(data, str):
            data = data.encode("utf-8")
        if e2e or e2e_only:
            env = dict(home_env(home), CLAUDE_PLUGIN_ROOT=PLUGIN_BASH, CLAUDE_PLUGIN_DATA=pydata,
                       CLAUDE_PROJECT_DIR=project)
            # On Windows Git Bash sets an unset HOME from the account's real
            # profile, which Python would prefer to USERPROFILE: unset it
            # inside bash (found on Windows 2026-11-14).
            cmd = ("unset HOME; " if IS_WIN else "") + hooks_guard_command()
            return run(["bash", "-c", cmd], env=env, input=data)
        return call_main(guard.main, None, env={"HOME": home, "USERPROFILE": None,
                                                 "CLAUDE_PROJECT_DIR": project}, input=data)
    return _g


# --- output ---------------------------------------------------------------

_CYGPATH = {}


def _cygpath(p):
    """Git Bash's own spelling of a native path, mounts included: pytest's
    temp folder sits under the user temp folder, which Git Bash mounts on
    /tmp (found on Windows 2026-11-14). Cached per path."""
    if p not in _CYGPATH:
        exe = Path(BASH).parent.parent / "usr" / "bin" / "cygpath.exe"
        try:
            r = subprocess.run([str(exe), "-u", p], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            _CYGPATH[p] = r.stdout.decode("utf-8").strip() if r.returncode == 0 else ""
        except OSError:
            _CYGPATH[p] = ""
    return _CYGPATH[p]


def spellings(p):
    """The forms one path can come back in."""
    p = posix(p)
    forms = {p, p.replace("/", "\\"), msys(p)}
    if IS_WIN:
        try:
            forms.add(posix(os.path.realpath(p)))
        except OSError:
            pass
        forms.add(_cygpath(p))
    forms.discard("")
    return sorted(forms, key=len, reverse=True)


def norm(data, tmp=None, extra=()):
    """Output as text with the test folder as @TMP@, the plugin as @PLUGIN@
    (in any spelling) and a carriage return as \\r."""
    s = data.decode("utf-8", errors="surrogateescape") if isinstance(data, bytes) else data
    pairs = [(f, "@TMP@") for f in (spellings(tmp) if tmp else [])]
    pairs += [(f, "@PLUGIN@") for f in spellings(PLUGIN_P)]
    pairs += list(extra)
    for f, to in sorted(pairs, key=lambda x: len(x[0]), reverse=True):
        s = s.replace(f, to)
    return s.replace("\r", "\\r")


def recorded(request, path, text):
    """Compare text with a recorded fixture, or rewrite it with --record."""
    path = Path(path)
    if request.config.getoption("--record"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8", errors="surrogateescape"))
        return
    want = path.read_bytes().decode("utf-8", errors="surrogateescape")
    assert text == want


def write(path, data):
    """Write bytes (str as UTF-8), making parent folders; no newline mapping."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8", errors="surrogateescape") if isinstance(data, str) else data)
    return path


def copytree(src, dst):
    shutil.copytree(str(src), str(dst), symlinks=True)
    return Path(dst)
