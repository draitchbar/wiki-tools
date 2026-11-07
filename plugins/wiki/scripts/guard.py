"""PreToolUse guard: keep the sources read-only and Claude away from the
guard machinery. Python port of guard.sh with block-push folded in (speed
plan, step 2b): same checks in the same order, same messages. Run through
py-launch.sh, which turns any exit other than 0 or 2 into a block.

See guard.sh for the rules. In short:
- Bash/PowerShell: no git push (checked first, before every exception);
  then no protected path, core keyword, guard word or filesystem root in the
  command, except a plain call of one of the plugin's scripts or a script a
  contract lists (Bash only).
- Write/Edit/MultiEdit: no protected path, nothing inside a filesystem root,
  no guard word in non-Markdown content.
- Read/Grep/Glob: agent_only roots are closed to the main session.
- A source file that can't be used blocks shell commands and Write/Edit
  (fail closed), except read-only diagnostics.

Windows: Python sees native paths (C:/...) where Git Bash sees /c/...; every
path is matched in both spellings, as in guard.sh, and a /c/... path is
turned into c:/... before the filesystem is touched.

This is a guardrail, not a security boundary.
"""

import os
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re  # noqa: E402

import contract as C  # noqa: E402
import hookjson  # noqa: E402
from hookjson import lower, norm  # noqa: E402

# Whitespace in commands: ASCII only. Stricter than guard.sh in a UTF-8
# locale, where sed's [[:space:]] also matches e.g. U+2003, so
# `bash<U+2003><plugin>/scripts/lint.sh` passes bash's plain-call test only.
WS = "[ \t\n\v\f\r]"
NOCHAIN = "[^;&|<>`$]"

# block-push: "git stash push" is let through only when written exactly so.
_STASH_PUSH = re.compile(r"\bgit(\.exe)?\s+stash\s+push\b", re.ASCII)
_PUSH = re.compile(r"\bgit\b.*\bpush\b", re.ASCII | re.DOTALL)

_PLAIN = re.compile(NOCHAIN + "*")
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


class Guard:
    def __init__(self, h):
        self.h = h
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
                                 ".claude/sources", ".claude/settings", ".claude/plugins/"]
        self.wiki_root = self._wiki_root()

    def _wiki_root(self):
        d = os.environ.get("CLAUDE_PROJECT_DIR", "")
        if d and os.path.isdir(native(d)):
            return native(d)
        cwd = self.h.cwd
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

    # Paths.

    def root_forms(self, inst):
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
            p = norm(self.h.cwd) + "/" + p
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

    # Read, Grep, Glob.

    def check_read(self):
        if not self.wiki_root:
            sys.exit(0)
        types = []
        for f in (glob_files(self.plugin + "/sources", "SOURCE.md")
                  + glob_files(self.wiki_root + "/.claude/sources/types", "SOURCE.md")):
            if any(_AGENT_ONLY.fullmatch(ln) for ln in C._lines(f)):
                t = f[: -len("/SOURCE.md")].rsplit("/", 1)[-1]
                if C.NAME_RE.fullmatch(t):
                    types.append(t)
        if not types:
            sys.exit(0)
        type_re = re.compile(r"type:\s*(" + "|".join(types) + r")\s*")
        roots = []
        for f in glob_files(C.instance_dir(self.wiki_root)):
            if any(type_re.fullmatch(ln) for ln in C._lines(f)):
                roots += self.root_forms(f)
        if not any(r.strip(" \t\n\v\f\r") for r in roots):
            sys.exit(0)
        for v in (self.h.file, self.h.path):
            if not v:
                continue
            a = self.abs_path(v)
            for r in roots:
                if r and (a == r or a.startswith(r + "/")):
                    block("'%s' is in '%s', a source only subagents may read (agent_only). "
                          "Dispatch an agent, as /wiki:research does." % (v, r))
        hit = contains_any(norm(self.h.pattern), roots)
        if hit:
            block("the pattern names '%s', a source only subagents may read (agent_only). "
                  "Dispatch an agent, as /wiki:research does." % hit)
        sys.exit(0)

    # Every source file, for Bash and Write/Edit.

    def scan(self):
        self.broken = ""
        self.guard_words = []
        self.roots = []
        # Stricter than guard.sh, which reads an unlistable folder as empty.
        folders = [self.plugin + "/sources"]
        if self.wiki_root:
            folders += [self.wiki_root + "/.claude/sources/types", C.instance_dir(self.wiki_root)]
        for d in folders:
            if not listable(d):
                self.set_broken(d, "the folder can't be read")
        contracts = glob_files(self.plugin + "/sources", "SOURCE.md")
        if self.wiki_root:
            contracts += glob_files(self.wiki_root + "/.claude/sources/types", "SOURCE.md")
        for c in contracts:
            if not C.has_fm(c):
                self.set_broken(c, "no frontmatter block (%s)" % first_line(c))
                continue
            self.guard_words += [lower(w) for w in C.list_(c, "guard_words")]
        if not self.wiki_root:
            return
        d = C.instance_dir(self.wiki_root)
        for k in C.instances(self.wiki_root):
            f = d + "/" + k + ".md"
            # Stricter than guard.sh, which splits a name with spaces into
            # words; validation requires kebab-case keys anyway.
            if not C.NAME_RE.fullmatch(k):
                self.set_broken(f, "its name isn't a kebab-case instance key")
                continue
            if not C.has_fm(f):
                self.set_broken(f, "no frontmatter block (%s)" % first_line(f))
                continue
            t = C.field(f, "type")
            try:
                c = C.contract(self.wiki_root, t)
            except C.ContractError as e:
                self.set_broken(f, str(e))
                continue
            if C.field(c, "access") != "filesystem":
                continue
            if not C.values(f, "roots"):
                self.set_broken(f, "a filesystem instance (type %s) with no roots" % t)
                continue
            self.roots += self.root_forms(f)

    def set_broken(self, f, reason):
        if self.broken:
            return
        self.broken = (
            "source file '%s' can't be used: %s. Until it is fixed, shell commands and Write/Edit "
            "are refused (fail closed), except git status/log/diff/show and sources.sh "
            "list/show/contract; Read still works on the file. The user fixes it with "
            "install-source-file.sh or an editor, outside Claude." % (f, reason))

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
        None. A core script gives ("", "")."""
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
        # Stricter than guard.sh: the key and the operation must be plain
        # words, so quotes or a backslash (a slash after norm) can't make the
        # guard read a different operation than the script gets.
        if len(fields) < 2 or not C.NAME_RE.fullmatch(fields[0]) or not _OP.fullmatch(fields[1]):
            return ""
        return fields[1]

    def under_root(self, path):
        for r in self.roots:
            if r and (path == r or path.startswith(r + "/")):
                return r
        return ""

    # The checks.

    def check_shell(self):
        h = self.h
        cmd = norm(h.command)
        if self.broken:
            if self.diagnostic_ok(cmd):
                sys.exit(0)
            block(self.broken)
        if h.tool == "Bash":
            got = self.allowed_script(cmd)
            if got is not None:
                c, name = got
                if not h.agent_id and C.field(c, "agent_only") == "yes":
                    wop = self.main_session_op(cmd)
                    ops = C.list_(c, "main_ops")
                    if wop not in [lower(o) for o in ops]:
                        block("'%s' of %s reads the source itself; only subagents may (the main "
                              "session may call: %s). Dispatch an agent, as /wiki:research does."
                              % (wop or "?", name, " ".join(ops)))
                sys.exit(0)
            # The wikis' settings allow wrappers by wildcard, so a lookalike
            # outside the plugin must not run.
            s = self.script_path(cmd)
            if s is not None and (s.endswith(LOOKALIKE_ENDS) or self._source_script(s)):
                block("'%s' is not this plugin's copy or not a script its contract lists. "
                      "Run the wiki's scripts from the plugin folder the skills name." % s)
            ps = ""
        else:
            ps = " The wiki's scripts run only through the Bash tool (Git Bash), not PowerShell."
        hit = contains_any(cmd, self.protected_paths + self.plugin_forms + PROTECTED_WORDS + self.guard_words)
        if hit:
            block("command touches protected '%s'. Sources are read only through their wrapper "
                  "scripts; guard and source files are edited by the user.%s" % (hit, ps))
        hit = contains_any(cmd, self.roots)
        if hit:
            block("command mentions the read-only source folder '%s'. Use the source's wrapper "
                  "script (see its SOURCE.md)." % hit)
        sys.exit(0)

    @staticmethod
    def _source_script(s):
        """case */sources/*/*.sh (a shell * also matches "/")."""
        i = s.find("/sources/")
        while i >= 0:
            rest = s[i + len("/sources/"):]
            if rest.endswith(".sh") and "/" in rest[:-3]:
                return True
            i = s.find("/sources/", i + 1)
        return False

    def check_write(self):
        h = self.h
        if not h.file:
            block("%s call without file_path; refusing (fail closed)." % h.tool)
        if self.broken:
            block(self.broken)
        path = norm(h.file)
        hit = contains_any(path, self.protected_paths)
        if hit:
            block("'%s' is protected ('%s'). The user edits it themselves." % (h.file, hit))
        hit = self.under_root(path)
        if hit:
            block("'%s' is inside the read-only source folder '%s'." % (h.file, hit))
        if not path.endswith(".md"):
            hit = contains_any(norm(h.content), self.guard_words)
            if hit:
                block("non-Markdown content calling '%s' is not allowed; use the source's "
                      "wrapper script." % hit)
        sys.exit(0)


def main():
    h = hookjson.parse(sys.stdin.buffer.read())
    if h is None:
        block("could not parse hook input; refusing (fail closed).")
    shell = h.tool in ("Bash", "PowerShell")
    # block-push, first: no exception below may let a push through.
    if shell:
        if not h.command:
            block("%s call without a command; refusing (fail closed)." % h.tool)
        if _PUSH.search(_STASH_PUSH.sub("git stash", norm(h.command))):
            block("git push is not allowed in wiki sessions. Commit locally; the user pushes.")
    if h.tool in ("Read", "Grep", "Glob"):
        if h.agent_id:
            sys.exit(0)
        Guard(h).check_read()
    if not shell and h.tool not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)
    g = Guard(h)
    g.scan()
    if shell:
        g.check_shell()
    g.check_write()


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
