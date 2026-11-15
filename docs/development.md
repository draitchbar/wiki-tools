# Development

Changing wiki-tools itself. The decisions behind the code are in `docs/adr.md`; plans are indexed in `docs/roadmap.md`, detailed ones in `docs/plans/`; the files are listed in `docs/layout.md`.

## Workflow

Edit this repo in a Claude session opened in the clone. The `wiki` plugin isn't enabled here, so the guards don't get in the way.

0. Once per clone, switch on the personal-data check: `git config core.hooksPath .githooks` ("Personal data", below). `run-tests.sh` says so while it is off.
1. Work on a branch. Every change to a script, a hook or a wrapper comes with a test: a case in a `tests/test_*.py` module, or a guard fixture in `tests/fixtures/<push|guard>/<pass|block>-<case>.json` (with a `.msg` beside it for the exact message).
2. `bash tests/run-tests.sh` must pass (pytest needs installing once: `python -m pip install --user --upgrade pytest`, on Debian/Ubuntu `sudo apt install python3-pytest`). A change to a launcher or another `.sh` file also needs `bash tests/run-tests.sh --e2e`, which runs the in-process tests through the launchers. `bash tests/run-tests.sh -k guard -x` runs a selection (pytest only).
3. Lint (below), commit, push the branch and open a pull request.
4. After the merge, on each machine: `git pull`, then start a new wiki session or run `/reload-plugins`.

## Pull requests and CI

`main` changes only through pull requests. CI (`.github/workflows/ci.yml`) runs lint and the tests, normally and with `--e2e`, on Linux and Windows; Claude reviews each pull request (`.github/workflows/claude-review.yml`).

Lint must be clean before committing:

```bash
ruff check .                                          # Python (ruff.toml)
git ls-files -z '*.sh' | xargs -0 shellcheck -S warning   # bash (.shellcheckrc)
```

Keep LF line endings everywhere (`.gitattributes`).

## Tests

The tests are pytest modules (`tests/test_*.py`, helpers in `tests/conftest.py`). They never call a real source CLI or account; they use fakes in `tests/sources/<type>/`. Recorded outputs (`tests/fixtures/*/*.out`) are rewritten with `bash tests/run-tests.sh --record`; review the diff. How the tests are built, and why: `docs/adr.md`, 7.

## Personal data

The repo is meant to go public, and a push to a public repo can't be taken back: a PR's commits stay reachable after the branch is deleted, squashed or force-pushed, and only GitHub Support can purge them. So nothing personal may reach a commit, a branch name, a tag or a PR's title and description: real names and emails, employer and work details, addresses and place names, hostnames and user folders, third parties, real file names from personal accounts, real names of personal wikis. Test data uses made-up names and reserved domains (`example.com`, `.invalid`, `/home/u`).

`scripts/pii-check.sh` finds them in three places:
- **`.githooks/pre-push`**, the first line: every commit, ref name and tag being pushed. Switched on per clone with `git config core.hooksPath .githooks`; never bypassed with `--no-verify`. It only runs where it is switched on: not in the GitHub web UI, nor in a fresh clone (a Claude cloud session included) until the line above has run.
- **CI** (`.github/workflows/pii.yml`): a PR's commits, title, description and branch name; and the commit GitHub creates on `main` at the merge (detection only).
- **The Claude review**, advisory, for what patterns miss.

Its rules: committed general patterns (emails other than GitHub noreply, `noreply@anthropic.com` and test domains; user folders; private hostnames; Claude session links), and a private denylist of known terms that is never committed: `~/.config/wiki-tools/pii-denylist.txt` locally (one term per line, `#` comments; the master copy is kept outside the repo), the secret `PII_DENYLIST` in CI, where a missing denylist fails the check. Matching ignores case, the Danish letters' spellings and separators between words. A hit names the place and the rule or denylist entry number, never the text.

Commit identities must be GitHub noreply addresses (`git config user.email <id>+<user>@users.noreply.github.com`); the only other emails allowed in commits are `noreply@anthropic.com` (`Co-Authored-By`) and `noreply@github.com` (GitHub's merges). Commits and PRs carry no `Claude-Session:` trailer.

On a hit: fix the commit (`git commit --amend`, or `git rebase -i` for an older one) and push again. A hit that already reached GitHub: tell the owner; don't push a "fix" on top, which leaves the original in the PR.

```bash
bash scripts/pii-check.sh tree                 # every file of HEAD
bash scripts/pii-check.sh range main..HEAD     # the branch's commits
printf '%s\n' 'some text' | bash scripts/pii-check.sh text sample   # a text, e.g. before posting it
```
