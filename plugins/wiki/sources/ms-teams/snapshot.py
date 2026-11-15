"""snapshot.py: the work of ms-teams/snapshot.sh (docs/adr.md, 4).

Compare a SharePoint folder walk with the previous one, and keep it for
the next run. SharePoint folder listings carry no dates, so the
ms-teams type finds new and changed files this way.

  snapshot.py <key> compare|save     (through snapshot.sh)

Files, in ~/.cache/wiki-sources/<wiki>/<key>/: walk.tsv (this run's walk,
written by Claude: URI<TAB><folder label>/<path><TAB>size in bytes) and
files.tsv (the last saved walk, same format). compare prints one line per
file that differs, keyed on the URI (new, changed, moved, removed), sorted
by path, then a summary line, and changes nothing; save replaces files.tsv
with walk.tsv and removes walk.tsv. Nothing outside that cache folder is
read or written; the connector is never called.

Same output as the bash version except, on Windows, paths in messages are
spelled as Python spells them (C:/Users/...), not as Git Bash does
(/c/Users/...). Exit 1 on a refusal, 3 on an internal error.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

import contract  # noqa: E402
import sourcelib  # noqa: E402

_SIZE = re.compile(r"[0-9]+", re.ASCII)
_BLANK = re.compile(r"[ \t\n\v\f\r]*")


class Die(Exception):
    pass


def out(s):
    sourcelib.out(s)


def clean(name, path):
    """The file's lines without CRs and blank lines, as (uri, path, size);
    Die after listing every bad line on stderr."""
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8", errors="surrogateescape").replace("\r", "")
    lines = [ln for ln in text.split("\n") if not _BLANK.fullmatch(ln)]
    rows, seen, bad = [], set(), False
    for i, ln in enumerate(lines, 1):
        f = ln.split("\t")
        if len(f) != 3 or not f[0] or not f[1] or not _SIZE.fullmatch(f[2]):
            sourcelib.err("%s line %d is not URI<TAB>path<TAB>size: %s" % (name, i, ln))
            bad = True
            continue
        if f[0] in seen:
            sourcelib.err("%s line %d repeats URI %s" % (name, i, f[0]))
            bad = True
        seen.add(f[0])
        rows.append(tuple(f))
    return rows, lines, bad


def _key(line):
    b = line.encode("utf-8", errors="surrogateescape")
    return (b.split(b"\t")[1] if b.count(b"\t") >= 1 else b"", b)


def run(argv):
    if len(argv) != 2:
        raise Die("usage: snapshot.sh <key> <compare|save>")
    key, op = argv
    if op not in ("compare", "save"):
        raise Die("operation '%s' is not allowed; ops are: compare save" % op)
    r = subprocess.run(["git", "-C", os.getcwd(), "rev-parse", "--show-toplevel"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    root = r.stdout.decode("utf-8", errors="surrogateescape").rstrip("\n")
    if r.returncode != 0 or not root:
        raise Die("not inside a git repo; run from a wiki.")
    if not any(contract.NAME_RE.fullmatch(ln) for ln in key.split("\n")):
        raise Die("invalid instance key '%s'" % key)
    inst = "%s/%s.md" % (contract.instance_dir(root), key)
    if not os.path.isfile(inst):
        raise Die("no instance '%s' (%s)." % (key, inst))
    if contract.field(inst, "type") != "ms-teams":
        raise Die("instance '%s' is not an ms-teams instance." % key)
    ok, _ = sourcelib.quietly(sourcelib.validate_instance, root, key, contract.PLUGIN)
    if not ok:
        raise Die("instance file %s doesn't validate; run /wiki:init to check it." % inst)
    d = "%s/.cache/wiki-sources/%s/%s" % (contract._home(), root.rstrip("/").rsplit("/", 1)[-1], key)
    walk, snap = d + "/walk.tsv", d + "/files.tsv"
    if not os.path.isfile(walk):
        raise Die("no walk file %s; write this run's folder walk there first." % walk)
    wrows, wlines, bad = clean("walk.tsv", walk)
    if bad:
        raise Die("fix %s and run it again." % walk)
    if not wlines:
        out("ms-teams snapshot: WARNING: walk.tsv is empty; a failed listing is more likely than an emptied "
            "library. Check the walk before saving.")
    if op == "compare":
        if os.path.isfile(snap):
            srows, _, bad = clean("files.tsv", snap)
            if bad:
                raise Die("%s is malformed; delete it to start over (every file then counts as new)." % snap)
        else:
            srows = []
            out("ms-teams snapshot: no files.tsv yet; every file is new.")
        old = {u: (p, s) for u, p, s in srows}
        seen, res = set(), []
        n = c = m = u_ = 0
        for uri, path, size in wrows:
            seen.add(uri)
            if uri not in old:
                res.append("new\t%s\t%s" % (path, size))
                n += 1
            elif int(size) != int(old[uri][1]):
                res.append("changed\t%s\t%s (was %s)" % (path, size, old[uri][1]))
                c += 1
            elif path != old[uri][0]:
                res.append("moved\t%s\tfrom %s" % (path, old[uri][0]))
                m += 1
            else:
                u_ += 1
        rm = 0
        for uri, (path, size) in old.items():
            if uri not in seen:
                res.append("removed\t%s\t%s" % (path, size))
                rm += 1
        for ln in sorted(res, key=_key):
            out(ln)
        out("ms-teams snapshot: summary: %d new, %d changed, %d moved, %d removed, %d unchanged" % (n, c, m, rm, u_))
    else:
        try:
            with open(snap + ".new", "wb") as fh:
                fh.write("".join(ln + "\n" for ln in wlines).encode("utf-8", errors="surrogateescape"))
            os.replace(snap + ".new", snap)
        except OSError:
            raise Die("cannot write %s" % snap) from None
        os.remove(walk)
        out("ms-teams snapshot: saved %d files to %s" % (len(wlines), snap))
    return 0


def main(argv):
    try:
        rc = run(argv)
    except Die as e:
        sourcelib.err("ms-teams snapshot: %s" % e)
        rc = 1
    except Exception as e:
        sourcelib.err("ms-teams snapshot: internal error: %s: %s" % (type(e).__name__, e))
        rc = 3
    sys.stdout.flush()
    sys.stdout.buffer.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
