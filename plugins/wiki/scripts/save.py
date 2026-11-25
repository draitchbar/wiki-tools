"""save.py: save a wiki's commits to its own remote.

The body of save.sh, which is its launcher (docs/adr.md, 4). The model
never gets a push: this script does it, to the URL and branch pinned in
the wiki's committed config, `.claude/settings.wiki-save.json`, read from
HEAD (never from the working tree, which must match it).

  save.sh                       integrate the remote's base, then push HEAD to it
  save.sh --check               everything but the merge and the push (a dry run)
  save.sh --update              fetch the base from the pinned URL and merge it, no push
  save.sh --unattended          as save.sh; paths that need permission go to a
                                holding branch (+ a draft pull request on GitHub)
  save.sh --update --unattended as --update; refused while a holding branch
                                (refs/heads/claude/wiki-*) is on the remote
  save.sh --allow <path>...     push with these paths, which need permission;
                                the list must be exactly the paths that do

Any other argument list is refused. The launcher puts `--plugin DIR` (the
plugin folder as bash spells it, for the `--allow` call it prints) first.

Config fields: enabled (true to save), url (https://, ssh:// or user@host:path),
base (the branch), content_paths (default wiki/ raw/ outputs/ open-questions.md;
a trailing / is a folder). Paths changed between the remote's base and the
commit: within content_paths, pushed; symlinks, submodules and .gitmodules,
never; anything else, only with the user's permission (--allow, or the
holding branch).

Git runs in a cleaned environment: every inherited GIT_* variable is dropped
except GIT_SSL_CAINFO and GIT_SSL_CAPATH, GIT_TERMINAL_PROMPT=0,
GIT_NO_REPLACE_OBJECTS=1, `-c core.hooksPath=<the plugin's git-hooks-off
folder>` and `-c http.sslVerify=true`. Pushes go to the
explicit URL, `<sha>:refs/heads/<branch>`, never forced, with
--no-follow-tags. The URL must survive `git ls-remote --get-url` unchanged,
no url.*.pushInsteadOf may exist, and in a cloud session
(CLAUDE_CODE_REMOTE=true) origin must be the pinned URL. On github.com the
base's ruleset is checked through `gh api` (not with --update).

Output: stdout's first line on success is one of
  saved <short sha> to <base>
  held <branch>
  checked: would push <short sha> to <base>
  updated <base>: ff | merge | up to date
A refusal is one `save: refused: <reason>` line on stderr plus details,
exit 1. A merge conflict is left in progress, its files listed on stdout as
`conflict: <path>` lines, exit 3.

Test seam (tests only): WIKI_SAVE_TEST_FILE_URLS=1 (exactly "1", which no
wiki session sets) accepts a local file:///path url in the config, so the
tests use a local bare repository as the remote (no host, no UNC path).
The tests reach a github.com pin's checks in-process by patching
transport(); nothing in the environment can redirect it.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any

CONFIG = ".claude/settings.wiki-save.json"
DEFAULT_CONTENT = ["wiki/", "raw/", "outputs/", "open-questions.md"]
KEYS = ("enabled", "url", "base", "content_paths")
HOLD_PREFIX = "claude/wiki-"
_PAGE = 100  # rules asked for in one page; a full page refuses
HOOKS_DIR = "git-hooks-off"
SETUP = 'docs/setup.md, "Optional: the wiki on GitHub"'
MERGE_MSG = "Merge %s from the wiki's remote"
USAGE = ("usage: save.sh [--check | --update | --unattended | --update --unattended "
         "| --allow <path>...]")
FORMS = {(): "save", ("--check",): "check", ("--update",): "update",
         ("--unattended",): "unattended", ("--update", "--unattended"): "update-unattended"}
_KEEP_GIT = ("GIT_SSL_CAINFO", "GIT_SSL_CAPATH")
_NEVER_MODES = ("120000", "160000")
# Names that configure Claude or git: a path with one of these as a
# component, at any depth, needs permission even inside content_paths.
_CONTROL = {"claude.md", "claude.local.md", ".claude", ".mcp.json", ".gitattributes", ".gitignore",
            ".github", ".githooks"}
# A conflict left in a file: both a start and an end marker line (a lone
# ======= line is a Markdown setext heading).
_MARK_START = re.compile(rb"^<<<<<<< ", re.M)
_MARK_END = re.compile(rb"^>>>>>>> ", re.M)

# URL forms (printable ASCII, no spaces). The host is group 1, the path group 2.
_HOST = r"([A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)"
_USER = r"(?:[A-Za-z0-9._~-]+@)?"
_URLS = (re.compile(r"https://" + _USER + _HOST + r"(?::[0-9]{1,5})?(/[!-~]*)"),
         re.compile(r"ssh://" + _USER + _HOST + r"(?::[0-9]{1,5})?(/[!-~]*)"),
         re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*@" + _HOST + r":([!-~]+)"))
_FILE_URL = re.compile(r"file://(/(?!/)[!-~]*)")  # no host, no UNC (file:////)
_GH_NAME = re.compile(r"[A-Za-z0-9._-]+")
_GH_BRANCH = re.compile(r"[A-Za-z0-9._/-]+")
_BAD_REF = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]")


class Refused(Exception):
    """`save: refused: <reason>` and the details on stderr, exit 1."""

    def __init__(self, reason: str, *details: str) -> None:
        super().__init__(reason)
        self.reason, self.details = reason, details


class Conflict(Exception):
    """A merge left in progress with these files unmerged: exit 3."""

    def __init__(self, base: str, files: list[str]) -> None:
        super().__init__(base)
        self.base, self.files = base, files


def _say(s: str) -> None:
    sys.stdout.write(s + "\n")


def _warn(s: str) -> None:
    sys.stdout.flush()
    sys.stderr.write("save: %s\n" % s)


def _file_urls_on() -> bool:
    """The file:// test seam (see the docstring)."""
    return os.environ.get("WIKI_SAVE_TEST_FILE_URLS") == "1"


# --- the config ------------------------------------------------------------

def valid_branch(name: str) -> bool:
    """A branch name git accepts (`git check-ref-format --branch`, the
    common rules)."""
    if not name or name.startswith(("-", "/")) or name.endswith(("/", ".", ".lock")):
        return False
    if name == "@" or ".." in name or "//" in name or "@{" in name or _BAD_REF.search(name):
        return False
    return all(not c.startswith(".") and not c.endswith(".lock") for c in name.split("/"))


def url_parts(url: str) -> tuple[str, str] | None:
    """(host in lower case, path) of an accepted URL form, else None. A
    file:// URL only with the test seam (host "")."""
    for rx in _URLS:
        m = rx.fullmatch(url)
        if m:
            return m.group(1).lower(), m.group(2)
    if _file_urls_on():
        m = _FILE_URL.fullmatch(url)
        if m:
            return "", m.group(1)
    return None


def normal(url: str) -> str:
    """For comparing two spellings: the host in lower case, no trailing /
    or .git."""
    p = url_parts(url)
    if p and p[0]:
        i = url.lower().find(p[0])
        url = url[:i] + p[0] + url[i + len(p[0]):]
    url = url.rstrip("/")
    return url[:-4].rstrip("/") if url.endswith(".git") else url


def github_repo(url: str) -> tuple[str, str] | None:
    """(owner, repo) of a URL on GitHub (github.com, or a host under it such
    as ssh.github.com), else None. A GitHub URL whose owner or repo gh
    would expand, or that breaks the API path, refuses: it must never fall
    back to the unchecked other-host case."""
    p = url_parts(url)
    if not p or not (p[0] == "github.com" or p[0].endswith(".github.com")):
        return None
    path = p[1].strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) != 2 or not all(_GH_NAME.fullmatch(x) for x in parts):
        raise Refused("can't check a GitHub repository named %s" % path,
                      "Pin the URL as https://github.com/<owner>/<repo> (you, not Claude).")
    return parts[0], parts[1]


def content_path_error(p: object) -> str | None:
    if not isinstance(p, str) or not p:
        return "%s is not a non-empty string" % json.dumps(p)
    if p.startswith("/") or "\\" in p:
        return "%s must be relative, with / as separator" % json.dumps(p)
    if any(c in ("", ".", "..") for c in p.rstrip("/").split("/")):
        return "%s has an empty, . or .. part" % json.dumps(p)
    return None


def validate(cfg: object) -> tuple[list[str], list[str]]:
    """(errors, unknown keys) of a parsed config."""
    if not isinstance(cfg, dict):
        return ["not a JSON object"], []
    errs: list[str] = []
    if not isinstance(cfg.get("enabled"), bool):
        errs.append("`enabled` must be true or false")
    url = cfg.get("url")
    if not isinstance(url, str) or url_parts(url) is None:
        errs.append("`url` must be an https://, ssh:// or user@host:path URL")
    base = cfg.get("base")
    if not isinstance(base, str) or not valid_branch(base):
        errs.append("`base` must be a branch name")
    cps = cfg.get("content_paths", DEFAULT_CONTENT)
    if not isinstance(cps, list):
        errs.append("`content_paths` must be a list of paths")
    else:
        errs += ["`content_paths`: %s" % e for e in map(content_path_error, cps) if e]
    return errs, sorted(k for k in cfg if k not in KEYS)


def in_content(path: str, cps: list[str]) -> bool:
    return any(path.startswith(c) if c.endswith("/") else path == c for c in cps)


# --- git -------------------------------------------------------------------

def clean_env() -> dict[str, str]:
    """The environment for git and gh: no inherited GIT_* but the TLS ones
    (the cloud proxy's CA bundle), no prompts. Proxy and GH_* variables
    stay (the cloud proxy needs them)."""
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("GIT_") or k.upper() in _KEEP_GIT}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


def hooks_dir() -> str:
    """The plugin's empty hooks folder (core.hooksPath for every git call):
    it holds only its README, never a hook."""
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), HOOKS_DIR)
    try:
        extra = sorted(e for e in os.listdir(d) if e != "README")
    except OSError:
        raise Refused("the plugin's empty hooks folder %s is missing; reinstall the wiki plugin"
                      % d.replace("\\", "/")) from None
    if extra:
        raise Refused("the plugin's hooks folder %s must hold only its README, not %s"
                      % (d.replace("\\", "/"), " ".join(extra)))
    return d.replace("\\", "/")


class Git:
    """git in the cleaned environment, in the wiki's root."""

    def __init__(self) -> None:
        self.env = clean_env()
        self.hooks = hooks_dir()
        self.root: str | None = None
        top = self.out("rev-parse", "--show-toplevel")
        if not top:
            raise Refused("not inside a git repo; run it from the wiki")
        self.root = top.rstrip("\n")

    def argv(self, *args: str) -> list[str]:
        return ["git", "-c", "core.hooksPath=" + self.hooks, "-c", "http.sslVerify=true"] + list(args)

    def run(self, *args: str, input: bytes = b"") -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(self.argv(*args),
                                  cwd=self.root, env=self.env, input=input,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            raise Refused("git can't be started: %s" % e) from None

    def out(self, *args: str) -> str | None:
        """stdout, or None when git fails."""
        r = self.run(*args)
        return r.stdout.decode("utf-8", "surrogateescape") if r.returncode == 0 else None

    def ok(self, *args: str) -> bool:
        return self.run(*args).returncode == 0

    def must(self, why: str, *args: str) -> str:
        r = self.run(*args)
        if r.returncode != 0:
            raise Refused(why, *_lines(r.stderr))
        return r.stdout.decode("utf-8", "surrogateescape")

    def blob(self, spec: str) -> bytes | None:
        r = self.run("cat-file", "blob", spec)
        return r.stdout if r.returncode == 0 else None

    def short(self, sha: str) -> str:
        return (self.out("rev-parse", "--short", sha) or sha[:7]).strip()


def _lines(b: bytes) -> list[str]:
    return [ln for ln in b.decode("utf-8", "surrogateescape").replace("\r", "").split("\n") if ln]


# --- the steps ---------------------------------------------------------------

_ALLOW_BAD = re.compile(r"[\x00-\x1f\x7f*?\[\]\\]")


def allow_path_ok(p: str) -> bool:
    """A path as git lists it, plain: relative, no .. part, no leading - or
    /, no wildcard, backslash or control character."""
    return (bool(p) and not p.startswith(("-", "/")) and not _ALLOW_BAD.search(p)
            and ".." not in p.split("/"))


def parse_args(argv: list[str]) -> tuple[str, list[str]]:
    """Exactly one of the accepted argument lists; no abbreviation, no
    --flag=value form."""
    t = tuple(argv)
    if t in FORMS:
        return FORMS[t], []
    if len(t) >= 2 and t[0] == "--allow":
        bad = [p for p in t[1:] if not allow_path_ok(p)]
        if bad:
            raise Refused("not a plain relative path after --allow: %s" % shlex.join(bad),
                          "--allow takes the paths save.sh printed: relative, with no .. part, no "
                          "leading - or /, no wildcard or control character.")
        return "allow", list(t[1:])
    raise Refused("unknown arguments: %s" % (shlex.join(argv) or "(none)"), USAGE)


def load_config(g: Git) -> dict[str, Any]:
    """HEAD's config, checked; the working tree's copy must match it."""
    head = g.blob("HEAD:" + CONFIG)
    if head is None:
        raise Refused("saving is off for this wiki (no committed %s)" % CONFIG)
    # Through git, so line-ending conversion (core.autocrlf) counts as no
    # change; staged and working-tree changes both refuse.
    if (not g.ok("diff", "--quiet", "--no-ext-diff", "HEAD", "--", CONFIG)
            or not g.ok("diff", "--quiet", "--no-ext-diff", "--cached", "HEAD", "--", CONFIG)
            or not os.path.isfile(os.path.join(str(g.root), CONFIG))):
        raise Refused("%s differs from the committed one" % CONFIG,
                      "Commit or restore it (you, not Claude): saving reads only the committed config.")
    try:
        cfg = json.loads(head.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise Refused("%s is not valid JSON: %s" % (CONFIG, e)) from None
    if not isinstance(cfg, dict) or cfg.get("enabled") is not True:
        raise Refused("saving is off for this wiki (`enabled` isn't true in %s)" % CONFIG)
    errs, _ = validate(cfg)
    if errs:
        raise Refused("%s is invalid: %s" % (CONFIG, "; ".join(errs)))
    cfg.setdefault("content_paths", list(DEFAULT_CONTENT))
    return cfg


def check_url(g: Git, url: str) -> None:
    """The URL git will really use is the pinned one."""
    pi = g.out("config", "--get-regexp", r"^url\..*\.pushinsteadof$")
    if pi:
        raise Refused("git config has a url.*.pushInsteadOf setting, which could send the push "
                      "elsewhere", *pi.rstrip("\n").split("\n"),
                      "Remove it (you, not Claude): `git config --show-origin --get-regexp "
                      "pushinsteadof` shows where it is.")
    # git takes a URL argument as a remote's name first: remote.<url>.pushurl
    # (or .url, ...) would send the push elsewhere. Spellings git might
    # match are refused too.
    rc = g.out("config", "--name-only", "--get-regexp", r"^remote\.")
    named = sorted({k for k in (rc or "").split("\n") if k.count(".") >= 2
                    and normal(k[len("remote."):k.rindex(".")]) == normal(url)})
    if named:
        raise Refused("git config has a remote named like the wiki's URL, which could send the push "
                      "elsewhere", *named,
                      "Remove it (you, not Claude): `git config --show-origin --get-regexp '^remote\\.'` "
                      "shows where it is.")
    r = g.run("remote", "get-url", "--push", "--all", url)
    if r.returncode == 0 and any(ln != url for ln in _lines(r.stdout)):
        raise Refused("git has a remote named like the wiki's URL, which could send the push elsewhere",
                      *_lines(r.stdout))
    got = (g.out("ls-remote", "--get-url", url) or "").rstrip("\r\n")
    if got != url:
        raise Refused("git rewrites the wiki's URL %s to %s (a url.*.insteadOf setting)" % (url, got),
                      "Remove that setting (you, not Claude): `git config --show-origin "
                      "--get-regexp insteadof` shows where it is.")
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        origin = (g.out("ls-remote", "--get-url", "origin") or "").rstrip("\r\n")
        if normal(origin) != normal(url):
            raise Refused("this session's repository is not the wiki's pinned remote",
                          "origin: %s" % origin, "pinned: %s" % url)


def transport(url: str) -> str:
    """The URL git talks to: the pinned one. (The tests patch this function
    in-process to reach a local repository for a github.com pin.)"""
    return url


def gh_json(gh: str, env: dict[str, str], *args: str) -> object:
    """`gh api --hostname github.com ARGS` as JSON; GH_HOST is dropped, so
    gh can't be pointed at another host."""
    env = {k: v for k, v in env.items() if k.upper() != "GH_HOST"}
    try:
        r = subprocess.run([gh, "api", "--hostname", "github.com"] + list(args), env=env,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise _GhError("gh can't be run: %s" % e) from None
    if r.returncode != 0:
        msg = _lines(r.stderr) or _lines(r.stdout) or ["gh exit %d" % r.returncode]
        raise _GhError(msg[-1])
    try:
        return json.loads(r.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _GhError("gh's reply is not JSON") from None


class _GhError(Exception):
    pass


def protection(g: Git, url: str, base: str) -> str:
    """The base refuses force pushes and deletion: checked on GitHub; for
    another host, the reminder to print when the save is done."""
    gr = github_repo(url)
    if gr is None:
        host = (url_parts(url) or ("the host", ""))[0] or "this host"
        return ("note: %s can't be checked from here; it must refuse force pushes and deletion "
                "of %s (docs/setup.md)" % (host, base))
    o, r = gr
    if not _GH_BRANCH.fullmatch(base):
        raise Refused("can't check GitHub's protection of a branch named %s" % base)
    gh = shutil.which("gh")
    fix = "Set up the ruleset as %s shows." % SETUP
    if not gh:
        raise Refused("gh isn't installed, so %s/%s's protection of %s can't be checked" % (o, r, base),
                      fix)
    try:
        rules = gh_json(gh, g.env, "repos/%s/%s/rules/branches/%s?per_page=%d" % (o, r, base, _PAGE))
        if not isinstance(rules, list):
            raise _GhError("the rules reply is not a list")
        if len(rules) >= _PAGE:
            raise Refused("%s/%s has %d or more rules on %s; too many to check" % (o, r, _PAGE, base), fix)
        rules = [x for x in rules if isinstance(x, dict)]
        types = {x.get("type") for x in rules}
        missing = [t for t in ("non_fast_forward", "deletion") if t not in types]
        if missing:
            raise Refused("%s/%s doesn't protect %s: no %s rule" % (o, r, base, " or ".join(missing)),
                          fix)
        ids: set[int] = set()
        for x in rules:
            if x.get("type") not in ("non_fast_forward", "deletion"):
                continue
            i = x.get("ruleset_id")
            if not isinstance(i, int) or isinstance(i, bool):
                raise Refused("%s/%s's %s rule names no ruleset, so who can bypass it can't be checked"
                              % (o, r, x.get("type")), fix)
            ids.add(i)
        for i in sorted(ids):
            rs = gh_json(gh, g.env, "repos/%s/%s/rulesets/%d" % (o, r, i))
            if not isinstance(rs, dict) or "current_user_can_bypass" not in rs:
                raise Refused("%s/%s's ruleset %d doesn't say whether you can bypass it (no "
                              "current_user_can_bypass)" % (o, r, i), fix)
            by = rs["current_user_can_bypass"]
            if by != "never":
                raise Refused("%s/%s's ruleset %d lets you bypass it (current_user_can_bypass: %s)"
                              % (o, r, i, by), fix)
    except _GhError as e:
        raise Refused("can't check %s/%s's protection of %s: %s" % (o, r, base, e), fix) from None
    return ""


def remote_heads(g: Git, turl: str) -> dict[str, str]:
    """ref -> sha of the remote's branches."""
    out = g.must("can't reach the wiki's remote", "ls-remote", "--heads", turl)
    heads = {}
    for ln in out.split("\n"):
        sha, _, ref = ln.partition("\t")
        if ref:
            heads[ref] = sha
    return heads


def fetch_base(g: Git, turl: str, base: str) -> str:
    """The remote's base, fetched (and the history unshallowed once when
    HEAD and it have no merge base): its sha."""
    g.must("can't fetch %s from the wiki's remote" % base,
           "fetch", "--no-tags", "--no-recurse-submodules", turl, "refs/heads/" + base)
    rsha = g.must("can't fetch %s from the wiki's remote" % base, "rev-parse", "FETCH_HEAD").strip()
    if not g.ok("merge-base", "HEAD", rsha):
        if (g.out("rev-parse", "--is-shallow-repository") or "").strip() == "true":
            g.must("can't fetch the full history of %s" % base, "fetch", "--unshallow", "--no-tags",
                   "--no-recurse-submodules", turl, "refs/heads/" + base)
        if not g.ok("merge-base", "HEAD", rsha):
            raise Refused("this wiki and its remote's %s share no history" % base)
    return rsha


def check_pin(g: Git, rsha: str, url: str, own: list[str]) -> list[str]:
    """A different pin on the remote: the change must come from the user.
    Returns the content_paths that sort the paths: the remote base's (a
    commit can't widen them for itself), the defaults when its config
    lacks them or is unreadable, this commit's (own) when it has none."""
    b = g.blob("%s:%s" % (rsha, CONFIG))
    if b is None:
        return own
    try:
        rc = json.loads(b.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return list(DEFAULT_CONTENT)
    if not isinstance(rc, dict):
        return list(DEFAULT_CONTENT)
    if isinstance(rc.get("url"), str) and rc["url"] != url:
        raise Refused("the wiki's remote pins %s, this commit %s" % (rc["url"], url),
                      "A change of the pin comes from you, through the remote: pull it by hand "
                      "(you, not Claude).")
    cps = rc.get("content_paths", DEFAULT_CONTENT)
    if not isinstance(cps, list) or any(content_path_error(p) for p in cps):
        return list(DEFAULT_CONTENT)
    return [str(p) for p in cps]


def ancestor(g: Git, a: str, b: str) -> bool:
    return g.ok("merge-base", "--is-ancestor", a, b)


def integrate(g: Git, rsha: str, base: str) -> str:
    """Bring the remote's base into HEAD: "up to date", "ff" or "merge"."""
    head = g.must("no commit at HEAD", "rev-parse", "HEAD").strip()
    if ancestor(g, rsha, head):
        return "up to date"
    if ancestor(g, head, rsha):
        g.must("can't fast-forward to %s from the wiki's remote" % base, "merge", "--ff-only", rsha)
        return "ff"
    r = g.run("merge", "--no-ff", "--no-edit", "-m", MERGE_MSG % base, rsha)
    if r.returncode == 0:
        return "merge"
    if g.ok("rev-parse", "-q", "--verify", "MERGE_HEAD"):
        out = g.out("diff", "--name-only", "--diff-filter=U", "-z") or ""
        raise Conflict(base, sorted({f for f in out.split("\0") if f}))
    raise Refused("can't merge %s from the wiki's remote" % base, *_lines(r.stderr + r.stdout))


def changes(g: Git, a: str, b: str) -> list[tuple[str, str, str, str]]:
    """(old mode, new mode, new blob, path) of each path changed a..b."""
    out = g.must("can't list the changes", "diff", "--raw", "--no-renames", "--no-abbrev",
                 "--no-ext-diff", "-z", a, b)
    toks = out.split("\0")
    res = []
    for meta, path in zip(toks[0::2], toks[1::2], strict=False):
        f = meta.lstrip(":").split(" ")
        if len(f) >= 4 and path:
            res.append((f[0], f[1], f[3], path))
    return res


def marked(g: Git, ch: list[tuple[str, str, str, str]]) -> list[str]:
    """Changed files (text, still there) that hold conflict markers."""
    todo = [(blob, path) for om, nm, blob, path in ch
            if nm.startswith("100") and blob.strip("0")]
    if not todo:
        return []
    bad: list[str] = []
    try:
        p = subprocess.Popen(g.argv("cat-file", "--batch"), cwd=g.root, env=g.env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError as e:
        raise Refused("git can't be started: %s" % e) from None
    assert p.stdin is not None and p.stdout is not None
    try:
        # One blob at a time: a wiki's raw/ can be large.
        for blob, path in todo:
            why = "can't read %s to check it for conflict markers" % path
            try:
                p.stdin.write(blob.encode("ascii") + b"\n")
                p.stdin.flush()
                head = p.stdout.readline().split()
            except (OSError, UnicodeEncodeError):
                raise Refused(why) from None
            if len(head) != 3 or head[1] != b"blob" or not head[2].isdigit():
                raise Refused(why)
            size = int(head[2])
            body = p.stdout.read(size)
            if len(body) != size or p.stdout.read(1) != b"\n":
                raise Refused(why)
            if b"\0" not in body[:8000] and _MARK_START.search(body) and _MARK_END.search(body):
                bad.append(path)
    finally:
        try:
            p.stdin.close()
        except OSError:
            pass
        p.stdout.close()
        p.wait()
    return bad


def tiers(ch: list[tuple[str, str, str, str]], cps: list[str]) -> tuple[list[str], list[str]]:
    """(never, needs permission) paths, each sorted."""
    never = sorted({p for om, nm, _, p in ch if om in _NEVER_MODES or nm in _NEVER_MODES
                    or _parts(p) & {".gitmodules"}}, key=_key)
    perm = sorted({p for _, _, _, p in ch if p not in never
                   and (p == CONFIG or _parts(p) & _CONTROL or not in_content(p, cps))}, key=_key)
    return never, perm


def _parts(p: str) -> set[str]:
    """The path's components in lower case (case-insensitive file systems)."""
    return {c.lower() for c in p.split("/")}


def _key(p: str) -> bytes:
    return p.encode("utf-8", "surrogateescape")


def call(script: str, paths: list[str]) -> str:
    """The exact --allow call (or the plain one, with no paths)."""
    s = "bash " + shlex.quote(script)
    return s + (" --allow " + " ".join(shlex.quote(p) for p in paths) if paths else "")


def push(g: Git, turl: str, url: str, sha: str, branch: str) -> None:
    r = g.run("push", "--no-follow-tags", "--no-signed", "--recurse-submodules=no", turl,
              "%s:refs/heads/%s" % (sha, branch))
    if r.returncode != 0:
        err = _lines(r.stderr)
        if any("[rejected]" in ln or "non-fast-forward" in ln or "fetch first" in ln for ln in err):
            raise Refused("%s on the wiki's remote moved meanwhile; run save again" % branch, *err)
        raise Refused("the push to %s failed" % url, *err)


def open_pr(g: Git, url: str, branch: str, base: str, perm: list[str]) -> None:
    """A draft pull request for the holding branch (GitHub, REST)."""
    gr = github_repo(url)
    if gr is None:
        _later.append("note: open a merge request for %s into %s on the wiki's host; merging it is the "
              "permission" % (branch, base))
        return
    gh = shutil.which("gh")
    body = ("An unattended wiki run changed paths that need your permission:\n\n%s\n\n"
            "Look at the diff; merging this pull request is the permission."
            % "\n".join("- `%s`" % p for p in perm))
    try:
        if not gh:
            raise _GhError("gh isn't installed")
        pr = gh_json(gh, g.env, "-X", "POST", "repos/%s/%s/pulls" % gr,
                     "-f", "title=Wiki changes that need your permission", "-f", "head=" + branch,
                     "-f", "base=" + base, "-f", "body=" + body, "-F", "draft=true")
        u = pr.get("html_url") if isinstance(pr, dict) else None
        if not isinstance(u, str):
            raise _GhError("no html_url in the reply")
    except _GhError as e:
        _later.append("warning: no draft pull request opened (%s); open one for %s into %s" % (e, branch, base))
        return
    _say("draft pull request: %s" % u)


# Warnings and notes for stderr once the save is done (a refusal shows only its own).
_later: list[str] = []


def dirty_warning(g: Git) -> None:
    if g.out("status", "--porcelain", "-z"):
        _later.append("warning: uncommitted changes aren't saved, only commits (`git status` lists them)")


# --- the forms --------------------------------------------------------------

def run(form: str, allow: list[str], script: str) -> int:
    g = Git()
    if g.ok("rev-parse", "-q", "--verify", "MERGE_HEAD"):
        raise Refused("a merge is in progress", "Resolve its conflicts, commit the merge, then save again.")
    if not g.ok("rev-parse", "-q", "--verify", "HEAD^{commit}"):
        raise Refused("this wiki has no commit yet")
    cfg = load_config(g)
    url, base, cps = cfg["url"], cfg["base"], cfg["content_paths"]
    check_url(g, url)
    turl = transport(url)
    update = form.startswith("update")
    note = "" if update else protection(g, url, base)
    heads = remote_heads(g, turl)
    if "refs/heads/" + base not in heads:
        raise Refused("the wiki's remote has no %s yet: create %s on the remote first (you, not Claude)"
                      % (base, base))
    if form == "update-unattended":
        held = sorted(r[len("refs/heads/"):] for r in heads if r.startswith("refs/heads/" + HOLD_PREFIX))
        if held:
            raise Refused("merge or delete %s first" % " ".join(held),
                          "An unattended save waits there for your permission; runs don't build on it.")
    rsha = fetch_base(g, turl, base)
    cps = check_pin(g, rsha, url, cps)

    if update:
        _say("updated %s: %s" % (base, integrate(g, rsha, base)))
        return 0

    head = g.must("no commit at HEAD", "rev-parse", "HEAD").strip()
    how, frm = "up to date", rsha
    if form == "check":
        # No merge: the paths are those HEAD changed since the common base.
        frm = g.must("no merge base", "merge-base", "HEAD", rsha).strip()
        if not ancestor(g, rsha, head) and not ancestor(g, head, rsha):
            how = "merge"
    else:
        how = integrate(g, rsha, base)
    sha = g.must("no commit at HEAD", "rev-parse", "HEAD").strip()
    ch = changes(g, frm, sha)
    bad = marked(g, ch)
    if bad:
        raise Refused("conflict markers left in %s" % " ".join(bad),
                      "Resolve them and commit, then save again.")
    never, perm = tiers(ch, cps)
    if never:
        raise Refused("symlinks and submodules are never saved: %s" % " ".join(never),
                      "Remove them from the commits (you decide how), then save again.")
    nothing = ancestor(g, sha, rsha)

    if form == "allow" and set(allow) != set(perm):
        if not perm:
            raise Refused("no path needs permission", "run: " + call(script, []))
        raise Refused("the --allow list isn't the set of paths that need permission",
                      "need permission: %s" % " ".join(perm), "run: " + call(script, perm))
    if perm and form in ("save", "check"):
        raise Refused("these changes need your permission: %s" % " ".join(perm),
                      "look: git diff %s %s -- %s" % (g.short(frm), g.short(sha),
                                                      " ".join(shlex.quote(p) for p in perm)),
                      "run: " + call(script, perm))

    dirty_warning(g)
    if note:
        _later.append(note)
    short = g.short(sha)
    if form == "check":
        _say("checked: would push %s to %s" % (short, base))
        if how == "merge":
            _say("would merge %s from the wiki's remote first" % base)
        elif nothing:
            _say("nothing new: %s already has it" % base)
        return 0
    if perm and form == "unattended":
        revs = g.must("can't list the commits", "rev-list", "--reverse", "%s..%s" % (rsha, sha)).split()
        branch = HOLD_PREFIX + revs[0][:12]
        push(g, turl, url, sha, branch)
        _say("held %s" % branch)
        open_pr(g, url, branch, base, perm)
        _say("needs your permission: %s" % " ".join(perm))
        return 0
    if not nothing:
        push(g, turl, url, sha, base)
    _say("saved %s to %s" % (short, base))
    if how != "up to date":
        _say("merged %s from the wiki's remote first (%s)" % (base, how))
    if nothing:
        _say("nothing new: %s already has it" % base)
    return 0


def main(argv: list[str]) -> int:
    plugin = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
    if argv[:1] == ["--plugin"] and len(argv) > 1:
        plugin, argv = argv[1], argv[2:]
    _later.clear()
    try:
        form, allow = parse_args(argv)
        rc = run(form, allow, plugin + "/scripts/save.sh")
        for w in _later:
            _warn(w)
    except Refused as e:
        sys.stdout.flush()
        sys.stderr.write("save: refused: %s\n" % e.reason)
        for d in e.details:
            sys.stderr.write(d + "\n")
        rc = 1
    except Conflict as e:
        for f in e.files:
            _say("conflict: %s" % f)
        _warn("merge conflict: the merge of %s from the wiki's remote is left in progress; resolve "
              "the files listed, commit the merge, then save again" % e.base)
        rc = 3
    except Exception as e:  # an internal error is never a save
        sys.stdout.flush()
        sys.stderr.write("save: refused: internal error: %s: %s\n" % (type(e).__name__, e))
        rc = 1
    sys.stdout.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
