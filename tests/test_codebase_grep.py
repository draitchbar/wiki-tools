"""codebase/git.sh's grep patterns: pattern files in the cache, -e patterns,
several pathspecs and the refusals, end to end through bash.

The steps run in order on one repository and wiki (`codebase_story.Ctx`):
later steps depend on the history and the cache the earlier ones leave.
Each check is its own test, named by the literal first argument of
has/chk/eq."""

import pytest

from codebase_story import build, names
from conftest import spellings, story_assert, write

NAMES = names(__file__)


@pytest.fixture(scope="module")
def story(tmp_path_factory, run):
    c = build(tmp_path_factory, run, "cbg")
    has, chk, eq, out, cbn, cbx = c.has, c.chk, c.eq, c.out, c.cbn, c.cbx
    cache, cbhome = c.cache, c.cbhome

    def refused(*args):
        """One call: its exit code for a tally, its message for a hint check."""
        o, rc = cbn(*args)
        return str(rc), o

    write(cache / "p.txt", "FO+|zzz\r\n^L6$\n")
    o = out("code", "grep", "ref", "@p.txt")
    has("codebase/grep-patfile", o, "app/src/A.java#L3: FOO")
    has("codebase/grep-patfile-or", o, "app/src/A.java#L7: L6")
    has("codebase/grep-patfile-head", o, "2 patterns from p.txt: FO+|zzz|^L6$")
    write(cache / "runs/r1/q.txt", "b1\n")
    has("codebase/grep-patfile-sub", out("code", "grep", "ref", "@runs/r1/q.txt", "lib/*"), "lib/B2.java#L1: b1")
    write(cache / "many.txt", "".join("p%d\n" % i for i in range(21)))
    write(cache / "empty.txt", "")
    # @nosuch.txt once: its message is checked at the end (cache-shown-as-tilde).
    nosuch = refused("code", "grep", "ref", "@nosuch.txt")
    rcs = [cbx("code", "grep", "ref", p) for p in ("@../x", "@runs/../p.txt", "@/etc/passwd")] + [nosuch[0]]
    rcs += [cbx("code", "grep", "ref", p) for p in ("@many.txt", "@empty.txt")]
    eq("codebase/refuse-patfile", "1 1 1 1 1 1", " ".join(rcs))
    eq("codebase/refuse-patfile-other-key", "1", cbx("sub", "grep", "ref", "@p.txt"))
    # -e patterns, or-ed, and a leading @ as a regex.
    o = out("code", "grep", "ref", "-e", "FO+", "-e", "^L6")
    chk("codebase/grep-multi-e", all(s in o for s in ("app/src/A.java#L3: FOO", "app/src/A.java#L7: L6",
                                                      " grep FO+|^L6 in ")), o)
    has("codebase/grep-multi-e-spec", out("code", "grep", "ref", "-e", "b1", "-e", "zzz", "lib/*"), "lib/B2.java#L1: b1")
    has("codebase/igrep-multi-e", out("code", "igrep", "ref", "-e", "zzz", "-e", "foo"), "app/src/A.java#L3: FOO")
    o, rc = cbn("code", "grep", "ref", "-e", "@x")
    chk("codebase/grep-e-at", " grep @x in " in o and rc == 0, o)
    o, rc = cbn("code", "grep", "ref", "-e", "--output=x")
    chk("codebase/grep-e-dash", " grep --output=x in " in o and rc == 0, o)
    has("codebase/patfile-missing-hint", out("code", "grep", "ref", "@McpToolKit"), "for a regex starting with @, use -e")
    many = [w for i in range(20) for w in ("-e", "p%d" % i)]
    eq("codebase/grep-20-e", "0", cbx("code", "grep", "ref", *many))
    many += ["-e", "p20"]
    eq("codebase/refuse-e-outside", "1 1", cbx("code", "grep", "ref", "-e", "a", "../x") + " "
       + cbx("sub", "grep", "ref", "-e", "a", "lib/*"))
    eq("codebase/refuse-e-mixed", "1", cbx("code", "grep", "ref", "foo", "-e", "bar"))
    trailing_e, too_many = refused("code", "grep", "ref", "-e", "a", "-e"), refused("code", "grep", "ref", *many)
    eq("codebase/refuse-multi-e", "1 1 1 1 1", " ".join([
        cbx("code", "grep", "ref", "-e"), trailing_e[0],
        cbx("code", "grep", "ref", "-e", ""), cbx("code", "grep", "ref", "-e", "a", "x", "-e", "b"),
        too_many[0]]))
    has("codebase/refuse-multi-e-msg", trailing_e[1], "-e needs a regex after it.")
    has("codebase/refuse-21-e-msg", too_many[1], "at most 20 -e patterns.")
    # Several pathspecs, -i pointed at igrep, the cache folder shown as ~.
    o = out("code", "grep", "ref", "-e", "b1", "-e", "FOO", "lib/*", "app/*")
    chk("codebase/grep-multi-spec", all(s in o for s in ("lib/B2.java#L1: b1", "app/src/A.java#L3: FOO",
                                                         " in lib/* app/*")), o)
    has("codebase/grep-multi-spec-pos", out("code", "grep", "ref", "b1", "app/*", "lib/*"), "lib/B2.java#L1: b1")
    elev = ["d%d" % i for i in range(11)]
    late_i, flag_w = refused("code", "grep", "ref", "-e", "foo", "-i"), refused("code", "grep", "ref", "foo", "-w")
    eq("codebase/refuse-grep-flags", "1 1 1 1 1", " ".join([
        cbx("code", "grep", "ref", "-i", "foo"), late_i[0],
        cbx("code", "grep", "ref", "foo", "--ignore-case"), flag_w[0],
        cbx("code", "grep", "ref", "foo", *elev)]))
    has("codebase/refuse-i-hint", late_i[1], "use igrep for a case-insensitive search")
    has("codebase/refuse-flag-hint", flag_w[1], "takes no flags but -e")
    o = nosuch[1]
    chk("codebase/cache-shown-as-tilde", "'~/.cache/wiki-sources/cbw/code/nosuch.txt' not found" in o
        and not any(s in o for s in spellings(cbhome)), o)
    return c.st


@pytest.mark.parametrize("name", [pytest.param(n, id=n) for n in NAMES])
def test_codebase(name, story):
    story_assert(story, name)


@pytest.mark.checks("codebase/grep-every-check-run")
def test_every_check_run(story):
    assert sorted(story.results) == NAMES
