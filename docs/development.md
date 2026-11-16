# Development

Changing wiki-tools itself. The decisions behind the code are in `docs/adr.md`; plans are indexed in `docs/roadmap.md`, detailed ones in `docs/plans/`; the files are listed in `docs/layout.md`.

## Workflow

Edit this repo in an agent session opened in the clone, Claude Code or Copilot CLI ("Agents", below). The `wiki` plugin isn't enabled here, so the guards don't get in the way.

0. Once per clone, switch on the personal-data check: `git config core.hooksPath .githooks` ("Personal data", below). `run-tests.sh` says so while it is off.
1. Work on a branch. Every change to a script, a hook or a wrapper comes with a test: a case in a `tests/test_*.py` module, or a guard fixture in `tests/fixtures/<push|guard>/<pass|block>-<case>.json` (with a `.msg` beside it for the exact message).
2. `bash tests/run-tests.sh` must pass (pytest needs installing once: `python -m pip install --user --upgrade pytest`, on Debian/Ubuntu `sudo apt install python3-pytest`). A change to a launcher or another `.sh` file also needs `bash tests/run-tests.sh --e2e`, which runs the in-process tests through the launchers. `bash tests/run-tests.sh -k guard -x` runs a selection (pytest only). With `pytest-xdist` installed (optional) the modules run in parallel; `-n 0` runs serially.
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

## Agents

The repo is developed with Claude Code and with GitHub Copilot CLI; every change must work in both (`CONTRIBUTING.md`). Their instructions and skills are written once: `CLAUDE.md` is the one line `@AGENTS.md`, `AGENTS.md` imports `CONTRIBUTING.md`, and both agents load skills from `.claude/skills/`. Copilot reads `AGENTS.md` and `CLAUDE.md` both, so it sees the rules twice; that is harmless. Why this layout: `docs/adr.md`, 10.

What both support, and so what agent files may use (Copilot CLI 1.0.112, tested 2026-11-15):

| Feature | Claude Code | Copilot CLI |
|---|---|---|
| `@path` imports in `CLAUDE.md` and `AGENTS.md` | yes | yes |
| Skills in `.claude/skills/<name>/SKILL.md`, `name` and `description` | yes | yes |
| `$ARGUMENTS` in a skill | yes | yes |
| `argument-hint` | shown | not shown: say the arguments in `description` too |
| `disable-model-invocation: true` | enforced | ignored: the skill's body starts with the guard line (`AGENTS.md`, "Agents") |
| Hooks and permissions in `.claude/settings.json` | yes | hooks read in a trusted folder; a deny's reason reaches the model only with Claude's JSON reply (below); permissions not read |

Copilot CLI's hooks, tested with a `PreToolUse` hook in `.claude/settings.json` (1.0.112 on Windows, a throwaway repo, one shell command per run):

| Hook | Result |
|---|---|
| Folder not trusted | Repo hooks skipped, with a warning; the command ran. |
| `"shell": "bash"`, command `bash hook.sh` | `shell` is ignored: `bash` came from PATH, on the test machine WSL's, with no distro. The hook failed and the call was denied as "hook errored". |
| Git Bash named explicitly, hook exits 2 | The hook ran, but the wrapping shell turned exit 2 into exit 1: denied only as an error. |
| The same, exit code passed through | Denied, "hook exited with code 2"; the hook's stderr reason doesn't reach the model. |
| Exit 0 with Claude's JSON (`hookSpecificOutput.permissionDecision: "deny"` and a reason) | Denied, and the reason reaches the model. |
| Exit 0, no output | The command ran. |

Also seen: the input has Claude's field names (`hook_event_name`, `session_id`, `cwd`, `tool_use_id`, `tool_name`, `tool_input`), and a PowerShell command arrives as `tool_name: "Bash"`; the main session sends no `agent_id`; a hook that errors denies the call even without `onFailure: "block"` (fail-closed). So a guard hook for both agents needs the JSON deny reply rather than exit 2 alone, Git Bash named explicitly on Windows, and a trusted folder. Still open: whether a Copilot subagent's calls carry `agent_id` (the guard uses it to tell subagents from the main session), and the same tests on Linux.

With Copilot CLI:
- Trust the folder when asked; don't use `--allow-all`/`--yolo`, and never `--enable-all-github-mcp-tools` here: the built-in GitHub MCP server is read-only by default, and its write tools would commit on GitHub, past the push hook. The same goes for `/delegate`.
- `/instructions` shows the instruction files it loaded, `/skills list` the skills.

## Tests

The tests are pytest modules (`tests/test_*.py`, helpers in `tests/conftest.py`). They never call a real source CLI or account; they use fakes in `tests/sources/<type>/`. Recorded outputs (`tests/fixtures/*/*.out`) are rewritten with `bash tests/run-tests.sh --record`; review the diff. How the tests are built, and why: `docs/adr.md`, 7.

## Personal data

The repo is meant to go public, and a push to a public repo can't be taken back: a PR's commits stay reachable after the branch is deleted, squashed or force-pushed, and only GitHub Support can purge them. So nothing personal may reach a commit, a branch name, a tag or a PR's title and description: real names and emails, employer and work details, addresses and place names, hostnames and user folders, third parties, real file names from personal accounts, real names of personal wikis. Test data uses made-up names and reserved domains (`example.com`, `.invalid`, `/home/u`).

`scripts/pii-check.sh` finds them in three places:
- **`.githooks/pre-push`**, the first line: every commit, ref name and tag being pushed. Switched on per clone with `git config core.hooksPath .githooks`; never bypassed with `--no-verify`. It only runs where it is switched on: not in the GitHub web UI, nor in a fresh clone (an agent's cloud session included) until the line above has run.
- **CI** (`.github/workflows/pii.yml`): a PR's commits, title, description and branch name; and the commit GitHub creates on `main` at the merge (detection only).
- **The Claude review**, advisory, for what patterns miss.

Its rules: committed general patterns (emails other than GitHub noreply, `noreply@anthropic.com` and test domains; user folders; private hostnames; Claude session links), and a private denylist of known terms that is never committed: `~/.config/wiki-tools/pii-denylist.txt` locally (one term per line, `#` comments; the master copy is kept outside the repo), the secret `PII_DENYLIST` in CI, where a missing denylist fails the check. Matching ignores case, the Danish letters' spellings and separators between words. A hit names the place and the rule or denylist entry number, never the text.

Commit identities must be GitHub noreply addresses (`git config user.email <id>+<user>@users.noreply.github.com`); the only other emails allowed in commits are `noreply@anthropic.com` (Claude's `Co-Authored-By`) and `noreply@github.com` (GitHub's merges). Copilot CLI's trailer uses a GitHub noreply address, so it passes. Commits and PRs carry no `Claude-Session:` trailer.

On a hit: fix the commit (`git commit --amend`, or `git rebase -i` for an older one) and push again. A hit that already reached GitHub: tell the owner; don't push a "fix" on top, which leaves the original in the PR.

```bash
bash scripts/pii-check.sh tree                 # every file of HEAD
bash scripts/pii-check.sh range main..HEAD     # the branch's commits
printf '%s\n' 'some text' | bash scripts/pii-check.sh text sample   # a text, e.g. before posting it
```
