"""PreToolUse guard (Bash, PowerShell, Write, Edit, MultiEdit, Read, Grep,
Glob): keep the sources read-only, keep Claude away from the guard
machinery, and block git push. Run through py-launch.sh, which turns any
exit other than 0 (allow) or 2 (block) into a block. Replaced guard.sh and
block-push.sh (speed plan, step 2b).

Structure: hookjson.parse turns the hook input into a HookCall (what kind
of call: shell, write, read or other; its command, paths and contents).
CHECKS lists the checks in order, one small function each, no_push first;
each gets the call and a Context (the plugin folder, the wiki root and
what the source files say, each loaded once, when first needed) and
returns a reason to refuse or None. The first reason wins; a call no
check refuses is allowed.

What the guard knows about sources comes from the contracts at hook time:
every standard type (plugins/wiki/sources/*/SOURCE.md), every local type of
this wiki (.claude/sources/types/*/SOURCE.md) and every instance
(.claude/sources/instances/*.md). From them it collects:
  guard words  blocked in shell commands and in non-Markdown files;
  scripts      wrapper scripts allowed as a plain `bash <path> <args>` call;
  roots        of filesystem instances: blocked in shell commands,
               read-only for Write/Edit.
A source file that can't be used (no frontmatter, unknown type, a
filesystem instance without roots, a name that isn't a kebab-case key, a
folder that can't be listed) blocks every shell command and Write/Edit call
(fail closed), except read-only diagnostics: git status/log/diff/show and
sources.sh list/show/contract. The message names the first such file.

Bash and PowerShell:
- git push, checked first so no exception below can let one through. The
  user pushes. `git stash push` passes, but only written exactly so: "git"
  (or "git.exe") directly followed by "stash push"; `git -C stash push`
  could be a real push. Known false positive: a command naming both "git"
  and the word "push", e.g. in a commit message. Rephrase it.
- then a protected path, a core keyword, a guard word or a filesystem root.
  Exceptions (Bash only, since the scripts run in Git Bash): a plain call of
  one of the plugin's core scripts, or of a script a contract lists, with no
  ; & | < > ` $ and no "..". Wrappers outside the plugin don't count: the
  wikis' settings allow them by wildcard.
Write/Edit/MultiEdit: no protected path, nothing inside a filesystem root,
no guard word in non-Markdown content (a helper script around a CLI).
agent_only types (e.g. codebase): their roots are for subagents only. In
the main session (hook input without agent_id) Read, Grep and Glob on them
are blocked, and their wrappers run only the contract's main_ops, named as
plain words. A main-session shell command naming such a root gets the
agent_only message.

Messages only (the command is refused either way): a Bash command that
would be an allowed script call but for ; & | < > $ or a backtick is told
which character, and where to look for passing it (the type's SOURCE.md).

Whitespace in commands is ASCII only, and lowercasing is ASCII only, so the
Kelvin sign is not a k.

Windows: Python sees native paths (C:/...) where Git Bash sees /c/...; every
path is matched in both spellings, and a /c/... path is turned into c:/...
before the filesystem is touched.

This is a guardrail, not a security boundary: an obfuscated command can
still get through.
"""

import os
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re  # noqa: E402

import contract as C  # noqa: E402
import hookjson  # noqa: E402
from hookjson import lower, norm  # noqa: E402

# Whitespace in commands: ASCII only, so `bash<U+2003><plugin>/scripts/lint.sh`
# is not a plain script call.
WS = "[ \t\n\v\f\r]"
NOCHAIN = "[^;&|<>`$]"

# git push: "git stash push" is let through only when written exactly so.
_STASH_PUSH = re.compile(r"\bgit(\.exe)?\s+stash\s+push\b", re.ASCII)
_PUSH = re.compile(r"\bgit\b.*\bpush\b", re.ASCII | re.DOTALL)

_PLAIN = re.compile(NOCHAIN + "*")
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

CORE_SCRIPTS = ("scripts/ocr.sh", "scripts/sync-status.sh", "scripts/lint.sh",
                "scripts/wiki-check.sh", "scripts/sources.sh", "scripts/decode-download.sh")
LOOKALIKE_ENDS = tuple("/" + s for s in CORE_SCRIPTS)
PROTECTED_WORDS = ["hooks.json", "claude plugin", "disableallhooks"]


def block(msg):
    b = ("wiki guard: %s\n" % msg)
    try:
        data = b.encode("utf-8", errors="surrogateescape")
    except UnicodeEncodeError:
        data = b.encode("utf-8", errors="replace")
    sys.stderr.buffer.write(data)
    sys.stderr.flush()
    sys.exit(2)


def drive_form(p):
    """/c/x -> c:/x (sed 's#^/\\([a-z]\\)/#\\1:/#'), else None."""
    if len(p) >= 3 and p[0] == "/" and "a" <= p[1] <= "z" and p[2] == "/":
        return p[1] + ":/" + p[3:]
    return None


def slash_form(p):
    """c:/x -> /c/x, else None."""
    if len(p) >= 3 and "a" <= p[0] <= "z" and p[1:3] == ":/":
        return "/" + p[0] + "/" + p[3:]
    return None


def native(p):
    """A path the filesystem can open: Git Bash's /c/x is c:/x on Windows."""
    if os.name == "nt":
        m = re.match(r"/([A-Za-z])/", p)
        if m:
            return m.group(1) + ":/" + p[3:]
    return p


def listable(d):
    """False if d is a folder that can't be listed; a missing one is fine."""
    try:
        os.listdir(d)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return False
    return True


def contains_any(text, needles):
    for n in needles:
        if n and n in text:
            return n
    return ""


def glob_files(d, name=None):
    """Regular files <d>/*/<name> (name given) or <d>/*.md, sorted; hidden
    entries skipped, as a shell glob does."""
    try:
        entries = sorted(os.listdir(d), key=lambda s: s.encode("utf-8", errors="surrogateescape"))
    except OSError:
        return []
    out = []
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


def first_line(path):
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

    __slots__ = ("call", "plugin", "plugin_forms", "protected_paths", "_wiki_root", "_sources",
                 "_scripts")

    def __init__(self, call):
        self.call = call
        self.plugin = C.PLUGIN
        p = norm(self.plugin)
        forms = [p, drive_form(p) or "", slash_form(p) or ""]
        home = norm(C._home())
        if home:
            homes = [home, drive_form(home) or "", slash_form(home) or ""]
            tilde = []
            for f in forms:
                for hf in homes:
                    if f and hf and f.startswith(hf + "/"):
                        tilde.append("~/" + f[len(hf) + 1:])
            forms += tilde
        self.plugin_forms = forms
        self.protected_paths = []
        for f in forms:
            if f:
                self.protected_paths += [f + "/scripts", f + "/hooks", f + "/sources"]
        self.protected_paths += ["plugins/wiki/scripts", "plugins/wiki/hooks", "plugins/wiki/sources",
                                 ".claude/sources", ".claude/settings"]
        self._wiki_root = None
        self._sources = None
        self._scripts = {}

    @property
    def wiki_root(self):
        if self._wiki_root is None:
            self._wiki_root = self._find_wiki_root()
        return self._wiki_root

    def _find_wiki_root(self):
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
    def sources(self):
        """Every source file, for shell and write calls (Sources)."""
        if self._sources is None:
            self._sources = Sources(self)
        return self._sources

    @property
    def broken(self):
        return self.sources.broken

    # Paths.

    @staticmethod
    def root_forms(inst):
        out = []
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

    def abs_path(self, v):
        p = norm(C.expand(v))
        if not p:
            return ""
        if not C.is_abs(p):
            p = norm(self.call.cwd) + "/" + p
        s = []
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

    def agent_only_read_roots(self):
        """The roots of every instance of an agent_only type, for Read, Grep
        and Glob: found from the contracts' agent_only line, without reading
        every source file."""
        types = []
        for f in (glob_files(self.plugin + "/sources", "SOURCE.md")
                  + glob_files(self.wiki_root + "/.claude/sources/types", "SOURCE.md")):
            if any(_AGENT_ONLY.fullmatch(ln) for ln in C._lines(f)):
                t = f[: -len("/SOURCE.md")].rsplit("/", 1)[-1]
                if C.NAME_RE.fullmatch(t):
                    types.append(t)
        if not types:
            return []
        type_re = re.compile(r"type:\s*(" + "|".join(types) + r")\s*")
        roots = []
        for f in glob_files(C.instance_dir(self.wiki_root)):
            if any(type_re.fullmatch(ln) for ln in C._lines(f)):
                roots += self.root_forms(f)
        return roots

    def protected_hit(self, text):
        """The first protected path text (normalised) names, or "": a
        protected path anywhere in it, or a protected segment
        (.claude/plugins)."""
        hit = contains_any(text, self.protected_paths)
        if hit:
            return hit
        m = _SEGMENTS.search(text)
        return m.group() if m else ""

    def under_root(self, path):
        for r in self.sources.roots:
            if r and (path == r or path.startswith(r + "/")):
                return r
        return ""

    # Script calls. cmd is normalised.

    @staticmethod
    def script_path(cmd):
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

    def allowed_script(self, cmd):
        """(contract, script name) of a plain call of an allowed script, or
        None. A core script gives ("", ""). Remembered per command."""
        if cmd not in self._scripts:
            self._scripts[cmd] = self._allowed_script(cmd)
        return self._scripts[cmd]

    def _allowed_script(self, cmd):
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
                return ("", "")
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

    def bash_script(self, cmd):
        """allowed_script(cmd) for a Bash call, None for PowerShell: the
        wiki's scripts run only through the Bash tool (Git Bash)."""
        if self.call.shell != "bash":
            return None
        return self.allowed_script(cmd)

    def diagnostic_ok(self, cmd):
        if "--output" in cmd:
            return False
        if _DIAG_GIT.fullmatch(cmd):
            return True
        if self.allowed_script(cmd) is None:
            return False
        if not (self.script_path(cmd) or "").endswith("/scripts/sources.sh"):
            return False
        return bool(_DIAG_SOURCES.search(cmd))

    def shell_exempt(self, cmd):
        """True for a shell command the checks after agent_only_ops let
        through: a read-only diagnostic while a source file is broken
        (broken_sources let it pass), or a plain call of an allowed script."""
        return bool(self.broken) or self.bash_script(cmd) is not None

    @staticmethod
    def main_session_op(cmd):
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

    def chained_message(self, cmd):
        """For a command that would be an allowed script call but for ; & |
        < > $ or a backtick: a message naming the character, else None.
        Only words the message: the command is refused either way."""
        m = _CHAIN_CHAR.search(cmd)
        if not m:
            return None
        plain = _CHAIN_CHAR.sub("", cmd)
        got = self.allowed_script(plain)
        if got is None:
            return None
        c = got[0]
        name = self.script_path(plain).rsplit("/", 1)[-1]
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


class Sources:
    """Every source file, read once per call: the contracts' guard words,
    the roots of filesystem instances (and of agent_only ones among them),
    and broken, the message for the first file that can't be used ("" if
    none)."""

    __slots__ = ("broken", "guard_words", "roots", "agent_roots")

    def __init__(self, ctx):
        self.broken = ""
        self.guard_words = []
        self.roots = []
        self.agent_roots = []
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
            if C.field(c, "access") != "filesystem":
                continue
            if not C.values(f, "roots"):
                self.set_broken(f, "a filesystem instance (type %s) with no roots" % t)
                continue
            self.roots += ctx.root_forms(f)
            if C.field(c, "agent_only") == "yes":
                self.agent_roots += ctx.root_forms(f)

    def set_broken(self, f, reason):
        if self.broken:
            return
        self.broken = (
            "source file '%s' can't be used: %s. Until it is fixed, shell commands and Write/Edit "
            "are refused (fail closed), except git status/log/diff/show and sources.sh "
            "list/show/contract; Read still works on the file. The user fixes it with "
            "install-source-file.sh or an editor, outside Claude." % (f, reason))


def source_script(s):
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

def no_push(call, ctx):
    """git push in a shell command. First, so no exception can let one
    through."""
    if call.kind != "shell":
        return None
    if _PUSH.search(_STASH_PUSH.sub("git stash", norm(call.command))):
        return "git push is not allowed in wiki sessions. Commit locally; the user pushes."
    return None


def shell_has_command(call, ctx):
    """A shell call without a command (fail closed)."""
    if call.kind == "shell" and not call.command:
        return "%s call without a command; refusing (fail closed)." % call.tool
    return None


def write_has_path(call, ctx):
    """A write call without file_path (fail closed)."""
    if call.kind == "write" and not call.paths:
        return "%s call without file_path; refusing (fail closed)." % call.tool
    return None


def agent_only_read(call, ctx):
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


def broken_sources(call, ctx):
    """While a source file can't be used, every shell and write call is
    refused (fail closed), except a read-only diagnostic in a shell."""
    if call.kind not in ("shell", "write") or not ctx.broken:
        return None
    if call.kind == "shell" and ctx.diagnostic_ok(norm(call.command)):
        return None
    return ctx.broken


def agent_only_ops(call, ctx):
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


def lookalike_script(call, ctx):
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


def protected_shell(call, ctx):
    """A shell command naming a protected path, a protected word or a guard
    word. A Bash command that would be an allowed script call but for a
    chaining character is told which one."""
    if call.kind != "shell":
        return None
    cmd = norm(call.command)
    if ctx.shell_exempt(cmd):
        return None
    hit = ctx.protected_hit(cmd) or contains_any(cmd, ctx.plugin_forms + PROTECTED_WORDS
                                                 + ctx.sources.guard_words)
    if not hit:
        return None
    if call.shell == "bash":
        msg = ctx.chained_message(cmd)
        if msg:
            return msg
        ps = ""
    else:
        ps = " The wiki's scripts run only through the Bash tool (Git Bash), not PowerShell."
    return ("command touches protected '%s'. Sources are read only as their SOURCE.md says "
            "(a wrapper script, MCP tools or a reader); guard and source files are edited "
            "by the user.%s" % (hit, ps))


def roots_shell(call, ctx):
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


def protected_write(call, ctx):
    """A write call on a protected path."""
    if call.kind != "write":
        return None
    hit = ctx.protected_hit(norm(call.paths[0]))
    if hit:
        return "'%s' is protected ('%s'). The user edits it themselves." % (call.paths[0], hit)
    return None


def roots_write(call, ctx):
    """A write call inside a filesystem instance's root."""
    if call.kind != "write":
        return None
    hit = ctx.under_root(norm(call.paths[0]))
    if hit:
        return "'%s' is inside the read-only source folder '%s'." % (call.paths[0], hit)
    return None


def guard_words_write(call, ctx):
    """Non-Markdown content naming a guard word: a helper script around a
    source's CLI, which no shell check would see when it runs."""
    if call.kind != "write" or norm(call.paths[0]).endswith(".md"):
        return None
    hit = contains_any(norm(" ".join(call.contents)), ctx.sources.guard_words)
    if hit:
        return ("non-Markdown content calling '%s' is not allowed; read the source as "
                "its SOURCE.md says." % hit)
    return None


CHECKS = [
    no_push,
    shell_has_command,
    write_has_path,
    agent_only_read,
    broken_sources,
    agent_only_ops,
    lookalike_script,
    protected_shell,
    roots_shell,
    protected_write,
    roots_write,
    guard_words_write,
]


def decide(call):
    """(check, reason) for the first check in CHECKS that refuses the call,
    or (None, None)."""
    ctx = Context(call)
    for check in CHECKS:
        reason = check(call, ctx)
        if reason is not None:
            return check, reason
    return None, None


def main():
    call = hookjson.parse(sys.stdin.buffer.read())
    if call is None:
        block("could not parse hook input; refusing (fail closed).")
    reason = decide(call)[1]
    if reason is not None:
        block(reason)
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
