"""hookjson.py: read Claude Code hook input.

parse(raw) takes the hook JSON as bytes and returns a HookCall, or None when
the input can't be used: not valid JSON, not an object, no tool_name, or a
field the guard reads that isn't a string (JSON null counts as absent: an
optional field may be null). Callers block on None (fail closed).

A HookCall says what the call does, whatever the tool:
  tool      the tool name as Claude Code sends it;
  kind      "shell" (Bash, PowerShell), "write" (Write, Edit, MultiEdit),
            "read" (Read, Grep, Glob), or "" for any other tool;
  shell     "bash" or "powershell" for a shell call, else "";
  command   the shell command ("" if none);
  paths     the paths the call names, empty ones left out: a write call's
            file_path; a read call's file_path and path;
  contents  what a write call writes: content, then every new_string;
  pattern   Grep's/Glob's pattern and glob, joined by a space;
  subagent  the hook input's agent_id ("" in the main session);
  cwd       the hook input's cwd.

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


_KINDS = {"Bash": "shell", "PowerShell": "shell", "Write": "write", "Edit": "write",
          "MultiEdit": "write", "Read": "read", "Grep": "read", "Glob": "read"}
_SHELLS = {"Bash": "bash", "PowerShell": "powershell"}


class HookCall:
    # A plain class, not a dataclass: dataclasses would add import time to
    # every tool call.
    __slots__ = ("kind", "shell", "command", "paths", "contents", "pattern", "subagent", "cwd", "tool")


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

    h = HookCall()
    h.tool = tool
    h.kind = _KINDS.get(tool, "")
    h.shell = _SHELLS.get(tool, "")
    h.command = vals["command"]
    if h.kind == "write":
        h.paths = tuple(v for v in (vals["file_path"],) if v)
    else:
        h.paths = tuple(v for v in (vals["file_path"], vals["path"]) if v)
    h.contents = (vals["content"],) + tuple(new_strings)
    h.pattern = vals["pattern"] + " " + vals["glob"]
    h.subagent = vals["agent_id"]
    h.cwd = vals["cwd"]
    return h


_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def lower(s):
    """ASCII letters lowercased."""
    return s.translate(_ASCII_LOWER)


def norm(s):
    """Lowercase (ASCII), backslashes to slashes, for path matching."""
    return lower(s.replace("\\", "/"))
