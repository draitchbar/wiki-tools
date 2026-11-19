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
on a folder (<prefix>/**) that holds its path.

--plugin stands in for lib-source.sh's SRC_PLUGIN (default: this script's
plugin folder). Exit 3: an internal error (a bug, an unreadable settings
file, or a Git Bash path on Windows), never "invalid".

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

import os
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re  # noqa: E402
import subprocess  # noqa: E402
import difflib  # noqa: E402
import json  # noqa: E402

import contract  # noqa: E402

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


# Paths: given spelling <-> native form (identity off Windows).

_shown = []  # (native, as given) pairs that differ


def native(p):
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


def show(s):
    for n, p in _shown:
        s = s.replace(n, p)
    return s


# Output: bytes (no \r\n on Windows), stdout flushed before every stderr write.

def _b(s):
    return show(s).encode("utf-8", errors="surrogateescape") + b"\n"


def out(s):
    sys.stdout.buffer.write(_b(s))


_sink = None  # a list while quietly() runs: err() collects instead of writing


def err(s):
    if _sink is not None:
        _sink.append(s)
        return
    sys.stdout.flush()
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(_b(s))
    sys.stderr.buffer.flush()


def quietly(fn, *args):
    """fn(*args) with its err() lines collected: (result, lines). The bash
    callers' `2>/dev/null` and `errs=$(... 2>&1)`."""
    global _sink
    saved, _sink = _sink, []
    try:
        return fn(*args), _sink
    finally:
        _sink = saved


def words(items):
    """`for x in $(...)`: the items split on space, tab and newline."""
    return [w for w in _IFS.split("\n".join(items)) if w]


def names(items):
    """src_names: each item up to a space, "(" or ":", empty ones dropped."""
    return [n for n in (_NAME_CUT.split(i, 1)[0] for i in items) if n]


def _grep_file(path, regex):
    return any(regex.fullmatch(ln) for ln in contract._lines(path))


# Helpers the scripts share. lower() is hookjson.lower, which
# the guard needs without this module.

def read_text(path):
    """A file's text, bytes kept (surrogateescape); "" if it can't be read."""
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", errors="surrogateescape")
    except OSError:
        return ""


def git(root, *args):
    """(rc, stdout) of git in root (no -C when root is empty or None), stderr
    dropped, bytes kept; (1, "") if git can't be started."""
    try:
        r = subprocess.run(["git"] + (["-C", root] if root else []) + list(args),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL)
    except OSError:
        return 1, ""
    return r.returncode, r.stdout.decode("utf-8", errors="surrogateescape")


def git_out(root, *args):
    """`$(git -C root ... 2>/dev/null)`: stdout without the final newlines,
    None if git fails."""
    rc, o = git(root, *args)
    return None if rc != 0 else o.rstrip("\n")


def toplevel(root):
    """The work tree holding root (None: the current folder), "" if none."""
    return git_out(root, "rev-parse", "--show-toplevel") or ""


# The bridged functions.

def validate_contract(f):
    """src_validate_contract: one error per line on stderr; True if valid."""
    bad = False

    def ce(m):
        nonlocal bad
        err("%s: %s" % (f, m))
        bad = True

    if not contract.has_fm(f):
        err("%s: no frontmatter block" % f)
        return False
    fld = lambda k: contract.field(f, k)  # noqa: E731
    lst = lambda k: contract.list_(f, k)  # noqa: E731
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
        seen = set()
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
    p = lst("platforms")
    if not p:
        ce("no platforms listed")
    for x in words(p):
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


def validate_instance(root, k, plugin):
    """src_validate_instance: an instance file and its contract."""
    bad = False
    f = "%s/%s.md" % (contract.instance_dir(root), k)

    def ie(m):
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
    for m in reader_errors(f, c):
        ie(m)
    for r in contract.values(f, "roots"):
        if not contract.is_abs(r):
            ie("root '%s' isn't an absolute path" % r)
        if contract.has_dots(r):
            ie("root '%s' contains '.' or '..'" % r)
    return not bad


def reader_errors(f, c):
    """What is wrong with an instance's reader binding (`reader`,
    `reader_deny`; docs/adr.md, 13), given its contract c."""
    items, deny = contract.list_(f, "reader"), contract.list_(f, "reader_deny")
    if contract.field(c, "access") != "tools":
        return (["only an access: tools instance has a reader binding ('reader', 'reader_deny')"]
                if items or deny else [])
    res = []
    ops = dict(p for p in map(contract.operation, contract.list_(c, "operations")) if p)
    bound, limited, free = set(), set(), set()
    for it in items:
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
    for t in sorted(limited & free, key=contract._bytes_key):
        res.append("reader binds %s both with and without a limit; the limit would have no effect" % t)
    if items:
        for op in [o for o, lvl in ops.items() if lvl == "required" and o not in bound]:
            res.append("reader doesn't bind '%s', a required operation" % op)
    rules = limited | free
    for r in deny:
        if not contract.rule_ok(r):
            res.append("reader_deny item '%s' must be an MCP tool or a Bash(...) or PowerShell(...) rule" % r)
        elif r in rules:
            res.append("reader_deny denies %s, which reader binds" % r)
    return res


def reader_rules(f):
    """An instance's binding as needed_rules lines: allow each bound rule
    (an MCP tool once, whatever its limits), deny each reader_deny rule."""
    res = []
    for it in contract.list_(f, "reader"):
        p = contract.reader_item(it)
        if p:
            res.append("allow\t%s\t%s" % (p[1], p[1]))
    for r in contract.list_(f, "reader_deny"):
        if contract.rule_ok(r):
            res.append("deny\t%s\t%s" % (r, r))
    return res


def codebase_instance(root, k, plugin):
    """The six lines of codebase-instance (see the docstring)."""
    f = "%s/%s.md" % (contract.instance_dir(root), k)
    ok, _ = quietly(validate_instance, root, k, plugin)
    roots = contract.values(f, "roots")
    return [contract.field(f, "type"), "1" if ok else "0", str(len(roots)),
            roots[0] if roots else "", contract.field(f, "ref"), contract.field(f, "gh_user")]


def manual_keys(root):
    """src_manual_keys: keys with a last_checked_<key> line in
    raw/sync-log.md but no instance file (other than raw), C order."""
    log = root + "/raw/sync-log.md"
    try:
        with open(log, "rb") as fh:
            text = fh.read().decode("utf-8", errors="surrogateescape")
    except OSError:
        return []
    keys = set()
    for ln in text.split("\n"):
        m = re.match(r"last_checked_([A-Za-z0-9_-]*):", ln, re.ASCII)
        if m:
            keys.add(m.group(1))
    idir = contract.instance_dir(root)
    return [k for k in sorted(keys, key=contract._bytes_key)
            if k != "raw" and not os.path.isfile("%s/%s.md" % (idir, k))]


def type_rules(c):
    """src_type_rules: "allow\t<rule>" / "deny\t<rule>" lines."""
    allow = contract.list_(c, "read_tools") + contract.list_(c, "bookkeeping_tools")
    return (["allow\t" + r for r in allow if r.split()]
            + ["deny\t" + r for r in contract.list_(c, "forbidden_tools") if r.split()])


def narrow_rules(lines, w, k):
    """src_narrow_rules: "<list>\t<rule narrowed to wiki w, key k>\t<rule>"."""
    c = "~/.cache/wiki-sources/"
    res = []
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


def needed_rules(root, plugin, reader=None):
    """src_needed_rules: the rules the wiki's instances need, no repeats:
    their contracts' rules, then the reader bindings of access: tools
    instances. A set passed as reader gets the lines that come from a
    binding (they may live in the user's settings too)."""
    w = root.rstrip("/").rsplit("/", 1)[-1] or "/"
    d = contract.instance_dir(root)
    seen, res = set(), []
    for k in words(contract.instances(root)):
        f = "%s/%s.md" % (d, k)
        try:
            c = contract.contract(root, contract.field(f, "type"), plugin)
        except contract.ContractError:
            continue
        bound = reader_rules(f) if contract.field(c, "access") == "tools" else []
        for ln in narrow_rules(type_rules(c), w, k) + bound:
            if ln not in seen:
                seen.add(ln)
                res.append(ln)
        if reader is not None:
            reader.update(bound)
    return res


def user_rules():
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


def rules_check(need, reader, have, user):
    """(missing, blocked) for the needed rules: a rule from a reader binding
    (in reader) may be met, or denied, by the user's settings too."""
    own = [ln for ln in need if ln not in reader]
    bound = [ln for ln in need if ln in reader]
    both = have + user
    return (missing_rules(own, have) + missing_rules(bound, both),
            blocked_rules(own, have) + blocked_rules(bound, both))


_PATH_RULE = re.compile(r"(Read|Edit)\((.*)\)\Z", re.S)


def covers(have, need):
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


def _fields(ln):
    """A needed_rules line as (list, rule, as in the contract)."""
    return tuple((ln.split("\t") + ["", ""])[:3])


def _by_list(have):
    """settings_rules lines ("<list>\t<rule>") as {list: [rule]}."""
    by = {}
    for ln in have:
        lst, _, r = ln.partition("\t")
        by.setdefault(lst, []).append(r)
    return by


def missing_rules(need, have):
    """The needed rules ("<list>\t<rule>\t<as in the contract>", needed_rules)
    that no rule of the same list in have ("<list>\t<rule>", settings_rules)
    covers: [(list, rule)]."""
    by = _by_list(have)
    res = []
    for lst, r, orig in map(_fields, need):
        hs = by.get(lst, [])
        if lst and not (orig in hs or any(covers(h, r) for h in hs)):
            res.append((lst, r))
    return res


def blocked_rules(need, have):
    """The needed allow rules (needed_rules) that a deny rule in have
    (settings_rules) covers: deny wins over allow in Claude Code, so they are
    refused even when allowed. [(rule, deny rule)]."""
    deny = _by_list(have).get("deny", [])
    res = []
    for lst, r, orig in map(_fields, need):
        if lst != "allow":
            continue
        for d in deny:
            # covers(d, r) is true for d == r too; the same narrowed rule
            # can come from two contract forms, hence the repeat check.
            if (d == orig or covers(d, r)) and (r, d) not in res:
                res.append((r, d))
    return res


def settings_check(root, plugin, sf):
    """(missing, blocked) for the wiki and its settings file sf, from one read:
    missing_rules (src_missing_rules; all needed rules when sf doesn't exist;
    for a settings.json that isn't valid JSON, reported elsewhere, a rule
    counts if it is quoted in it) and blocked_rules ([] when sf is missing or
    invalid)."""
    reader = set()
    need = needed_rules(root, plugin, reader)
    user = user_rules() if reader else []
    if not os.path.isfile(sf):
        return rules_check(need, reader, [], user)[0], []
    with open(sf, "rb") as fh:
        text = fh.read().decode("utf-8", errors="surrogateescape")
    have, e = settings_rules(text)
    if e is None:
        return rules_check(need, reader, have, user)
    missing = []
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


def settings_key_typos(text):
    """[(key path, the known key it is close to)] for keys of a settings
    file that look like misspellings; [] when text isn't a JSON object."""
    try:
        d = json.loads(text)
    except ValueError:
        return []
    if not isinstance(d, dict):
        return []
    found = []

    def scan(obj, known, where):
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


def settings_rules(text):
    """src_settings_rules' JSON parser, as is: (rules, None) or (None, error).
    Positions are 1-based, as in the awk."""
    s = text if text.endswith("\n") or not text else text + "\n"
    n = len(s)
    st = {"i": 1, "err": "", "last": ""}
    rules = []

    def ch(j=None):
        j = st["i"] if j is None else j
        return s[j - 1] if 1 <= j <= n else ""

    def fail(m):
        if not st["err"]:
            st["err"] = "%s (line %d)" % (m, s[:max(st["i"], 0)].count("\n") + 1)
        return False

    def ws():
        while st["i"] <= n and ch() in " \t\r\n":
            st["i"] += 1

    def string():
        st["i"] += 1
        o = []
        while st["i"] <= n:
            c = ch()
            if c == "\\":
                c = ch(st["i"] + 1)
                o.append(c if c in ("\\", '"', "/") else "\\" + c)
                st["i"] += 2
                continue
            if c == '"':
                st["i"] += 1
                st["last"] = "".join(o)
                return True
            if c == "\n":
                return fail("line break inside a string")
            o.append(c)
            st["i"] += 1
        return fail("unterminated string")

    lit = re.compile(r"true|false|null|-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?")

    def value(key):
        ws()
        c = ch()
        if c == "{":
            return obj()
        if c == "[":
            return arr(key)
        if c == '"':
            return string()
        m = lit.match(s, st["i"] - 1) if st["i"] >= 1 else None
        if m:
            st["i"] += m.end() - m.start()
            return True
        return fail("unexpected end of file" if c == "" else 'unexpected "%s"' % c)

    def obj():
        st["i"] += 1
        ws()
        if ch() == "}":
            st["i"] += 1
            return True
        while True:
            ws()
            if ch() != '"':
                return fail("expected a quoted key")
            if not string():
                return False
            k = st["last"]
            ws()
            if ch() != ":":
                return fail('expected : after "%s"' % k)
            st["i"] += 1
            if not value(k):
                return False
            ws()
            c = ch()
            if c == ",":
                st["i"] += 1
                ws()
                if ch() == "}":
                    return fail("comma before }")
                continue
            if c == "}":
                st["i"] += 1
                return True
            return fail("unexpected end of file" if c == "" else "expected , or } (a missing comma?)")

    def arr(key):
        st["i"] += 1
        ws()
        if ch() == "]":
            st["i"] += 1
            return True
        while True:
            ws()
            if ch() == '"' and key in ("allow", "deny", "ask"):
                if not string():
                    return False
                rules.append(key + "\t" + st["last"])
            elif not value(""):
                return False
            ws()
            c = ch()
            if c == ",":
                st["i"] += 1
                ws()
                if ch() == "]":
                    return fail("comma before ]")
                continue
            if c == "]":
                st["i"] += 1
                return True
            return fail("unexpected end of file" if c == "" else "expected , or ] (a missing comma?)")

    ok = value("")
    ws()
    if ok and st["i"] <= n:
        fail("text after the end")
    if st["err"]:
        return None, st["err"]
    return rules, None


# Command line.

def _main(argv):
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


def main(argv):
    try:
        rc = _main(argv)
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
