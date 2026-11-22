"""pii-check: find personal data before it reaches the public repo.

Run through scripts/pii-check.sh (docs/development.md, "Personal data").

    pii-check.sh [--require-denylist] range REV-LIST-ARGS...
        every commit `git rev-list REV-LIST-ARGS` gives: author, committer,
        message, file paths and added lines (against the first parent)
    pii-check.sh [--require-denylist] tree [REV]
        every path and text line of REV (default HEAD)
    pii-check.sh [--require-denylist] text LABEL
        stdin, reported as LABEL (a PR title, a branch name, ...)
    pii-check.sh pre-push REMOTE
        git's pre-push hook: the ref lines on stdin

Two kinds of rule:
- general patterns, committed here: email addresses other than the allowed
  noreply ones and test domains, user folders (C:/Users/<name>, /home/<name>),
  private hostnames, Claude session links;
- the private denylist: one term per line ('#' comments), from $PII_DENYLIST
  (CI's secret) or the file $PII_DENYLIST_FILE, else
  ~/.config/wiki-tools/pii-denylist.txt. Matching ignores case, Danish
  letters' spellings (o/oe for the o with a stroke, ...) and separators
  between words (first.last, first_last, firstlast).

A hit names where it is and which rule or denylist entry number matched;
never the text, which would publish it a second time. Exit: 0 clean,
1 hits (or, with --require-denylist, no denylist), 2 usage or git error.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata
from typing import Literal, overload  # git()'s overloads: not a guard module
from urllib.parse import unquote

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
ZERO = re.compile(r"^0+$")

# --- general patterns ------------------------------------------------------

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Commit identities: only these.
NOREPLY = re.compile(r"(?i)^([0-9]+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com$"
                     r"|^noreply@(anthropic|github)\.com$")
# In text: also test data on reserved names, and a few fixed strings.
TEST_DOMAIN = re.compile(r"(?i)(^|\.)(example\.(com|org|net)|example|invalid|test|localhost)$")
ALLOWED_EMAILS = {"git@github.com", "abc@thread.tacv"}

USER_DIR = re.compile(r"(?i)(?:\b[A-Za-z]:|^|(?<=[\s\"'`(=]))[/\\]+(?:Users|home)[/\\]+"
                      r"([^/\\\s\"'`),;:]+)")
ALLOWED_USERS = {"u", "x", "user", "you", "runner", "...", "\u2026", "firstname.lastname",
                 ".cache", "username"}

HOSTNAME = re.compile(r"(?i)\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:home|lan|corp|internal|localdomain)\b")
SESSION = re.compile(r"(?i)claude\.ai/code/session_[A-Za-z0-9]")


def general_hits(text: str) -> list[str]:
    """The general rules text breaks, by name, in order of first match."""
    hits: list[str] = []
    for m in EMAIL.finditer(text):
        e = m.group(0).rstrip(".")
        dom = e.rsplit("@", 1)[1]
        if not (NOREPLY.match(e) or TEST_DOMAIN.search(dom) or e.lower() in ALLOWED_EMAILS):
            hits.append("email address")
    for m in USER_DIR.finditer(text):
        name = m.group(1).rstrip(".")
        if name.lower() not in ALLOWED_USERS and name[:1] not in "<$%*{" and name:
            hits.append("user folder")
    if HOSTNAME.search(text):
        hits.append("private hostname")
    if SESSION.search(text):
        hits.append("Claude session link")
    return list(dict.fromkeys(hits))


# --- the denylist ----------------------------------------------------------

_FOLD = {"\u00f8": "o", "\u00e6": "a", "\u00e5": "a", "\u00df": "ss", "\u0111": "d",
         "\u0142": "l", "\u00fe": "th"}
# Two-letter spellings of the same letters, folded the same way.
_PAIRS = re.compile(r"oe|ae|aa")


def fold(text: str) -> str:
    """Case, accents and Danish letters folded; o/oe, ae and aa/a alike."""
    t = unicodedata.normalize("NFKD", text.casefold())
    t = "".join(_FOLD.get(c, c) for c in t if not unicodedata.combining(c))
    return _PAIRS.sub(lambda m: m.group(0)[0], t)


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(unquote(text)))


class Denylist:
    """Terms as token lists, with their entry numbers (1-based, among the
    lines that are terms)."""

    SHORT = 6   # a one-word term shorter than this must be a whole word

    def __init__(self, text: str) -> None:
        self.terms: list[tuple[int, list[str]]] = []
        n = 0
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            n += 1
            t = tokens(line)
            if t:
                self.terms.append((n, t))

    def __len__(self) -> int:
        return len(self.terms)

    def hits(self, text: str) -> list[int]:
        toks = tokens(text)
        if not toks:
            return []
        joined = " ".join(toks)
        found: list[int] = []
        for n, t in self.terms:
            whole = "".join(t)
            if len(t) > 1 and (" " + " ".join(t) + " ") in (" " + joined + " "):
                found.append(n)
            elif len(whole) >= self.SHORT and any(whole in w for w in toks):
                found.append(n)
            elif len(whole) < self.SHORT and whole in toks:
                found.append(n)
        return found


def load_denylist() -> Denylist:
    text = os.environ.get("PII_DENYLIST", "")
    if not text.strip():
        path = os.environ.get("PII_DENYLIST_FILE") or os.path.join(
            os.path.expanduser("~"), ".config", "wiki-tools", "pii-denylist.txt")
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = ""
    return Denylist(text)


# --- scanning --------------------------------------------------------------

def lines(text: str) -> list[str]:
    """Lines split on \\n only: str.splitlines() also splits on form feeds and
    Unicode separators, which would hide what follows them from a rule."""
    out = text.split("\n")
    if out and out[-1] == "":
        out.pop()
    return [line[:-1] if line.endswith("\r") else line for line in out]


class Scan:
    def __init__(self, deny: Denylist) -> None:
        self.deny = deny
        self.count = 0

    def safe(self, name: str, mask: str = "<path>") -> str:
        """A path or ref name fit to print: itself unless a rule matches it."""
        return mask if general_hits(name) or self.deny.hits(name) else name

    def text(self, where: str, text: str, identity: bool = False) -> None:
        """Check one piece of text; identity: an author or committer email,
        which must be a noreply address."""
        rules: list[str] = []
        if identity:
            if not NOREPLY.match(text.strip()):
                rules.append("email address that isn't a noreply address")
        else:
            rules = general_hits(text)
        rules += ["denylist entry %d" % n for n in self.deny.hits(text)]
        for r in rules:
            self.count += 1
            print("pii-check: %s: %s" % (where, r))


@overload
def git(*args: str, binary: Literal[False] = False) -> str: ...
@overload
def git(*args: str, binary: Literal[True]) -> bytes: ...


def git(*args: str, binary: bool = False) -> bytes | str:
    r = subprocess.run(["git", "-c", "core.quotepath=off"] + list(args),
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise GitError("git %s: %s" % (" ".join(args[:2]),
                                       r.stderr.decode("utf-8", "replace").strip()))
    return r.stdout if binary else r.stdout.decode("utf-8", "surrogateescape")


class GitError(Exception):
    pass


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


def scan_commit(scan: Scan, sha: str) -> None:
    short = sha[:10]
    meta = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", sha)
    an, ae, cn, ce, msg = meta.split("\0", 4)
    scan.text("commit %s author name" % short, an)
    scan.text("commit %s author email" % short, ae, identity=True)
    scan.text("commit %s committer name" % short, cn)
    scan.text("commit %s committer email" % short, ce, identity=True)
    for i, mline in enumerate(lines(msg), 1):
        scan.text("commit %s message line %d" % (short, i), mline)
    parents = git("rev-list", "--parents", "-n", "1", sha).split()
    base = parents[1] if len(parents) > 1 else EMPTY_TREE
    names = git("diff", "--name-status", "-z", "-M", "--no-ext-diff", base, sha).split("\0")
    for name in names:
        if name and not re.match(r"^[ACDMRTUXB][0-9]*$", name):
            scan.text("commit %s path %s" % (short, scan.safe(name)), name)
    diff = git("diff", "-M", "--no-color", "--no-ext-diff", "--no-textconv", "-U0", base, sha)
    path, line, header = "?", 0, False
    for d in lines(diff):
        if d.startswith("diff --git "):
            header = True   # until the file's first hunk: "+++ " is the path
        elif header and d.startswith("+++ "):
            path = d[6:] if d.startswith("+++ b/") else d[4:]
        elif d.startswith("@@"):
            header = False
            m = HUNK.match(d)
            line = int(m.group(1)) if m else 0
        elif not header and d.startswith("+"):
            scan.text("commit %s %s:%d" % (short, scan.safe(path), line), d[1:])
            line += 1


def scan_range(scan: Scan, args: list[str]) -> None:
    for sha in git("rev-list", "--reverse", *args).split():
        scan_commit(scan, sha)


def scan_tree(scan: Scan, rev: str) -> None:
    for path in git("ls-tree", "-r", "-z", "--name-only", rev).split("\0"):
        if path:
            scan.text("%s path %s" % (rev, scan.safe(path)), path)
    out = git("grep", "-I", "-n", "-z", "-e", "", rev, "--")
    for rec in lines(out):
        # REV:PATH \0 LINE \0 TEXT
        parts = rec.split("\0", 2)
        if len(parts) != 3:
            continue
        path = parts[0][len(rev) + 1:]
        scan.text("%s:%s" % (scan.safe(path), parts[1]), parts[2])


def scan_pre_push(scan: Scan, remote: str, refs: str) -> None:
    for raw in lines(refs):
        f = raw.split()
        if len(f) != 4:
            continue
        lref, lsha, rref, rsha = f
        if ZERO.match(lsha):
            continue  # deleting a ref
        name = re.sub(r"^refs/(heads|tags)/", "", rref)
        scan.text("ref name %s" % scan.safe(name, "<ref>"), name)
        if git("cat-file", "-t", lsha).strip() == "tag":
            for i, line in enumerate(lines(git("cat-file", "-p", lsha)), 1):
                scan.text("tag %s line %d" % (lsha[:10], i), line)
        known = not ZERO.match(rsha) and subprocess.run(
            ["git", "cat-file", "-e", rsha + "^{commit}"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if known:
            scan_range(scan, ["%s..%s" % (rsha, lsha)])
        else:
            # Commits the remote may lack: those on none of its tracking refs.
            # Pushed to a URL, git passes the URL, which names no tracking
            # refs, so every remote's count as known.
            named = remote in git("remote").split()
            scan_range(scan, [lsha, "--not", "--remotes=" + remote if named else "--remotes"])


USAGE = ("usage: pii-check.sh [--require-denylist] range REV-LIST-ARGS... | tree [REV] |"
         " text LABEL | pre-push REMOTE")


def main(argv: list[str]) -> int:
    args = list(argv)
    require = False
    if args and args[0] == "--require-denylist":
        require = True
        args.pop(0)
    if not args or args[0] not in ("range", "tree", "text", "pre-push"):
        print(USAGE, file=sys.stderr)
        return 2
    mode, rest = args[0], args[1:]
    if (mode in ("text", "pre-push") and len(rest) != 1) or (mode == "tree" and len(rest) > 1) \
            or (mode == "range" and not rest):
        print(USAGE, file=sys.stderr)
        return 2
    deny = load_denylist()
    if not deny:
        if require:
            print("pii-check: no denylist ($PII_DENYLIST is empty): refusing to pass",
                  file=sys.stderr)
            return 1
        print("pii-check: no denylist (~/.config/wiki-tools/pii-denylist.txt or"
              " $PII_DENYLIST_FILE): general patterns only", file=sys.stderr)
    scan = Scan(deny)
    try:
        if mode == "range":
            scan_range(scan, rest)
        elif mode == "tree":
            scan_tree(scan, rest[0] if rest else "HEAD")
        elif mode == "text":
            for i, line in enumerate(lines(sys.stdin.read()), 1):
                scan.text("%s line %d" % (rest[0], i), line)
        else:
            scan_pre_push(scan, rest[0], sys.stdin.read())
    except GitError as e:
        print("pii-check: %s" % e, file=sys.stderr)
        return 2
    if scan.count:
        print("pii-check: %d finding(s). Remove them (amend or rebase) before pushing;"
              " the text isn't shown, so it isn't published again." % scan.count,
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
