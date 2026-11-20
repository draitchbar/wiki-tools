"""lint.py: deterministic health checks for a raw/wiki-layout wiki.

The body of lint.sh, which is its launcher (docs/adr.md, 4). Same checks, report and exit codes as
the bash version, byte for byte (checked by recording every call of the
test suite and the edge cases in tests/fixtures/lint/ on both), except
the differences the plan lists:

- day counts are calendar days (bash divided epoch seconds by 86400, so the
  result moved with the time zone and the clock change);
- one CR is stripped from each frontmatter line (a CRLF page's dates read
  as dates, not as "2026-10-01\\r is not a YYYY-MM-DD date").

  lint.py [--plugin DIR]

Run it from inside a wiki. Read-only: prints a Markdown findings report to
stdout and writes nothing. Exit 1: not in a git repo or a bad
WIKI_LINT_TODAY; exit 3: an internal error. wiki_check.py calls report()
in-process.

Checks (inspired by kfchou/wiki-skills' lint-mechanical.py, adapted to the
schema in schema/wiki-layout.md):
  ERROR  missing frontmatter, missing required fields, broken [[links]]
         (not in log.md), removed or changed lines in log.md (uncommitted
         or in the last 30 days of commits; a commit's error names the
         date it ages out of that window)
  WARN   orphan pages, pages missing from index.md, pages without sources,
         bad or inconsistent dates, stale pages, index.md rows whose
         Updated date differs from the page's updated: (only in tables of
         the one format /wiki:init writes: header `| Page | Summary |
         Updated |`, Page a [[link]], Updated a YYYY-MM-DD date; any other
         table or row is skipped)
         open questions (open-questions.md) raised more than 30 days ago,
         ^[open: <id>] markers below wiki/ (not in log.md) with no question
         and questions no file marks, a malformed open-questions.md
         (heading not an ID, duplicate ID, bad kind or raised, pages links
         to no page, merge-conflict lines)
  INFO   pages without status_as_of whose type carries it (its template,
         templates/<type>.md, has a status_as_of field), `sources:`
         entries that match no source of the wiki (only once it has
         .claude/sources/instances/)
A status_as_of older than 90 days is a warning on any page but one with
as_of: (a dated analysis, historical by design: no stale findings).

Environment (for tests): WIKI_LINT_TODAY=YYYY-MM-DD overrides today's date.

Rules kept from the bash version, which its findings depend on:
- pages are the regular files *.md below wiki/ (symlinks skipped, hidden
  ones included), in byte order of their path; index.md and log.md at the
  top are not pages;
- link targets and slugs are lowercased in ASCII only (tr), and a target is
  [[x]] up to the first | or #, after the last /, trimmed;
- page frontmatter is lint's own reading (not contract.py's): any
  `key:` line of [A-Za-z_] sets the current key, one quote is stripped at
  each end of a value, an inline `sources: a, b` counts its commas;
- a double-quoted `sources:` item has its \\" and \\\\ unescaped before the
  prefix check and the INFO line (bash printed them as written);
- a page body is every line after the second line that starts with ---,
  except lines that start with ---;
- the log.md window is 30 days of the real clock, not WIKI_LINT_TODAY.
"""

import collections
import datetime
import os
import re
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contract  # noqa: E402
import sourcelib  # noqa: E402
from hookjson import lower  # noqa: E402
from sourcelib import git, read_text  # noqa: E402

STALE_DAYS = 90
QUESTION_DAYS = 30
LOG_DAYS = 30
REQUIRED = ("title", "type", "sources", "created", "updated")
# Words that suggest a claim goes out of date (English and Danish).
STALE_WORDS = re.compile("pending|awaiting|not yet|currently|latest|expected|upcoming|"
                         "afventer|venter på|endnu ikke", re.IGNORECASE)

_SP = " \t\n\v\f\r"  # [[:space:]] as awk and sed take it here
_FENCE = re.compile(r"---[ \t\n\v\f\r]*")
_KEY = re.compile(r"[A-Za-z_]+:", re.ASCII)
_VAL_HEAD = re.compile(r"[^:]*:[ \t\n\v\f\r]*")
_VAL_QUOTES = re.compile(r"^[\"']|[\"'][ \t\n\v\f\r]*$")
_DQ_ESC = re.compile(r'\\(["\\])')  # \" and \\ in a double-quoted YAML string
_SRC_ITEM = re.compile(r"[ \t\n\v\f\r]+-[ \t\n\v\f\r]*[^ \t\n\v\f\r]")
_LINK = re.compile(r"\[\[[^\]\n]+\]\]")
_LINK_CUT = re.compile(r"[|#].*", re.DOTALL)
_DIR_CUT = re.compile(r".*/", re.DOTALL)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_LOG_OLD = re.compile(r"--- (a/|/dev/null)")
_SKIP_SRC = ("raw/", "raw:", "Local file: raw/", "local file: raw/", "User statement",
             "http://", "https://")


class Die(Exception):
    """lint.sh's die: `lint: <message>` on stderr, exit 1."""


def _key(s):
    return contract._bytes_key(s)


def _word_key(s):
    """sort -u in a UTF-8 locale for the stale words: case-blind first,
    then lower case before upper ("venter på" before "venter pÅ")."""
    return (s.lower(), s.swapcase())


def _lines(text):
    """awk's records: split on newline, no empty record after a final one."""
    ls = text.split("\n")
    if ls[-1] == "":
        ls.pop()
    return ls


def pages_of(wiki):
    """Regular *.md files below wiki/ (find -type f), relative, byte order."""
    found = []

    def walk(d, rel):
        try:
            entries = list(os.scandir(d))
        except OSError:
            return
        for e in entries:
            r = rel + e.name
            try:
                if e.is_dir(follow_symlinks=False):
                    walk(e.path, r + "/")
                elif e.is_file(follow_symlinks=False) and e.name.endswith(".md"):
                    found.append(r)
            except OSError:
                continue

    walk(wiki, "")
    return sorted(found, key=_key)


def slug_of(p):
    b = p.rsplit("/", 1)[-1]
    if b.endswith(".md"):
        b = b[:-3]
    return lower(b)


def status_types(root):
    """Page types whose template's frontmatter has status_as_of."""
    d = root + "/templates"
    try:
        names = os.listdir(d)
    except OSError:
        return set()
    res = set()
    for n in names:
        if n.startswith(".") or not n.endswith(".md") or not os.path.isfile(d + "/" + n):
            continue
        for i, ln in enumerate(_lines(read_text(d + "/" + n).replace("\r", ""))):
            if (i == 0 and ln != "---") or (i > 0 and ln == "---"):
                break
            if ln.startswith("status_as_of:"):
                res.add(n[:-3])
                break
    return res


def _val(s):
    s = s[_VAL_HEAD.match(s).end():]
    return _VAL_QUOTES.sub("", s)


def facts(text):
    """has_fm, the frontmatter values and the number of sources (-1: no
    sources key), as lint.sh's awk read them; one CR stripped per line."""
    f = {"title": "", "type": "", "created": "", "updated": "", "status_as_of": "", "as_of": ""}
    ls = [ln[:-1] if ln.endswith("\r") else ln for ln in _lines(text)]
    if not ls or not _FENCE.fullmatch(ls[0]):
        return False, f, -1
    nsrc, seen, cur = 0, False, None
    for ln in ls[1:]:
        if _FENCE.fullmatch(ln):
            break
        if _KEY.match(ln):
            key = ln.split(":", 1)[0]
            cur = key
            if key in f:
                f[key] = _val(ln)
            elif key == "sources":
                v, seen = _val(ln), True
                if v not in ("", "[]"):
                    nsrc += v.count(",") + 1
        elif cur == "sources" and _SRC_ITEM.match(ln):
            nsrc += 1
    return True, f, (nsrc if seen else -1)


def body_lines(text):
    """awk 'BEGIN{n=0} /^---/{n++; next} n>=2'."""
    n, res = 0, []
    for ln in _lines(text):
        if ln.startswith("---"):
            n += 1
        elif n >= 2:
            res.append(ln)
    return res


_IDX_CELL = re.compile(r"(?<!\\)\|")
_IDX_LINK = re.compile(r"\[\[[^\]\n]+\]\]")


def _cells(ln):
    """The cells of a table row (| split, \\| kept), or None."""
    ln = ln.strip(_SP)
    if not (ln.startswith("|") and ln.endswith("|")) or len(ln) < 2:
        return None
    return [c.strip(_SP) for c in _IDX_CELL.split(ln[1:-1])]


def index_rows(text):
    """(link target, Updated date) of each row of index.md's
    `| Page | Summary | Updated |` tables whose Page cell is one [[link]]
    and whose Updated cell is a YYYY-MM-DD date. Other rows are skipped."""
    res, in_table = [], False
    for ln in _lines(text):
        cells = _cells(ln)
        if cells is None:
            in_table = False
        elif cells == ["Page", "Summary", "Updated"]:
            in_table = True
        elif in_table and len(cells) == 3 and _IDX_LINK.fullmatch(cells[0]) \
                and _DATE.fullmatch(cells[2]):
            t = links_of(cells[0])
            if t:
                res.append((t[0], cells[2]))
    return res


def links_of(text):
    """The link targets of a page, in order (duplicates kept)."""
    res = []
    for ln in text.split("\n"):
        for m in _LINK.finditer(ln):
            t = _LINK_CUT.sub("", m.group(0)[2:-2], count=1)
            t = _DIR_CUT.sub("", t, count=1).strip(_SP)
            t = lower(t)
            if t:
                res.append(t)
    return res


def log_removed(text):
    """Removed lines in a diff: ^- but not ^--- a/ or ^--- /dev/null."""
    return sum(1 for ln in _lines(text) if ln.startswith("-") and not _LOG_OLD.match(ln))


LogEdit = collections.namedtuple("LogEdit", "hash when lines ages_out")


def log_history(root):
    """The commits of the last LOG_DAYS days that remove or rewrite lines of
    wiki/log.md, as LogEdits (when: "date, subject"; ages_out: the commit
    date plus LOG_DAYS). Restoring the lines can't clear these: the commit
    stays in the window until then."""
    _, d = git(root, "log", "--no-merges", "--since=%d days ago" % LOG_DAYS, "--no-color", "-U0",
               "--date=short", "--format=%x01%h%x02%cd%x02%ad, %s", "-p", "--", "wiki/log.md")
    res = []
    for chunk in ("\n" + d).split("\n\x01")[1:]:
        head, _, diff = chunk.partition("\n")
        h, _, rest = head.partition("\x02")
        cd, _, when = rest.partition("\x02")
        n = log_removed(diff)
        if n:
            out = (parse_today(cd) + datetime.timedelta(days=LOG_DAYS)).isoformat()
            res.append(LogEdit(h, when, n, out))
    return res


def parse_today(s):
    if not _DATE.fullmatch(s):
        raise ValueError
    return datetime.date(int(s[:4]), int(s[5:7]), int(s[8:]))


def days_since(v, today):
    """Calendar days from v (YYYY-MM-DD) to today, or None."""
    try:
        return (today - parse_today(v)).days
    except ValueError:
        return None


def report(root, plugin, history=None):
    """lint.sh's report for the wiki at root: (text, number of errors).
    history: log_history(root), when the caller already has it.
    Raises Die for a bad WIKI_LINT_TODAY."""
    wiki = root + "/wiki"
    today_s = os.environ.get("WIKI_LINT_TODAY") or datetime.date.today().isoformat()
    try:
        today = parse_today(today_s)
    except ValueError:
        raise Die("bad WIKI_LINT_TODAY '%s'" % today_s) from None
    stypes = status_types(root)

    all_ = pages_of(wiki)
    pages = [p for p in all_ if p not in ("index.md", "log.md")]
    texts = {p: read_text(wiki + "/" + p) for p in all_}
    slugs = [(slug_of(p), p) for p in all_]
    links = [(p, t) for p in all_ for t in links_of(texts[p])]
    known = {s for s, _ in slugs}

    e_nofm, e_fields, e_broken, e_log = [], [], [], []
    w_orphan, w_noindex, w_nosrc, w_dates, w_stale = [], [], [], [], []
    w_idxdate = []
    updated = {}
    i_status, i_srcprefix = [], []

    for p in pages:
        hasfm, f, nsrc = facts(texts[p])
        if not hasfm:
            e_nofm.append("- `%s`: no YAML frontmatter" % p)
            continue
        missing = [k for k in REQUIRED if (nsrc == -1 if k == "sources" else not f[k])]
        if missing:
            e_fields.append("- `%s`: missing %s" % (p, " ".join(missing)))
        if nsrc == 0:
            w_nosrc.append("- `%s`: `sources:` is empty; every claim is uncited" % p)
        for d in ("created", "updated", "status_as_of", "as_of"):
            v = f[d]
            if not v:
                continue
            age = days_since(v, today)
            if age is None:
                w_dates.append("- `%s`: `%s: %s` is not a YYYY-MM-DD date" % (p, d, v))
            elif age < 0:
                w_dates.append("- `%s`: `%s: %s` is in the future" % (p, d, v))
        cr, up = f["created"], f["updated"]
        updated[p] = up
        if cr and up and _key(up) < _key(cr):
            w_dates.append("- `%s`: updated (%s) is before created (%s)" % (p, up, cr))
        # A page with as_of: is a dated analysis, historical by design.
        age = days_since(up, today) if up else None
        if not f["as_of"] and age is not None and age > STALE_DAYS:
            hits = set()
            for ln in body_lines(texts[p]):
                hits.update(lower(m.group(0)) for m in STALE_WORDS.finditer(ln))
            if hits:
                w_stale.append("- `%s`: updated %d days ago and still says: %s"
                               % (p, age, ",".join(sorted(hits, key=_word_key))))
        st = f["status_as_of"]
        if st:
            age = days_since(st, today)
            if not f["as_of"] and age is not None and age > STALE_DAYS:
                w_stale.append("- `%s` (%s): status_as_of %s is %d days old" % (p, f["type"], st, age))
        elif f["type"] and f["type"] in stypes:
            i_status.append("- `%s` (%s): no `status_as_of`" % (p, f["type"]))

    # Citations that match no source: an entry must start with a configured
    # type's cite_prefix, a manual key ("web: ..."), "raw/" or "raw:",
    # "User statement" or a URL.
    keys = contract.instances(root)
    if keys:
        pre = set(sourcelib.manual_keys(root))
        idir = contract.instance_dir(root)
        for k in keys:
            try:
                c = contract.contract(root, contract.field("%s/%s.md" % (idir, k), "type"), plugin)
            except contract.ContractError:
                continue
            pre.add(contract.field(c, "cite_prefix"))
        prefixes = [lower(x) for x in sorted(pre, key=_key) if x]
        for p in pages:
            for s in contract.list_(wiki + "/" + p, "sources"):
                dq = len(s) > 1 and s[0] == s[-1] == '"'
                s = re.sub(r"[\"']$", "", re.sub(r"^[\"']", "", s))
                if dq:
                    s = _DQ_ESC.sub(r"\1", s)
                if s.startswith(_SKIP_SRC):
                    continue
                ls = lower(s)
                if not any(ls.startswith(x + ":") or ls.startswith(x + " ") for x in prefixes):
                    i_srcprefix.append("- `%s`: source `%s` matches no source of this wiki" % (p, s))

    # Broken links (grouped by target, with how many pages reference it).
    # Links in log.md are skipped: entries are never edited, so after a
    # rename old entries keep the old name.
    pairs = sorted({"%s\t%s" % (t, src) for src, t in set(links)
                    if src != "log.md" and t not in known}, key=_key)
    by = {}
    for ln in pairs:
        t, src = ln.split("\t", 1)
        by.setdefault(t, []).append(src)
    for t in sorted(by, key=_key):
        e_broken.append("- `[[%s]]` (no such page) linked from %s"
                        % (t, ", ".join("`%s`" % s for s in by[t])))

    # Orphans: no inbound link from any other page (index.md and log.md don't
    # count). Not in index: page slug never linked from index.md.
    for s, p in slugs:
        if p in ("index.md", "log.md"):
            continue
        if not any(t == s and src != p and src not in ("index.md", "log.md") for src, t in links):
            w_orphan.append("- `%s`: no inbound links from other pages" % p)
        if not any(src == "index.md" and t == s for src, t in links):
            w_noindex.append("- `%s`: not listed in index.md" % p)

    # index.md's Updated column mirrors each page's updated: (the fixed
    # /wiki:init table format only; a slug shared by two pages is skipped).
    by_slug = {}
    for s, p in slugs:
        by_slug.setdefault(s, []).append(p)
    for t, d in index_rows(texts.get("index.md", "")):
        ps = by_slug.get(t, [])
        if len(ps) != 1 or ps[0] in ("index.md", "log.md"):
            continue
        up = updated.get(ps[0], "")
        if days_since(up, today) is not None and up != d:
            w_idxdate.append("- `%s`: index.md says Updated %s, the page says `updated: %s`"
                             % (ps[0], d, up))

    # Deferred questions (open-questions.md, sourcelib.open_questions) and
    # their ^[open: <id>] markers in wiki/ (log.md aside).
    w_qold, w_qmark, w_qbad = questions(root, all_, texts, known, today)

    # log.md is append-only: no removed or changed lines, neither uncommitted
    # nor in the commits of the last LOG_DAYS days.
    _, d = git(root, "diff", "--no-color", "-U0", "HEAD", "--", "wiki/log.md")
    n = log_removed(d)
    if n:
        e_log.append("- uncommitted changes remove or rewrite %d line(s) of existing entries" % n)
    for c in log_history(root) if history is None else history:
        e_log.append("- commit %s (%s) removes or rewrites %d line(s) (ages out on %s)"
                     % (c.hash, c.when, c.lines, c.ages_out))

    n_err = len(e_nofm) + len(e_fields) + len(e_broken) + len(e_log)
    n_warn = (len(w_orphan) + len(w_noindex) + len(w_idxdate) + len(w_nosrc) + len(w_dates)
              + len(w_stale) + len(w_qold) + len(w_qmark) + len(w_qbad))
    n_info = len(i_status) + len(i_srcprefix)
    o = ["## Mechanical checks: %s (%s)" % (root.rstrip("/").rsplit("/", 1)[-1], today_s), "",
         "Pages: %d. Errors: %d. Warnings: %d. Info: %d." % (len(pages), n_err, n_warn, n_info)]
    for lines, title in ((e_nofm, "ERROR: missing frontmatter"),
                         (e_fields, "ERROR: missing required fields"),
                         (e_broken, "ERROR: broken links"),
                         (e_log, "ERROR: wiki/log.md changed (append-only)"),
                         (w_orphan, "WARN: orphan pages"),
                         (w_noindex, "WARN: not in index.md"),
                         (w_idxdate, "WARN: index.md Updated date differs from the page"),
                         (w_nosrc, "WARN: no sources"),
                         (w_dates, "WARN: bad dates"),
                         (w_stale, "WARN: possibly stale (not updated in %d+ days)" % STALE_DAYS),
                         (w_qold, "WARN: open questions older than %d days" % QUESTION_DAYS),
                         (w_qmark, "WARN: open question markers that don't match"),
                         (w_qbad, "WARN: open-questions.md malformed"),
                         (i_status, "INFO: missing status_as_of"),
                         (i_srcprefix, "INFO: citations with no matching source")):
        if lines:
            o += ["", "### %s (%d)" % (title, len(lines)), ""] + lines

    # Clusters for the judgement pass: one per top-level folder of wiki/.
    cl = {}
    for p in pages:
        k = p.split("/", 1)[0] if "/" in p else "(top level)"
        cl.setdefault(k, []).append("`%s`" % p)
    o += ["", "## Clusters for contradiction checks", ""]
    o += sorted(("- **%s**: %s" % (k, ", ".join(v)) for k, v in cl.items()), key=_key)
    return "\n".join(o), n_err


def questions(root, all_, texts, known, today):
    """The three open-question sections: questions raised more than
    QUESTION_DAYS ago, markers and questions that don't match, and a
    malformed open-questions.md."""
    old, mark, bad = [], [], []
    r = sourcelib.read_questions(root)
    qs, conflict = r if r else ([], False)
    marks = sorted({(p, m.group(1)) for p in all_ if p != "log.md"
                    for m in sourcelib.MARKER.finditer(texts[p])}, key=lambda x: (_key(x[0]), x[1]))
    ids = [q.id for q in qs]
    for p, i in marks:
        if i not in ids:
            mark.append("- `%s`: marker %s has no question in %s" % (p, i, sourcelib.QUESTIONS))
    marked = {i for _, i in marks}
    if conflict:
        bad.append("- merge conflict lines (<<<<<<<, =======, >>>>>>>)")
    seen = set()
    for q in qs:
        if q.raised_date is not None:
            age = (today - q.raised_date).days
            if age > QUESTION_DAYS:
                old.append("- `%s` raised %s (%d days ago)" % (q.id, q.raised_date.isoformat(), age))
        if q.valid and q.id not in marked:
            mark.append("- `%s`: no page carries its marker" % q.id)
        probs = []
        if not q.valid:
            probs.append("not a question ID (q-YYYY-MM-DD-<slug>)")
        if q.id in seen:
            probs.append("duplicate ID")
        seen.add(q.id)
        if q.kind not in sourcelib.KINDS:
            probs.append("kind `%s` is not one of %s" % (q.kind, ", ".join(sourcelib.KINDS))
                         if q.kind else "no kind")
        if q.raised_date is None:
            probs.append("raised `%s` has no YYYY-MM-DD date" % q.raised if q.raised else "no raised")
        for t in links_of(q.pages):
            if t not in known:
                probs.append("pages links to [[%s]], no such page" % t)
        if probs:
            bad.append("- `%s`: %s" % (q.id, "; ".join(probs)))
    return old, mark, bad


def wiki_root():
    top = sourcelib.toplevel(os.getcwd())
    if not top:
        raise Die("not inside a git repo; run from a wiki.")
    return top


def _main(argv):
    plugin = contract.PLUGIN
    if argv[:1] == ["--plugin"] and len(argv) > 1:
        plugin, argv = sourcelib.native(argv[1]), argv[2:]
    root = wiki_root()
    if not os.path.isdir(root + "/wiki"):
        sourcelib.out("lint: no wiki/ folder in %s; this wiki does not use the raw/wiki layout." % root)
        return 0
    text, _ = report(root, plugin)
    sourcelib.out(text)
    return 0


def main(argv):
    try:
        rc = _main(argv)
    except Die as e:
        sourcelib.err("lint: %s" % e)
        rc = 1
    except sourcelib.GitBashPath as e:
        sourcelib.err("lint: %s" % e)
        rc = 3
    except Exception as e:  # an internal error is never a finding
        sourcelib.err("lint: internal error: %s: %s" % (type(e).__name__, e))
        rc = 3
    sys.stdout.flush()
    sys.stdout.buffer.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
