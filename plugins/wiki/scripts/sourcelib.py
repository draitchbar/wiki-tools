"""sourcelib.py: the lib-source.sh functions the scripts call, in Python.

Contract and instance validation, the rules a wiki's sources need, and
settings parsing, each one call of this script through py-run.sh (the
bridge lib-source.sh's wrappers use). Edge cases are recorded in
tests/fixtures/lib-source/ (tests/test_lib_source_edge.py). Built on
contract.py, which stays the guard's lean import.

  sourcelib.py [--plugin DIR] validate-contract FILE     errors on stderr, exit 0|1
  sourcelib.py [--plugin DIR] validate-instance ROOT KEY errors on stderr, exit 0|1
  sourcelib.py [--plugin DIR] needed-rules ROOT          "<list>\t<rule>\t<as written>"
  sourcelib.py [--plugin DIR] settings-rules FILE        "<list>\t<rule>", or ERROR line, exit 1
  sourcelib.py [--plugin DIR] codebase-instance ROOT KEY six lines, exit 0 (below)
  sourcelib.py [--plugin DIR] missing-rules ROOT FILE    "<list>\t<rule>" the settings lack

codebase-instance is what codebase/git.sh and
gh.sh need from an instance file, in one start instead of ~24: its type,
1 if src_validate_instance passes (its messages dropped, as the wrappers'
`2>/dev/null` did) else 0, the number of roots, the first root as written,
ref and gh_user. Values are printed as read, without the path mapping.

missing-rules is the one coverage check for sources.sh
check-settings, wiki-check.sh and install-source-file.sh: a needed rule is
covered by its narrowed or contract form, or by a broader Read/Edit rule
on a folder (<prefix>/**) that holds its path. A reader binding's rules
may be met in the user's settings too, except their cloud names.

Connector names per surface (docs/adr.md, 25): the pair table
sources/connectors.md maps a claude.ai connector's local server name
(mcp__claude_ai_Gmail) to its cloud one (mcp__Gmail). The needed rules
give each binding rule under its cloud name too (a tool bound only with
limits: denied there), and those cloud-name rules count only from the
wiki's own .claude/settings.json, which is all a cloud session reads. The
table is read only when a binding has an mcp__ rule.

--plugin stands in for lib-source.sh's SRC_PLUGIN (default: this script's
plugin folder). Exit 3: an internal error (a bug, an unreadable settings
file, or a Git Bash path on Windows), never "invalid". Exit 1 from
needed-rules and missing-rules: the wiki's bindings name one connector
under its local and its cloud name (BindingMixError), message on stderr.

Paths. Every path comes back in messages exactly as it was given. Python
opens files through the native form: on Windows Git Bash's /c/x is c:/x;
a path on a Git Bash mount (/tmp, /home, /usr, ...) can't be opened from
Python, so it is refused (exit 3) rather than reported as missing. Callers
hand such paths over as `pwd -W` prints them.

Known differences from bash, all accepted in the plan: names and items are
split into words on space, tab and newline but never glob-expanded; type
and key order is C order; settings-rules counts characters where mawk
counts bytes (only the quoted character in `unexpected "c"` can differ).
"""

from __future__ import annotations

import os
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datetime  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import difflib  # noqa: E402
import json  # noqa: E402

import contract  # noqa: E402

# Names for the annotations only (never evaluated): nothing to import at run time.
TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Container, Iterable
    from typing import TypeVar, TypeVarTuple

    T = TypeVar("T")
    Ts = TypeVarTuple("Ts")

PLACEHOLDER_RE = re.compile(
    r"(^|[^a-z0-9])(tbd|todo|fixme|xxx)([^a-z0-9]|$)|<[^>]*>|^\s*(\?|\.\.\.|…)\s*$",
    re.IGNORECASE)
_CACHE_RULE = re.compile(r"(Read|Edit)\(~/\.cache/wiki-sources/[^)]*\)")
_SCRIPT = re.compile(r"[A-Za-z0-9_-]+\.sh", re.ASCII)
_OP = re.compile(r"[a-z][a-z0-9-]*", re.ASCII)
_IFS = re.compile(r"[ \t\n]+")
_NAME_CUT = re.compile(r"[\s(:]")
SECTIONS = ("Check", "List new", "Fetch", "Mark ingested", "Cite", "Resolve citation", "Caveats")


class GitBashPath(Exception):
    pass


class ConnectorsError(Exception):
    """The pair table (sources/connectors.md) is missing or broken."""


class BindingMixError(Exception):
    """The wiki's bindings name one connector under its local name in one
    instance and its cloud name in another; key is the latter instance."""

    def __init__(self, message: str, key: str) -> None:
        super().__init__(message)
        self.key = key


# Paths: given spelling <-> native form (identity off Windows).

_shown: list[tuple[str, str]] = []  # (native, as given) pairs that differ


def native(p: str) -> str:
    if os.name != "nt" or not p.startswith("/"):
        return p
    m = re.match(r"/([A-Za-z])(/|$)", p)
    if m:
        n = m.group(1) + ":/" + p[3:]
    else:
        raise GitBashPath("%s is a Git Bash path, which Python on Windows can't use; "
                          "hand it over as `pwd -W` prints it" % p)
    if n != p:
        _shown.append((n, p))
    return n


def show(s: str) -> str:
    for n, p in _shown:
        s = s.replace(n, p)
    return s


# Output: bytes (no \r\n on Windows), stdout flushed before every stderr write.

def _b(s: str) -> bytes:
    return show(s).encode("utf-8", errors="surrogateescape") + b"\n"


def out(s: str) -> None:
    sys.stdout.buffer.write(_b(s))


_sink: list[str] | None = None  # a list while quietly() runs: err() collects instead of writing


def err(s: str) -> None:
    if _sink is not None:
        _sink.append(s)
        return
    sys.stdout.flush()
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(_b(s))
    sys.stderr.buffer.flush()


def quietly(fn: Callable[[*Ts], T], *args: *Ts) -> tuple[T, list[str]]:
    """fn(*args) with its err() lines collected: (result, lines). The bash
    callers' `2>/dev/null` and `errs=$(... 2>&1)`."""
    global _sink
    lines: list[str] = []
    saved, _sink = _sink, lines
    try:
        return fn(*args), lines
    finally:
        _sink = saved


def words(items: Iterable[str]) -> list[str]:
    """`for x in $(...)`: the items split on space, tab and newline."""
    return [w for w in _IFS.split("\n".join(items)) if w]


def names(items: Iterable[str]) -> list[str]:
    """src_names: each item up to a space, "(" or ":", empty ones dropped."""
    return [n for n in (_NAME_CUT.split(i, 1)[0] for i in items) if n]


def _grep_file(path: str, regex: re.Pattern[str]) -> bool:
    return any(regex.fullmatch(ln) for ln in contract._lines(path))


# Helpers the scripts share. lower() is hookjson.lower, which
# the guard needs without this module.

def read_text(path: str) -> str:
    """A file's text, bytes kept (surrogateescape); "" if it can't be read."""
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", errors="surrogateescape")
    except OSError:
        return ""


def git(root: str | None, *args: str) -> tuple[int, str]:
    """(rc, stdout) of git in root (no -C when root is empty or None), stderr
    dropped, bytes kept (surrogateescape); (1, "") if git can't be started."""
    try:
        r = subprocess.run(["git"] + (["-C", root] if root else []) + list(args),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL)
    except OSError:
        return 1, ""
    return r.returncode, r.stdout.decode("utf-8", errors="surrogateescape")


def git_out(root: str | None, *args: str) -> str | None:
    """`$(git -C root ... 2>/dev/null)`: stdout without the final newlines,
    None if git fails."""
    rc, o = git(root, *args)
    return None if rc != 0 else o.rstrip("\n")


def toplevel(root: str | None) -> str:
    """The work tree holding root (None: the current folder), "" if none."""
    return git_out(root, "rev-parse", "--show-toplevel") or ""


# Deferred questions (open-questions.md at the wiki root), shared by
# sync_status.py and lint.py. Written by /wiki:ingest --unattended, answered
# with /wiki:clarify; the format is in schema/wiki-layout.md.
QUESTIONS = "open-questions.md"
QID = re.compile(r"q-[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]{1,40}", re.ASCII)
MARKER = re.compile(r"\^\[open: (q-[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]{1,40})\]", re.ASCII)
KINDS = ("unclear", "conflict", "filing")
_Q_HEAD = re.compile(r"### (.*)")
_Q_END = re.compile(r"#{1,2}( |$)")
_Q_FIELD = re.compile(r"- ([a-z]+): ?(.*)", re.ASCII)
_Q_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", re.ASCII)
_Q_CONFLICT = re.compile(r"(<{7}|={7}|>{7}|\|{7})( |$)")
_Q_FENCE = re.compile(r" {0,3}(```|~~~)")
MARKER_ANY = re.compile(r"\^\[open:[^\]\n]*\]")


class Question:
    """One block: id (the heading, stripped), valid (the id matches QID),
    kind and raised ("" when the bullet is missing), raised_date (a
    datetime.date, or None) and pages (the bullet's text)."""

    id: str
    valid: bool
    kind: str
    raised: str
    pages: str
    raised_date: datetime.date | None

    def __init__(self, qid: str) -> None:
        self.id, self.valid = qid, bool(QID.fullmatch(qid))
        self.kind = self.raised = self.pages = ""
        self.raised_date = None


def _q_date(v: str) -> datetime.date | None:
    m = _Q_DATE.match(v)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def open_questions(text: str) -> tuple[list[Question], bool]:
    """(questions in file order, True if the text has merge-conflict lines).
    A block runs from its `### ` heading to the next heading of level 1 to
    3; its `- <field>: <value>` bullets are read in any order, the first of
    each field wins. Lines inside a fenced code block (an example) are
    skipped."""
    qs: list[Question] = []
    cur: Question | None = None
    conflict = fence = False
    for ln in text.split("\n"):
        if ln.endswith("\r"):
            ln = ln[:-1]
        if _Q_FENCE.match(ln):
            fence = not fence
            continue
        if fence:
            continue
        if _Q_CONFLICT.match(ln):
            conflict = True
            continue
        m = _Q_HEAD.fullmatch(ln)
        if m:
            cur = Question(m.group(1).strip())
            qs.append(cur)
            continue
        if _Q_END.match(ln):
            cur = None
            continue
        m = _Q_FIELD.fullmatch(ln)
        if cur is None or not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if k == "kind" and not cur.kind:
            cur.kind = v
        elif k == "raised" and not cur.raised:
            cur.raised, cur.raised_date = v, _q_date(v)
        elif k == "pages" and not cur.pages:
            cur.pages = v
    return qs, conflict


def read_questions(root: str) -> tuple[list[Question], bool] | None:
    """open_questions() of the wiki's open-questions.md, or None if it has
    none."""
    p = os.path.join(root, QUESTIONS)
    if not os.path.isfile(p):
        return None
    return open_questions(read_text(p))


# Connector names per surface (docs/adr.md, 25): sources/connectors.md
# pairs a claude.ai connector's local server name with its cloud one.

CONNECTORS = "sources/connectors.md"
_SERVER = r"[A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)*"
_PAIR = re.compile(r"local=(%s) cloud=(%s)" % (_SERVER, _SERVER), re.ASCII)
_SERVERS_KEY = re.compile(r"servers:")
_pairs: dict[str, dict[str, str]] = {}  # plugin -> {local server: cloud server}

TABLE_ERR = "can't check its connector names: "  # an instance error from a broken table
CLOUD_NOTE = ("Cloud names (the plugin's sources/connectors.md) go in this wiki's .claude/settings.json "
              "even when the local names are in ~/.claude/settings.json: a cloud session reads no other "
              "settings file.")
SETTINGS_CLOUD = ("Each rule for a claude.ai connector listed in the plugin's sources/connectors.md comes "
                  "under its local name and its Claude Code cloud name (mcp__Gmail__… for "
                  "mcp__claude_ai_Gmail__…); a tool bound with a limit is denied under its cloud name, "
                  "where the limit can't hold.")


def connector_pairs(plugin: str | None) -> dict[str, str]:
    """The pair table as {local server: cloud server}, in its order; cached
    per plugin. Raises ConnectorsError for a missing or broken table."""
    plugin = contract.PLUGIN if plugin is None else plugin
    got = _pairs.get(plugin)
    if got is not None:
        return got
    path = "%s/%s" % (plugin, CONNECTORS)
    if not contract.has_fm(path):
        raise ConnectorsError("%s: missing or has no frontmatter" % path)
    if not any(_SERVERS_KEY.match(ln) for ln in contract.fm(path)):
        raise ConnectorsError("%s: no 'servers' list" % path)
    items = contract.list_(path, "servers")
    if not items:
        raise ConnectorsError("%s: the 'servers' list is empty" % path)
    res: dict[str, str] = {}
    seen: set[str] = set()
    for it in items:
        m = _PAIR.fullmatch(it)
        if not m:
            raise ConnectorsError("%s: servers item '%s' must be 'local=<server> cloud=<server>'" % (path, it))
        for s in m.groups():
            if s in seen:
                raise ConnectorsError("%s: server '%s' is listed twice" % (path, s))
            seen.add(s)
        res[m.group(1)] = m.group(2)
    _pairs[plugin] = res
    return res


def server_of(rule: str) -> str | None:
    """An MCP rule's server: the text after mcp__ up to the next __ (or the
    whole rest, for a server rule); None for any other rule."""
    if not rule.startswith("mcp__"):
        return None
    return rule[5:].split("__", 1)[0]


def cloud_name(rule: str, pairs: dict[str, str]) -> str | None:
    """The rule under its server's cloud name, when its server is exactly a
    local server of the table; else None (never cloud to local)."""
    s = server_of(rule)
    if s is None or s not in pairs:
        return None
    return "mcp__" + pairs[s] + rule[5 + len(s):]


def is_cloud(rule: str, pairs: dict[str, str]) -> bool:
    """The rule's server is a cloud server of the table."""
    s = server_of(rule)
    return s is not None and s in pairs.values()


def _unquoted(s: str) -> str:
    return s[1:-1] if _quoted(s) else s


def binding_rules(f: str, unquote: bool = False) -> list[str]:
    """The rules an instance's binding names: each parsed `reader` item's
    tool or rule, then each `reader_deny` rule; quoted items taken without
    their quotes only with unquote (validation), as the settings and the
    guard skip them."""
    q = _unquoted if unquote else (lambda s: s)
    res = [p[1] for p in (contract.reader_item(q(it)) for it in contract.list_(f, "reader")) if p]
    res.extend(r for r in map(q, contract.list_(f, "reader_deny")) if contract.rule_ok(r))
    return res


def _has_mcp(f: str) -> bool:
    return any(r.startswith("mcp__") for r in binding_rules(f, unquote=True))


def _both_forms(rules: Iterable[str], pairs: dict[str, str]) -> list[tuple[str, str]]:
    """The pairs (local, cloud) whose servers both appear in rules."""
    servers = {server_of(r) for r in rules}
    return [(lo, cl) for lo, cl in pairs.items() if lo in servers and cl in servers]


def tools_instances(root: str, plugin: str | None) -> list[tuple[str, str]]:
    """(key, instance file) of every instance whose type resolves to an
    access: tools contract, valid or not (the guard's set), in key order."""
    d = contract.instance_dir(root)
    res: list[tuple[str, str]] = []
    for k in words(contract.instances(root)):
        f = "%s/%s.md" % (d, k)
        try:
            c = contract.contract(root, contract.field(f, "type"), plugin)
        except contract.ContractError:
            continue
        if contract.field(c, "access") == "tools":
            res.append((k, f))
    return res


def wiki_pairs(root: str, plugin: str | None) -> dict[str, str]:
    """The pair table if some access: tools instance binds an mcp__ rule,
    else {} (the table isn't read)."""
    if any(_has_mcp(f) for _, f in tools_instances(root, plugin)):
        return connector_pairs(plugin)
    return {}


def _free_of(f: str, pairs: dict[str, str]) -> set[str]:
    """The cloud names instance f binds without a limit: a mapped local
    tool or a tool written in a cloud name."""
    res: set[str] = set()
    for it in contract.list_(f, "reader"):
        p = contract.reader_item(it)
        if not p or p[2]:
            continue
        cn = cloud_name(p[1], pairs)
        if cn:
            res.add(cn)
        elif is_cloud(p[1], pairs):
            res.add(p[1])
    return res


def free_cloud(root: str, plugin: str | None, pairs: dict[str, str]) -> set[str]:
    """The cloud names some instance of the wiki binds free. A tool free
    anywhere is unlimited, as the guard treats it, so its cloud name is
    allowed even where another instance binds it with a limit."""
    res: set[str] = set()
    for _, f in tools_instances(root, plugin):
        res |= _free_of(f, pairs)
    return res


def wiki_binding_error(root: str, plugin: str | None, pairs: dict[str, str]) -> tuple[str, str] | None:
    """(message, key) when the wiki's bindings name a paired connector under
    its local name and its cloud name: in two instances, or in one (which
    validation refuses too, but its rules would still be printed); key is
    the instance with the cloud name. None otherwise."""
    insts = [(k, {server_of(r) for r in binding_rules(f)}) for k, f in tools_instances(root, plugin)]
    for lo, cl in pairs.items():
        loc = [k for k, s in insts if lo in s]
        for k2 in (k for k, s in insts if cl in s):
            k1 = next((k for k in loc if k != k2), k2 if k2 in loc else None)
            if k1 is None:
                continue
            who = "instance %s names" % k2 if k1 == k2 else "instances %s, %s name" % (k1, k2)
            return ("%s one connector under both its local name (mcp__%s__…) and its cloud name "
                    "(mcp__%s__…); bind every instance with the local names: sources.sh settings adds "
                    "the cloud names (the plugin's sources/connectors.md)" % (who, lo, cl), k2)
    return None


def cloud_setup(root: str, plugin: str | None) -> tuple[dict[str, str], set[str]]:
    """(pairs, free_cloud) for the wiki's settings rules; ({}, set()) when no
    binding has an mcp__ rule. Raises BindingMixError (wiki_binding_error)."""
    pairs = wiki_pairs(root, plugin)
    if not pairs:
        return pairs, set()
    mix = wiki_binding_error(root, plugin, pairs)
    if mix:
        raise BindingMixError(*mix)
    return pairs, free_cloud(root, plugin, pairs)


def cloud_missing(root: str, plugin: str | None, f: str) -> list[tuple[str, str]]:
    """The cloud-name lines of instance f's binding (reader_rules, as the
    wiki's settings give them) that the wiki's own .claude/settings.json
    lacks: [(list, rule)]. A missing or invalid settings file lacks them
    all (fail closed). Raises BindingMixError (cloud_setup)."""
    pairs, free = cloud_setup(root, plugin)
    if not pairs:
        return []
    lines = [ln for ln in reader_rules(f, pairs, free) if is_cloud(_fields(ln)[1], pairs)]
    have, e = settings_rules(read_text(root + "/.claude/settings.json"))
    res: list[tuple[str, str]] = []
    for m in missing_rules(lines, have if e is None else []):
        if m not in res:
            res.append(m)
    return res


# The bridged functions.

def validate_contract(f: str) -> bool:
    """src_validate_contract: one error per line on stderr; True if valid."""
    bad = False

    def ce(m: str) -> None:
        nonlocal bad
        err("%s: %s" % (f, m))
        bad = True

    if not contract.has_fm(f):
        err("%s: no frontmatter block" % f)
        return False
    def fld(k: str) -> str:
        return contract.field(f, k)

    def lst(k: str) -> list[str]:
        return contract.list_(f, k)

    for k in ("type", "title", "access", "cite_prefix"):
        if not fld(k):
            ce("missing '%s'" % k)
    t = fld("type")
    d = f[:-len("/SOURCE.md")] if f.endswith("/SOURCE.md") else f
    base = d.rsplit("/", 1)[-1]
    if t != base:
        ce("type '%s' doesn't match its folder '%s'" % (t, base))
    access = fld("access")
    if access not in ("mcp", "script", "filesystem", "tools", ""):
        ce("access must be mcp, script, filesystem or tools")
    if access == "tools":
        for k in ("bookkeeping_tools", "scripts"):
            if lst(k):
                ce("access: tools names no tools, so '%s' must be empty" % k)
        if any(not _CACHE_RULE.fullmatch(r) for r in lst("read_tools")):
            ce("access: tools names no tools, so 'read_tools' may hold only Read/Edit rules on ~/.cache/wiki-sources/")
        ops = lst("operations")
        if not ops:
            ce("access: tools needs 'operations': the operations an instance's reader binds")
        seen: set[str] = set()
        for o in ops:
            p = contract.operation(o)
            if p is None:
                ce("operations item '%s' must be '<name> (required|recommended|optional)'" % o)
            elif p[0] in seen:
                ce("operation '%s' is listed twice" % p[0])
            else:
                seen.add(p[0])
    elif lst("operations"):
        ce("only access: tools lists 'operations'")
    plats = lst("platforms")
    if not plats:
        ce("no platforms listed")
    for x in words(plats):
        if x not in ("linux", "windows", "macos"):
            ce("unknown platform '%s'" % x)
    mode = fld("mode")
    if mode not in ("ingest", "research", ""):
        ce("mode must be ingest or research")
    ao = fld("agent_only")
    if ao == "yes":
        if access != "filesystem":
            ce("agent_only: yes needs access: filesystem (its roots are what the main session may not read)")
    elif ao not in ("no", ""):
        ce("agent_only must be yes or no")
    for x in words(lst("main_ops")):
        if not _OP.fullmatch(x):
            ce("main_ops item '%s' must be a plain operation name" % x)
    if mode == "research" and not _grep_file(f, re.compile(r"## Research\s*")):
        ce("mode: research needs a '## Research' section")
    if "last_checked" not in names(lst("state")):
        ce("state must include last_checked")
    for s in words(lst("scripts")):
        if not _SCRIPT.fullmatch(s):
            ce("script name '%s' must be a plain <name>.sh" % s)
            continue
        if not os.path.isfile(d + "/" + s):
            ce("script '%s' is listed but missing" % s)
    for s in SECTIONS:
        if not _grep_file(f, re.compile("## " + re.escape(s) + r"\s*")):
            ce("missing section '## %s' (write \"not supported\" under it if it doesn't apply)" % s)
    return not bad


def validate_instance(root: str, k: str, plugin: str | None) -> bool:
    """src_validate_instance: an instance file and its contract."""
    bad = False
    f = "%s/%s.md" % (contract.instance_dir(root), k)

    def ie(m: str) -> None:
        nonlocal bad
        err("%s: %s" % (f, m))
        bad = True

    if not os.path.isfile(f):
        err("no instance file %s" % f)
        return False
    if not contract.has_fm(f):
        err("%s: no frontmatter block" % f)
        return False
    if not any(contract.NAME_RE.fullmatch(ln) for ln in k.split("\n")):
        ie("key must be kebab-case")
    if k == "raw":
        ie("'raw' is built in and can't be an instance")
    if k == "all":
        ie("'all' is reserved (/wiki:ingest all) and can't be an instance")
    key = contract.field(f, "key")
    if key != k:
        ie("key '%s' doesn't match the file name" % key)
    t = contract.field(f, "type")
    if not t:
        ie("missing 'type'")
        return False
    try:
        c = contract.contract(root, t, plugin)
    except contract.ContractError as e:
        err(str(e))
        return False
    if not validate_contract(c):
        bad = True
    params = contract.list_(c, "parameters")
    for p in words(names([x for x in params if "(required)" in x])):
        if not contract.values(f, p):
            ie("required parameter '%s' is empty" % p)
    for p in words(names(params)):
        hit = [v for v in contract.values(f, p) if PLACEHOLDER_RE.search(v)]
        if hit:
            ie("parameter '%s' holds a placeholder ('%s'); put in the real value" % (p, hit[0]))
    pairs = None
    if contract.field(c, "access") == "tools" and _has_mcp(f):
        try:
            pairs = connector_pairs(plugin)
        except ConnectorsError as e:
            ie(TABLE_ERR + str(e))
    for m in reader_errors(f, c, pairs):
        ie(m)
    for r in contract.values(f, "roots"):
        if not contract.is_abs(r):
            ie("root '%s' isn't an absolute path" % r)
        if contract.has_dots(r):
            ie("root '%s' contains '.' or '..'" % r)
    return not bad


def _quoted(s: str) -> bool:
    """A list item wrapped in one pair of matching quotes, as a YAML
    writer would quote `get item: mcp__...`."""
    return len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'"


def reader_errors(f: str, c: str, pairs: dict[str, str] | None = None) -> list[str]:
    """What is wrong with an instance's reader binding (`reader`,
    `reader_deny`; docs/adr.md, 13), given its contract c. With the pair
    table (connector_pairs), also a connector named under both its local
    and its cloud name (docs/adr.md, 25)."""
    items, deny = contract.list_(f, "reader"), contract.list_(f, "reader_deny")
    if contract.field(c, "access") != "tools":
        return (["only an access: tools instance has a reader binding ('reader', 'reader_deny')"]
                if items or deny else [])
    res: list[str] = []
    ops = dict(p for p in map(contract.operation, contract.list_(c, "operations")) if p)
    bound: set[str] = set()
    limited: set[str] = set()
    free: set[str] = set()
    for it in items:
        if _quoted(it):
            res.append("reader item %s is in quotes; write it without them (the frontmatter isn't "
                       "YAML: quotes become part of the item)" % it)
            it = it[1:-1]
        p = contract.reader_item(it)
        if p is None:
            res.append("reader item '%s' must be '<operation>: <tool or rule>' (an MCP tool, optionally "
                       "with one <field>=<value> limit, or a Bash(...) or PowerShell(...) rule)" % it)
            continue
        op, rule, fld, _ = p
        if op not in ops:
            res.append("reader binds '%s', which isn't an operation of the contract (%s)"
                       % (op, ", ".join(ops)))
        elif op in bound:
            res.append("reader binds '%s' twice" % op)
        bound.add(op)
        (limited if fld else free).add(rule)
    res.extend("reader binds %s both with and without a limit; the limit would have no effect" % t
               for t in sorted(limited & free, key=contract._bytes_key))
    if items:
        res.extend("reader doesn't bind '%s', a required operation" % o
                   for o, lvl in ops.items() if lvl == "required" and o not in bound)
    rules = limited | free
    for r in deny:
        if _quoted(r):
            res.append("reader_deny item %s is in quotes; write it without them (the frontmatter isn't "
                       "YAML: quotes become part of the item)" % r)
            r = r[1:-1]
        if not contract.rule_ok(r):
            res.append("reader_deny item '%s' must be an MCP tool or a Bash(...) or PowerShell(...) rule" % r)
        elif r in rules:
            res.append("reader_deny denies %s, which reader binds" % r)
    if pairs:
        res.extend("reader and reader_deny name one connector under both its local name (mcp__%s__…) and "
                   "its cloud name (mcp__%s__…); bind the local names only: sources.sh settings adds the "
                   "cloud names (the plugin's sources/connectors.md)" % lc
                   for lc in _both_forms(binding_rules(f, unquote=True), pairs))
    return res


def has_body_section(f: str, name: str) -> bool:
    """True if file f has a `## <name>` heading in its body: after the
    frontmatter (when it has one) and outside fenced code blocks."""
    lines = contract._lines(f)
    if contract.has_fm(f):
        lines = lines[len(contract.fm(f)) + 2:]
    head = re.compile("## " + re.escape(name) + r"\s*")
    fence = False
    for ln in lines:
        if _Q_FENCE.match(ln):
            fence = not fence
        elif not fence and head.fullmatch(ln):
            return True
    return False


def reader_rules(f: str, pairs: dict[str, str] | None = None, free: Container[str] | None = None) -> list[str]:
    """An instance's binding as needed_rules lines: allow each bound rule
    (an MCP tool once, whatever its limits), deny each reader_deny rule.
    With the pair table, each line whose rule has a cloud name is followed
    by the cloud name's line: denied for a reader_deny rule, and for a tool
    bound with a limit unless its cloud name is in free (the cloud names
    bound without a limit; default: this instance's own), since a limit
    holds only under the bound name (docs/adr.md, 25)."""
    if pairs and free is None:
        free = _free_of(f, pairs)
    res: list[str] = []
    for it in contract.list_(f, "reader"):
        p = contract.reader_item(it)
        if not p:
            continue
        res.append("allow\t%s\t%s" % (p[1], p[1]))
        cn = cloud_name(p[1], pairs) if pairs else None
        if cn:
            lst = "allow" if not p[2] or (free is not None and cn in free) else "deny"
            res.append("%s\t%s\t%s" % (lst, cn, cn))
    for r in contract.list_(f, "reader_deny"):
        if not contract.rule_ok(r):
            continue
        res.append("deny\t%s\t%s" % (r, r))
        cn = cloud_name(r, pairs) if pairs else None
        if cn:
            res.append("deny\t%s\t%s" % (cn, cn))
    return res


def codebase_instance(root: str, k: str, plugin: str | None) -> list[str]:
    """The six lines of codebase-instance (see the docstring)."""
    f = "%s/%s.md" % (contract.instance_dir(root), k)
    ok, _ = quietly(validate_instance, root, k, plugin)
    roots = contract.values(f, "roots")
    return [contract.field(f, "type"), "1" if ok else "0", str(len(roots)),
            roots[0] if roots else "", contract.field(f, "ref"), contract.field(f, "gh_user")]


def manual_keys(root: str) -> list[str]:
    """src_manual_keys: keys with a last_checked_<key> line in
    raw/sync-log.md but no instance file (other than raw), C order."""
    log = root + "/raw/sync-log.md"
    try:
        with open(log, "rb") as fh:
            text = fh.read().decode("utf-8", errors="surrogateescape")
    except OSError:
        return []
    keys: set[str] = set()
    for ln in text.split("\n"):
        m = re.match(r"last_checked_([A-Za-z0-9_-]*):", ln, re.ASCII)
        if m:
            keys.add(m.group(1))
    idir = contract.instance_dir(root)
    return [k for k in sorted(keys, key=contract._bytes_key)
            if k != "raw" and not os.path.isfile("%s/%s.md" % (idir, k))]


def type_rules(c: str) -> list[str]:
    """src_type_rules: "allow\t<rule>" / "deny\t<rule>" lines."""
    allow = contract.list_(c, "read_tools") + contract.list_(c, "bookkeeping_tools")
    return (["allow\t" + r for r in allow if r.split()]
            + ["deny\t" + r for r in contract.list_(c, "forbidden_tools") if r.split()])


def narrow_rules(lines: Iterable[str], w: str, k: str) -> list[str]:
    """src_narrow_rules: "<list>\t<rule narrowed to wiki w, key k>\t<rule>"."""
    c = "~/.cache/wiki-sources/"
    res: list[str] = []
    for ln in lines:
        fs = ln.split("\t")
        lst, orig = fs[0], (fs[1] if len(fs) > 1 else "")
        r = orig
        m = re.match(r"(Read|Edit)\(", r)
        if m:
            tool, rest = r[:m.end()], r[m.end():]
            if rest == c + "**)":
                r = tool + c + w + "/" + k + "/**)"
            elif rest.startswith(c + "*/*/"):
                r = tool + c + w + "/" + k + "/" + rest[len(c) + 4:]
        res.append("%s\t%s\t%s" % (lst, r, orig))
    return res


def needed_rules(root: str, plugin: str | None, reader: set[str] | None = None) -> list[str]:
    """src_needed_rules: the rules the wiki's instances need, no repeats:
    their contracts' rules, then the reader bindings of access: tools
    instances. A set passed as reader gets the lines that come from a
    binding (they may live in the user's settings too), except those in a
    connector's cloud name, which count only from the wiki's settings.
    Raises BindingMixError (wiki_binding_error)."""
    w = root.rstrip("/").rsplit("/", 1)[-1] or "/"
    d = contract.instance_dir(root)
    pairs, free = cloud_setup(root, plugin)
    seen: set[str] = set()
    res: list[str] = []
    for k in words(contract.instances(root)):
        f = "%s/%s.md" % (d, k)
        try:
            c = contract.contract(root, contract.field(f, "type"), plugin)
        except contract.ContractError:
            continue
        bound = reader_rules(f, pairs, free) if contract.field(c, "access") == "tools" else []
        for ln in narrow_rules(type_rules(c), w, k) + bound:
            if ln not in seen:
                seen.add(ln)
                res.append(ln)
        if reader is not None:
            reader.update(ln for ln in bound if not is_cloud(_fields(ln)[1], pairs))
    return res


def user_rules() -> list[str]:
    """The permission rules in the user's settings (~/.claude/settings.json),
    as settings_rules lines; [] when the file is missing or not valid JSON.
    Only reader rules may be met there (docs/adr.md, 13)."""
    sf = contract._home() + "/.claude/settings.json"
    try:
        with open(native(sf), "rb") as fh:
            text = fh.read().decode("utf-8", errors="surrogateescape")
    except OSError:
        return []
    have, e = settings_rules(text)
    return have if e is None else []


def rules_check(need: list[str], reader: Container[str], have: list[str],
                user: list[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(missing, blocked) for the needed rules: a rule from a reader binding
    (in reader) may be met, or denied, by the user's settings too."""
    own = [ln for ln in need if ln not in reader]
    bound = [ln for ln in need if ln in reader]
    both = have + user
    return (missing_rules(own, have) + missing_rules(bound, both),
            blocked_rules(own, have) + blocked_rules(bound, both))


# The allow rules stale_rules may report: a source script, as contracts'
# read_tools name it (standard */sources/<type>/<script>.sh, local
# .claude/sources/types/<type>/<script>.sh), and an MCP tool.
_SOURCE_SCRIPT = re.compile(r"Bash\(bash (\S*/)?sources/(types/)?[A-Za-z0-9_-]+/[A-Za-z0-9_-]+\.sh( \*)?\)\Z", re.ASCII)


def stale_rules(need: Iterable[str], have: Iterable[str]) -> list[str]:
    """The allow rules in have (settings_rules) for a source script or an
    MCP tool that no needed allow rule (needed_rules) is, in either form:
    left over from a source or a reader that is gone. A server rule
    (mcp__<server>, mcp__<server>__*) counts as used by its tools. Every
    other rule is never stale. In have's order, no repeats."""
    used: set[str] = set()
    for lst, r, orig in map(_fields, need):
        if lst == "allow":
            used.update((r, orig))
    res: list[str] = []
    for r in _by_list(have).get("allow", []):
        if r in used or r in res:
            continue
        if r.startswith("mcp__"):
            base = r[:-1] if r.endswith("__*") else r + "__"
            if any(u.startswith(base) for u in used):
                continue
        elif not _SOURCE_SCRIPT.match(r):
            continue
        res.append(r)
    return res


_PATH_RULE = re.compile(r"(Read|Edit)\((.*)\)\Z", re.S)


def covers(have: str, need: str) -> bool:
    """A settings rule covers a needed one: the same rule, or the same tool
    (Read or Edit) on a folder <prefix>/** that holds need's path, segment by
    segment with no wildcards in the prefix."""
    if have == need:
        return True
    h, n = _PATH_RULE.match(have), _PATH_RULE.match(need)
    if not h or not n or h.group(1) != n.group(1) or not h.group(2).endswith("/**"):
        return False
    hs, ns = h.group(2)[:-3].split("/"), n.group(2).split("/")
    return len(hs) < len(ns) and hs == ns[:len(hs)]


def _fields(ln: str) -> tuple[str, str, str]:
    """A needed_rules line as (list, rule, as in the contract)."""
    fs = ln.split("\t") + ["", ""]
    return fs[0], fs[1], fs[2]


def _by_list(have: Iterable[str]) -> dict[str, list[str]]:
    """settings_rules lines ("<list>\t<rule>") as {list: [rule]}."""
    by: dict[str, list[str]] = {}
    for ln in have:
        lst, _, r = ln.partition("\t")
        by.setdefault(lst, []).append(r)
    return by


def missing_rules(need: Iterable[str], have: Iterable[str]) -> list[tuple[str, str]]:
    """The needed rules ("<list>\t<rule>\t<as in the contract>", needed_rules)
    that no rule of the same list in have ("<list>\t<rule>", settings_rules)
    covers: [(list, rule)]."""
    by = _by_list(have)
    res: list[tuple[str, str]] = []
    for lst, r, orig in map(_fields, need):
        hs = by.get(lst, [])
        if lst and not (orig in hs or any(covers(h, r) for h in hs)):
            res.append((lst, r))
    return res


def blocked_rules(need: Iterable[str], have: Iterable[str]) -> list[tuple[str, str]]:
    """The needed allow rules (needed_rules) that a deny rule in have
    (settings_rules) covers: deny wins over allow in Claude Code, so they are
    refused even when allowed. [(rule, deny rule)]."""
    deny = _by_list(have).get("deny", [])
    res: list[tuple[str, str]] = []
    for lst, r, orig in map(_fields, need):
        if lst != "allow":
            continue
        for d in deny:
            # covers(d, r) is true for d == r too; the same narrowed rule
            # can come from two contract forms, hence the repeat check.
            if (d == orig or covers(d, r)) and (r, d) not in res:
                res.append((r, d))
    return res


def settings_check(root: str, plugin: str | None,
                   sf: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(missing, blocked) for the wiki and its settings file sf, from one read:
    missing_rules (src_missing_rules; all needed rules when sf doesn't exist;
    for a settings.json that isn't valid JSON, reported elsewhere, a rule
    counts if it is quoted in it) and blocked_rules ([] when sf is missing or
    invalid)."""
    reader: set[str] = set()
    need = needed_rules(root, plugin, reader)
    user = user_rules() if reader else []
    if not os.path.isfile(sf):
        return rules_check(need, reader, [], user)[0], []
    with open(sf, "rb") as fh:
        text = fh.read().decode("utf-8", errors="surrogateescape")
    have, e = settings_rules(text)
    if e is None:
        return rules_check(need, reader, have, user)
    missing: list[tuple[str, str]] = []
    for ln in need:
        lst, r, orig = _fields(ln)
        if not lst or '"%s"' % r in text or '"%s"' % orig in text:
            continue
        if ln in reader and "%s\t%s" % (lst, r) in user:
            continue
        missing.append((lst, r))
    return missing, []


# Settings keys a wiki's settings.json uses, at the top level and under
# "permissions". A key one or two letters off one of these is almost
# certainly a typo; an unknown key once made Claude Code ignore the whole
# file, deny rules included, without an error (2026-11-19). Keys far from
# all of these pass: Claude Code adds settings faster than a list could.
SETTINGS_KEYS = ("$schema", "permissions", "hooks", "env", "enabledPlugins", "extraKnownMarketplaces",
                 "model", "statusLine", "sandbox", "disableAllHooks", "outputStyle", "includeCoAuthoredBy",
                 "cleanupPeriodDays", "enableAllProjectMcpServers", "enabledMcpjsonServers",
                 "disabledMcpjsonServers")
PERMISSION_KEYS = ("allow", "deny", "ask", "defaultMode", "additionalDirectories",
                   "disableBypassPermissionsMode")


def settings_key_typos(text: str) -> list[tuple[str, str]]:
    """[(key path, the known key it is close to)] for keys of a settings
    file that look like misspellings; [] when text isn't a JSON object."""
    try:
        d: object = json.loads(text)
    except ValueError:
        return []
    if not isinstance(d, dict):
        return []
    found: list[tuple[str, str]] = []

    def scan(obj: dict[str, object], known: tuple[str, ...], where: str) -> None:
        for k in obj:
            if k in known:
                continue
            m = difflib.get_close_matches(k, known, n=1, cutoff=0.75)
            if m:
                found.append((where + k, m[0]))

    scan(d, SETTINGS_KEYS, "")
    if isinstance(d.get("permissions"), dict):
        scan(d["permissions"], PERMISSION_KEYS, "permissions.")
    return found


class _ParseState:
    """settings_rules' parser state: i, the 1-based position in the text;
    err, the first error ("" while none); last, the last string read."""

    __slots__ = ("i", "err", "last")

    def __init__(self) -> None:
        self.i = 1
        self.err = ""
        self.last = ""


def settings_rules(text: str) -> tuple[list[str], str | None]:
    """src_settings_rules' JSON parser, as is: (rules, None), or ([], error)
    for text that isn't valid JSON. Positions are 1-based, as in the awk."""
    s = text if text.endswith("\n") or not text else text + "\n"
    n = len(s)
    st = _ParseState()
    rules: list[str] = []

    def ch(j: int | None = None) -> str:
        j = st.i if j is None else j
        return s[j - 1] if 1 <= j <= n else ""

    def fail(m: str) -> bool:
        if not st.err:
            st.err = "%s (line %d)" % (m, s[:max(st.i, 0)].count("\n") + 1)
        return False

    def ws() -> None:
        while st.i <= n and ch() in " \t\r\n":
            st.i += 1

    def string() -> bool:
        st.i += 1
        o: list[str] = []
        while st.i <= n:
            c = ch()
            if c == "\\":
                c = ch(st.i + 1)
                o.append(c if c in ("\\", '"', "/") else "\\" + c)
                st.i += 2
                continue
            if c == '"':
                st.i += 1
                st.last = "".join(o)
                return True
            if c == "\n":
                return fail("line break inside a string")
            o.append(c)
            st.i += 1
        return fail("unterminated string")

    lit = re.compile(r"true|false|null|-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?")

    def value(key: str) -> bool:
        ws()
        c = ch()
        if c == "{":
            return obj()
        if c == "[":
            return arr(key)
        if c == '"':
            return string()
        m = lit.match(s, st.i - 1) if st.i >= 1 else None
        if m:
            st.i += m.end() - m.start()
            return True
        return fail("unexpected end of file" if c == "" else 'unexpected "%s"' % c)

    def obj() -> bool:
        st.i += 1
        ws()
        if ch() == "}":
            st.i += 1
            return True
        while True:
            ws()
            if ch() != '"':
                return fail("expected a quoted key")
            if not string():
                return False
            k = st.last
            ws()
            if ch() != ":":
                return fail('expected : after "%s"' % k)
            st.i += 1
            if not value(k):
                return False
            ws()
            c = ch()
            if c == ",":
                st.i += 1
                ws()
                if ch() == "}":
                    return fail("comma before }")
                continue
            if c == "}":
                st.i += 1
                return True
            return fail("unexpected end of file" if c == "" else "expected , or } (a missing comma?)")

    def arr(key: str) -> bool:
        st.i += 1
        ws()
        if ch() == "]":
            st.i += 1
            return True
        while True:
            ws()
            if ch() == '"' and key in ("allow", "deny", "ask"):
                if not string():
                    return False
                rules.append(key + "\t" + st.last)
            elif not value(""):
                return False
            ws()
            c = ch()
            if c == ",":
                st.i += 1
                ws()
                if ch() == "]":
                    return fail("comma before ]")
                continue
            if c == "]":
                st.i += 1
                return True
            return fail("unexpected end of file" if c == "" else "expected , or ] (a missing comma?)")

    ok = value("")
    ws()
    if ok and st.i <= n:
        fail("text after the end")
    if st.err:
        return [], st.err
    return rules, None


# Command line.

def _main(argv: list[str]) -> int:
    plugin = contract.PLUGIN
    if argv[:1] == ["--plugin"] and len(argv) > 1:
        plugin, argv = argv[1], argv[2:]
    op, args = (argv[0], argv[1:]) if argv else ("", [])
    plugin = native(plugin)
    if op == "validate-contract" and len(args) == 1:
        return 0 if validate_contract(native(args[0])) else 1
    if op == "validate-instance" and len(args) == 2:
        return 0 if validate_instance(native(args[0]), args[1], plugin) else 1
    if op == "needed-rules" and len(args) == 1:
        for ln in needed_rules(native(args[0]), plugin):
            out(ln)
        return 0
    if op == "missing-rules" and len(args) == 2:
        for lst, r in settings_check(native(args[0]), plugin, native(args[1]))[0]:
            out("%s\t%s" % (lst, r))
        return 0
    if op == "codebase-instance" and len(args) == 2:
        for v in codebase_instance(native(args[0]), args[1], plugin):
            sys.stdout.buffer.write(v.encode("utf-8", errors="surrogateescape") + b"\n")
        return 0
    if op == "settings-rules" and len(args) == 1:
        with open(native(args[0]), "rb") as fh:
            text = fh.read().decode("utf-8", errors="surrogateescape")
        rules, e = settings_rules(text)
        if e is not None:
            out("ERROR\t" + e)
            return 1
        for ln in rules:
            out(ln)
        return 0
    err("usage: see the docstring of sourcelib.py")
    return 2


def main(argv: list[str]) -> int:
    try:
        rc = _main(argv)
    except BindingMixError as e:  # the wiki's bindings, not a bug
        err("sourcelib: %s" % e)
        rc = 1
    except GitBashPath as e:
        err("sourcelib: %s" % e)
        rc = 3
    except Exception as e:  # an internal error is never "invalid"
        err("sourcelib: internal error: %s: %s" % (type(e).__name__, e))
        rc = 3
    sys.stdout.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
