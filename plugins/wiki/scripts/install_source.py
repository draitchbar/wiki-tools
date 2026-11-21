"""install_source.py: the checks and the writing for install-source-file.sh.

The user (docs/adr.md, 2)
installs one file into a wiki's protected .claude/sources/ tree from a
terminal outside Claude; install-source-file.sh keeps everything that
touches the terminal (the refusal inside Claude, reading the pasted file,
the diff, the y/n prompt) and calls this script for the rest:

  install_source.py [--plugin DIR] target TARGET
      check TARGET only (run before asking for a paste on a terminal);
      exit 0, or 1 with the reason on stderr
  install_source.py [--plugin DIR] check TARGET SCRATCH
      SCRATCH/pasted holds what was given. Checks it in a scratch copy of
      .claude/sources/ (SCRATCH/wiki): frontmatter, key matches the file
      name, the type exists, required parameters, roots of filesystem
      instances, the contract of a local type; and re-checks every
      instance, so one file can't break another. Writes SCRATCH/new (the
      file to install: no CR, a final newline) and, if the file exists,
      SCRATCH/current (normalised the same way). Exit 0: ready; 1: refused
      (reasons on stderr); 2: already exactly this (said on stdout)
  install_source.py [--plugin DIR] write TARGET SCRATCH
      install SCRATCH/new, then print the settings rules
      (.claude/settings.json) the wiki's source types need that are
      still missing, and how to commit

TARGET is instances/<key>.md or types/<type>/<file>, relative to
.claude/sources/ (a leading ./ or .claude/sources/ is dropped). Run from
inside the wiki. Never touches git. Exit 3: an internal error.

--plugin is the plugin folder as bash spells it (the launcher passes it):
messages use that spelling, files are opened through its native form.
SCRATCH is passed in native form (`pwd -W` on Windows).

Same output as the bash version (checked by recording every call of the
test suite on both).
"""

from __future__ import annotations

import os
import re
import shutil
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contract  # noqa: E402
import sourcelib  # noqa: E402

_FILE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", re.ASCII)


class Die(Exception):
    """`install-source-file: <message>` on stderr, exit 1."""


def _grep(rx, s):
    """printf '%s' "$s" | grep -Eq '^rx$': any line matches."""
    return any(rx.fullmatch(ln) for ln in s.split("\n"))


def parse_target(arg, plugin):
    """(target, kind, key-or-type, file name) or Die."""
    t = arg[2:] if arg.startswith("./") else arg
    if t.startswith(".claude/sources/"):
        t = t[len(".claude/sources/"):]
    if t.startswith("instances/") and t.endswith(".md") and len(t) >= len("instances/.md"):
        key = t[len("instances/"):-3]
        if not _grep(contract.NAME_RE, key):
            raise Die("instance key '%s' must be kebab-case (a-z, 0-9, -)." % key)
        return t, "instance", key, None
    if t.startswith("types/") and "/" in t[len("types/"):]:
        typ, name = t[len("types/"):].split("/", 1)
        if not _grep(contract.NAME_RE, typ):
            raise Die("type name '%s' must be kebab-case." % typ)
        if not _grep(_FILE_NAME, name):
            raise Die("file name '%s' must be a plain name in types/%s/ (no subfolders)."
                      % (name, typ))
        if os.path.isfile("%s/sources/%s/SOURCE.md" % (plugin, typ)):
            raise Die("'%s' is a standard type; a local type can't use its name." % typ)
        return t, "type", typ, name
    raise Die("target must be instances/<key>.md or types/<type>/<file>, relative to "
              ".claude/sources/.")


def wiki_root():
    top = sourcelib.toplevel(os.getcwd())
    if not top:
        raise Die("not inside a git repo; run it from the wiki.")
    if not os.path.isfile(top + "/CLAUDE.md"):
        raise Die("%s has no CLAUDE.md; run it from the wiki." % top)
    return top


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _normal(data):
    """No CR; a final newline unless empty."""
    data = data.replace(b"\r", b"")
    if data and not data.endswith(b"\n"):
        data += b"\n"
    return data


def check(target_arg, scratch, plugin):
    target, kind, tk, name = parse_target(target_arg, plugin)
    root = wiki_root()
    sw = scratch + "/wiki"
    os.makedirs(sw + "/.claude/sources", exist_ok=True)
    if os.path.isdir(root + "/.claude/sources"):
        shutil.copytree(root + "/.claude/sources", sw + "/.claude/sources",
                        symlinks=True, dirs_exist_ok=True)
    new = "%s/.claude/sources/%s" % (sw, target)
    os.makedirs(new.rsplit("/", 1)[0], exist_ok=True)
    data = _read(scratch + "/pasted").replace(b"\r", b"")
    if not data:
        raise Die("nothing pasted; nothing installed.")
    data = _normal(data)
    with open(new, "wb") as fh:
        fh.write(data)

    # 1. Check, in the scratch copy. A contract may list scripts not
    # installed yet (contract first, then its scripts): that is a warning,
    # everything else an error.
    errs, warns = "", ""

    def add_err(text):
        nonlocal errs, warns
        for ln in text.split("\n"):
            if not ln:
                continue
            if "is listed but missing" in ln:
                if ln not in warns:
                    warns += "\n  - %s (install it next)" % ln
            else:
                errs += "\n  - " + ln

    def scrubbed(lines):
        return "\n".join(lines).replace(sw + "/", "")

    if kind == "instance":
        if not contract.has_fm(new):
            first = data.split(b"\n", 1)[0].decode("utf-8", errors="surrogateescape")[:60]
            add_err("no frontmatter: the file must start with a line '---' and close the "
                    "block with another '---' (first line pasted: \"%s\")" % first)
    elif name == "SOURCE.md":
        ok, lines = sourcelib.quietly(sourcelib.validate_contract, new)
        if not ok:
            add_err(scrubbed(lines))
    else:
        c = "%s/.claude/sources/types/%s/SOURCE.md" % (sw, tk)
        if not os.path.isfile(c):
            add_err("types/%s/SOURCE.md doesn't exist yet; install the contract first." % tk)
        elif name.endswith(".sh") and name not in contract.list_(c, "scripts"):
            add_err("%s isn't listed under scripts: in types/%s/SOURCE.md, so the guard "
                    "won't let Claude run it." % (name, tk))
    # Every instance must still validate (the new file included).
    idir = contract.instance_dir(sw)
    for k in sourcelib.words(contract.instances(sw)):
        f = "%s/%s.md" % (idir, k)
        ok, lines = sourcelib.quietly(sourcelib.validate_instance, sw, k, plugin)
        if not ok:
            add_err(scrubbed(lines))
            continue
        c = contract.contract(sw, contract.field(f, "type"), plugin)
        if contract.field(c, "access") == "filesystem" and not contract.values(f, "roots"):
            add_err(".claude/sources/instances/%s.md: a filesystem instance needs roots" % k)
    if errs:
        raise Die("not installed; fix these and run it again:" + errs)
    if warns:
        sourcelib.out("Note:" + warns)

    # 2. What the launcher shows: the new file, and the current one
    # normalised as the pasted one was (a CRLF checkout of the same file is
    # no change).
    with open(scratch + "/new", "wb") as fh:
        fh.write(data)
    dest = "%s/.claude/sources/%s" % (root, target)
    if os.path.isfile(dest):
        cur = _normal(_read(dest))
        if cur == data:
            sourcelib.out("install-source-file: .claude/sources/%s is already exactly this; "
                          "nothing to do." % target)
            return 2
        with open(scratch + "/current", "wb") as fh:
            fh.write(cur)
    return 0


def write(target_arg, scratch, plugin):
    target = parse_target(target_arg, plugin)[0]
    root = wiki_root()
    dest = "%s/.claude/sources/%s" % (root, target)
    d = dest.rsplit("/", 1)[0]
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        raise Die("cannot create %s" % d) from None
    try:
        with open(dest, "wb") as fh:
            fh.write(_read(scratch + "/new"))
    except OSError:
        raise Die("cannot write %s" % dest) from None
    sourcelib.out("Installed .claude/sources/%s." % target)

    # 3. Settings rules the wiki's source types need that settings.json
    # lacks (a broader Read/Edit rule, e.g. the contract's own form, covers
    # one too), and those a deny rule blocks (deny wins).
    sf = root + "/.claude/settings.json"
    try:
        miss, blocked = sourcelib.settings_check(root, plugin, sf)
    except Exception as e:
        sourcelib.err("sourcelib: internal error: %s: %s" % (type(e).__name__, e))
        miss, blocked = None, []
    lists: dict[str, list[str]] = {}
    for lst, r in miss or []:
        ls = lists.setdefault(lst, [])
        ln = '      "%s",' % r
        if ln not in ls:
            ls.append(ln)
    allow, deny = lists.get("allow", []), lists.get("deny", [])
    if allow or deny:
        sourcelib.out("\n.claude/settings.json still lacks rules these sources need. "
                      "Add them by hand:")
        if allow:
            sourcelib.out('  under "permissions" -> "allow":\n' + "\n".join(allow))
        if deny:
            sourcelib.out('  under "permissions" -> "deny":\n' + "\n".join(deny))
    elif miss is not None and not blocked:
        sourcelib.out("\n.claude/settings.json has every rule these sources need.")
    if blocked:
        sourcelib.out("\n.claude/settings.json denies rules these sources need (deny wins over "
                      "allow). Remove or narrow these deny rules by hand:\n"
                      + "\n".join('  "%s" blocks "%s"' % (d, r) for r, d in blocked))
    sourcelib.out("\nWhen all files are in, commit them yourself, e.g.\n  git add -- "
                  ".claude/sources/%s && git commit -m \"Add source files\"" % target)
    return 0


def _main(argv):
    plugin = contract.PLUGIN
    if argv[:1] == ["--plugin"] and len(argv) > 1:
        plugin, argv = sourcelib.native(argv[1]), argv[2:]
    op, args = (argv[0], argv[1:]) if argv else ("", [])
    if op == "target" and len(args) == 1:
        parse_target(args[0], plugin)
        wiki_root()
        return 0
    if op == "check" and len(args) == 2:
        return check(args[0], sourcelib.native(args[1]), plugin)
    if op == "write" and len(args) == 2:
        return write(args[0], sourcelib.native(args[1]), plugin)
    sourcelib.err("usage: see the docstring of install_source.py")
    return 3


def main(argv):
    try:
        rc = _main(argv)
    except Die as e:
        sourcelib.err("install-source-file: %s" % e)
        rc = 1
    except sourcelib.GitBashPath as e:
        sourcelib.err("install-source-file: %s" % e)
        rc = 3
    except Exception as e:
        sourcelib.err("install-source-file: internal error: %s: %s" % (type(e).__name__, e))
        rc = 3
    sys.stdout.flush()
    sys.stdout.buffer.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
