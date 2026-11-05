"""hookjson.py: read Claude Code hook input, the Python side of lib-hookjson.sh.

parse(raw) takes the hook JSON as bytes and returns a Hook, or None when the
input can't be used: not JSON, not an object, no tool_name, or a field the
guards read that isn't a string. Callers block on None (fail closed).

Carried over from lib-hookjson.sh:
- newlines and carriage returns in a value become ";" so a multi-line
  command looks chained; a tab becomes a space;
- "description" is never read, so prose can't trigger a guard.

Stricter than lib-hookjson.sh (each has a fixture, see
tests/fixtures/py-stricter.txt):
- the input must be valid JSON (bash read a truncated object);
- \\uXXXX escapes are decoded (bash left them as text);
- every MultiEdit new_string is read (bash read only the last one);
- a field that isn't a string makes the input unusable (bash read it as "").
"""

import json

# Fields of tool_input the guards read, as in lib-hookjson.sh.
_INPUT_KEYS = ("command", "file_path", "path", "pattern", "glob", "content", "new_string")


class Hook:
    __slots__ = ("tool", "command", "file", "content", "cwd", "path", "pattern", "agent_id")


def _clean(s):
    return s.replace("\r", ";").replace("\n", ";").replace("\t", " ")


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
    ti = data.get("tool_input", {})
    if not isinstance(ti, dict):
        return None
    vals = {}
    for k in _INPUT_KEYS:
        v = ti.get(k, "")
        if not isinstance(v, str):
            return None
        vals[k] = _clean(v)
    new_strings = [vals["new_string"]]
    edits = ti.get("edits", [])
    if not isinstance(edits, list):
        return None
    for e in edits:
        if not isinstance(e, dict):
            return None
        v = e.get("new_string", "")
        if not isinstance(v, str):
            return None
        new_strings.append(_clean(v))
    for k in ("cwd", "agent_id"):
        v = data.get(k, "")
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


def norm(s):
    """Lowercase, backslashes to slashes, for path matching (as norm in bash)."""
    return s.replace("\\", "/").lower()
