"""sources.py: read-only view of a wiki's sources for the wiki skills.

The body of sources.sh, which is its launcher (docs/adr.md, 4). Same operations, arguments, output
byte for byte, messages (`sources: ...`) and exit codes as the bash version
(checked by a dual run and real use on both machines, then deleted; the
dual run's edge cases are kept in tests/fixtures/sources/edge.out):

  sources.py [--plugin DIR] list
  sources.py [--plugin DIR] show <key>
  sources.py [--plugin DIR] due
  sources.py [--plugin DIR] catalog
  sources.py [--plugin DIR] contract <type>
  sources.py [--plugin DIR] settings [<type>... [--key <key>]]
  sources.py [--plugin DIR] check-settings

--plugin is the plugin folder as bash spells it (the launcher passes it):
messages and filled-in contracts use that spelling, files are opened
through its native form (sourcelib.native). Run it from inside a wiki.
Writes nothing. Exit 1: a refusal or a problem (as the bash version);
exit 3: an internal error.

Known differences from bash, accepted in the plan: names and types are
split into words on space, tab and newline but never glob-expanded; type,
key and catalog order is C order; a key is matched literally in
raw/sync-log.md (sed took it as a regex).
"""

from __future__ import annotations

import datetime
import os
import re
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contract  # noqa: E402
import sourcelib  # noqa: E402
import sync_status  # noqa: E402
from sourcelib import err, git, out  # noqa: E402

# Names for the annotations only (never evaluated): nothing to import at run time.
TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

USAGE = ("usage: sources.sh <list|show <key>|due|catalog|contract <type>|"
         "settings [<type>... [--key <key>]]|check-settings>")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_MANUAL = re.compile(r"last_checked_([A-Za-z0-9_-]*):", re.ASCII)


class Die(Exception):
    """sources.sh's die: message on stderr, exit 1."""


def raw(b: bytes) -> None:
    """Bytes to stdout as they are (file contents)."""
    sys.stdout.buffer.write(b)


def name_ok(s: str) -> bool:
    """`printf '%s' "$s" | grep -Eq "$SRC_NAME_RE"`: any line matches."""
    return any(contract.NAME_RE.fullmatch(ln) for ln in s.split("\n"))


def basename(p: str) -> str:
    return p.rstrip("/").rsplit("/", 1)[-1]


def platform() -> str:
    """src_platform."""
    p = sys.platform
    if p.startswith("linux"):
        return "linux"
    if p in ("win32", "cygwin", "msys"):
        return "windows"
    if p == "darwin":
        return "macos"
    import platform as pf
    return pf.system().lower()


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


class Wiki:
    def __init__(self, plugin: str) -> None:
        self.plugin = plugin                # native
        self.plugin_shown = sourcelib.show(plugin)
        top = sourcelib.toplevel(None)
        if not top:
            raise Die("not inside a git repo; run from a wiki.")
        self.root = top
        self.plat = platform()
        self.log = self.root + "/raw/sync-log.md"
        self.idir = contract.instance_dir(self.root)

    def state_of(self, k: str) -> str:
        """The last_checked value in raw/sync-log.md."""
        if not os.path.isfile(self.log):
            return "no sync-log"
        pre = re.compile(r"last_checked_" + re.escape(k) + r":\s*")
        for ln in read_bytes(self.log).decode("utf-8", errors="surrogateescape").split("\n"):
            m = pre.match(ln)
            if m:
                v = ln[m.end():].replace("\r", "")
                return v or "no last_checked_%s line" % k
        return "no last_checked_%s line" % k

    def contract(self, t: str) -> str:
        return contract.contract(self.root, t, self.plugin)

    def platform_ok(self, c: str) -> bool:
        return self.plat in contract.list_(c, "platforms")

    def print_contract(self, c: str) -> None:
        """The contract with ${CLAUDE_PLUGIN_ROOT} filled in, CRs dropped."""
        b = read_bytes(c).replace(b"\r", b"")
        raw(b.replace(b"${CLAUDE_PLUGIN_ROOT}",
                      self.plugin_shown.encode("utf-8", errors="surrogateescape")))

    def manual_keys(self) -> list[str]:
        """src_manual_keys."""
        if not os.path.isfile(self.log):
            return []
        keys: set[str] = set()
        for ln in read_bytes(self.log).decode("utf-8", errors="surrogateescape").split("\n"):
            m = _MANUAL.match(ln)
            if m:
                keys.add(m.group(1))
        return [k for k in sorted(keys, key=contract._bytes_key)
                if k != "raw" and not os.path.isfile("%s/%s.md" % (self.idir, k))]

    def catalog(self) -> list[tuple[str, str, str]]:
        """src_catalog: (type, standard|local, title)."""
        res: list[tuple[str, str, str]] = []
        for base, kind in ((self.plugin + "/sources", "standard"),
                           (self.root + "/.claude/sources/types", "local")):
            try:
                names = os.listdir(base)
            except OSError:
                continue
            for t in sorted((n for n in names if not n.startswith(".")), key=contract._bytes_key):
                f = "%s/%s/SOURCE.md" % (base, t)
                if os.path.isfile(f):
                    res.append((t, kind, contract.field(f, "title")))
        return res


# The operations.

def op_list(w: Wiki, args: list[str]) -> int:
    if len(args) != 0:
        raise Die("usage: sources.sh list")
    out("Sources of %s (platform: %s):" % (basename(w.root), w.plat))
    out("- raw: built in (raw/), last checked: %s" % w.state_of("raw"))
    for k in sourcelib.words(contract.instances(w.root)):
        t = contract.field("%s/%s.md" % (w.idir, k), "type")
        try:
            c = w.contract(t)
        except contract.ContractError:
            out("- %s: type %s: UNKNOWN TYPE" % (k, t or "?"))
            continue
        kind = "standard" if c.startswith(w.plugin + "/") else "local"
        valid, _ = sourcelib.quietly(sourcelib.validate_instance, w.root, k, w.plugin)
        ok = "valid" if valid else "INVALID (run: sources.sh show %s)" % k
        p = "yes" if w.platform_ok(c) else "no (only %s)" % ",".join(contract.list_(c, "platforms"))
        m = ""
        if contract.field(c, "mode") == "research":
            m = ', research (/wiki:research %s "<question>"; not ingested)' % k
        out("- %s: type %s (%s)%s, %s, available here: %s, last checked: %s"
            % (k, t, kind, m, ok, p, w.state_of(k)))
    for k in sourcelib.words(w.manual_keys()):
        out("- %s: manual key (no source file; enters via raw/ or user statements; "
            "/wiki:ingest cannot read it), last checked: %s" % (k, w.state_of(k)))
    return 0


def unbound(c: str, f: str) -> bool:
    """A tool-neutral type (access: tools, contract c) is read only through
    the instance's reader binding; True when instance file f has none."""
    return contract.field(c, "access") == "tools" and not contract.list_(f, "reader")


def check_needed(w: Wiki, k: str, f: str) -> str | None:
    """The instance file changed since the last ingest (a new root or
    label): its parameters haven't met reality yet. The message, or None."""
    last = w.state_of(k)
    if not _DATE.fullmatch(last):
        return None
    rel = f[len(w.root) + 1:] if f.startswith(w.root + "/") else f
    _, st = git(w.root, "status", "--porcelain", "--", rel)
    if st.rstrip("\n"):
        return "Check needed: the instance file has uncommitted changes since the last ingest (%s)." % last
    # Exact commit times: the instance file vs the last ingest commit, the
    # later of the last commit that added a history row of this key (every
    # ingest adds one; a second ingest on one day leaves the last_checked
    # line as it is) and the last that changed its last_checked line (a log
    # with other rows); by date if neither was ever committed. The patterns
    # read the same as basic and as extended regex ([|], no {n}), and a key
    # ([a-z0-9-]) needs no escaping; the cell borders keep other keys out.
    _, changed = git(w.root, "log", "-1", "--format=%ct %cs", "--", rel)
    changed = changed.rstrip("\n")
    if not changed:
        return None
    ct, _, cs = changed.partition(" ")
    day = "-".join("[0-9]" * n for n in (4, 2, 2))
    stamped: list[str] = []
    for pat in ("^[|] *%s *[|] *%s *[|]" % (day, k), "^last_checked_%s:" % k):
        _, o = git(w.root, "log", "-1", "--format=%ct", "-G" + pat, "--", "raw/sync-log.md")
        if o.rstrip("\n"):
            stamped.append(o.rstrip("\n"))
    if stamped:
        try:
            need = not int(ct) <= max(int(t) for t in stamped)
        except ValueError:
            need = True
    else:
        need = not cs < last
    if need:
        return "Check needed: the instance file changed (%s) since the last ingest (%s)." % (cs, last)
    return None


def op_show(w: Wiki, args: list[str]) -> int:
    if len(args) != 1:
        raise Die("usage: sources.sh show <key>")
    k = args[0]
    if k == "raw":
        out("raw is built in: new or changed files in raw/ that the raw/sync-log.md history "
            "does not list. Last checked: %s" % w.state_of("raw"))
        return 0
    if not name_ok(k):
        raise Die("invalid key '%s'" % k)
    f = "%s/%s.md" % (w.idir, k)
    if not os.path.isfile(f):
        raise Die("no source '%s' in this wiki (no %s). Known: raw %s. Add one with /wiki:add-source."
                  % (k, f, " ".join(contract.instances(w.root))))
    valid, errs = sourcelib.quietly(sourcelib.validate_instance, w.root, k, w.plugin)
    if not valid:
        raise Die("source '%s' doesn't validate:\n%s" % (k, "\n".join(errs)))
    t = contract.field(f, "type")
    c = w.contract(t)
    if not w.platform_ok(c):
        raise Die("source '%s' (type %s) isn't available on %s; it supports: %s."
                  % (k, t, w.plat, " ".join(contract.list_(c, "platforms"))))
    out("Source %s: valid, available on %s, last checked: %s" % (k, w.plat, w.state_of(k)))
    msg = check_needed(w, k, f)
    if msg:
        out(msg)
    if unbound(c, f):
        # Without a reader binding, Check (its step 1) must stop the ingest,
        # whatever the instance file's history. A `## Reader` section alone
        # is a binding in prose, from before the `reader` list (docs/adr.md, 13).
        if sourcelib.has_body_section(f, "Reader"):
            out("Check needed: %s names no tools (access: tools) and this instance's reader binding "
                "is in prose only (a '## Reader' section, no 'reader' list); run /wiki:bind-reader %s "
                "again to make it machine-readable." % (t, k))
        else:
            out("Check needed: %s names no tools (access: tools) and this instance has no reader "
                "binding yet; /wiki:bind-reader %s drafts it." % (t, k))
    out("")
    out("===== Instance file %s =====" % (f[len(w.root) + 1:] if f.startswith(w.root + "/") else f))
    raw(read_bytes(f).replace(b"\r", b""))
    out("")
    out("===== Contract %s =====" % c)
    w.print_contract(c)
    return 0


def _due_state(w: Wiki, k: str) -> tuple[str, datetime.date | None]:
    """last_checked of k as sync-status reads it: (value, date or None)."""
    v = w.state_of(k)
    if v in ("no sync-log", "no last_checked_%s line" % k):
        return "never", None
    v = sync_status._SPACE.sub("", v)
    return v, sync_status.day(v)


def _due_skip(w: Wiki, k: str) -> str | None:
    """Why /wiki:ingest all skips instance k, or None. Reasons in a fixed
    order: research, invalid, platform, then the state (in op_due)."""
    f = "%s/%s.md" % (w.idir, k)
    t = contract.field(f, "type")
    try:
        c = w.contract(t)
    except contract.ContractError:
        return "unknown type %s (sources.sh show %s)" % (t or "?", k)
    if contract.field(c, "mode") == "research":
        return 'research (/wiki:research %s "<question>")' % k
    valid, _ = sourcelib.quietly(sourcelib.validate_instance, w.root, k, w.plugin)
    if not valid:
        return "invalid (sources.sh show %s)" % k
    if not w.platform_ok(c):
        return "not available on %s (only %s)" % (w.plat, ",".join(contract.list_(c, "platforms")))
    return None


def op_due(w: Wiki, args: list[str]) -> int:
    """What /wiki:ingest all ingests: every source last checked before
    today, oldest first; raw only when sync-status doesn't find it
    unchanged. The rest, with the reason, under Not due or Skipped."""
    if len(args) != 0:
        raise Die("usage: sources.sh due")
    today = datetime.date.today()
    due: list[tuple[datetime.date, str]] = []
    quiet: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for k in ["raw"] + sourcelib.words(contract.instances(w.root)):
        f = "%s/%s.md" % (w.idir, k)
        why = None if k == "raw" else _due_skip(w, k)
        if why:
            skipped.append((k, why))
            continue
        v, d = _due_state(w, k)
        if v == "never":
            skipped.append((k, "never checked (first ingest: /wiki:ingest %s)" % k))
        elif d is None:
            skipped.append((k, "unreadable date '%s'" % v))
        elif d >= today:
            quiet.append((k, "checked today"))
        elif k == "raw" and sync_status.raw_unchanged(w.root, d):
            quiet.append((k, "nothing new in raw/ since %s" % v))
        elif k != "raw" and (check_needed(w, k, f) or unbound(w.contract(contract.field(f, "type")), f)):
            skipped.append((k, "Check needed (/wiki:ingest %s)" % k))
        else:
            due.append((d, k))
    skipped.extend((k, "manual key (enters via raw/ or user statements)")
                   for k in sourcelib.words(w.manual_keys()))
    due.sort(key=lambda x: x[0])  # stable: raw first, then C order

    def section(title: str, rows: list[tuple[str, str]]) -> None:
        out(title)
        for k, why in rows:
            out("- %s: %s" % (k, why))
        if not rows:
            out("- none")

    section("Due for ingest (today %s), oldest first:" % today.isoformat(),
            [(k, "last checked %s" % d.isoformat()) for d, k in due])
    section("Not due:", quiet)
    section("Skipped (need the user or another skill):", skipped)
    return 0


def op_catalog(w: Wiki, args: list[str]) -> int:
    if len(args) != 0:
        raise Die("usage: sources.sh catalog")
    out("Source types (platform: %s):" % w.plat)
    for t, kind, title in w.catalog():
        try:
            c = w.contract(t)
        except contract.ContractError:
            out("- %s (%s): BROKEN (shadows a standard type?)" % (t, kind))
            continue
        p = "" if w.platform_ok(c) else ", not available on %s" % w.plat
        out("- %s (%s, %s%s): %s" % (t, kind, contract.field(c, "access"), p, title))
    return 0


def op_contract(w: Wiki, args: list[str]) -> int:
    if len(args) != 1:
        raise Die("usage: sources.sh contract <type>")
    t = args[0]
    try:
        c = w.contract(t)
    except contract.ContractError as e:
        err(str(e))
        # Shadowed by a local type: still show the standard contract, which
        # is what the instances must be rewritten to.
        std = "%s/sources/%s/SOURCE.md" % (w.plugin, t)
        if not (name_ok(t) and os.path.isfile(std)):
            return 1
        c = std
        out("WARNING: shown is the standard contract; a local type of the same name shadows it (see above).")
        out("")
    valid, errs = sourcelib.quietly(sourcelib.validate_contract, c)
    if not valid:
        out("WARNING: contract does not validate:")
        out("\n".join(errs))
        out("")
    out("===== Contract %s =====" % c)
    w.print_contract(c)
    return 0


def json_list(items: Iterable[str]) -> str:
    """grep -v '^$' | dedupe | escape \\ and " | quote | comma all but last."""
    seen: set[str] = set()
    res: list[str] = []
    for r in items:
        if r == "" or r in seen:
            continue
        seen.add(r)
        res.append('      "%s"' % r.replace("\\", "\\\\").replace('"', '\\"'))
    return ",\n".join(res)


def op_settings(w: Wiki, args: list[str]) -> int:
    types, key = "", ""
    i = 0
    while i < len(args):
        if args[i] == "--key":
            if i + 1 >= len(args):
                raise Die("--key needs an instance key")
            key = args[i + 1]
            i += 2
        else:
            types += " " + args[i]
            i += 1
    if key and not name_ok(key):
        raise Die("invalid instance key '%s'" % key)
    if not types:
        if key:
            raise Die("--key goes with a type: settings <type> --key <key>")
        rules = sourcelib.needed_rules(w.root, w.plugin)
    else:
        rules = []
        for t in sourcelib.words([types]):
            try:
                c = w.contract(t)
            except contract.ContractError as e:
                err(str(e))
                return 1
            tr = sourcelib.type_rules(c)
            if key:
                rules += sourcelib.narrow_rules(tr, basename(w.root), key)
                f = "%s/%s.md" % (w.idir, key)
                if (contract.field(c, "access") == "tools" and os.path.isfile(f)
                        and contract.field(f, "type") == t):
                    rules += sourcelib.reader_rules(f)
            else:
                rules += ["%s\t%s\t%s" % (ln.split("\t")[0], _f(ln, 1), _f(ln, 1)) for ln in tr]

    def pick(lst: str) -> list[str]:
        return [_f(ln, 1) for ln in rules if _f(ln, 0) == lst]

    out('{\n  "permissions": {\n    "allow": [\n%s\n    ],\n    "deny": [\n%s\n    ]\n  }\n}'
        % (json_list(pick("allow")), json_list(pick("deny"))))
    wide = [ln for ln in rules if _f(ln, 1) != _f(ln, 2)]
    if wide:
        out("\nCache rules are narrowed to this wiki and instance (~/.cache/wiki-sources/<wiki>/<key>/); "
            "a broader rule already in settings.json, e.g. %s, covers them too." % _f(wide[0], 2))
    # access: tools types name no tools, so they add nothing above; say so.
    if not types:
        seen: set[str] = set()
        ts: list[str] = []
        for k in sourcelib.words(contract.instances(w.root)):
            t = contract.field("%s/%s.md" % (w.idir, k), "type")
            if t not in seen:
                seen.add(t)
                ts.append(t)
        tlist = sourcelib.words(ts)
    else:
        tlist = sourcelib.words([types])
    for t in tlist:
        try:
            c = w.contract(t)
        except contract.ContractError:
            continue
        if contract.field(c, "access") != "tools":
            continue
        # The whole wiki or one instance: only instances not bound yet need
        # the note. A type alone: always, since its rules come per instance.
        if key or not types:
            keys = [key] if key else [k for k in sourcelib.words(contract.instances(w.root))
                                      if contract.field("%s/%s.md" % (w.idir, k), "type") == t]
            nob = [k for k in keys if unbound(c, "%s/%s.md" % (w.idir, k))]
            if not nob:
                continue
            prose = [k for k in nob if sourcelib.has_body_section("%s/%s.md" % (w.idir, k), "Reader")]
            never = [k for k in nob if k not in prose]
            how = ""
            if never:
                how += "; not bound yet: %s (/wiki:bind-reader <key> drafts it)" % ", ".join(never)
            if prose:
                how += ("; bound in prose only (a '## Reader' section, no 'reader' list): %s "
                        "(/wiki:bind-reader <key> again makes it machine-readable)" % ", ".join(prose))
        else:
            how = " (sources.sh settings %s --key <key>)" % t
        out("\n%s (access: tools) names no tools, so it adds no tool rules here (only its cache rules, "
            "if any). An instance's reader binding (its 'reader' list) adds the reader's rules%s. "
            "How read-only is kept is in its Caveats, not in these settings." % (t, how))
    return 0


def _f(ln: str, n: int) -> str:
    """awk -F'\\t' field n+1 ("" when missing)."""
    fs = ln.split("\t")
    return fs[n] if n < len(fs) else ""


def op_check_settings(w: Wiki, args: list[str]) -> int:
    if len(args) != 0:
        raise Die("usage: sources.sh check-settings")
    sf = w.root + "/.claude/settings.json"
    if not os.path.isfile(sf):
        out("settings.json: missing (%s)" % sf)
        return 1
    try:
        text = read_bytes(sf).decode("utf-8", errors="surrogateescape")
    except OSError as e:
        err("sourcelib: internal error: %s: %s" % (type(e).__name__, e))
        out("settings.json: NOT valid JSON: ")
        return 1
    have, jerr = sourcelib.settings_rules(text)
    if jerr is not None:
        out("settings.json: NOT valid JSON: %s" % jerr)
        return 1
    out("settings.json: valid JSON, %d permission rules" % len(have))
    bad = 0
    typos = ["  %s (%s?)" % t for t in sourcelib.settings_key_typos(text)]
    if typos:
        bad = 1
        out("misspelled keys (Claude Code may ignore the whole file, deny rules included):\n"
            + "\n".join(typos))
    else:
        out("misspelled keys: none")
    hs = set(have)
    reader: set[str] = set()
    need = sourcelib.needed_rules(w.root, w.plugin, reader)
    user = sourcelib.user_rules() if reader else []
    if reader:
        out("reader rules (from the instances' reader bindings) count in your user settings too "
            "(~/.claude/settings.json, %d permission rules)" % len(user))
    missing, blocked = sourcelib.rules_check(need, reader, have, user)
    miss = ["  %s: %s" % m for m in missing]
    if miss:
        bad = 1
        out("missing (rules your sources need):\n" + "\n".join(miss))
    else:
        out("missing: none")
    counts: dict[str, int] = {}
    for ln in have:
        counts[ln] = counts.get(ln, 0) + 1
    dup = ["  " + ln.replace("\t", ": ", 1)
           for ln in sorted((ln for ln, n in counts.items() if n > 1), key=contract._bytes_key)]
    if dup:
        bad = 1
        out("duplicates:\n" + "\n".join(dup))
    else:
        out("duplicates: none")
    allow = {_f(ln, 1) for ln in have if _f(ln, 0) == "allow"}
    deny = {_f(ln, 1) for ln in have if _f(ln, 0) == "deny"}
    both = ["  " + r for r in sorted(allow & deny, key=lambda s: contract._bytes_key("  " + s))]
    if both:
        bad = 1
        out("in both allow and deny (deny wins):\n" + "\n".join(both))
    else:
        out("conflicts: none")
    blk = ["  allow: %s (deny: %s)" % m for m in blocked]
    if blk:
        bad = 1
        out("blocked by deny (rules your sources need; deny wins):\n" + "\n".join(blk))
    else:
        out("blocked by deny: none")
    # Report only: a leftover allow rule is hygiene, not a broken setup.
    stale = ["  allow: " + r for r in sorted(sourcelib.stale_rules(need, have), key=contract._bytes_key)]
    if stale:
        out("stale (allow rules for source scripts and MCP tools that no source instance uses; "
            "remove any that nothing else needs):\n" + "\n".join(stale))
    else:
        out("stale: none")
    seen: set[str] = set()
    broad: list[str] = []
    for ln in need:
        if _f(ln, 1) == _f(ln, 2):
            continue
        pair = _f(ln, 0) + "\t" + _f(ln, 2)
        if pair in seen:
            continue
        seen.add(pair)
        if pair in hs:
            broad.append("  " + _f(ln, 2))
    if broad:
        out("note: these rules reach every wiki's cache; the per-instance rules (sources.sh settings) "
            "would do:\n" + "\n".join(broad))
    return bad


OPS: dict[str, Callable[[Wiki, list[str]], int]] = {"list": op_list, "show": op_show, "due": op_due, "catalog": op_catalog, "contract": op_contract,
       "settings": op_settings, "check-settings": op_check_settings}


def _main(argv: list[str]) -> int:
    plugin = contract.PLUGIN
    if argv[:1] == ["--plugin"] and len(argv) > 1:
        plugin, argv = argv[1], argv[2:]
    plugin = sourcelib.native(plugin)
    op, args = (argv[0], argv[1:]) if argv else ("", [])
    w = Wiki(plugin)
    fn = OPS.get(op)
    if fn is None:
        raise Die(USAGE)
    return fn(w, args)


def main(argv: list[str]) -> int:
    try:
        rc = _main(argv)
    except Die as e:
        err("sources: %s" % e)
        rc = 1
    except sourcelib.GitBashPath as e:
        err("sources: %s" % e)
        rc = 3
    except Exception as e:  # an internal error is never a refusal
        err("sources: internal error: %s: %s" % (type(e).__name__, e))
        rc = 3
    sys.stdout.flush()
    sys.stdout.buffer.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
