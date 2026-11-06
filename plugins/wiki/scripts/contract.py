"""contract.py: read source-type contracts and source instances.

The Python side of the lib-source.sh functions the guard uses (speed plan,
step 2b): has_fm, field, list_, values, contract, instances, expand,
is_abs, has_dots. Same rules, same results, same messages; until
sources.sh, wiki-check, lint and install move here, tests/run-tests.sh
checks the two parsers against each other ("contract-parity").

The frontmatter of SOURCE.md and instance files is flat `key: value` lines
and `- item` lists, between a first line `---` and the next `---`. Files
are read as UTF-8 with surrogateescape, so any byte survives a round trip,
and one CR is stripped from each line end, as the awk in lib-source.sh does.
Whitespace around values and before list items is any Unicode whitespace:
the hooks run in the user's locale, where sed (and gawk in Git Bash) match
e.g. U+2003 with [[:space:]], so a root written "/home/u/Scans<U+2003>" is
still /home/u/Scans. Python's set is a little larger than glibc's (it has
U+00A0), which only makes the guard stricter. The `---` fences take ASCII
whitespace only, as mawk does.

Imported by the Python hooks. Also a small command line for the tests:

  contract.py [--plugin DIR] field FILE KEY
  contract.py [--plugin DIR] list FILE KEY
  contract.py [--plugin DIR] values FILE KEY
  contract.py [--plugin DIR] has-fm FILE          exit 0 or 1
  contract.py [--plugin DIR] contract ROOT TYPE   path, or message and exit 1
  contract.py [--plugin DIR] instances ROOT
  contract.py [--plugin DIR] expand|is-abs|has-dots PATH
  contract.py [--plugin DIR] parity FILE KEY...   has-fm and values per key

Output matches the bash function's byte for byte. --plugin stands in for
lib-source.sh's SRC_PLUGIN (default: this script's plugin folder).
"""

import os
import re
import sys


PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")

NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*", re.ASCII)
_FENCE = re.compile(r"---[ \t\n\v\f\r]*")
_KEY_LINE = re.compile(r"[A-Za-z_]+:", re.ASCII)
_ITEM = re.compile(r"\s+-\s*")
_FIELD_KEY = re.compile(r"[a-z_]+", re.ASCII)
_DRIVE = re.compile(r"[A-Za-z]:[/\\]")


class ContractError(Exception):
    """A type that can't be resolved; str(e) is lib-source.sh's message."""


_cache = {}


def _lines(path):
    """The file's lines, one CR stripped from each; [] if unreadable."""
    got = _cache.get(path)
    if got is None:
        try:
            with open(path, "rb") as f:
                text = f.read().decode("utf-8", errors="surrogateescape")
        except OSError:
            text = ""
        got = text.split("\n")
        if got[-1] == "":
            got.pop()
        got = [ln[:-1] if ln.endswith("\r") else ln for ln in got]
        _cache[path] = got
    return got


def fm(path):
    """The frontmatter lines (src_fm): [] without an opening `---`; to EOF
    without a closing one."""
    lines = _lines(path)
    if not lines or not _FENCE.fullmatch(lines[0]):
        return []
    out = []
    for ln in lines[1:]:
        if _FENCE.fullmatch(ln):
            break
        out.append(ln)
    return out


def has_fm(path):
    """True if the file opens and closes a frontmatter block (src_has_fm)."""
    lines = _lines(path)
    if not lines or not _FENCE.fullmatch(lines[0]):
        return False
    return any(_FENCE.fullmatch(ln) for ln in lines[1:])


def field(path, key, default=""):
    """A scalar value (src_field); `default` when the key is absent.
    Raises ValueError for a key that isn't [a-z_]+, where bash returns 1."""
    if not _FIELD_KEY.fullmatch(key):
        raise ValueError("bad key %r" % key)
    pre = key + ":"
    for ln in fm(path):
        if ln.startswith(pre):
            return ln[len(pre):].strip()
    return default


def list_(path, key):
    """The `- item` lines under KEY (src_list), empty items dropped."""
    out = []
    cur = None
    for ln in fm(path):
        m = _KEY_LINE.match(ln)
        if m:
            cur = m.group(0)[:-1]
            continue
        if cur == key:
            m = _ITEM.match(ln)
            if m:
                s = ln[m.end():].rstrip()
                if s:
                    out.append(s)
    return out


def values(path, key):
    """A scalar value as a one-item list, or else the list items (src_values)."""
    v = field(path, key) if _FIELD_KEY.fullmatch(key) else ""
    return [v] if v else list_(path, key)


def instance_dir(root):
    return root + "/.claude/sources/instances"


def _bytes_key(s):
    return s.encode("utf-8", errors="surrogateescape")


def instances(root):
    """The instance keys of a wiki, sorted as LC_ALL=C sort (src_instances)."""
    d = instance_dir(root)
    try:
        entries = os.listdir(d)
    except OSError:
        return []
    keys = [e[:-3] for e in entries
            if e.endswith(".md") and not e.startswith(".") and os.path.isfile(d + "/" + e)]
    return sorted(keys, key=_bytes_key)


def contract(root, t, plugin=None):
    """Path of the type's SOURCE.md (src_contract). A local type may not
    shadow a standard one. Raises ContractError with bash's message."""
    plugin = PLUGIN if plugin is None else plugin
    if not NAME_RE.fullmatch(t):
        raise ContractError("invalid source type name '%s'" % t)
    std = "%s/sources/%s/SOURCE.md" % (plugin, t)
    loc = "%s/.claude/sources/types/%s/SOURCE.md" % (root, t)
    s, l = os.path.isfile(std), os.path.isfile(loc)
    if s and l:
        raise ContractError(
            "local type '%s' (%s) shadows the standard type of the same name. If the standard "
            "type replaces it, in a terminal outside Claude: 1) delete the folder "
            ".claude/sources/types/%s/; 2) right after, install each instance of type %s "
            "rewritten to the standard contract's parameters and state (sources.sh contract %s "
            "shows it); 3) add any new state lines to raw/sync-log.md. Otherwise rename the "
            "local type" % (t, loc, t, t, t))
    if s:
        return std
    if l:
        return loc
    raise ContractError("unknown source type '%s' (looked in %s and %s)" % (t, std, loc))


def _home():
    h = os.environ.get("HOME") or os.environ.get("USERPROFILE") or ""
    return h.replace("\\", "/")


def expand(p):
    """"~/x" -> "$HOME/x"; backslashes -> slashes; repeated slashes folded;
    no trailing "/" (src_expand). HOME, else USERPROFILE, with slashes."""
    p = p.replace("\\", "/")
    if p.startswith("~/"):
        p = _home() + "/" + p[2:]
    p = re.sub("/+", "/", p)
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


def is_abs(p):
    """"/x", "~/x" or "C:/x" (src_is_abs)."""
    return p.startswith("/") or p.startswith("~/") or bool(_DRIVE.match(p))


def has_dots(p):
    """True if a path segment is "." or ".." (src_has_dots)."""
    s = "/" + p.replace("\\", "/") + "/"
    return "/./" in s or "/../" in s


# Command line, for the tests.

def _out(lines):
    for s in lines:
        sys.stdout.buffer.write(s.encode("utf-8", errors="surrogateescape") + b"\n")


def _cli(argv):
    plugin = None
    if argv[:1] == ["--plugin"] and len(argv) > 1:
        plugin, argv = argv[1], argv[2:]
    op, args = (argv[0], argv[1:]) if argv else ("", [])
    if op == "field" and len(args) == 2:
        if not _FIELD_KEY.fullmatch(args[1]):
            return 1
        v = field(args[0], args[1], None)
        _out([] if v is None else [v])
    elif op == "list" and len(args) == 2:
        _out(list_(args[0], args[1]))
    elif op == "values" and len(args) == 2:
        _out(values(args[0], args[1]))
    elif op == "has-fm" and len(args) == 1:
        return 0 if has_fm(args[0]) else 1
    elif op == "contract" and len(args) == 2:
        try:
            _out([contract(args[0], args[1], plugin)])
        except ContractError as e:
            sys.stderr.buffer.write(str(e).encode("utf-8", errors="surrogateescape") + b"\n")
            return 1
    elif op == "instances" and len(args) == 1:
        _out(instances(args[0]))
    elif op == "expand" and len(args) == 1:
        sys.stdout.buffer.write(expand(args[0]).encode("utf-8", errors="surrogateescape"))
    elif op == "is-abs" and len(args) == 1:
        return 0 if is_abs(args[0]) else 1
    elif op == "has-dots" and len(args) == 1:
        return 0 if has_dots(args[0]) else 1
    elif op == "parity" and args:
        out = ["has_fm %d" % (0 if has_fm(args[0]) else 1)]
        for k in args[1:]:
            out.append("-- " + k)
            out.extend(values(args[0], k))
        _out(out)
    else:
        sys.stderr.write("usage: see the docstring of contract.py\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
