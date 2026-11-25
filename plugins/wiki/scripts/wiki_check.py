"""wiki_check.py: read-only setup check for a raw/wiki-layout wiki.

The body of wiki-check.sh, which is its launcher (docs/adr.md, 4). Same checks, report and exit
codes as the bash version, byte for byte (checked by recording every call
of the test suite on both), except:

- lint runs in-process (lint.report), not as a second script;
- lint's errors for past commits that rewrote wiki/log.md don't count as a
  failure, only as an INFO line with the date the last ages out;
- the source permission rules are checked by sourcelib.settings_check
  directly, so a failure there is an internal error (exit 3), not "all
  present";
- the Python check names the interpreter running this check (bash probed
  one like py-launch.sh does). Without Python the launcher prints its own
  message and exits 1 instead of a report;
- two checks the bash version never had: Markdown files outside the
  layout (INFO), and, outside a git repo, a pointer to /wiki:init when
  the folder's settings enable the plugin.

  wiki_check.py --plugin DIR

--plugin is the plugin folder as bash spells it (the launcher passes it):
messages use that spelling, files are opened through its native form. Run
it from inside a wiki. Prints a Markdown pass/fail list with a fix for
each failure and writes nothing. Makes no calls to any source; sources are
checked at their first ingest. Exit 0 when every check passes, 1 when any
check fails or outside a git repo, 3 on an internal error.

Environment (for tests): WIKI_CHECK_TEMPLATE overrides the settings
template path; CLAUDE_CONFIG_DIR (as in Claude Code) moves ~/.claude.
"""

from __future__ import annotations

import datetime
import os
import re
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contract  # noqa: E402
import lint  # noqa: E402
import sourcelib  # noqa: E402
from sourcelib import git, read_text  # noqa: E402

# Names for the annotations only (never evaluated): nothing to import at run time.
TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeVarTuple

    Ts = TypeVarTuple("Ts")

_SCHEMA_IMPORT = re.compile(r"@.*/schema/wiki-(conventions|layout)\.md")
_TEMPLATE_RULE = re.compile(r'"(mcp__[A-Za-z_]+|Bash\([^"]*\)|Read\([^"]*\))"')
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_SPACE = re.compile(r"[ \t\n\v\f\r]")
_AWK_FS = re.compile(r"[ \t\n]+")
_ENABLED = '"wiki@wiki-tools":true'
# Where a wiki's Markdown lives (schema/wiki-layout.md), and the root files
# that aren't pages.
_LAYOUT_DIRS = ("raw", "wiki", "outputs", "templates", "work")
_ROOT_MD = ("CLAUDE.md", "README.md", "open-questions.md")


class Die(Exception):
    """`wiki-check: <message>` on stderr, exit 1."""


def _read_lines(path: str) -> list[str]:
    """`while IFS= read -r line`: newline-terminated lines only."""
    return read_text(path).split("\n")[:-1]


def _grep_lines(path: str) -> list[str]:
    """The lines grep sees: the last one even without a newline."""
    return lint._lines(read_text(path))


def _ok_date(v: str) -> bool:
    if not _DATE.fullmatch(v):
        return False
    try:
        datetime.date(int(v[:4]), int(v[5:7]), int(v[8:]))
    except ValueError:
        return False
    return True


def _plugin_enabled(settings: str) -> bool:
    """True if the settings file at this path enables the wiki plugin
    (False if it can't be read)."""
    return _ENABLED in _SPACE.sub("", read_text(settings))


class Check:
    plugin_shown: str
    plugin: str
    here: str
    root: str
    fails: int
    out: list[str]

    def __init__(self, plugin_shown: str) -> None:
        self.plugin_shown = plugin_shown
        self.plugin = sourcelib.native(plugin_shown)
        self.here = plugin_shown + "/scripts"           # as bash spells it
        top = sourcelib.toplevel(".")
        if not top:
            if _plugin_enabled(".claude/settings.json"):
                raise Die("not inside a git repo, but `.claude/settings.json` here enables the "
                          "wiki plugin: this wiki isn't initialised yet. Run (or finish) "
                          "`/wiki:init`.")
            raise Die("not inside a git repo; run from a wiki.")
        self.root = top
        self.fails = 0
        self.out = []

    def ok(self, m: str) -> None:
        self.out.append("- PASS %s" % m)

    def fail(self, m: str, fix: str) -> None:
        self.out.append("- FAIL %s. Fix: %s" % (m, fix))
        self.fails += 1

    def info(self, m: str) -> None:
        self.out.append("- INFO %s" % m)

    def source_rules(self, root: str, miss_l: list[tuple[str, str]],
                     blocked_l: list[tuple[str, str]]) -> None:
        """The source permission rules' result (settings_check)."""
        miss = "".join(' "%s"' % r for _, r in miss_l)
        blocked = "".join(' "%s" (deny "%s")' % m for m in blocked_l)
        if not miss:
            self.ok("all permission rules of the sources' types are present")
        else:
            pairs = sourcelib.wiki_pairs(root, self.plugin)
            tail = ("; " + sourcelib.CLOUD_NOTE
                    if any(sourcelib.is_cloud(r, pairs) for _, r in miss_l) else "")
            self.fail("source permission rules missing from .claude/settings.json:%s" % miss,
                      "add them as `sources.sh settings` prints (allow: read and bookkeeping tools, "
                      "deny: forbidden tools)" + tail)
        if blocked:
            self.fail("source permission rules blocked by a deny rule in .claude/settings.json:%s"
                      % blocked, "remove or narrow those deny rules (deny wins over allow)")

    def tracked(self, f: str) -> bool:
        rc, _ = git(self.root, "ls-files", "--error-unmatch", "--", f)
        return rc == 0

    def changed(self, f: str) -> bool:
        _, o = git(self.root, "status", "--porcelain", "--", f)
        return o != ""

    def errs(self, fn: Callable[[*Ts], bool], *args: *Ts) -> tuple[bool, str]:
        """`errs=$(fn ... 2>&1)` with "$root/" removed, lines joined by ;."""
        ok, lines = sourcelib.quietly(fn, *args)
        text = "\n".join(lines).rstrip("\n").replace(self.root + "/", "")
        return ok, ";".join(text.split("\n")) if text else ""

    def run(self) -> int:
        root = self.root
        instances = contract.instances(root)

        # 1. Layout.
        for d in ("raw", "wiki", "outputs", "templates"):
            if os.path.isdir("%s/%s" % (root, d)):
                self.ok("folder `%s/` exists" % d)
            else:
                self.fail("folder `%s/` is missing" % d, "re-run /wiki:init, or create it")
        for f in ("raw/sync-log.md", "wiki/index.md", "wiki/log.md", "CLAUDE.md", ".gitignore"):
            if os.path.isfile("%s/%s" % (root, f)):
                self.ok("`%s` exists" % f)
            else:
                self.fail("`%s` is missing" % f, "re-run /wiki:init, or create it as described "
                          "in the wiki plugin's schema/wiki-layout.md")
        n: int | None  # also lint's error count below, None if it didn't run
        try:
            n = sum(1 for e in os.listdir(root + "/templates") if e.endswith(".md"))
        except OSError:
            n = 0
        if n > 0:
            self.ok("%d page template(s) in `templates/`" % n)
        else:
            self.fail("no page templates in `templates/`",
                      "add templates/<type>.md for each page type named in CLAUDE.md")

        # 2. The plugin loads the shared schema at session start; CLAUDE.md
        # must not import it by path any more.
        cm = root + "/CLAUDE.md"
        if os.path.isfile(cm):
            old = [ln.replace("\r", "") for ln in _grep_lines(cm) if _SCHEMA_IMPORT.match(ln)]
            if not old:
                self.ok("CLAUDE.md has no schema imports (the plugin loads the schema)")
            else:
                self.fail("CLAUDE.md still imports the schema by path: %s" % " ".join(old),
                          "remove these lines; the wiki plugin loads the schema at session start")

        # 3. Sync log: every last_checked line is a date or "never".
        log = root + "/raw/sync-log.md"
        if os.path.isfile(log):
            keys = 0
            for line in _read_lines(log):
                if line.endswith("\r"):
                    line = line[:-1]
                if not line.startswith("last_checked_") or ":" not in line:
                    continue
                keys += 1
                key, _, val = line.partition(":")
                val = _SPACE.sub("", val)
                if val != "never" and not _ok_date(val):
                    self.fail("`%s: %s` in raw/sync-log.md is neither a YYYY-MM-DD date nor "
                              "`never`" % (key, val), "correct the value")
            lines = _grep_lines(log)
            if not any(ln.startswith("last_checked_raw:") for ln in lines):
                self.fail("raw/sync-log.md has no `last_checked_raw` line (raw/ is always a "
                          "source)", "add `last_checked_raw: <date of the newest raw row in the "
                          "history, or never>`")
            for k in instances:
                if not any(ln.startswith("last_checked_%s:" % k) for ln in lines):
                    self.fail("source `%s` has no `last_checked_%s` line in raw/sync-log.md"
                              % (k, k), "add `last_checked_%s: never`" % k)
            if keys > 0:
                self.ok("raw/sync-log.md has %d source line(s)" % keys)
            else:
                self.fail("raw/sync-log.md has no `last_checked_<source>:` lines",
                          "add one line per source, value `never`")

        # 4. .gitignore.
        gi = root + "/.gitignore"
        if os.path.isfile(gi):
            have = {ln[:-1] if ln.endswith("\r") else ln for ln in _grep_lines(gi)}
            pats = [".obsidian/", ".claude/*", "!.claude/settings.json"]
            if instances:
                pats.append("!.claude/sources/")
            for pat in pats:
                if pat in have:
                    self.ok("`.gitignore` has `%s`" % pat)
                else:
                    self.fail("`.gitignore` lacks `%s`" % pat, "add the line `%s`" % pat)

        # 5. Project settings: plugin enabled, permissions from the template,
        # committed.
        st = root + "/.claude/settings.json"
        if not os.path.isfile(st):
            self.fail("`.claude/settings.json` is missing",
                      "paste the settings shown by /wiki:init, then commit it")
        else:
            text = read_text(st)
            if _ENABLED in _SPACE.sub("", text):
                self.ok("plugin `wiki@wiki-tools` is enabled")
            else:
                self.fail("plugin `wiki@wiki-tools` is not enabled", "run `claude plugin install "
                          "wiki@wiki-tools --scope project` in the wiki")
            tshown = os.environ.get("WIKI_CHECK_TEMPLATE") or \
                self.here + "/../templates/project-settings.json"
            tpath = sourcelib.native(tshown)
            if os.path.isfile(tpath):
                missing = "".join(" " + m.group(0) for ln in _grep_lines(tpath)
                                  for m in _TEMPLATE_RULE.finditer(ln)
                                  if m.group(0) not in text)
                if not missing:
                    self.ok("all permission rules from the template are present")
                else:
                    self.fail("permission rules missing from .claude/settings.json:%s" % missing,
                              "paste the settings shown by /wiki:init")
            else:
                self.info("settings template not found at %s; permissions not compared" % tshown)
            _, e = sourcelib.settings_rules(text)
            if e is not None:
                self.fail("`.claude/settings.json` is not valid JSON: %s" % e,
                          "fix it by hand (`sources.sh check-settings` shows where)")
            if instances:
                # A broader Read/Edit rule (e.g. the contract's own form)
                # covers a per-instance cache rule too.
                try:
                    miss_l, blocked_l = sourcelib.settings_check(root, self.plugin, st)
                except sourcelib.ConnectorsError as e:
                    self.fail("source permission rules can't be checked: %s" % e,
                              "update or reinstall the wiki plugin (plugins/wiki/sources/connectors.md)")
                except sourcelib.BindingMixError as e:
                    self.fail(str(e), "bind the instance again locally with /wiki:bind-reader %s" % e.key)
                else:
                    self.source_rules(root, miss_l, blocked_l)
            f = ".claude/settings.json"
            if self.tracked(f) and self.changed(f):
                self.fail("`%s` has uncommitted changes" % f, "review them, then `git add -- "
                          "%s && git commit` (you, not Claude)" % f)
            elif self.tracked(f):
                self.ok("`%s` is committed" % f)
            else:
                self.fail("`%s` isn't committed" % f, "`git add -- %s && git commit` "
                          "(you, not Claude)" % f)

        # 6. Sources in .claude/sources/: every instance valid, available,
        # committed.
        if not instances:
            self.info("no sources besides `raw/` (no files in `.claude/sources/instances/`)")
        plat = sourcelib_platform()
        for k in instances:
            f = ".claude/sources/instances/%s.md" % k
            t = contract.field("%s/%s" % (root, f), "type")
            ok, errs = self.errs(sourcelib.validate_instance, root, k, self.plugin)
            if ok:
                self.ok("source `%s` (type %s) is valid" % (k, t))
                c = contract.contract(root, t, self.plugin)
                plats = contract.list_(c, "platforms")
                if plat not in plats:
                    self.info("source `%s` (type %s) isn't available on %s; it supports %s"
                              % (k, t, plat, " ".join(plats)))
            else:
                self.fail("source `%s` doesn't validate: %s" % (k, errs),
                          "correct `%s` (you, not Claude)" % f)
            if self.tracked(f) and self.changed(f):
                self.fail("`%s` has uncommitted changes" % f, "review them, then `git add -- "
                          "%s && git commit` (you, not Claude)" % f)
            elif self.tracked(f):
                self.ok("`%s` is committed" % f)
            else:
                self.fail("`%s` isn't committed" % f, "`git add -- %s && git commit` "
                          "(you, not Claude)" % f)
        td = root + "/.claude/sources/types"
        try:
            types = sorted((e for e in os.listdir(td) if not e.startswith(".")),
                           key=contract._bytes_key)
        except OSError:
            types = []
        for t in types:
            c = "%s/%s/SOURCE.md" % (td, t)
            if not os.path.isfile(c):
                continue
            ok, errs = self.errs(sourcelib.validate_contract, c)
            if ok:
                self.ok("local source type `%s` is valid" % t)
            else:
                self.fail("local source type `%s` doesn't validate: %s" % (t, errs),
                          "correct `.claude/sources/types/%s/` (you, not Claude)" % t)
            for s in ["SOURCE.md"] + sourcelib.words(contract.list_(c, "scripts")):
                tf = ".claude/sources/types/%s/%s" % (t, s)
                if not self.tracked(tf):
                    self.fail("`%s` isn't committed" % tf, "`git add -- .claude/sources/types/%s "
                              "&& git commit` (you, not Claude)" % t)
                elif self.changed(tf):
                    self.fail("`%s` has uncommitted changes" % tf, "review them, then `git add -- "
                              "%s && git commit` (you, not Claude)" % tf)

        # 7. Structural lint (errors only; warnings are normal on a young wiki).
        if os.path.isdir(root + "/wiki"):
            # Read below only when n is not None, so after log_history returned;
            # bound on every path all the same.
            hist: list[lint.LogEdit] = []
            why = ""
            try:
                hist = lint.log_history(root)
                _, n = lint.report(root, self.plugin, hist)
                n -= len(hist)
            except (lint.Die, sourcelib.GitBashPath) as e:
                n, why = None, str(e)
            except Exception as e:  # named, so a bug in lint isn't hidden
                n, why = None, "internal error: %s: %s" % (type(e).__name__, e)
            if n == 0:
                self.ok("lint finds no structural errors")
            elif n is None:
                self.fail("lint.sh didn't run (%s)" % " ".join(why.split()),
                          "run `bash %s/lint.sh` and read its error" % self.here)
            else:
                self.fail("lint finds %d structural error(s)" % n, "run /wiki:lint")
            if n is not None and hist:
                self.info("lint flags %d past commit(s) that rewrote `wiki/log.md`; not a setup "
                          "failure, restoring the lines won't clear it, the last ages out on %s"
                          % (len(hist), max(c.ages_out for c in hist)))

        # 8. Setup files committed.
        _, dirty = git(root, "status", "--porcelain", "--", "CLAUDE.md", ".gitignore",
                       "raw/sync-log.md", "wiki/index.md", "wiki/log.md", "templates")
        if not dirty.strip("\n"):
            self.ok("setup files are committed")
        else:
            names: list[str] = []
            for ln in dirty.rstrip("\n").split("\n"):
                fs = [x for x in _AWK_FS.split(ln) if x]
                names.append(fs[1] if len(fs) > 1 else "")
            self.fail("uncommitted setup files: %s" % " ".join(names), "review and commit them")

        # 9. Markdown outside the layout: neither a source nor a page, so
        # lint, the index and ingest never see it. The wiki works with it.
        # Dot folders (.claude/sources/instances/ and the like) and dot files
        # aren't pages.
        _, o = git(root, "ls-files", "-z")
        stray = [f for f in o.split("\0")
                 if f.lower().endswith(".md") and f not in _ROOT_MD
                 and f.split("/", 1)[0] not in _LAYOUT_DIRS
                 and not any(p.startswith(".") for p in f.split("/"))]
        if stray:
            self.info("%d Markdown file(s) outside the wiki layout: %s. Move each to `work/` "
                      "(drafts) or `raw/` (source material), or delete it"
                      % (len(stray), " ".join("`%s`" % f for f in stray)))

        # 10. Python for the guard hooks and the scripts: this check runs in it.
        v = sys.version_info
        self.ok("the guard hooks and the source scripts find Python %d.%d.%d %s"
                % (v[0], v[1], v[2], sys.executable.replace("\\", "/")))
        cfg = os.environ.get("CLAUDE_CONFIG_DIR") or \
            (os.environ.get("HOME") or os.path.expanduser("~")) + "/.claude"
        # py-launch.sh's cache, named after its floor (_pl_floor).
        cache = cfg + "/plugins/data/wiki-wiki-tools/python-3.11"
        if os.path.isfile(cache):
            first = read_text(cache).split("\n", 1)[0].replace("\r", "")
            self.info("the guard hooks have cached `%s`" % first)
        else:
            self.info("no interpreter cached yet; the first guard call caches it (about 0.2 s, once)")

        sourcelib.out("## Wiki check: %s\n\nFailures: %d.\n\n%s"
                      % (root.rstrip("/").rsplit("/", 1)[-1], self.fails, "\n".join(self.out)))
        return 0 if self.fails == 0 else 1


def sourcelib_platform() -> str:
    """src_platform (as sources.py has it)."""
    p = sys.platform
    if p.startswith("linux"):
        return "linux"
    if p in ("win32", "cygwin", "msys"):
        return "windows"
    if p == "darwin":
        return "macos"
    import platform as pf
    return pf.system().lower()


def _main(argv: list[str]) -> int:
    plugin = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
    if argv[:1] == ["--plugin"] and len(argv) > 1:
        plugin, argv = argv[1], argv[2:]
    return Check(plugin).run()


def main(argv: list[str]) -> int:
    try:
        rc = _main(argv)
    except Die as e:
        sourcelib.err("wiki-check: %s" % e)
        rc = 1
    except sourcelib.GitBashPath as e:
        sourcelib.err("wiki-check: %s" % e)
        rc = 3
    except Exception as e:  # an internal error is never a pass
        sourcelib.err("wiki-check: internal error: %s: %s" % (type(e).__name__, e))
        rc = 3
    sys.stdout.flush()
    sys.stdout.buffer.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
