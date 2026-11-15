"""sync_status.py: how long ago each source in raw/sync-log.md was checked.

The body of sync-status.sh, which is its launcher (docs/adr.md, 4). Runs as a SessionStart hook
(stdout becomes session context) and from the /wiki:sync-status skill.
Prints nothing when the wiki has no sync-log. Read-only, always exit 0.

A value of "never" (set by /wiki:init and /wiki:add-source) means the
source was never ingested. Instances in .claude/sources/instances/ that
have no line yet are listed too, and keys with no instance file are marked
as manual once the wiki has instances. Research instances (mode: research)
aren't ingested, so they are left out. A dated raw line says
"nothing new in raw/" when git shows nothing new there (raw_unchanged).

Same output as the bash version (checked by recording every call of the
test suite on both), except:
- a date is a real YYYY-MM-DD date; anything else (bash took whatever
  `date -d` parses, an empty value as today) is "unreadable date";
- days are calendar days, not epoch seconds / 86400 (time zone and clock
  changes made the bash count drift by one);
- keys match literally where bash's grep took them as a regex;
- the "nothing new in raw/" note is an addition, not in bash.

  sync_status.py [--plugin DIR]

Environment: CLAUDE_PROJECT_DIR (set by Claude Code for hooks) is the wiki;
else the git toplevel of the current directory.
"""

import datetime
import os
import re
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contract  # noqa: E402
import sourcelib  # noqa: E402
from sourcelib import git_out  # noqa: E402

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_SPACE = re.compile(r"[ \t\n\v\f\r]")


def plugin_note(plugin):
    """A plugin from a local-directory marketplace runs from the wiki-tools
    working tree, not from a copy pinned to a commit: uncommitted edits there
    are live in every wiki, and skills (read at session start) can differ from
    scripts (read at each call). Say so when that tree has uncommitted plugin
    changes."""
    top = git_out(plugin, "rev-parse", "--show-toplevel")
    if top is None:
        return None
    dirty = git_out(plugin, "status", "--porcelain", "--", ".") or ""
    dirty = "\n".join(dirty.split("\n")[:5])
    if not dirty:
        return None
    head = git_out(plugin, "rev-parse", "--short", "HEAD") or ""
    return ("Note: the wiki plugin runs from the working tree %s (commit %s), which has "
            "uncommitted changes in the plugin:\n%s\nSkills were read when this session "
            "started, scripts are read at each call, so they may not match. Commit the "
            "changes and run /reload-plugins (or restart)." % (top, head, dirty))


def day(v):
    if not _DATE.fullmatch(v):
        return None
    try:
        return datetime.date(int(v[:4]), int(v[5:7]), int(v[8:]))
    except ValueError:
        return None


def _changed_since(path, since):
    """True when the file at path, or any file under it, was modified or
    created at or after the timestamp since. ctime counts too (creation on
    Windows, inode change elsewhere), so a copy that kept an old mtime is
    still new."""
    paths = [path]
    if os.path.isdir(path):
        paths = [os.path.join(dp, f) for dp, _, fs in os.walk(path) for f in fs]
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            return True
        if max(st.st_mtime, st.st_ctime) >= since:
            return True
    return False


def raw_unchanged(root, d):
    """True when raw/ has no change but raw/sync-log.md since day d: none
    uncommitted or untracked, no ignored file modified or created that day
    or later (git can't date one, so its file times decide: wikis ignore
    raw/ PDFs), and no commit dated d or later (the whole day counts: a
    check that day may have come before the commit). False when git can't
    tell."""
    spec = ["--", "raw", ":(exclude)raw/sync-log.md"]
    st = git_out(root, "status", "--porcelain", "-z", "--untracked-files=all", "--ignored", *spec)
    if st is None:
        return False
    since = datetime.datetime.combine(d, datetime.time()).timestamp()
    for entry in filter(None, st.split("\0")):
        if not entry.startswith("!! ") or _changed_since(os.path.join(root, entry[3:]), since):
            return False
    return git_out(root, "log", "-1", "--format=%H", "--since=%s 00:00:00" % d.isoformat(), "HEAD", *spec) == ""


def report(root, plugin, today):
    """The report for the wiki at root, or None."""
    log = root + "/raw/sync-log.md"
    if not os.path.isfile(log):
        return None
    with open(log, "rb") as fh:
        text = fh.read().decode("utf-8", errors="surrogateescape")
    keys = sourcelib.words(contract.instances(root))

    # Keys with a line but no instance file, once the wiki has instances:
    # they are kept by hand and can't be ingested. The strings and their
    # " key " tests are as in bash.
    manual = ""
    if keys:
        manual = " " + "".join(k + " " for k in sourcelib.manual_keys(root))
    research = " "
    idir = contract.instance_dir(root)
    for k in keys:
        try:
            c = contract.contract(root, contract.field("%s/%s.md" % (idir, k), "type"), plugin)
        except contract.ContractError:
            continue
        if contract.field(c, "mode") == "research":
            research += k + " "

    out = []
    # `while read`: a last line without a newline isn't read.
    for line in text.split("\n")[:-1]:
        if line.endswith("\r"):
            line = line[:-1]
        if not line.startswith("last_checked_") or ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key[len("last_checked_"):]
        if " %s " % key in research:
            continue
        note = " (manual key: enters via raw/ or user statements)" if " %s " % key in manual else ""
        val = _SPACE.sub("", rest)
        d = day(val)
        if val == "never" and note:
            out.append("- %s: never checked%s" % (key, note))
        elif val == "never":
            out.append("- %s: never checked (first ingest asks for a starting point)" % key)
        elif d is not None:
            quiet = ", nothing new in raw/" if key == "raw" and raw_unchanged(root, d) else ""
            out.append("- %s: last checked %s (%d days ago)%s%s" % (key, val, (today - d).days, note, quiet))
        else:
            out.append("- %s: unreadable date '%s'" % (key, val))

    lines = text.split("\n")
    for k in keys:
        if " %s " % k in research:
            continue
        pre = "last_checked_%s:" % k
        if not any(ln.startswith(pre) for ln in lines):
            out.append("- %s: no last_checked_%s line yet (treated as never checked)" % (k, k))
    if not out:
        return None
    return "Wiki sync status (raw/sync-log.md):\n" + "\n".join(out)


def _main(argv):
    plugin = contract.PLUGIN
    if argv[:1] == ["--plugin"] and len(argv) > 1:
        plugin = sourcelib.native(argv[1])
    note = plugin_note(plugin)
    if note:
        sourcelib.out(note)
    root = os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not (root and os.path.isdir(root)):
        root = sourcelib.toplevel(os.getcwd())
        if not root:
            return 0
    r = report(root, plugin, datetime.date.today())
    if r:
        sourcelib.out(r)
    return 0


def main(argv):
    try:
        rc = _main(argv)
    except Exception as e:  # a hook: say it, but never fail the session start
        sys.stdout.flush()
        sourcelib.out("sync-status: internal error: %s: %s" % (type(e).__name__, e))
        rc = 0
    sys.stdout.flush()
    sys.stdout.buffer.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
