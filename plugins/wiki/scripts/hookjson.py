"""hookjson.py: read Claude Code hook input.

parse(raw) takes the hook JSON as bytes and returns a Hook, or None when the
input can't be used: not valid JSON, not an object, no tool_name, or a field
the guard reads that isn't a string (JSON null counts as absent: an optional
field may be null). Callers block on None (fail closed).

- \\uXXXX escapes are decoded, and every MultiEdit new_string is read;
- newlines and carriage returns in a value become ";" so a multi-line
  command looks chained; a tab becomes a space;
- "description" is never read, so prose can't trigger the guard.

norm() lowercases ASCII letters only, so the guard's matching doesn't depend
on the locale.
"""

import json

# Fields of tool_input the guard reads.
_INPUT_KEYS = ("command", "file_path", "path", "pattern", "glob", "content", "new_string")


class Hook:
    __slots__ = ("tool", "command", "file", "content", "cwd", "path", "pattern", "agent_id")


def _clean(s):
    return s.replace("\r", ";").replace("\n", ";").replace("\t", " ")


def _opt(v):
    """An absent or null field is ""."""
    return "" if v is None else v


def parse(raw):
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    tool = data.get("tool_name")
    if not isinstance(tool, str) or not tool:
        return None
    ti = data.get("tool_input")
    if ti is None:
        ti = {}
    if not isinstance(ti, dict):
        return None
    vals = {}
    for k in _INPUT_KEYS:
        v = _opt(ti.get(k))
        if not isinstance(v, str):
            return None
        vals[k] = _clean(v)
    new_strings = [vals["new_string"]]
    edits = ti.get("edits")
    if edits is None:
        edits = []
    if not isinstance(edits, list):
        return None
    for e in edits:
        if not isinstance(e, dict):
            return None
        v = _opt(e.get("new_string"))
        if not isinstance(v, str):
            return None
        new_strings.append(_clean(v))
    for k in ("cwd", "agent_id"):
        v = _opt(data.get(k))
        if not isinstance(v, str):
            return None
        vals[k] = _clean(v)

    h = Hook()
    h.tool = tool
    h.command = vals["command"]
    h.file = vals["file_path"]
    h.content = vals["content"] + " " + " ".join(new_strings)
    h.cwd = vals["cwd"]
    h.path = vals["path"]
    h.pattern = vals["pattern"] + " " + vals["glob"]
    h.agent_id = vals["agent_id"]
    return h


_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def lower(s):
    """ASCII letters lowercased."""
    return s.translate(_ASCII_LOWER)


def norm(s):
    """Lowercase (ASCII), backslashes to slashes, for path matching."""
    return lower(s.replace("\\", "/"))
