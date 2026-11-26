"""PreToolUse guard (every tool, matcher "*"): keep the sources read-only,
keep Claude away from the guard machinery, and block git push. Run through
py-launch.sh, which turns any exit other than 0 (allow) or 2 (block) into a
block. Replaced guard.sh and block-push.sh (speed plan, step 2b).

Structure: hookjson.parse turns the hook input into a HookCall (what kind
of call: shell, write, read, harmless, mcp or unknown; its command, paths
and contents). CHECKS lists the checks in order, one small function each,
no_push first; each gets the call and a Context (the plugin folder, the
wiki root and what the source files say, each loaded once, when first
needed) and returns a reason to refuse or None. The first reason wins; a
call no check refuses is allowed. Harmless and mcp tools pass (but no
GitHub MCP tool, which can push); an unknown tool is refused (fail closed).

What the guard knows about sources comes from the contracts at hook time:
every standard type (plugins/wiki/sources/*/SOURCE.md), every local type of
this wiki (.claude/sources/types/*/SOURCE.md) and every instance
(.claude/sources/instances/*.md). From them it collects:
  guard words  blocked in shell commands and in non-Markdown files;
  scripts      wrapper scripts allowed as a plain `bash <path> <args>` call;
  roots        of filesystem instances: blocked in shell commands,
               read-only for the write tools.
  readers      the reader bindings of access: tools instances (their
               reader lists, docs/adr.md, 11).
A source file that can't be used (no frontmatter, unknown type, a
filesystem instance without roots, a reader binding that doesn't parse, a
name that isn't a kebab-case key, a folder that can't be listed) blocks
every shell and write call (fail closed), except read-only diagnostics:
git status/log/diff/show and sources.sh list/show/contract. The message
names the first such file.

MCP tools pass, except as the reader bindings say: a tool bound only with
a limit (`<field>=<value>`, a dispatcher's operation name) runs only with
one of its bindings' values in that input field, which no settings rule
can express (docs/adr.md, 3 and 11). While a source file can't be used, an
MCP tool named in any reader list is refused too, since its limits are
unknown. Denying a reader's write tools (reader_deny) is left to the deny
rules sources.sh settings gives, as for forbidden_tools.

Shell tools (Bash, PowerShell, Monitor's command):
- git push, checked first so no exception below can let one through. The
  user pushes. `git stash push` passes, but only written exactly so: "git"
  (or "git.exe") directly followed by "stash push"; `git -C stash push`
  could be a real push. Known false positive: a command naming both "git"
  and the word "push", e.g. in a commit message. Rephrase it.
  When saving is on for the wiki (its .claude/settings.wiki.json in the
  working tree has "save": {"enabled": true}), the message names
  /wiki:save; only the wording changes.
- gh api, pr, repo, release, workflow, secret, variable or gist, right after git
  push: they write to GitHub past git. "gh" counts only as a command word
  (options such as -R owner/repo may stand before the subcommand), never as
  text; a plain call of an allowed script (a wrapper around gh) passes.
- a nested claude session: "claude" as a command word, never as text.
- then a protected path (the plugin folder, .claude/sources, settings,
  plugins, skills and agents, .git/hooks, .git/config, .mcp.json; skills
  only the wiki's own, not the user's ~/.claude/skills), a guard
  word or a filesystem root. Exceptions (Bash and Monitor, since the
  scripts run in Git Bash): a plain call of one of the plugin's core
  scripts, or of a script a contract lists, with no ; & | < > ` $ and no
  "..". Wrappers outside the plugin don't count: the wikis' settings allow
  them by wildcard.
- save.sh: only as a plain call of the plugin's copy. With no arguments
  but --check, --update and --unattended it passes like any core script.
  Any other argument is the permission case (save.sh --allow <paths>,
  saving paths that need the user's permission): only from the Bash tool,
  only as --allow followed by plain paths, and then, if every other check
  lets it through, not a plain pass: the guard answers "ask"
  (hookjson.ask), so the user gets Claude Code's permission prompt. Any
  other command naming save.sh is refused.
Write tools (Write, Edit, MultiEdit, NotebookEdit): no protected path,
nothing in the plugin folder, nothing inside a filesystem root (the path
resolved first), no guard word in non-Markdown content (a helper script
around a CLI).
agent_only types (e.g. codebase): their roots are for subagents only. In
the main session (hook input without agent_id) Read, Grep and Glob on them
are blocked, and their wrappers run only the contract's main_ops, named as
plain words. A main-session shell command naming such a root gets the
agent_only message.

Messages only (the command is refused either way): a Bash command that
would be an allowed script call but for ; & | < > $ or a backtick is told
which character, and where to look for passing it (the type's SOURCE.md);
one that chains an allowed script call to another command is told to run
the script as a call of its own. A command naming a protected path or a
guard word is told what to do instead: there is no exception for commands
that only read (`cat`, `git log`), since the guard matches text and can't
tell them apart safely (docs/guard.md, known false positives).

Whitespace in commands is ASCII only, and lowercasing is ASCII only, so the
Kelvin sign is not a k.

Windows: Python sees native paths (C:/...) where Git Bash sees /c/...; every
path is matched in both spellings, and a /c/... path is turned into c:/...
before the filesystem is touched.

This is a guardrail, not a security boundary: an obfuscated command can
still get through.
"""

from __future__ import annotations

import os
import sys

# The Python floor (py-launch.sh's _pl_floor), checked before anything a
# newer Python may need: exit 2, so py-launch.sh passes this message on
# instead of a bare "guard.py failed". Up to here this file must parse on
# an old Python (no match, no except*).
if sys.version_info < (3, 11):
    sys.stderr.write("wiki guard: Python 3.11 or later is needed, %s is %d.%d. Install it (Windows: "
                     "from python.org), then start Claude again; refusing (fail closed).\n"
                     % (sys.executable, sys.version_info[0], sys.version_info[1]))
    sys.exit(2)

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402
import re  # noqa: E402

import contract as C  # noqa: E402
import hookjson  # noqa: E402
from hookjson import lower, norm  # noqa: E402

# Annotation-only names: typing is never imported at run time (AGENTS.md).
TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from typing import NoReturn

    from hookjson import HookCall

    # A check: the reason to refuse the call, or None.
    Check = Callable[[HookCall, "Context"], str | None]

# Whitespace in commands: ASCII only, so `bash<U+2003><plugin>/scripts/lint.sh`
# is not a plain script call.
WS = "[ \t\n\v\f\r]"
NOCHAIN = "[^;&|<>`$]"

# git push: "git stash push" is let through only when written exactly so.
_STASH_PUSH = re.compile(r"\bgit(\.exe)?\s+stash\s+push\b", re.ASCII)
_PUSH = re.compile(r"\bgit\b.*\bpush\b", re.ASCII | re.DOTALL)

_PLAIN = re.compile(NOCHAIN + "*")
_WS_SPLIT = re.compile(WS + "+")
_CHAIN_CHAR = re.compile("[;&|<>`$]")
_SCRIPT_QUOTED = re.compile(WS + "*bash" + WS + '+"([^"]+)"(' + WS + ".*)?", re.DOTALL)
_SCRIPT_BARE = re.compile(WS + "*bash" + WS + '+([^ \t\n\v\f\r"]+)(' + WS + ".*)?", re.DOTALL)
_DIAG_GIT = re.compile(WS + "*git" + WS + "+(status|log|diff|show)(" + WS + NOCHAIN + "*)?")
_DIAG_SOURCES = re.compile(r'sources\.sh"?' + WS + "+(list|show|contract)(" + WS + NOCHAIN + r"*)?\Z")
_OP_PREFIX = re.compile(WS + "*bash" + WS + "+")
_OP_QUOTED = re.compile(r'"[^"]+"')
_OP_BARE = re.compile("[^ \t\n\v\f\r]+")
_SCRIPT_NAME = re.compile(r"[a-z0-9_-]+\.sh", re.ASCII)
# Contract lines may hold any Unicode whitespace (see contract.py).
_AGENT_ONLY = re.compile(r"agent_only:\s*yes\s*")
_OP = re.compile(r"[a-z][a-z0-9-]*", re.ASCII)
# Protected path segments: the name followed by "/", a quote, whitespace, a
# shell character or the end, not by another name character, so
# ~/.claude/plugins is protected and .claude/plugins-notes is not.
_SEGMENTS = re.compile(r"\.claude/plugins(?![a-z0-9_.-])", re.ASCII)
# The wiki's own skills run code later and are protected; the user's
# (~/.claude/skills) are not: their scripts are readers some sources use
# (onenote's), which a session must be able to run. An occurrence is the
# user's when a home spelling directly precedes it, at the start of the
# text or after whitespace, a quote or a shell character, and the path
# after it holds no "..".
_SKILLS = ".claude/skills"
_SKILLS_BEFORE = " \t\n\v\f\r\"'=(;&|<>`"
_PATH_END = re.compile(r"[ \t\n\v\f\r\"';&|<>()`]")
# A nested claude session: "claude" (or a path ending in /claude, or
# claude.exe, bare or in quotes) as a command word: at the start of the
# command or of a segment (after ; & | ( $( or a backtick; hookjson turns
# newlines into ;), after any number of VAR=value assignments, wrappers
# (env, exec, command, nohup, timeout <n>, ...), their options and numbers.
# Never as text: ~/.claude/x, claude-notes.md, a commit message.
_CLAUDE_CMD = re.compile(
    r"(?:\A|[;&|(`])" + WS + "*"
    r"(?:(?:[a-z_][a-z0-9_]*=[^ \t\n\v\f\r;&|]*|env|exec|command|builtin|nohup|time|nice|stdbuf"
    r"|xargs|timeout|then|do|else|!|-[^ \t\n\v\f\r;&|]*|[0-9][0-9.]*[smhd]?)" + WS + "+)*"
    r"""(?:"(?:[^"]*/)?claude(?:\.exe)?"|'(?:[^']*/)?claude(?:\.exe)?'"""
    r"""|(?:[^ \t\n\v\f\r;&|()`"']*/)?claude(?:\.exe)?)"""
    r"""(?=[ \t\n\v\f\r;&|)`]|\Z)""", re.ASCII)
# gh writing to GitHub past git (`gh api -X PUT .../contents/...` changes
# the default branch with no push): "gh" (a path ending in /gh, or gh.exe,
# bare or in quotes) as a command word, found as _CLAUDE_CMD finds claude,
# also after { or a variable assignment ($x = gh ..., PowerShell), after
# eval sudo bash sh zsh pwsh powershell and an opening quote (`bash -c "gh
# api ..."`); then any options (`-R owner/repo`, each with an optional
# value: gh finds its subcommand past them) and one of these subcommands,
# bare or quoted. Never as text: echo gh api, a commit message.
_GH_SUBCOMMANDS = ("api", "pr", "repo", "release", "workflow", "secret", "variable", "gist")
_GH_CMD = re.compile(
    r"(?:\A|[;&|(`{]|\$\{?[a-z0-9_:]+\}?" + WS + "*=(?!=))" + WS + "*"
    r"(?:(?:[a-z_][a-z0-9_]*=[^ \t\n\v\f\r;&|]*|env|exec|command|builtin|nohup|time|nice|stdbuf"
    r"|xargs|timeout|then|do|else|!|eval|sudo|bash|sh|zsh|pwsh|powershell"
    r"|-[^ \t\n\v\f\r;&|(){}`]*|[0-9][0-9.]*[smhd]?)" + WS + "+)*"
    r"""(?:"(?:[^"]*/)?gh(?:\.exe)?"|'(?:[^']*/)?gh(?:\.exe)?'"""
    r"""|["']?(?:[^ \t\n\v\f\r;&|(){}`"']*/)?gh(?:\.exe)?)"""
    r"(?:" + WS + r"""+["']?-[^ \t\n\v\f\r;&|(){}`]*"""
    r"(?:" + WS + r"""+[^- \t\n\v\f\r;&|(){}`][^ \t\n\v\f\r;&|(){}`]*)?)*"""
    + WS + r"""+["']?(?:""" + "|".join(_GH_SUBCOMMANDS) + r""")["']?(?=[ \t\n\v\f\r;&|)`]|\Z)""",
    re.ASCII)

CORE_SCRIPTS = ("scripts/ocr.sh", "scripts/sync-status.sh", "scripts/lint.sh",
                "scripts/wiki-check.sh", "scripts/sources.sh", "scripts/decode-download.sh",
                "scripts/file-snapshot.sh", "scripts/save.sh")
LOOKALIKE_ENDS = tuple("/" + s for s in CORE_SCRIPTS)

# save.sh: the arguments that save only free paths; any other argument is
# the permission case. save.sh named in a command (normalised text), not
# as part of a longer name (autosave.sh).
SAVE_FLAGS = frozenset(("--check", "--update", "--unattended"))
_SAVE_WORD = re.compile(r"(?<![a-z0-9_.-])save\.sh", re.ASCII)
# A path the permission prompt shows, as save.sh gets it: no character a
# shell expands or a reader could misread (control, invisible and bidi
# characters, Unicode spaces).
_SAVE_PATH_BAD = "*?[]{}()~#\\=\"'!"
_SAVE_PATH_INVISIBLE = re.compile(
    r"[\x00-\x1f\x7f-\x9f\u00a0\u061c\u1680\u180e\u2000-\u200f\u2028-\u202f\u205f-\u206f"
    r"\u3000\ufeff]")
SAVE_MAX_PATHS = 50
SAVE_MAX_CHARS = 2000


def block(msg: str) -> NoReturn:
    b = ("wiki guard: %s\n" % msg)
    try:
        data = b.encode("utf-8", errors="surrogateescape")
    except UnicodeEncodeError:
        data = b.encode("utf-8", errors="replace")
    sys.stderr.buffer.write(data)
    sys.stderr.flush()
    sys.exit(2)


def drive_form(p: str) -> str | None:
    """/c/x -> c:/x (sed 's#^/\\([a-z]\\)/#\\1:/#'), else None."""
    if len(p) >= 3 and p[0] == "/" and "a" <= p[1] <= "z" and p[2] == "/":
        return p[1] + ":/" + p[3:]
    return None


def slash_form(p: str) -> str | None:
    """c:/x -> /c/x, else None."""
    if len(p) >= 3 and "a" <= p[0] <= "z" and p[1:3] == ":/":
        return "/" + p[0] + "/" + p[3:]
    return None


def native(p: str) -> str:
    """A path the filesystem can open: Git Bash's /c/x is c:/x on Windows."""
    if os.name == "nt":
        m = re.match(r"/([A-Za-z])/", p)
        if m:
            return m.group(1) + ":/" + p[3:]
    return p


def listable(d: str) -> bool:
    """False if d is a folder that can't be listed; a missing one is fine."""
    try:
        os.listdir(d)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return False
    return True


def contains_any(text: str, needles: Iterable[str]) -> str:
    for n in needles:
        if n and n in text:
            return n
    return ""


def glob_files(d: str, name: str | None = None) -> list[str]:
    """Regular files <d>/*/<name> (name given) or <d>/*.md, sorted; hidden
    entries skipped, as a shell glob does."""
    try:
        entries = sorted(os.listdir(d), key=lambda s: s.encode("utf-8", errors="surrogateescape"))
    except OSError:
        return []
    out: list[str] = []
    for e in entries:
        if e.startswith("."):
            continue
        if name is None:
            if not e.endswith(".md"):
                continue
            f = d + "/" + e
        else:
            f = d + "/" + e + "/" + name
        if os.path.isfile(f):
            out.append(f)
    return out


def first_line(path: str) -> str:
    try:
        with open(path, "rb") as f:
            line = f.readline()
    except OSError:
        line = b""
    line = line.split(b"\n")[0].replace(b"\r", b"")[:60]
    return 'its first line is "%s"' % line.decode("utf-8", errors="surrogateescape")


class Context:
    """What the checks share for one call: the plugin folder in every
    spelling, the wiki root and what the source files say. Each part is
    loaded once, when a check first needs it."""

    __slots__ = ("call", "plugin", "plugin_forms", "protected_paths", "home_prefixes",
                 "_wiki_root", "_sources", "_scripts")

    call: HookCall
    plugin: str
    plugin_forms: list[str]
    protected_paths: list[str]
    home_prefixes: list[str]
    _wiki_root: str | None
    _sources: Sources | None
    # allowed_script's answers, by command.
    _scripts: dict[str, tuple[str, str] | None]

    def __init__(self, call: HookCall) -> None:
        self.call = call
        self.plugin = C.PLUGIN
        p = norm(self.plugin)
        forms = [p, drive_form(p) or "", slash_form(p) or ""]
        home = norm(C._home())
        homes: list[str] = []
        if home:
            homes = [home, drive_form(home) or "", slash_form(home) or ""]
            tilde: list[str] = []
            for f in forms:
                for hf in homes:
                    if f and hf and f.startswith(hf + "/"):
                        tilde.append("~/" + f[len(hf) + 1:])
            forms += tilde
        self.plugin_forms = forms
        self.home_prefixes = [h + "/" for h in homes if h] + [
            "~/", "$home/", "${home}/", "$env:userprofile/", "${env:userprofile}/"]
        self.protected_paths = []
        for f in forms:
            if f:
                self.protected_paths += [f + "/scripts", f + "/hooks", f + "/sources"]
        self.protected_paths += ["plugins/wiki/scripts", "plugins/wiki/hooks", "plugins/wiki/sources",
                                 ".claude/sources", ".claude/settings",
                                 # Files that run code later: git hooks and config, MCP
                                 # servers, skills and agents (their frontmatter hooks).
                                 # .claude/skills: the wiki's own only, see wiki_skills.
                                 ".git/hooks", ".git/config", ".mcp.json", ".claude/agents"]
        self._wiki_root = None
        self._sources = None
        self._scripts = {}

    @property
    def wiki_root(self) -> str:
        if self._wiki_root is None:
            self._wiki_root = self._find_wiki_root()
        return self._wiki_root

    def _find_wiki_root(self) -> str:
        d = os.environ.get("CLAUDE_PROJECT_DIR", "")
        if d and os.path.isdir(native(d)):
            return native(d)
        cwd = self.call.cwd
        if cwd and os.path.isdir(native(cwd)):
            import subprocess
            try:
                r = subprocess.run(["git", "-C", native(cwd), "rev-parse", "--show-toplevel"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, check=False)
            except OSError:
                return ""
            if r.returncode != 0:
                return ""
            return r.stdout.decode("utf-8", errors="surrogateescape").rstrip("\n")
        return ""

    @property
    def sources(self) -> Sources:
        """Every source file, for shell, write and MCP calls (Sources)."""
        if self._sources is None:
            self._sources = Sources(self)
        return self._sources

    @property
    def broken(self) -> str:
        return self.sources.broken

    # Paths.

    @staticmethod
    def root_forms(inst: str) -> list[str]:
        out: list[str] = []
        for r in C.values(inst, "roots"):
            if not r:
                continue
            x = norm(C.expand(r))
            w = norm(r)
            if len(w) > 1 and w.endswith("/"):
                w = w[:-1]
            out += [w, x]
            if w.startswith("~/"):
                out += ["$home/" + w[2:], "$env:userprofile/" + w[2:]]
            for f in (drive_form(x), slash_form(x)):
                if f is not None:
                    out.append(f)
        return out

    def abs_path(self, v: str) -> str:
        p = norm(C.expand(v))
        if not p:
            return ""
        if not C.is_abs(p):
            p = norm(self.call.cwd) + "/" + p
        s: list[str] = []
        for i, f in enumerate(p.split("/")):
            if f == "" and i > 0:
                continue
            if f == ".":
                continue
            if f == "..":
                if len(s) > 1:
                    s.pop()
                continue
            s.append(f)
        return "/".join(s) or "/"

    def agent_only_read_roots(self) -> list[str]:
        """The roots of every instance of an agent_only type, for Read, Grep
        and Glob: found from the contracts' agent_only line, without reading
        every source file."""
        types: list[str] = []
        for f in (glob_files(self.plugin + "/sources", "SOURCE.md")
                  + glob_files(self.wiki_root + "/.claude/sources/types", "SOURCE.md")):
            if any(_AGENT_ONLY.fullmatch(ln) for ln in C._lines(f)):
                t = f[: -len("/SOURCE.md")].rsplit("/", 1)[-1]
                if C.NAME_RE.fullmatch(t):
                    types.append(t)
        if not types:
            return []
        type_re = re.compile(r"type:\s*(" + "|".join(types) + r")\s*")
        roots: list[str] = []
        for f in glob_files(C.instance_dir(self.wiki_root)):
            if any(type_re.fullmatch(ln) for ln in C._lines(f)):
                roots += self.root_forms(f)
        return roots

    def protected_hit(self, text: str) -> str:
        """The first protected path text (normalised) names, or "": a
        protected path anywhere in it, or a protected segment
        (.claude/plugins)."""
        hit = contains_any(text, self.protected_paths)
        if hit:
            return hit
        m = _SEGMENTS.search(text)
        if m:
            return m.group()
        return _SKILLS if self.wiki_skills(text) else ""

    def wiki_skills(self, text: str) -> bool:
        """True if text names .claude/skills other than the user's
        ~/.claude/skills (in any home spelling, with no ".." after it)."""
        i = text.find(_SKILLS)
        while i >= 0:
            if not self._user_skills(text, i):
                return True
            i = text.find(_SKILLS, i + 1)
        return False

    def _user_skills(self, text: str, i: int) -> bool:
        rest = text[i + len(_SKILLS):]
        m = _PATH_END.search(rest)
        if ".." in (rest[:m.start()] if m else rest):
            return False
        before = text[:i]
        for h in self.home_prefixes:
            if before.endswith(h):
                j = len(before) - len(h)
                if j == 0 or text[j - 1] in _SKILLS_BEFORE:
                    return True
        return False

    def under_root(self, path: str) -> str:
        for r in self.sources.roots:
            if r and (path == r or path.startswith(r + "/")):
                return r
        return ""

    # Script calls. cmd is normalised.

    @staticmethod
    def script_path(cmd: str) -> str | None:
        if not _PLAIN.fullmatch(cmd):
            return None
        m = _SCRIPT_QUOTED.fullmatch(cmd) or _SCRIPT_BARE.fullmatch(cmd)
        if not m or not m.group(1):
            return None
        s = m.group(1)
        if s.startswith("./"):
            s = s[2:]
        if C.has_dots(s):
            return None
        return s

    def allowed_script(self, cmd: str) -> tuple[str, str] | None:
        """(contract, script name) of a plain call of an allowed script, or
        None. A core script gives ("", its name). Remembered per command."""
        if cmd not in self._scripts:
            self._scripts[cmd] = self._allowed_script(cmd)
        return self._scripts[cmd]

    def _allowed_script(self, cmd: str) -> tuple[str, str] | None:
        s = self.script_path(cmd)
        if s is None:
            return None
        rel = ""
        for f in self.plugin_forms:
            if f and s.startswith(f + "/"):
                rel = s[len(f) + 1:]
                break
        if rel:
            if rel in CORE_SCRIPTS:
                return ("", rel.rsplit("/", 1)[-1])
            if not (rel.startswith("sources/") and rel.endswith(".sh") and "/" in rel[len("sources/"):]):
                return None
            c = "%s/sources/%s/SOURCE.md" % (self.plugin, rel.split("/")[1])
        else:
            if not self.wiki_root:
                return None
            w = norm(self.wiki_root)
            rel = s
            for pre in (w, drive_form(w), slash_form(w), "."):
                if pre is None:
                    continue
                if s.startswith(pre + "/"):
                    rel = s[len(pre) + 1:]
                    break
            pre = ".claude/sources/types/"
            if not (rel.startswith(pre) and rel.endswith(".sh") and "/" in rel[len(pre):]):
                return None
            c = "%s/.claude/sources/types/%s/SOURCE.md" % (self.wiki_root, rel.split("/")[3])
        name = rel.rsplit("/", 1)[-1]
        if rel.count("/") != (2 if rel.startswith("sources/") else 4):
            return None
        if not _SCRIPT_NAME.fullmatch(name):
            return None
        if not os.path.isfile(c):
            return None
        if name not in [lower(x) for x in C.list_(c, "scripts")]:
            return None
        return (c, name)

    def bash_script(self, cmd: str) -> tuple[str, str] | None:
        """allowed_script(cmd) for a Bash call, None for PowerShell: the
        wiki's scripts run only through the Bash tool (Git Bash)."""
        if self.call.shell != "bash":
            return None
        return self.allowed_script(cmd)

    def diagnostic_ok(self, cmd: str) -> bool:
        if "--output" in cmd:
            return False
        if _DIAG_GIT.fullmatch(cmd):
            return True
        if self.allowed_script(cmd) is None:
            return False
        if not (self.script_path(cmd) or "").endswith("/scripts/sources.sh"):
            return False
        return bool(_DIAG_SOURCES.search(cmd))

    def shell_exempt(self, cmd: str) -> bool:
        """True for a shell command the checks after agent_only_ops let
        through: a read-only diagnostic while a source file is broken
        (broken_sources let it pass), or a plain call of an allowed script."""
        return bool(self.broken) or self.bash_script(cmd) is not None

    @staticmethod
    def main_session_op(cmd: str) -> str:
        """The third word of `bash <script> <key> <op> ...`, or "" unless the
        key and the operation are plain words. Like sed -E, the script word
        is the longest match of "..." or a word."""
        m = _OP_PREFIX.match(cmd)
        rest = cmd
        if m:
            i = m.end()
            ends = [x.end() for x in (_OP_QUOTED.match(cmd, i), _OP_BARE.match(cmd, i)) if x]
            if ends:
                rest = cmd[max(ends):]
        fields = re.split("[ \t\n]+", rest.strip(" \t\n"))
        # The key and the operation must be plain words, so quotes or a
        # backslash (a slash after norm) can't make the guard read a
        # different operation than the script gets.
        if len(fields) < 2 or not C.NAME_RE.fullmatch(fields[0]) or not _OP.fullmatch(fields[1]):
            return ""
        return fields[1]

    def chained_message(self, cmd: str) -> str | None:
        """For a command that would be an allowed script call but for ; & |
        < > $ or a backtick: a message naming the character, else None.
        Only words the message: the command is refused either way."""
        m = _CHAIN_CHAR.search(cmd)
        if not m:
            return None
        plain = _CHAIN_CHAR.sub("", cmd)
        got = self.allowed_script(plain)
        if got is None:
            return self.chained_part_message(cmd, m.group())
        c, name = got
        ch = "a backtick" if m.group() == "`" else "'%s'" % m.group()
        how = ""
        if c:  # a contract's wrapper, not a core script
            t = c[: -len("/SOURCE.md")].rsplit("/", 1)[-1]
            if any("pattern file" in ln.lower() for ln in C._lines(c)):
                how = " For an argument that needs one (e.g. a regex), see %s's SOURCE.md on pattern files." % t
            else:
                how = " For an argument that needs one, see %s's SOURCE.md." % t
        return ("the call of %s contains %s. A script call must be plain: no ; & | < > $ or "
                "backtick, one call per Bash call.%s" % (name, ch, how))

    def chained_part_message(self, cmd: str, ch: str) -> str | None:
        """For a command one part of which, between ; & | < > $ or
        backticks, is an allowed script call (`git commit ... && bash
        <plugin>/scripts/sources.sh due`): a message saying the script needs
        a call of its own, else None. ch is the command's first such
        character. Only words the message, as chained_message."""
        for part in _CHAIN_CHAR.split(cmd):
            got = self.allowed_script(part)
            if got is not None:
                name = got[1]
                return ("the call of %s is chained to another command (%s). A script call must "
                        "be plain: no ; & | < > $ or backtick, one call per Bash call. Run %s "
                        "as a Bash call of its own." % (
                            name, "a backtick" if ch == "`" else "'%s'" % ch, name))
        return None


class Sources:
    """Every source file, read once per call: the contracts' guard words,
    the roots of filesystem instances (and of agent_only ones among them),
    the reader bindings (limits: {tool: {(field, value): [keys]}}, free:
    tools bound without a limit, named: every MCP tool a reader list names,
    even in an item that doesn't parse), and broken, the
    message for the first file that can't be used ("" if none)."""

    __slots__ = ("broken", "guard_words", "roots", "agent_roots", "limits", "free", "named")

    broken: str
    guard_words: list[str]
    roots: list[str]
    agent_roots: list[str]
    limits: dict[str, dict[tuple[str, str], list[str]]]
    free: set[str]
    named: set[str]

    def __init__(self, ctx: Context) -> None:
        self.broken = ""
        self.guard_words = []
        self.roots = []
        self.agent_roots = []
        self.limits = {}
        self.free = set()
        self.named = set()
        plugin, wiki_root = ctx.plugin, ctx.wiki_root
        # A folder that can't be listed is broken, not empty.
        folders = [plugin + "/sources"]
        if wiki_root:
            folders += [wiki_root + "/.claude/sources/types", C.instance_dir(wiki_root)]
        for d in folders:
            if not listable(d):
                self.set_broken(d, "the folder can't be read")
        contracts = glob_files(plugin + "/sources", "SOURCE.md")
        if wiki_root:
            contracts += glob_files(wiki_root + "/.claude/sources/types", "SOURCE.md")
        for c in contracts:
            if not C.has_fm(c):
                self.set_broken(c, "no frontmatter block (%s)" % first_line(c))
                continue
            self.guard_words += [lower(w) for w in C.list_(c, "guard_words")]
        if not wiki_root:
            return
        d = C.instance_dir(wiki_root)
        for k in C.instances(wiki_root):
            f = d + "/" + k + ".md"
            # Validation requires kebab-case keys anyway.
            if not C.NAME_RE.fullmatch(k):
                self.set_broken(f, "its name isn't a kebab-case instance key")
                continue
            if not C.has_fm(f):
                self.set_broken(f, "no frontmatter block (%s)" % first_line(f))
                continue
            t = C.field(f, "type")
            try:
                c = C.contract(wiki_root, t)
            except C.ContractError as e:
                self.set_broken(f, str(e))
                continue
            access = C.field(c, "access")
            if access == "tools":
                self.add_reader(f, k)
            if access != "filesystem":
                continue
            if not C.values(f, "roots"):
                self.set_broken(f, "a filesystem instance (type %s) with no roots" % t)
                continue
            self.roots += ctx.root_forms(f)
            if C.field(c, "agent_only") == "yes":
                self.agent_roots += ctx.root_forms(f)

    def add_reader(self, f: str, k: str) -> None:
        """An access: tools instance's reader list (reader_deny becomes deny
        rules, not a guard check)."""
        items = C.list_(f, "reader")
        for s in items:
            self.named.update(C.MCP_NAME.findall(s))
        for s in items:
            p = C.reader_item(s)
            if p is None:
                self.set_broken(f, "reader item '%s' doesn't parse" % s)
                continue
            _, tool, fld, val = p
            if not tool.startswith("mcp__"):
                continue
            if fld:
                self.limits.setdefault(tool, {}).setdefault((fld, val), []).append(k)
            else:
                self.free.add(tool)

    def set_broken(self, f: str, reason: str) -> None:
        if self.broken:
            return
        self.broken = (
            "source file '%s' can't be used: %s. Until it is fixed, shell commands and Write/Edit "
            "are refused (fail closed), except git status/log/diff/show and sources.sh "
            "list/show/contract; Read still works on the file. The user fixes it with "
            "install-source-file.sh or an editor, outside Claude." % (f, reason))


def source_script(s: str) -> bool:
    """case */sources/*/*.sh (a shell * also matches "/")."""
    i = s.find("/sources/")
    while i >= 0:
        rest = s[i + len("/sources/"):]
        if rest.endswith(".sh") and "/" in rest[:-3]:
            return True
        i = s.find("/sources/", i + 1)
    return False


# The checks. Each takes the call (hookjson.HookCall) and the Context and
# returns the reason to refuse the call, or None. They run in CHECKS order,
# the first reason wins, and a call no check refuses is allowed. A check
# looks at the context only for the kinds of call it covers, so a call loads
# only what its checks need: git push and Read/Grep/Glob never read every
# source file.

def no_push(call: HookCall, ctx: Context) -> str | None:
    """git push in a shell command, or any tool of a GitHub MCP server
    (push_files, merge_pull_request and the like push past git). First, so
    no exception can let one through."""
    if call.kind == "mcp":
        server = call.tool[len("mcp__"):].split("__", 1)[0]
        if "github" in lower(server):
            return ("%s is a GitHub tool, and GitHub tools are not allowed in wiki sessions "
                    "(they can push). Commit locally; the user pushes.%s" % (call.tool, save_hint(ctx)))
        return None
    if call.kind != "shell":
        return None
    if _PUSH.search(_STASH_PUSH.sub("git stash", norm(call.command))):
        return "git push is not allowed in wiki sessions. Commit locally; the user pushes.%s" % save_hint(ctx)
    return None


def save_hint(ctx: Context) -> str:
    """" Or run /wiki:save." when saving is on for the wiki: its
    .claude/settings.wiki.json in the working tree is a regular file (not a
    FIFO, which open would wait on) that parses as a JSON object whose
    "save" object has "enabled": true. Wording only (the push is refused
    either way), so the working-tree copy is enough (save.sh reads HEAD's);
    any error gives ""."""
    root = ctx.wiki_root
    if not root:
        return ""
    f_path = root + "/.claude/settings.wiki.json"
    try:
        if not os.path.isfile(f_path):
            return ""
        with open(f_path, "rb") as f:
            data: object = json.loads(f.read(65536))
    except (OSError, ValueError, RecursionError):
        return ""
    sec = data.get("save") if isinstance(data, dict) else None
    if isinstance(sec, dict) and sec.get("enabled") is True:
        return " Or run /wiki:save."
    return ""


def no_gh_write(call: HookCall, ctx: Context) -> str | None:
    """A shell command running gh with a subcommand that can write to
    GitHub past git (api, pr, repo, release, workflow, secret, variable,
    gist): the same protection as no_push, so right after it. A plain call
    of an allowed script (a source's wrapper around gh) passes."""
    if call.kind != "shell":
        return None
    cmd = norm(call.command)
    if not _GH_CMD.search(cmd) or ctx.bash_script(cmd) is not None:
        return None
    return ("gh api, pr, repo, release, workflow, secret, variable and gist are not allowed "
            "in wiki sessions: they can write to GitHub past git. Commit locally; the user "
            "pushes. A source reads GitHub only through its wrapper (see its SOURCE.md).")


def shell_has_command(call: HookCall, ctx: Context) -> str | None:
    """A shell call without a command (fail closed)."""
    if call.kind == "shell" and not call.command:
        return "%s call without a command; refusing (fail closed)." % call.tool
    return None


def write_has_path(call: HookCall, ctx: Context) -> str | None:
    """A write call without file_path (fail closed)."""
    if call.kind == "write" and not call.paths:
        field = "notebook_path" if call.tool == "NotebookEdit" else "file_path"
        return "%s call without %s; refusing (fail closed)." % (call.tool, field)
    return None


def known_tool(call: HookCall, ctx: Context) -> str | None:
    """A tool the guard doesn't classify (fail closed)."""
    if call.kind == "unknown":
        return ("tool '%s' is not known to the wiki guard; refusing (fail closed). If it is "
                "safe, it is added to the guard's list in wiki-tools." % call.tool)
    return None


def nested_claude(call: HookCall, ctx: Context) -> str | None:
    """A shell command that starts a nested claude session: it would run
    without this guard's settings, or change the plugins."""
    if call.kind == "shell" and _CLAUDE_CMD.search(norm(call.command)):
        return ("starting a nested Claude session (claude) is not allowed in wiki sessions. "
                "The user runs claude in a terminal.")
    return None


def agent_only_read(call: HookCall, ctx: Context) -> str | None:
    """A main-session Read, Grep or Glob on an agent_only root."""
    if call.kind != "read" or call.subagent or not ctx.wiki_root:
        return None
    roots = ctx.agent_only_read_roots()
    if not any(r.strip(" \t\n\v\f\r") for r in roots):
        return None
    for v in call.paths:
        a = ctx.abs_path(v)
        for r in roots:
            if r and (a == r or a.startswith(r + "/")):
                return ("'%s' is in '%s', a source only subagents may read (agent_only). "
                        "Dispatch an agent, as /wiki:research does." % (v, r))
    hit = contains_any(norm(call.pattern), roots)
    if hit:
        return ("the pattern names '%s', a source only subagents may read (agent_only). "
                "Dispatch an agent, as /wiki:research does." % hit)
    return None


def broken_sources(call: HookCall, ctx: Context) -> str | None:
    """While a source file can't be used, every shell and write call is
    refused (fail closed), except a read-only diagnostic in a shell."""
    if call.kind not in ("shell", "write") or not ctx.broken:
        return None
    if call.kind == "shell" and ctx.diagnostic_ok(norm(call.command)):
        return None
    return ctx.broken


def agent_only_ops(call: HookCall, ctx: Context) -> str | None:
    """In the main session, an agent_only type's wrappers run only the
    operations its contract lists under main_ops."""
    if call.kind != "shell" or call.subagent or ctx.broken:
        return None
    cmd = norm(call.command)
    got = ctx.bash_script(cmd)
    if got is None:
        return None
    c, name = got
    if C.field(c, "agent_only") != "yes":
        return None
    wop = ctx.main_session_op(cmd)
    ops = C.list_(c, "main_ops")
    if wop in [lower(o) for o in ops]:
        return None
    return ("'%s' of %s reads the source itself; only subagents may (the main "
            "session may call: %s). Dispatch an agent, as /wiki:research does."
            % (wop or "?", name, " ".join(ops)))


def reader_tools(call: HookCall, ctx: Context) -> str | None:
    """An MCP call to a tool the reader bindings name only with limits,
    with none of their values."""
    if call.kind != "mcp" or not ctx.wiki_root:
        return None
    s, tool = ctx.sources, call.tool
    if s.broken and tool in s.named:
        return s.broken
    lim = s.limits.get(tool)
    if not lim or tool in s.free:
        return None
    if any(call.inputs.get(fld) == val for fld, val in lim):
        return None
    allowed = sorted(set(lim), key=lambda p: C._bytes_key(p[0] + "=" + p[1]))
    keys = sorted({k for ks in lim.values() for k in ks}, key=C._bytes_key)
    return ("%s may be called here only with %s (the reader binding of %s). Call it only for the "
            "operations the source's binding names." % (
                tool, " or ".join("%s=%s" % p for p in allowed), ", ".join(keys)))


def lookalike_script(call: HookCall, ctx: Context) -> str | None:
    """A core-script name or */sources/*/*.sh outside the plugin (Bash): the
    wikis' settings allow wrappers by wildcard, so a lookalike must not
    run."""
    if call.shell != "bash":
        return None
    cmd = norm(call.command)
    if ctx.shell_exempt(cmd):
        return None
    s = ctx.script_path(cmd)
    if s is not None and (s.endswith(LOOKALIKE_ENDS) or source_script(s)):
        return ("'%s' is not this plugin's copy or not a script its contract lists. "
                "Run the wiki's scripts from the plugin folder the skills name." % s)
    return None


def save_words(call: HookCall, ctx: Context) -> list[str] | None:
    """The argument words of a plain call of the plugin's save.sh (any
    shell tool), as the command writes them, not lowercased; None for any
    other command. norm keeps every character's position, so the words are
    cut from the command as Claude wrote it."""
    cmd = norm(call.command)
    if ctx.allowed_script(cmd) != ("", "save.sh"):
        return None
    m = _SCRIPT_QUOTED.fullmatch(cmd) or _SCRIPT_BARE.fullmatch(cmd)
    if not m or not m.group(2):
        return []
    return [w for w in _WS_SPLIT.split(call.command[m.start(2):m.end(2)]) if w]


def save_permission(words: list[str] | None) -> bool:
    """True for save.sh words with any argument but --check, --update and
    --unattended: the permission case, whatever the spelling (--al""low,
    --allo, --{allow,check} too)."""
    return words is not None and any(w not in SAVE_FLAGS for w in words)


def allow_problem(words: list[str]) -> str:
    """What keeps save.sh's words from being --allow followed by plain
    paths, which the permission prompt can show as they are; "" if
    nothing."""
    if not words or words[0] != "--allow":
        return "'%s' is not --allow" % (words[0] if words else "")
    paths = words[1:]
    if not paths:
        return "no paths after --allow"
    if len(paths) > SAVE_MAX_PATHS:
        return "more than %d paths" % SAVE_MAX_PATHS
    if len(" ".join(words)) > SAVE_MAX_CHARS:
        return "longer than %d characters" % SAVE_MAX_CHARS
    for p in paths:
        if _SAVE_PATH_INVISIBLE.search(p):
            return "a path holds a control, invisible or space character"
        bad = contains_any(p, _SAVE_PATH_BAD)
        if bad:
            return "path '%s' contains '%s'" % (p, bad)
        if p.startswith("-"):
            return "path '%s' starts with '-'" % p
        if ".." in p.split("/"):
            return "path '%s' has a '..' segment" % p
    return ""


def save_form(call: HookCall, ctx: Context) -> str | None:
    """save.sh other than as a plain call of the plugin's copy with plain
    arguments: any other command naming save.sh (chained, substituted,
    through a variable, a copy outside the plugin), the permission case
    from Monitor or PowerShell, or permission-case words that aren't
    --allow followed by plain paths. Only the plain Bash call gets the
    permission prompt (save_ask); any other form could save those paths
    without it. Known false positive: any other command naming save.sh, a
    commit message too. Also any command naming save.py's test seams
    (WIKI_SAVE_TEST_*, which point a save at a local test repository): no
    session sets them, in front of save.sh or as an export of its own."""
    if call.kind != "shell":
        return None
    if "wiki_save_test_" in norm(call.command):
        return ("WIKI_SAVE_TEST_* are save.sh's test settings, not for wiki sessions. Run save.sh "
                "plainly: bash <plugin>/scripts/save.sh with its arguments only.")
    words = save_words(call, ctx)
    if words is None:
        if not _SAVE_WORD.search(norm(call.command)):
            return None
        return ("save.sh runs only as a plain call of the plugin's copy, one per Bash call: "
                "bash <plugin>/scripts/save.sh with --check, --update, --unattended or --allow "
                "<paths> (no ; & | < > $ or backtick, no variable). Any other command naming "
                "save.sh is refused, a commit message too: leave the name out.")
    if not save_permission(words):
        return None
    if call.tool != "Bash":
        return ("save.sh with an argument other than --check, --update or --unattended (--allow "
                "<paths>) runs only from the Bash tool, which asks the user. Run it as a Bash call.")
    problem = allow_problem(words)
    if problem:
        return ("save.sh's arguments are --check, --update, --unattended or --allow followed by "
                "plain paths (no quotes, * ? [ ] { } ( ) ~ # \\ = !, no '..', at most %d paths); "
                "here %s. Run the call exactly as save.sh printed it." % (SAVE_MAX_PATHS, problem))
    return None


def protected_shell(call: HookCall, ctx: Context) -> str | None:
    """A shell command naming a protected path, a protected word or a guard
    word. A Bash command that would be an allowed script call but for a
    chaining character is told which one."""
    if call.kind != "shell":
        return None
    cmd = norm(call.command)
    if ctx.shell_exempt(cmd):
        return None
    hit = ctx.protected_hit(cmd) or contains_any(cmd, ctx.plugin_forms)
    word = "" if hit else contains_any(cmd, ctx.sources.guard_words)
    if not (hit or word):
        return None
    if call.shell == "bash":
        msg = ctx.chained_message(cmd)
        if msg:
            return msg
        ps = ""
    else:
        ps = " The wiki's scripts run only through the Bash tool (Git Bash), not PowerShell."
    # What to do instead. Read, Grep and Glob are named only for a path:
    # a guard word is a command's name, not a file.
    if hit:
        how = ("a command that only reads (cat, git log) is refused too: read such files with "
               "Read, Grep or Glob; other commands the user runs in a terminal")
    else:
        how = ("any command containing this word is refused, a commit message too: leave the "
               "word out, or the user runs the command in a terminal")
    return ("command touches protected '%s'. The guard matches the command's text, so %s. "
            "Sources are read only as their SOURCE.md says (a wrapper script, MCP tools or a "
            "reader); guard and source files are edited by the user.%s" % (hit or word, how, ps))


def roots_shell(call: HookCall, ctx: Context) -> str | None:
    """A shell command naming a filesystem instance's root."""
    if call.kind != "shell":
        return None
    cmd = norm(call.command)
    if ctx.shell_exempt(cmd):
        return None
    hit = contains_any(cmd, ctx.sources.roots)
    if not hit:
        return None
    if not call.subagent and hit in ctx.sources.agent_roots:
        return ("command mentions '%s', a source only subagents may read (agent_only). "
                "Dispatch an agent, as /wiki:research does." % hit)
    return ("command mentions the read-only source folder '%s'. Use the source's wrapper "
            "script (see its SOURCE.md)." % hit)


def protected_write(call: HookCall, ctx: Context) -> str | None:
    """A write call on a protected path or anywhere in the plugin folder, as
    for shell commands: its skills, schema and templates are what every
    wiki session is told."""
    if call.kind != "write":
        return None
    path = ctx.abs_path(call.paths[0])
    hit = ctx.protected_hit(path) or contains_any(path, ctx.plugin_forms)
    if hit:
        return "'%s' is protected ('%s'). The user edits it themselves." % (call.paths[0], hit)
    return None


def roots_write(call: HookCall, ctx: Context) -> str | None:
    """A write call inside a filesystem instance's root. The path is made
    absolute and its ".." resolved first, as for agent_only reads, so
    <wiki>/../Scans/x can't get past."""
    if call.kind != "write":
        return None
    hit = ctx.under_root(ctx.abs_path(call.paths[0]))
    if hit:
        return "'%s' is inside the read-only source folder '%s'." % (call.paths[0], hit)
    return None


def guard_words_write(call: HookCall, ctx: Context) -> str | None:
    """Non-Markdown content naming a guard word: a helper script around a
    source's CLI, which no shell check would see when it runs."""
    if call.kind != "write" or norm(call.paths[0]).endswith(".md"):
        return None
    hit = contains_any(norm(" ".join(call.contents)), ctx.sources.guard_words)
    if hit:
        return ("non-Markdown content calling '%s' is not allowed; read the source as "
                "its SOURCE.md says." % hit)
    return None


CHECKS: list[Check] = [
    no_push,
    no_gh_write,
    shell_has_command,
    write_has_path,
    known_tool,
    nested_claude,
    agent_only_read,
    broken_sources,
    agent_only_ops,
    reader_tools,
    lookalike_script,
    save_form,
    protected_shell,
    roots_shell,
    protected_write,
    roots_write,
    guard_words_write,
]


def save_ask(call: HookCall, ctx: Context) -> str | None:
    """For a plain Bash call of the plugin's save.sh in the permission case
    (save_form has let only --allow followed by plain paths through), which
    every check lets through: the reason for the user's permission prompt,
    naming exactly those paths; else None. Not a check: it never refuses,
    and runs only when no check does."""
    if call.tool != "Bash":
        return None
    words = save_words(call, ctx)
    if words is None or not save_permission(words) or allow_problem(words):
        return None
    return ("saving will push changes to: %s. These paths can change how Claude, git or the "
            "host behave in this wiki. Check the diff first (git diff <base>..HEAD -- <paths>), "
            "then choose Yes, not \"don't ask again\"." % " ".join(words[1:]))


def decide(call: HookCall, ctx: Context | None = None) -> tuple[Check, str] | tuple[None, None]:
    """(check, reason) for the first check in CHECKS that refuses the call,
    or (None, None)."""
    if ctx is None:
        ctx = Context(call)
    for check in CHECKS:
        reason = check(call, ctx)
        if reason is not None:
            return check, reason
    return None, None


def main() -> NoReturn:
    call = hookjson.parse(sys.stdin.buffer.read())
    if call is None:
        block("could not parse hook input; refusing (fail closed).")
    ctx = Context(call)
    reason = decide(call, ctx)[1]
    if reason is not None:
        block(reason)
    question = save_ask(call, ctx)
    if question is not None:
        sys.stdout.buffer.write(hookjson.ask("wiki guard: " + question))
        sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 - any failure blocks
        try:
            sys.stderr.write("wiki guard: guard.py failed (%s); refusing (fail closed).\n" % type(e).__name__)
        finally:
            os._exit(2)
