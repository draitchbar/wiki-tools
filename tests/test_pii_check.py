"""scripts/pii-check.sh: the personal-data check (docs/development.md,
"Personal data"). Every term and address here is made up. Every case runs
in-process in both modes; the cases in BOUNDARY also run through
pii-check.sh, in both modes (docs/adr.md, 6)."""

import functools
import subprocess
import sys

import pytest

from conftest import TESTS, call_main, git, posix, rerun

REPO = TESTS.parent
sys.path.insert(0, str(REPO / "scripts"))

import pii_check  # noqa: E402

NOREPLY = "1+someone@users.noreply.github.com"
# Strings the general rules must catch, built at run time so this file
# itself passes the check.
REAL_EMAIL = "someone.real" + "@gmail.com"
USER = "realname"
HOST = ".".join(["nas", "home", "lan"])
SESSION = "claude.ai/code/" + "session_01ABC"
DENY = "# test denylist\nJens Hansen\nSkovvej 12\nFrø\nmyhost-pc\n"


@pytest.fixture
def pii(run, tmp_path):
    """pii(*args, cwd, input=b"", deny=DENY, launcher=False) -> Result,
    in-process in both modes, or (launcher=True) through pii-check.sh in
    both modes (the cases in BOUNDARY)."""
    def _pii(*args, cwd=None, input=b"", deny=DENY, launcher=False):
        f = tmp_path / "deny.txt"
        f.write_text(deny, encoding="utf-8")
        env = {"PII_DENYLIST": None, "PII_DENYLIST_FILE": posix(f)}
        if launcher:
            return run(["bash", posix(REPO / "scripts" / "pii-check.sh")] + list(args),
                       cwd=cwd, env=env, input=input)
        return call_main(pii_check.main, list(args), cwd=cwd, env=env, input=input)
    return _pii


def commit(repo, files, msg="change", email=NOREPLY, name="someone"):
    for p, text in files.items():
        f = repo / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=" + name, "-c", "user.email=" + email,
                    "commit", "-q", "-m", msg], check=True, stdout=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    commit(r, {"README.md": "clean start\n"})
    return r


def out(r):
    return r.out.decode("utf-8", "replace")


# --- matching ----------------------------------------------------------------

@pytest.mark.parametrize("text, rule", [
    ("mail me at " + REAL_EMAIL, "email address"),
    ("cd C:/Users/" + USER + "/src", "user folder"),
    ("cd C:\\Users\\" + USER + "\\src", "user folder"),
    ("ls /home/" + USER + "/x", "user folder"),
    ("ssh " + HOST, "private hostname"),
    ("see https://" + SESSION, "Claude session link"),
], ids=["pii/email", "pii/windows-user", "pii/windows-user-backslash", "pii/home-dir",
        "pii/hostname", "pii/session-link"])
def test_general_rule_hits(text, rule):
    assert rule in pii_check.general_hits(text)


@pytest.mark.parametrize("text", [
    "alice@example.com and ci@example.invalid and git@github.com",
    "61011242+draitchbar@users.noreply.github.com noreply@anthropic.com",
    "/home/u/wikis and C:/Users/<name>/src and C:\\Users\\u and /Users/...",
    "Co-Authored-By: Claude <noreply@anthropic.com>",
    "threading.local and self.home_dir",
], ids=["pii/test-domains", "pii/noreply", "pii/placeholder-users", "pii/trailer",
        "pii/code-not-hostname"])
def test_general_rule_passes(text):
    assert pii_check.general_hits(text) == []


@pytest.mark.parametrize("text, n", [
    ("written by JENS HANSEN", 1),
    ("jens.hansen@x", 1),
    ("jens_hansen and jenshansen", 1),
    ("Skovvej 12, 2. tv", 2),
    ("skovvej-12", 2),
    ("bor i Frø", 3),
    ("bor i Froe", 3),
    ("bor i Fro", 3),
    ("host MYHOST-PC", 4),
    ("Fr%C3%B8 in a URL", 3),
], ids=["deny/case", "deny/dots", "deny/joined", "deny/address", "deny/dash", "deny/o-stroke",
        "deny/oe", "deny/o", "deny/hostname", "deny/percent"])
def test_denylist_hits(text, n):
    assert n in pii_check.Denylist(DENY).hits(text)


@pytest.mark.parametrize("text", ["frost and front", "Jens alone", "Hansen alone", "skovvej 13"],
                         ids=["deny/short-word-only", "deny/first-name", "deny/last-name",
                              "deny/other-number"])
def test_denylist_passes(text):
    assert pii_check.Denylist(DENY).hits(text) == []


# --- modes -------------------------------------------------------------------

@pytest.mark.checks("pii/text-mode")
def test_text_mode_never_prints_the_term(pii):
    r = pii("text", "PR title", input="Fix for Jens Hansen\nfine line\n".encode())
    assert r.rc == 1
    assert "PR title line 1: denylist entry 1" in out(r)
    assert "Jens" not in r.merged.decode() and "jens" not in r.merged.decode().lower()


@pytest.mark.checks("pii/text-clean")
def test_text_mode_clean(pii):
    assert pii("text", "branch", input=b"feature/lint-dates\n").rc == 0


@pytest.mark.checks("pii/text-non-ascii")
def test_text_mode_non_ascii(pii):
    """A non-ASCII denylist entry (Frø) matches non-ASCII input, and only
    its number is printed."""
    r = pii("text", "PR body", input="bor i Frø\n".encode())
    assert r.rc == 1
    assert "PR body line 1: denylist entry 3" in out(r)
    assert "Fr" not in r.merged.decode()


@pytest.mark.checks("pii/range")
def test_range_finds_lines_paths_messages_and_identities(pii, repo):
    commit(repo, {"docs/a.md": "line one\nby Jens Hansen\n", "Skovvej-12/notes.md": "x\n"},
           msg="notes\n\nfrom " + REAL_EMAIL)
    commit(repo, {"b.md": "ok\n"}, email=REAL_EMAIL)
    r = pii("range", "HEAD~2..HEAD", cwd=repo)
    o = out(r)
    assert r.rc == 1
    assert "docs/a.md:2: denylist entry 1" in o
    assert "path <path>: denylist entry 2" in o
    assert "message line 3: email address" in o
    assert "author email: email address that isn't a noreply address" in o
    assert "committer email: email address that isn't a noreply address" in o
    assert "gmail" not in r.merged.decode() and "Skovvej" not in r.merged.decode()


@pytest.mark.checks("pii/range-rename")
def test_range_checks_a_rename(pii, repo):
    commit(repo, {"plain.md": "x\n"})
    git(repo, "mv", "plain.md", "jens-hansen.md")
    commit(repo, {})
    r = pii("range", "HEAD~1..HEAD", cwd=repo)
    assert r.rc == 1 and "denylist entry 1" in out(r)


@pytest.mark.checks("pii/range-merge")
def test_range_checks_a_merge_against_its_first_parent(pii, repo):
    git(repo, "checkout", "-q", "-b", "side")
    commit(repo, {"side.md": "clean\n"})
    git(repo, "checkout", "-q", "main")
    commit(repo, {"main.md": "clean\n"})
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=someone", "-c",
                    "user.email=" + NOREPLY, "merge", "-q", "--no-ff", "-m", "merge", "side"],
                   check=True, stdout=subprocess.DEVNULL)
    assert pii("range", "HEAD~1..HEAD", cwd=repo).rc == 0


@pytest.mark.checks("pii/odd-line-breaks")
@pytest.mark.parametrize("sep", ["\f", "\v", "\x1c", "\x85", "\u2028"])
def test_odd_line_breaks_hide_nothing(pii, repo, sep):
    commit(repo, {"a.md": "x" + sep + REAL_EMAIL + "\n"})
    assert "a.md:1: email address" in out(pii("tree", cwd=repo))
    assert "a.md:1: email address" in out(pii("range", "HEAD~1..HEAD", cwd=repo))


@pytest.mark.checks("pii/plus-plus-line")
def test_added_line_that_looks_like_a_header(pii, repo):
    commit(repo, {"a.md": "one\n++ Jens Hansen\n-- Jens Hansen\n"})
    o = out(pii("range", "HEAD~1..HEAD", cwd=repo))
    assert "a.md:2: denylist entry 1" in o and "a.md:3: denylist entry 1" in o


@pytest.mark.checks("pii/tree")
def test_tree_mode(pii, repo):
    assert pii("tree", cwd=repo).rc == 0
    commit(repo, {"src/x.py": "PATH = 'C:/Users/" + USER + "/x'\n"})
    r = pii("tree", cwd=repo)
    assert r.rc == 1 and "src/x.py:1: user folder" in out(r)


@pytest.mark.checks("pii/pre-push")
def test_pre_push_new_branch_and_update(pii, repo, tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    commit(repo, {"a.md": "Jens Hansen\n"})
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], stdout=subprocess.PIPE,
                         check=True).stdout.decode().strip()
    zero = "0" * 40
    new = ("refs/heads/topic %s refs/heads/topic %s\n" % (sha, zero)).encode()
    r = pii("pre-push", "origin", cwd=repo, input=new)
    assert r.rc == 1 and "a.md:1: denylist entry 1" in out(r)
    # Only the commit the remote lacks: the clean start isn't scanned again.
    assert out(r).count("pii-check: commit") == 1
    old = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD~1"], stdout=subprocess.PIPE,
                         check=True).stdout.decode().strip()
    upd = ("refs/heads/main %s refs/heads/main %s\n" % (sha, old)).encode()
    assert pii("pre-push", "origin", cwd=repo, input=upd).rc == 1
    delete = ("(delete) %s refs/heads/old %s\n" % (zero, old)).encode()
    assert pii("pre-push", "origin", cwd=repo, input=delete).rc == 0


@pytest.mark.checks("pii/pre-push-url")
def test_pre_push_to_a_url_scans_only_new_commits(pii, repo, tmp_path):
    # Pushed to a URL, git passes the URL instead of a remote name: commits
    # on any remote's tracking refs are known, not the whole history.
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    commit(repo, {"old.md": "Jens Hansen\n"})   # already pushed history
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")
    commit(repo, {"new.md": "clean\n"})
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], stdout=subprocess.PIPE,
                         check=True).stdout.decode().strip()
    line = ("refs/heads/topic %s refs/heads/topic %s\n" % (sha, "0" * 40)).encode()
    r = pii("pre-push", posix(remote), cwd=repo, input=line)
    assert r.rc == 0, out(r)


@pytest.mark.checks("pii/pre-push-ref-name")
def test_pre_push_checks_the_branch_name(pii, repo, tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], stdout=subprocess.PIPE,
                         check=True).stdout.decode().strip()
    line = ("refs/heads/fix-for-jens-hansen %s refs/heads/fix-for-jens-hansen %s\n"
            % (sha, "0" * 40)).encode()
    r = pii("pre-push", "origin", cwd=repo, input=line)
    assert r.rc == 1 and "ref name <ref>: denylist entry 1" in out(r)


# --- the denylist's presence -------------------------------------------------

@pytest.mark.checks("pii/no-denylist")
def test_no_denylist_warns_locally_and_fails_when_required(pii):
    r = pii("text", "t", input=b"clean\n", deny="")
    assert r.rc == 0 and "general patterns only" in r.err.decode()
    r = pii("--require-denylist", "text", "t", input=b"clean\n", deny="# only a comment\n")
    assert r.rc == 1 and "refusing to pass" in r.err.decode()


@pytest.mark.checks("pii/env-denylist")
def test_denylist_from_the_environment():
    r = call_main(pii_check.main, ["--require-denylist", "text", "t"],
                  env={"PII_DENYLIST": "Jens Hansen\n", "PII_DENYLIST_FILE": None},
                  input=b"jens hansen\n")
    assert r.rc == 1 and "denylist entry 1" in r.out.decode()


@pytest.mark.checks("pii/usage")
def test_usage(pii):
    assert pii().rc == 2
    assert pii("bogus").rc == 2
    assert pii("text").rc == 2


@pytest.mark.checks("pii/git-error")
def test_git_error_exits_2(pii, repo):
    assert pii("range", "no-such-rev..HEAD", cwd=repo).rc == 2


# --- the repo itself -----------------------------------------------------------

@pytest.mark.checks("pii/hook-executable")
def test_hook_is_committed_executable():
    r = subprocess.run(["git", "-C", str(REPO), "ls-files", "-s", ".githooks/pre-push",
                        "scripts/pii-check.sh"], stdout=subprocess.PIPE, check=True)
    modes = [line.split()[0] for line in r.stdout.decode().splitlines()]
    assert modes == ["100755", "100755"], modes


# --- the boundary ----------------------------------------------------------------

# The cases that also run through pii-check.sh (bash, py-run.sh, Python's
# stdin, stdout and stderr), in both modes. It is the pre-push hook, on Git
# Bash too, so it keeps more of them than the plugin's scripts: each covers
# something the boundary can break that the in-process run can't see.
BOUNDARY = [
    # A finding: exit 1 on stdout, the term itself never printed.
    ("refusal", test_text_mode_never_prints_the_term),
    # Clean: exit 0.
    ("clean", test_text_mode_clean),
    # Non-ASCII in the denylist file and on stdin: the encodings.
    ("non-ascii", test_text_mode_non_ascii),
    # The hook's own mode: ref lines on stdin, git started from the script.
    ("pre-push", test_pre_push_new_branch_and_update),
    # A path as the remote (a push to a URL): Git Bash's path conversion.
    ("pre-push-url", test_pre_push_to_a_url_scans_only_new_commits),
    # The warning on stderr with exit 0, and the refusal without a denylist, exit 1.
    ("no-denylist", test_no_denylist_warns_locally_and_fails_when_required),
    # Usage errors: exit 2, which the hook treats as a block too.
    ("usage", test_usage),
]


@pytest.mark.parametrize("test", [pytest.param(t, id="pii/boundary-" + n) for n, t in BOUNDARY])
def test_boundary(test, request, pii):
    """The chosen cases through pii-check.sh, whatever --e2e says: same
    assertions as in-process."""
    rerun(request, test, pii=functools.partial(pii, launcher=True))
