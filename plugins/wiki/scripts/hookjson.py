"""hookjson.py: read Claude Code hook input.

parse(raw) takes the hook JSON as bytes and returns a HookCall, or None when
the input can't be used: not valid JSON, not an object, no tool_name, a
tool_input that isn't an object, a cwd or agent_id that isn't a string, or,
for a tool the guard checks (shell, write, read), a field it reads that
isn't a string (JSON null counts as absent: an optional field may be
null). Callers block on None (fail closed). The input of any other tool is
not read, so it may hold lists, objects or numbers.

Every tool is classified (kind()):
  shell     Bash, PowerShell, Monitor (its command; a Monitor WebSocket
            watch, with ws and no command, runs none and is "harmless");
  write     Write, Edit, MultiEdit, NotebookEdit;
  read      Read, Grep, Glob;
  harmless  the built-in tools in HARMLESS, which neither run commands nor
            write or read files;
  mcp       any mcp__* tool (settings rules govern them; the guard checks
            only the reader bindings' limits and denies, docs/adr.md, 13);
  unknown   anything else, which the guard refuses.

A HookCall says what the call does, whatever the tool:
  tool      the tool name as Claude Code sends it;
  kind      as above;
  shell     "bash" (Bash, Monitor) or "powershell" for a shell call, else "";
  command   the shell command ("" if none);
  paths     the paths the call names, empty ones left out: a write call's
            file_path or notebook_path; a read call's file_path and path;
  contents  what a write call writes: content, new_source, then every
            new_string;
  pattern   Grep's/Glob's pattern and glob, joined by a space;
  subagent  the hook input's agent_id ("" in the main session);
  cwd       the hook input's cwd;
  inputs    an mcp call's top-level tool_input fields that are strings
            (others left out), unchanged; {} for every other kind.

- \\uXXXX escapes are decoded, and every MultiEdit new_string is read;
- newlines and carriage returns in a value become ";" so a multi-line
  command looks chained; a tab becomes a space;
- "description" is never read, so prose can't trigger the guard.

norm() lowercases ASCII letters only, so the guard's matching doesn't depend
on the locale.
"""

import json

# Built-in tools that don't run commands, write files or read files: the
# guard lets them pass. A tool on none of the lists here is refused.
HARMLESS = frozenset((
    "Agent", "Artifact", "AskUserQuestion", "CronCreate", "CronDelete", "CronList",
    "EndConversation", "EnterPlanMode", "EnterWorktree", "ExitPlanMode", "ExitWorktree",
    "ListAgents", "ListMcpResourcesTool", "PushNotification", "ReadMcpResourceTool",
    "RemoteTrigger", "ReportFindings", "ScheduleWakeup", "SendFeedback", "SendMessage",
    "SendUserFile", "ShareOnboardingGuide", "Skill", "SubagentHandback",
    "Task",  # Agent's name in older Claude Code versions
    "TaskCreate", "TaskGet",
    "TaskList", "TaskStop", "TaskUpdate", "TaskOutput", "TodoWrite", "ToolSearch",
    "WaitForMcpServers", "WebFetch", "WebSearch", "Workflow",
))

_KINDS = {"Bash": "shell", "PowerShell": "shell", "Monitor": "shell",
          "Write": "write", "Edit": "write", "MultiEdit": "write", "NotebookEdit": "write",
          "Read": "read", "Grep": "read", "Glob": "read"}
_SHELLS = {"Bash": "bash", "PowerShell": "powershell", "Monitor": "bash"}
_CHECKED = ("shell", "write", "read")

# Fields of tool_input the guard reads, for the kinds it checks.
_INPUT_KEYS = ("command", "file_path", "notebook_path", "path", "pattern", "glob", "content",
               "new_string", "new_source")


def kind(tool):
    """shell, write, read, harmless, mcp or unknown."""
    if tool in _KINDS:
        return _KINDS[tool]
    if tool in HARMLESS:
        return "harmless"
    if tool.startswith("mcp__"):
        return "mcp"
    return "unknown"


class HookCall:
    # A plain class, not a dataclass: dataclasses would add import time to
    # every tool call.
    __slots__ = ("kind", "shell", "command", "paths", "contents", "pattern", "subagent", "cwd", "tool",
                 "inputs")


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
    top = {}
    for k in ("cwd", "agent_id"):
        v = _opt(data.get(k))
        if not isinstance(v, str):
            return None
        top[k] = _clean(v)

    h = HookCall()
    h.tool = tool
    h.kind = kind(tool)
    h.shell = _SHELLS.get(tool, "")
    h.command = ""
    h.paths = ()
    h.contents = ()
    h.pattern = " "
    h.subagent = top["agent_id"]
    h.cwd = top["cwd"]
    h.inputs = {}
    if h.kind == "mcp":
        h.inputs = {k: v for k, v in ti.items() if isinstance(k, str) and isinstance(v, str)}
    if h.kind not in _CHECKED:
        return h

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

    h.command = vals["command"]
    if tool == "Monitor" and not h.command and ti.get("ws") is not None:
        # A WebSocket watch runs no command.
        h.kind, h.shell = "harmless", ""
        return h
    if h.kind == "write":
        h.paths = tuple(v for v in (vals["file_path"], vals["notebook_path"]) if v)
        h.contents = (vals["content"], vals["new_source"]) + tuple(new_strings)
    else:
        h.paths = tuple(v for v in (vals["file_path"], vals["path"]) if v)
        h.contents = (vals["content"],) + tuple(new_strings)
    h.pattern = vals["pattern"] + " " + vals["glob"]
    return h


_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def lower(s):
    """ASCII letters lowercased."""
    return s.translate(_ASCII_LOWER)


def norm(s):
    """Lowercase (ASCII), backslashes to slashes, for path matching."""
    return lower(s.replace("\\", "/"))
