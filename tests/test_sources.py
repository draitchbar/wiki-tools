"""sources.sh against a copy of guard-wiki (gmail, scans, teams, local type
books), the standard contracts, and the recorded edge cases in
fixtures/sources/edge.out (formerly the sources section of run-tests.sh).

The checks replay the old section's steps in order on one wiki (`Story`),
because the recorded edge cases depend on the state the steps leave."""

import re
import sys

import pytest

import sourcelib
from conftest import PLUGIN, PLUGIN_BASH, TESTS, Story, call_main, copytree, git, norm, posix, recorded, story_assert, write

HOST = {"linux": "linux", "darwin": "macos"}.get(sys.platform, "windows")
OTHER = "macos" if HOST == "linux" else "linux"

# sexpect rows: name, text, args (on the wiki as the steps left it).
LIST_ETC = [
    ("list-raw", "- raw: built in (raw/), last checked: never", ["list"]),
    ("list-standard", "- gmail: type gmail (standard), valid, available here: yes, last checked: 2026-10-01", ["list"]),
    ("list-local", "- books: type bookish (local), valid", ["list"]),
    ("list-no-state", "last checked: no last_checked_scans line", ["list"]),
    ("list-manual", "- web: manual key (no source file; enters via raw/ or user statements; /wiki:ingest "
                    "cannot read it), last checked: 2026-10-02", ["list"]),
    ("show-header", "Source scans: valid", ["show", "scans"]),
    ("show-instance", "  - ~/Pictures/Receipts", ["show", "scans"]),
    ("show-contract", "# Source type: Local folder", ["show", "scans"]),
    ("show-raw", "raw is built in", ["show", "raw"]),
    ("show-unknown", "no source 'nosuch' in this wiki", ["show", "nosuch"]),
    ("catalog", "- bookish (local, script): Bookish (local test type)", ["catalog"]),
    ("contract", "type: gmail", ["contract", "gmail"]),
    ("settings-allow", '"Bash(bash .claude/sources/types/bookish/fetch.sh *)",', ["settings"]),
    # gmail's deny rules come from its instance's reader binding (reader_deny).
    ("settings-deny", '"mcp__claude_ai_Gmail__send_message",', ["settings"]),
    ("settings-type", '"Bash(bash */sources/local-folder/read.sh *)"', ["settings", "local-folder"]),
    # proton-files (access: tools): only the deny rule for the CLI its
    # reader wraps; the reader's own rule lives in the user's settings.
    ("settings-proton-deny", '"Bash(proton-drive *)"', ["settings", "proton-files"]),
    ("settings-proton-note", "proton-files (access: tools) names no tools", ["settings", "proton-files"]),
    ("contract-root", "bash %s/sources/local-folder/read.sh <key> list" % PLUGIN_BASH, ["contract", "local-folder"]),
    # google-drive (access: tools): no tool rules until an instance is bound.
    ("settings-gdrive-note", "google-drive (access: tools) names no tools", ["settings", "google-drive"]),
    ("catalog-gdrive", "- google-drive (standard, tools): Google Drive", ["catalog"]),
    ("catalog-teams", "- ms-teams (standard, tools): Microsoft Teams", ["catalog"]),
    # gmail (access: tools, docs/adr.md 23): no tool rules until an instance
    # is bound; guard-wiki's gmail binds the connector, label writes and
    # draft reads denied.
    ("catalog-gmail", "- gmail (standard, tools): Gmail", ["catalog"]),
    ("settings-gmail-note", "gmail (access: tools) names no tools", ["settings", "gmail"]),
    ("settings-gmail-key", '"mcp__claude_ai_Gmail__download_gmail_attachment"', ["settings", "gmail", "--key", "gmail"]),
    ("settings-gmail-key-deny-label", '"mcp__claude_ai_Gmail__label_thread",', ["settings", "gmail", "--key", "gmail"]),
    ("settings-gmail-key-deny-drafts", '"mcp__claude_ai_Gmail__list_drafts",', ["settings", "gmail", "--key", "gmail"]),
    # jira (access: tools): no tool rules; the reader is settled per wiki.
    ("catalog-jira", "- jira (standard, tools): Jira", ["catalog"]),
    ("settings-jira-note", "jira (access: tools) names no tools", ["settings", "jira"]),
    ("settings-jira-note-key", "(sources.sh settings jira --key <key>)", ["settings", "jira"]),
    # tracker's reader binding: its tools allowed, its write tools denied,
    # a dispatcher once whatever its limits.
    ("settings-reader-allow", '"mcp__claude_ai_Atlassian_MCP__getJiraIssue",', ["settings"]),
    ("settings-reader-deny", '"mcp__claude_ai_Atlassian_MCP__executeWrite",', ["settings"]),
    ("settings-reader-key", '"mcp__claude_ai_Atlassian_MCP__executeRead",', ["settings", "jira", "--key", "tracker"]),
    ("show-reader-valid", "Source tracker: valid", ["show", "tracker"]),
    # An access: tools instance without a reader binding: Check is needed
    # at every ingest until it is bound, not only after the file changed.
    ("show-unbound-check", "Check needed: proton-files names no tools (access: tools) and this instance "
     "has no reader binding yet; /wiki:bind-reader proton drafts it.", ["show", "proton"]),
    ("list-research", '- code: type codebase (standard), research (/wiki:research code "<question>"; '
                      'not ingested), valid', ["list"]),
    ("catalog-codebase", "- codebase (standard, filesystem): Codebase", ["catalog"]),
    # ms-teams (access: tools): only the walk file's cache rule; teams's
    # binding gives the connector's rules, Outlook and people tools denied.
    ("settings-teams-note", "ms-teams (access: tools) names no tools", ["settings", "ms-teams"]),
    ("settings-teams-edit", '"Edit(~/.cache/wiki-sources/*/*/walk.tsv)"', ["settings", "ms-teams"]),
    ("settings-teams-key", '"mcp__claude_ai_Microsoft_365__read_resource"', ["settings", "ms-teams", "--key", "teams"]),
    ("settings-teams-key-deny-outlook", '"mcp__claude_ai_Microsoft_365__outlook_email_search",',
     ["settings", "ms-teams", "--key", "teams"]),
    ("settings-teams-key-deny-write", '"mcp__claude_ai_Microsoft_365__teams_send_chat_message",',
     ["settings", "ms-teams", "--key", "teams"]),
    ("settings-teams-key-deny-me", '"mcp__claude_ai_Microsoft_365__get_me"', ["settings", "ms-teams", "--key", "teams"]),
    ("show-teams-valid", "Source teams: valid", ["show", "teams"]),
    ("settings-narrow-key", '"Edit(~/.cache/wiki-sources/sw/code/**)"', ["settings", "codebase", "--key", "code"]),
    ("settings-narrow-read", '"Read(~/.cache/wiki-sources/sw/code/**)"', ["settings", "codebase", "--key", "code"]),
    ("settings-narrow-teams", '"Edit(~/.cache/wiki-sources/sw/x/walk.tsv)"', ["settings", "ms-teams", "--key", "x"]),
    ("settings-narrow-all", '"Edit(~/.cache/wiki-sources/sw/code/**)"', ["settings"]),
    ("settings-narrow-note", "covers them too", ["settings", "codebase", "--key", "code"]),
    ("settings-key-alone", "--key goes with a type", ["settings", "--key", "code"]),
    ("settings-key-bad", "invalid instance key", ["settings", "codebase", "--key", "a b"]),
    ("catalog-onenote", "- onenote (standard, tools): OneNote", ["catalog"]),
    ("settings-tools-note", "onenote (access: tools) names no tools, so it adds no tool rules here",
     ["settings", "onenote"]),
]
COUNTS = [  # name, args, a regex no line may match
    ("settings-proton-no-allow", ["settings", "proton-files"], r"Bash\(bash|read\.sh|wiki-sources"),
    ("settings-jira-no-tools", ["settings", "jira"], r"mcp__|Bash\(|wiki-sources"),
    ("settings-gdrive-no-tools", ["settings", "google-drive"], r"mcp__|Bash\(|wiki-sources"),
    ("settings-teams-no-tools", ["settings", "ms-teams"], r"mcp__|Bash\("),
    ("settings-tools-empty", ["settings", "onenote"], r"mcp__|Bash\("),
    ("settings-gmail-no-tools", ["settings", "gmail"], r"mcp__|Bash\(|wiki-sources"),
    # A type that isn't access: tools prints no tools note.
    ("settings-tools-quiet", ["settings", "local-folder"], r"access: tools"),
    # Bound: no note for jira; executeRead once.
    ("settings-reader-no-note", ["settings"], r"^jira \(access: tools\)"),
    ("show-bound-no-check", ["show", "tracker"], r"^Check needed"),
    ("settings-reader-key-quiet", ["settings", "jira", "--key", "tracker"], r"access: tools"),
]
COUNT_ONE = [  # name, args, a regex exactly one line matches
    ("settings-reader-once", ["settings"], r'"mcp__claude_ai_Atlassian_MCP__executeRead"'),
]
NOTES = [
    ("show-tools-instance", "Source notes: valid", ["show", "notes"]),
    ("settings-tools-all", "onenote (access: tools) names no tools", ["settings"]),
    ("settings-tools-cache", '"Edit(~/.cache/wiki-sources/sw/notes/**)"', ["settings", "onenote", "--key", "notes"]),
]
# Bound before the `reader` list existed: a `## Reader` section alone is a
# binding in prose, still unbound (Check stops the ingest), but the messages
# say it needs binding again, not a first binding. A `## Reader` inside a
# fenced code block doesn't count.
PROSE = [
    ("show-prose-check", "Check needed: proton-files names no tools (access: tools) and this instance's reader "
     "binding is in prose only (a '## Reader' section, no 'reader' list); run /wiki:bind-reader pdocs again to "
     "make it machine-readable.", ["show", "pdocs"]),
    ("show-fenced-unbound", "this instance has no reader binding yet; /wiki:bind-reader pfence drafts it.",
     ["show", "pfence"]),
    ("settings-prose-key", "adds the reader's rules; bound in prose only (a '## Reader' section, no 'reader' "
     "list): pdocs (/wiki:bind-reader <key> again makes it machine-readable). How read-only",
     ["settings", "proton-files", "--key", "pdocs"]),
    ("settings-prose-all", "adds the reader's rules; not bound yet: pfence, proton (/wiki:bind-reader <key> "
     "drafts it); bound in prose only (a '## Reader' section, no 'reader' list): pdocs (/wiki:bind-reader <key> "
     "again makes it machine-readable). How read-only", ["settings"]),
]
SHADOW = [
    ("shadow-fix-order", "delete the folder .claude/sources/types/onenote/", ["contract", "onenote"]),
    ("shadow-contract", "shown is the standard contract", ["contract", "onenote"]),
    ("shadow-contract-body", "# Source type: OneNote", ["contract", "onenote"]),
]


def _first(pattern, repl):
    """sed '0,/re/s//repl/': the first line matching re, changed."""
    def f(text):
        lines = text.split("\n")
        for i, ln in enumerate(lines):
            if re.search(pattern, ln):
                lines[i] = re.sub(pattern, repl, ln, count=1)
                break
        return "\n".join(lines)
    return f


def _lines(fn):
    return lambda text: "\n".join(fn(ln) for ln in text.split("\n"))


def _drop(pred):
    return lambda text: "\n".join(ln for ln in text.split("\n") if not pred(ln))


def _sub(a, b):
    return lambda text: text.replace(a, b)


def _seq(*fns):
    def f(text):
        for fn in fns:
            text = fn(text)
        return text
    return f


CODE_EDIT = '"Edit(~/.cache/wiki-sources/sw/code/**)"'
MISSING_CODE = "allow: Edit(~/.cache/wiki-sources/sw/code/**)"
STALE = ("stale (allow rules for source scripts and MCP tools that no source instance uses; "
         "remove any that nothing else needs):")
SCK = [  # name, exit, text, change to the settings `settings` prints
    ("ok", 0, "missing: none", None),
    ("ok-json", 0, "settings.json: valid JSON", None),
    ("ok-keys", 0, "misspelled keys: none", None),
    # A misspelled key once made Claude Code ignore the whole file, deny rules included.
    ("typo-key", 1, "misspelled keys (Claude Code may ignore the whole file",
     lambda t: t.replace("{\n", '{\n  "hoooks": {},\n', 1)),
    ("typo-permissions", 1, "permissions.alow (allow?)", lambda t: t.replace('"allow"', '"alow"', 1)),
    ("unknown-key-far", 0, "misspelled keys: none",
     lambda t: t.replace("{\n", '{\n  "spinnerTipsEnabled": true,\n', 1)),
    ("trailing", 1, "NOT valid JSON: comma before ]",
     _seq(_first(r'",$', '",\n'), _first(r'^      "[^"]*"$', lambda m: m.group(0) + ","))),
    ("no-comma", 1, "NOT valid JSON: expected , or ] (a missing comma?)", _first(r'",$', '"')),
    ("unclosed", 1, "NOT valid JSON: unexpected end of file", lambda t: "\n".join(t.split("\n")[:-2]) + "\n"),
    ("missing", 1, MISSING_CODE, _drop(lambda ln: 'wiki-sources/sw/code/**)"' in ln and "Edit" in ln)),
    # The Gmail send_message deny comes from guard-wiki's gmail reader_deny.
    ("dup", 1, "duplicates:", _lines(lambda ln: re.sub(r'^(      "mcp__claude_ai_Gmail__send_message")(,?)$',
                                                      r"\1,\n\1\2", ln))),
    ("conflict", 1, "in both allow and deny",
     _lines(lambda ln: re.sub(r'^(      "Bash\(bash \*/sources/codebase/git\.sh \*\)")(,?)$',
                              r'\1,\n      "mcp__claude_ai_Gmail__send_message"\2', ln))),
    ("broad-ok", 0, "note: these rules reach every wiki", _sub(CODE_EDIT, '"Edit(~/.cache/wiki-sources/**)"')),
    # A broader Read/Edit rule on a folder that holds the needed path covers it.
    ("broad-wiki", 0, "missing: none", _sub(CODE_EDIT, '"Edit(~/.cache/wiki-sources/sw/**)"')),
    ("broad-star", 1, MISSING_CODE, _sub(CODE_EDIT, '"Edit(~/.cache/wiki-sources/*/code/**)"')),
    ("broad-lead-star", 1, MISSING_CODE, _sub(CODE_EDIT, '"Edit(*/**)"')),
    # A broader rule in deny doesn't cover a needed allow rule.
    ("broad-deny", 1, MISSING_CODE, _seq(_sub(CODE_EDIT, '"Edit(~/.cache/wiki-sources/sw/code/x/**)"'),
                                         _sub('"deny": [', '"deny": [ "Edit(~/.cache/wiki-sources/**)",'))),
    # A deny rule that covers a needed allow rule blocks it: deny wins.
    ("deny-broad", 1, "allow: Edit(~/.cache/wiki-sources/sw/code/**) (deny: Edit(~/.cache/wiki-sources/**))",
     _sub('"deny": [', '"deny": [ "Edit(~/.cache/wiki-sources/**)",')),
    ("deny-exact", 1, "allow: Edit(~/.cache/wiki-sources/sw/code/**) (deny: Edit(~/.cache/wiki-sources/sw/code/**))",
     _sub('"deny": [', '"deny": [ %s,' % CODE_EDIT)),
    ("deny-other", 0, "blocked by deny: none", _sub('"deny": [', '"deny": [ "Edit(~/.cache/wiki-sources/other/**)",')),
    ("broad-other", 1, MISSING_CODE, _sub(CODE_EDIT, '"Edit(~/.cache/wiki-sources/other/**)"')),
    ("broad-tool", 1, MISSING_CODE, _sub(CODE_EDIT, '"Read(~/.cache/wiki-sources/**)"')),
    ("broad-file", 1, MISSING_CODE, _sub(CODE_EDIT, '"Edit(~/.cache/wiki-sources/sw/code)"')),
    # Stale allow rules (a source script or an MCP tool no instance needs):
    # reported, never a failure. Needed and unrelated rules aren't.
    ("stale-none", 0, "stale: none", None),
    ("stale-wrapper", 0, STALE + "\n  allow: Bash(bash */sources/ms-teams/snapshot.sh *)\n",
     _sub('"allow": [', '"allow": [ "Bash(bash */sources/ms-teams/snapshot.sh *)",')),
    ("stale-local", 0, STALE + "\n  allow: Bash(bash .claude/sources/types/oldtype/fetch.sh *)\n",
     _sub('"allow": [', '"allow": [ "Bash(bash .claude/sources/types/oldtype/fetch.sh *)",')),
    ("stale-mcp", 0, STALE + "\n  allow: mcp__example_reader__get_note\n  allow: mcp__example_reader__list_notes\n",
     _sub('"allow": [', '"allow": [ "mcp__example_reader__list_notes", "mcp__example_reader__get_note",')),
    ("stale-unrelated", 0, "\nstale: none\n",
     _seq(_sub('"allow": [', '"allow": [ "Bash(git status *)", "Bash(bash */scripts/file-snapshot.sh *)", '
               '"WebFetch", "Skill(wiki:ingest)", "Read(~/.cache/wiki-sources/**)", "mcp__claude_ai_Gmail",'),
          _sub('"deny": [', '"deny": [ "mcp__example_reader__delete_note", '
               '"Bash(bash */sources/ms-teams/snapshot.sh *)",'))),
]
CONTRACTS = sorted(p.parent.name for p in PLUGIN.glob("sources/*/SOURCE.md"))
PLACEHOLDERS = ["FOLDER-ID-TBD", "<label>", "todo", "?", "..."]
EDGE_ARGS = [a.split() for a in ("", "bogus", "list extra", "show", "show a?b", "show raw", "catalog x",
                                 "contract", "contract nosuch", "check-settings extra", "settings nosuch",
                                 "settings --key", "settings gmail --key x --key y", "settings onenote gmail",
                                 "show -x")]
EDGE_ARGS += [["show", ""], ["show", "a b"], ["contract", "bad name"], ["settings", ""], ["settings", "gmail jira"]]

NAMES = (["sources/" + n for n, _, _ in LIST_ETC + NOTES + PROSE + SHADOW] + ["sources/contract-root-filled"]
         + ["sources/" + n for n, _, _ in COUNTS + COUNT_ONE] +["sources/check-settings-" + n for n, _, _, _ in SCK]
         + ["sources/check-settings-none"] + ["contract/%s-valid" % t for t in CONTRACTS]
         + ["sources/check-uncommitted", "sources/check-same-commit", "sources/check-committed-after",
            "sources/check-not-needed", "sources/check-not-for-never"]
         + ["sources/placeholder-" + v for v in PLACEHOLDERS]
         + ["sources/placeholder-word-inside", "sources/show-platform", "sources/show-invalid",
            "sources-edge/same", "sources-edge/cases"])


@pytest.fixture(scope="module")
def story(tmp_path_factory, cli, request):
    t = tmp_path_factory.mktemp("src")
    sw = copytree(TESTS / "guard-wiki", t / "sw")
    git(sw, "init", "-q")
    write(sw / "raw/sync-log.md", "last_checked_gmail: 2026-10-01\nlast_checked_raw: never\nlast_checked_web: 2026-10-02\n")
    st = Story()
    inst = sw / ".claude/sources/instances"

    def srun(*args, memo=None):
        """sources.sh's output; with memo (a dict, for steps on one unchanged
        wiki) each argument list runs once."""
        if memo is None or args not in memo:
            o = cli("sources", *args, cwd=sw).merged.decode("utf-8", errors="surrogateescape")
            if memo is None:
                return o
            memo[args] = o
        return memo[args]

    def expect(rows):
        memo = {}
        for n, text, args in rows:
            st.found("sources/" + n, text, srun(*args, memo=memo))

    memo = {}
    for n, text, args in LIST_ETC:
        st.found("sources/" + n, text, srun(*args, memo=memo))
    st.check("sources/contract-root-filled", "${CLAUDE_PLUGIN_ROOT}" not in srun("contract", "local-folder", memo=memo))
    for n, args, rx in COUNTS:
        st.eq("sources/" + n, 0, sum(bool(re.search(rx, ln)) for ln in srun(*args, memo=memo).split("\n")))
    for n, args, rx in COUNT_ONE:
        st.eq("sources/" + n, 1, sum(bool(re.search(rx, ln)) for ln in srun(*args, memo=memo).split("\n")))
    write(inst / "notes.md", "---\nkey: notes\ntype: onenote\nsections:\n  - Book > Tab\nstate:\n"
          "  - last_checked\n  - cursor\n---\n")
    expect(NOTES)
    (inst / "notes.md").unlink()
    pfm = "---\nkey: %s\ntype: proton-files\nroots:\n  - /my-files/Projects/beta\nstate:\n  - last_checked\n---\n"
    write(inst / "pdocs.md", pfm % "pdocs" + "Read with the example-drive plugin.\n\n## Reader\n\n"
          "list: drive.sh list <root>\n")
    write(inst / "pfence.md", pfm % "pfence" + "Example:\n\n```\n## Reader\n```\n")
    expect(PROSE)
    (inst / "pdocs.md").unlink()
    (inst / "pfence.md").unlink()
    # A local type shadowing a standard one: the error names the fix order,
    # and `contract` still shows the standard contract to migrate to.
    shadow = sw / ".claude/sources/types/onenote/SOURCE.md"
    write(shadow, (sw / ".claude/sources/types/bookish/SOURCE.md").read_bytes())
    expect(SHADOW)
    shadow.unlink()
    shadow.parent.rmdir()
    # check-settings: start from what `settings` prints, then plant one fault each.
    out = srun("settings").split("\n")
    a = next(i for i, ln in enumerate(out) if ln.startswith("{"))
    b = next(i for i, ln in enumerate(out) if i > a and ln.startswith("}"))
    sjson = "\n".join(out[a:b + 1]) + "\n"
    for n, code, text, change in SCK:
        write(sw / ".claude/settings.json", change(sjson) if change else sjson)
        r = cli("sources", "check-settings", cwd=sw)
        o = r.merged.decode("utf-8", errors="surrogateescape")
        st.check("sources/check-settings-" + n, text in o and r.rc == code, "rc %d, output:\n%s" % (r.rc, o))
    (sw / ".claude/settings.json").unlink()
    st.found("sources/check-settings-none", "settings.json: missing", srun("check-settings"))
    # Every standard contract validates.
    for c in CONTRACTS:
        r = call_main(sourcelib.main, ["validate-contract", posix(PLUGIN / "sources" / c / "SOURCE.md")])
        st.check("contract/%s-valid" % c, r.rc == 0 and not r.merged, r)
    # Check needed: the instance file changed since the last ingest.
    st.found("sources/check-uncommitted", "Check needed: the instance file has uncommitted changes since the "
             "last ingest (2026-10-01).", srun("show", "gmail"))

    def swc(date, msg):
        git(sw, "add", "-A")
        git(sw, "commit", "-qm", msg, date=date)

    swc("2026-10-01T10:00:00", "init")
    st.check("sources/check-same-commit", "Check needed" not in srun("show", "gmail"))
    write(inst / "gmail.md", (inst / "gmail.md").read_bytes() + b"\nNotes.\n")
    swc("2026-10-01T15:00:00", "edit instance")
    st.found("sources/check-committed-after", "Check needed: the instance file changed (2026-10-01) since the "
             "last ingest (2026-10-01).", srun("show", "gmail"))
    log = sw / "raw/sync-log.md"
    write(log, re.sub(r"(?m)^last_checked_gmail: .*$", "last_checked_gmail: 2026-10-02", log.read_text()))
    swc("2026-10-02T09:00:00", "ingest")
    st.check("sources/check-not-needed", "Check needed" not in srun("show", "gmail"))
    st.check("sources/check-not-for-never", "Check needed" not in srun("show", "books"))
    # Placeholders in parameter values.
    for v in PLACEHOLDERS:
        write(inst / "ph.md", "---\nkey: ph\ntype: gmail\nlabels: %s\n---\n" % v)
        st.found("sources/placeholder-" + v, "parameter 'labels' holds a placeholder", srun("show", "ph"))
    write(inst / "ph.md", "---\nkey: ph\ntype: gmail\nlabels: Todoroki\nsenders:\n  - xxl@example.com\n---\n")
    st.check("sources/placeholder-word-inside", re.search(r"(?m)^Source ph: valid", srun("show", "ph")))
    (inst / "ph.md").unlink()
    # Leave bookish only a platform that isn't this host's.
    bk = sw / ".claude/sources/types/bookish/SOURCE.md"
    text = re.sub(r"(?m)^  - (linux|macos|windows)\n", "", bk.read_text())
    write(bk, text.replace("platforms:\n", "platforms:\n  - %s\n" % OTHER, 1))
    st.found("sources/show-platform", "isn't available on", srun("show", "books"))
    write(inst / "bad.md", "---\nkey: worse\ntype: gmail\n---\n")
    st.found("sources/show-invalid", "doesn't validate", srun("show", "bad"))

    # Edge cases (recorded): usage, odd keys and types, a key file with a
    # space, a manual key and a sync-log with CRs and trailing spaces.
    cases = []

    def plat(s):
        return (s.replace("(platform: %s)" % HOST, "(platform: @HOST@)", 1)
                .replace("not available on %s)" % HOST, "not available on @HOST@)", 1)
                .replace(": valid, available on %s," % HOST, ": valid, available on @HOST@,", 1)
                .replace("(only %s)" % OTHER, "(only @OTHER@)", 1))

    def se_case(args, d=sw):
        r = cli("sources", *args, cwd=d, both=True)
        block = "rc=%d\n-- out\n%s-- err\n%s-- merged\n%s" % (
            r.rc, r.out.decode("utf-8", "surrogateescape"), r.err.decode("utf-8", "surrogateescape"),
            r.merged.decode("utf-8", "surrogateescape"))
        block = "\n".join(plat(ln) for ln in norm(block.rstrip("\n"), t).split("\n"))
        cases.append("== %s\n%s\n" % (norm(" ".join(args), t), block))

    for a in EDGE_ARGS:
        se_case(a)
    write(inst / "two words.md", "---\nkey: two words\ntype: gmail\n---\n")
    write(inst / "odd.md", "---\nkey: odd\ntype: nosuchtype\n---\n")
    write(log, "last_checked_gmail: 2026-10-01\r\nlast_checked_odd:   2026-10-03  \r\nlast_checked_x_y: never\n"
          "last_checked_: x\nlast_checked_raw:\n")
    for a in (["list"], ["show", "odd"], ["show", "two"], ["settings"], ["catalog"]):
        se_case(a)
    (inst / "two words.md").unlink()
    (inst / "odd.md").unlink()
    log.unlink()
    se_case(["list"])
    se_case(["show", "gmail"])
    se_case(["list"], d=t)  # outside a git repo
    out = "".join(cases)
    try:
        recorded(request, TESTS / "fixtures/sources/edge.out", out)
        st.check("sources-edge/same", True)
    except AssertionError:
        want = (TESTS / "fixtures/sources/edge.out").read_text(encoding="utf-8", errors="surrogateescape")
        import difflib
        st.check("sources-edge/same", False, "".join(difflib.unified_diff(
            want.splitlines(True), out.splitlines(True), "recorded", "now"))[:4000])
    st.eq("sources-edge/cases", 28, len(cases))
    return st


@pytest.mark.parametrize("name", [pytest.param(n, id=n) for n in NAMES])
def test_sources(name, story):
    story_assert(story, name)


@pytest.mark.checks("sources/every-check-run")
def test_every_check_run(story):
    assert sorted(story.results) == sorted(NAMES)
