# Development

Changing wiki-tools itself. The decisions behind the code are in `docs/adr.md`; plans are indexed in `docs/roadmap.md`, detailed ones in `docs/plans/`; the files are listed in `docs/layout.md`.

## Workflow

Edit this repo in an agent session opened in the clone, Claude Code or Copilot CLI ("Agents", below). The `wiki` plugin isn't enabled here, so the guards don't get in the way.

0. Once per clone, switch on the personal-data check: `git config core.hooksPath .githooks` ("Personal data", below). `run-tests.sh` says so while it is off. Once per clone and per worktree, make the dev tools' venv: `uv sync --locked` ("Dev environment", below).
1. Work on a branch. Every change to a script, a hook or a wrapper comes with a test: a case in a `tests/test_*.py` module, or a guard fixture in `tests/fixtures/<push|guard>/<pass|block>-<case>.json` (with a `.msg` beside it for the exact message).
   - **`hooks.json` and the scripts it launches move apart in the cloud.** A cloud session updates the plugin's files at its start but runs the snapshot's `hooks.json`, read before the update, until the environment's snapshot is rebuilt (up to about seven days; `docs/adr.md`, 19). So a change to `hooks.json` must keep working with the previous `hooks.json`'s launch lines for a week: a script it launches keeps its name, arguments and output contract, or the old line still finds something that works. The guard fails closed, so a mismatch there blocks calls; it never leaves a session unguarded.
2. `bash tests/run-tests.sh` must pass. A change to a launcher or another `.sh` file also needs `bash tests/run-tests.sh --e2e`, which runs most in-process tests through the launchers ("Tests", below). `bash tests/run-tests.sh -k guard -x` runs a selection (pytest only). The modules run in parallel (pytest-xdist); `-n 0` runs serially.
3. Lint (below), commit, push the branch and open a pull request.
4. After the merge, on each machine: `git pull`, then start a new wiki session or run `/reload-plugins`.

### Recording a decision

A change gets a new decision in `docs/adr.md` only when it sets a rule of its own that code, tests or contributors will follow and no existing decision covers: a new mechanism, guard check, dependency, layer or way of working. A change that applies, extends or narrows an existing decision edits that decision in place, keeping its number; the rule it changes goes in the decision, the history in the commit. A type's or reader's details go in its `SOURCE.md`, how-to in the `docs/` page, not in the ADR. Keep each decision to a 1–2 sentence **Decision**, short **Why** and **Consequences**, about 200 words, and add it to the index. Numbers are consecutive; other files cite them as `docs/adr.md, N` (`tests/test_adr_refs.py` checks each one).

## Running the plugin from a clone

To try changes in your wikis, run the plugin from your clone instead of the GitHub install. Clone wherever you like; nothing depends on the path.

```bash
git clone https://github.com/draitchbar/wiki-tools.git ~/src/wiki-tools
claude plugin marketplace add ~/src/wiki-tools     # registers the marketplace only
```

In each wiki, enable the plugin without installing it:

```bash
claude plugin enable wiki@wiki-tools --scope project   # adds it to enabledPlugins in .claude/settings.json
```

Not `claude plugin install`: it also writes a copy to `~/.claude/plugins/cache/`, and a session can start from that stale copy instead of the clone (seen 2026-11-20 on Windows, until `/reload-plugins`). `enable` writes no copy and keeps the rest of the settings file (checked 2026-11-21 on Linux, Claude Code 2.1.330).

Claude Code then runs the plugin straight from `plugins/wiki/`, so **uncommitted edits are live in every wiki at once**, guard included, and a running wiki session mixes skills read at its start with scripts read at each call. The session-start status in a wiki says so when `plugins/wiki/` has uncommitted changes. After changing or pulling the plugin, restart `claude` in each wiki or run `/reload-plugins` there.

## Pull requests and CI

`main` changes only through pull requests. CI (`.github/workflows/ci.yml`) runs lint and the tests, normally and with `--e2e`, on Linux and Windows; Claude reviews each pull request (`.github/workflows/claude-review.yml`).

Once the review has no blocking finding open, its summary comment starts with a **reviewer guide** for the person who approves, in sections: the goal, a description of how the pull request reaches it, a table of the blast radius (`none`, `contributors`, `one source`, `all wikis`, `guard` or `irreversible`), the risk of a bug and the cost of maintenance, what to focus on, and a demo. A title or description that doesn't match the diff is a blocking finding, so the guide waits until it is fixed. It is written once and again only when a push changes it; until then the comment says the guide is unchanged or withheld. The guide is the review agent's reading of the diff, not a check: it says what it did not assess, and it never advises on merging. Why: `docs/adr.md`, 14.

Lint must be clean before committing:

```bash
bash scripts/dev-lint.sh
```

It runs what CI's lint job runs, each step even after one fails, and names the failed ones at the end: `ruff check .` (Python, `ruff.toml`), `mypy` (Python types, `mypy.ini`), `shellcheck -S warning` on every tracked `*.sh` (`.shellcheckrc`), and no CRLF in any committed file (`git ls-files --eol`, so a Windows checkout's `core.autocrlf` doesn't count). The tools come from `.venv` ("Dev environment"). mypy runs from the repo root and checks the files `mypy.ini` lists, all strict; ruff's `ANN` rules keep every function annotated (`tests/` excepted). Why: `docs/adr.md`, 15. Like ruff and pytest it is a dev tool only; the plugin never imports it. Annotations in the plugin's Python follow `AGENTS.md`'s run-time rule: `from __future__ import annotations` everywhere; in the guard's modules `typing` only under `if TYPE_CHECKING:`, so a hook never pays for importing it (about 3 ms); elsewhere a plain `from typing import ...`.

Keep LF line endings everywhere (`.gitattributes`).

## Dev environment

The dev tools (pytest, pytest-xdist, ruff, mypy, shellcheck-py) are the `dev` dependency group in `pyproject.toml`, locked with hashes in `uv.lock`, and installed into a `.venv` in the clone (gitignored) by uv. The plugin never uses them: it is standard library only. Why: `docs/adr.md`, 15.

- **Prerequisites:** Python 3.11 or later and uv 0.13.7 or later, both installed by you ([uv's installation page](https://docs.astral.sh/uv/getting-started/installation/); a distribution's package may be older). Python: on Linux your distribution's `python3`; on Windows the python.org installer.
- **Setup:** `uv sync --locked`, once per clone and per worktree (a worktree has no `.venv`; uv fills it from its cache). `uv sync --locked --python 3.11` makes it on a given Python. `--locked` fails when `uv.lock` doesn't match `pyproject.toml`, instead of quietly re-resolving.
- **Stale:** `run-tests.sh` and `dev-lint.sh` check `.venv` against `uv.lock` first (`uv sync --locked --check`, offline, no install) and stop when it is missing or out of date, with the command to run, usually `uv sync --locked` (after a pull that changed `uv.lock`, say).
- **Downloads off:** uv never downloads a Python here (`python-downloads = "never"` in `pyproject.toml`; CI sets `UV_PYTHON_DOWNLOADS=never` too), and installs wheels only (`no-build`). Don't set `UV_PYTHON_DOWNLOADS` yourself (it overrides the file) or `UV_PROJECT_ENVIRONMENT` (the scripts use `.venv` and refuse it).
- **Never `uv run`** in scripts, hooks, docs or by hand: it syncs implicitly. The scripts call `.venv`'s tools directly, without activation.
- **Changing a tool:** edit the `dev` group in `pyproject.toml`, run `uv lock`, commit both files. **A version bump:** `uv lock --upgrade` (or `--upgrade-package <name>`), run the tests and lint, commit `uv.lock`. A bump of uv itself: `required-version` in `pyproject.toml` and `version:` under `setup-uv` in `ci.yml` together (a test checks they agree).
- **Outside the lock:** `WIKI_TOOLS_DEV_VENV=off` makes both scripts take the tools from PATH (`run-tests.sh` then finds Python as the plugin's scripts do, and needs pytest installed there), and they say so. For a session without uv only; a report from such a run says it ran outside the lock.

## Agents

The repo is developed with Claude Code and with GitHub Copilot CLI; every change must work in both (`CONTRIBUTING.md`). Their instructions and skills are written once: `CLAUDE.md` is the one line `@AGENTS.md`, `AGENTS.md` imports `CONTRIBUTING.md`, and both agents load skills from `.claude/skills/`. Copilot reads `AGENTS.md` and `CLAUDE.md` both, so it sees the rules twice; that is harmless. Why this layout: `docs/adr.md`, 9. The repo's skills: `/new-source-type`; `/fix-issues-ai` (issues to pull requests) and `/implement-feature-ai` (a goal to one pull request), which share `docs/agent-pr-flow.md` (`docs/adr.md`, 13).

What both support, and so what agent files may use (Copilot CLI 1.0.112, tested 2026-11-15):

| Feature | Claude Code | Copilot CLI |
|---|---|---|
| `@path` imports in `CLAUDE.md` and `AGENTS.md` | yes | yes |
| Skills in `.claude/skills/<name>/SKILL.md`, `name` and `description` | yes | yes |
| `$ARGUMENTS` in a skill | yes | yes |
| `argument-hint` | shown | not shown: say the arguments in `description` too |
| `disable-model-invocation: true` | enforced | enforced at the `skill` tool in 1.0.112, for plugin and project skills, in every approval mode (retested 2026-11-18; the earlier test found it ignored). In autopilot with allow-all the model once read the skill file and followed it by hand; the guard line (`AGENTS.md`, "Agents") covers that case |
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

Also seen: the input has Claude's field names (`hook_event_name`, `session_id`, `cwd`, `tool_use_id`, `tool_name`, `tool_input`), and a PowerShell command arrives as `tool_name: "Bash"`; the main session sends no `agent_id`; a hook that errors denies the call even without `onFailure: "block"` (fail-closed). So a guard hook for both agents needs the JSON deny reply rather than exit 2 alone, Git Bash named explicitly on Windows, and a trusted folder. The Linux results, subagents included, are in the next table.

The wiki plugin in both clients, from the spike of the Copilot plan (`docs/plans/copilot-wiki-support.md`, step 1): Copilot CLI 1.0.112 and Claude Code 2.1.326 on Linux, 2026-11-17, both with `claude-sonnet-5.5` (Copilot also with `gpt-6.1-sol`, for its patch tool), in a disposable container (`tests/live/`) with a capture hook beside the real guard. The container has none of the dev tools and stays outside `uv.lock`: the repo's own tests and lint are not run there (with tools installed by hand, `WIKI_TOOLS_DEV_VENV=off` runs them from PATH). The payloads, normalized, are in `tests/fixtures/clients/` (for reference; no test runs them yet), one line per run in `tests/live/results.md`. Copilot CLI 1.0.113 reviewed it; rows marked "(review)" come from that review and Copilot's docs, not from a run. Windows was not part of it.

| | Claude Code | Copilot CLI |
|---|---|---|
| Discovery (`--plugin-dir`) | 8 skills as `wiki:<name>`, 2 agents, all hook events | 7 skills, named without `wiki:`: `research` is rejected (its description's `mode: research` is invalid YAML); agents load, `effort:` ignored with a warning |
| Activation from the wiki's `.claude/settings.json` (`enabledPlugins`, `extraKnownMarketplaces` with a directory source) | only once the marketplace is registered for the user (`claude plugin marketplace add`); in `-p` the project file alone loads nothing | the project file alone, in a trusted folder. `-p` in a folder not saved as trusted: the plugin silently doesn't load, no hooks, no warning; an interactive start asks, and No exits (review). `--plugin-dir` hooks run without trust |
| Unrelated folder, wiki-tools itself | no plugin hooks | no plugin hooks |
| Plugin files; plugin data | the directory itself; `~/.claude/plugins/data/<plugin>-<marketplace>` | the directory itself; `~/.copilot/plugin-data/<marketplace>/<plugin>` (`--plugin-dir`: `_direct/<hash>`) |
| Hook environment | `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, `CLAUDE_PROJECT_DIR`; command run by `/bin/sh -c` (dash) | the same three, plus `COPILOT_PLUGIN_ROOT`, `COPILOT_PLUGIN_DATA`, `COPILOT_PROJECT_DIR`, `PLUGIN_ROOT`, `COPILOT_HOOK_DIR`, `COPILOT_CLI=1`; command run by bash |
| Tool names in hooks | `Bash`, `Read`, `Grep`, `Glob`, `Write`, `Edit`, `Agent`, `Skill` | the same names for its bash, view, grep, glob, create, edit, apply_patch and task tools; also `skill`, `stop_bash`, `tool_search_tool`. `read_bash` fires no hook; `write_bash` (input to a running shell) isn't offered, neither in `-p` nor in an interactive autopilot session (the model's tool search found none); `task_complete` (autopilot's end) fires PreToolUse. Also `list_bash`, `web_fetch`, `web_search`, `sql`, `store_memory`, `ask_user`, `read_agent`/`write_agent`, `task_complete` and MCP tools as `<server>-<tool>`, with a separate `preMcpToolCall` event (review) |
| `tool_input` fields | `file_path`; Write `content`; Edit `old_string`/`new_string`; Grep `path` | `path`; Write `file_text`; Edit `old_str`/`new_str`; Grep and Glob `paths`, a string or a list. A multi-file patch arrives as `Edit` with `tool_input` a string (the patch, absolute paths; Add, Update and Move seen), before Copilot parses it. Async shell: `mode: "async"`, `shellId` |
| Today's guard on those | as designed | every Write and Edit refused: "Write call without file_path" (fail closed). Grep and Glob `paths` into a source only subagents may read (`agent_only`) **passed** from the main session, where Claude's `path` is refused. The guard after #24 (every tool checked, unknown names refused) also refuses Copilot's `skill`, `stop_bash` and `tool_search_tool`, and its patch as unparseable (run against the recorded payloads) |
| Several hooks on one call | run in parallel | run one after another, in order; the first deny stops the rest |
| Subagents | no `agent_id` in the main session; a child's calls carry `agent_id`, `agent_type` | the same (a synchronous child; background and nested not tried), plus `parent_agent_id`, and the child's `session_id` is its `agent_id`. SubagentStart is camelCase (`sessionId`, `transcriptPath`, `agentName`) without `hook_event_name` |
| Hook exits 2 (the command allowed by `--allowedTools`/`--allow-tool`) | denied; stderr reaches the model | denied; the reason doesn't reach the model |
| Hook exits 1, or its script exits 127 (a missing hook interpreter not tried) | **the command runs** | denied ("hook errored") |
| Claude's JSON deny | denied; the reason reaches the model | the same |
| Hook timeout (killed at its `timeout`) | **the command runs**; with `onFailure: "block"` denied | **the command runs**, `onFailure: "block"` or not |
| JSON deny of a subagent's call | denied; the reason reaches the model | the same |
| `--autopilot --allow-all` | | the plugin's hooks still run: the real guard refused `git push` and a write to `.claude/settings.json`, main session and subagent; refs and file unchanged |
| `--assisted-approval` (a safety judge approves instead of asking) | | the guard still refuses first, and the judge doesn't overrule it. Without the guard, the judge approved `git push`, a write to `.claude/settings.json` and a write into a source root, and refused a harmless wiki page; no extra premium requests, about 5 s per judged call (`-p`, `tests/live/results.md`) |
| SessionStart context | plain stdout, or `hookSpecificOutput.additionalContext` | only a top-level `additionalContext`. One JSON object with both keys works in both |
| Resume | SessionStart again (`source: resume`); old context stays in the history | SessionStart again (`source: resume`), `startup`-matcher hooks too (whether matchers are ignored or mapped is open; a new session's `source` is `new`, Claude's `startup`); the new context replaces the old. `--resume` refuses `--trust-folder` |
| Compaction | PreCompact, then SessionStart (`source: compact`) (`/compact`; automatic not tried) | PreCompact, no SessionStart; the SessionStart context survived two automatic compactions |
| Skill bodies | `` !`cmd` `` runs, `${CLAUDE_PLUGIN_ROOT}` filled in | loaded as written: no `` !`cmd` ``, no substitution (the model found the scripts from the skill's own path). `allowed-tools` ignored, not an error: the wrapper still asks |
| Cost per tool call | capture hook ~7 ms, guard 20-33 ms | the same per hook, added up (serial) |
| Reliability | | 5 of about 45 starts crashed before any hook (4 SIGSEGV, 1 "Failed to load package index"); rerun, once by `run.sh`, the others by hand |

On Windows (Copilot CLI 1.0.113 from PowerShell, the same day, plan step 1.7): the agent's shell is PowerShell (tool `powershell`, sent to hooks as `Bash`), and plugin hook commands run in PowerShell too; `"shell": "bash"` and `COPILOT_BASH_PATH` change neither, and a command starting with `bash` gets WSL's `bash.exe` from PATH. So today's guard hook, written in bash, fails to parse and Copilot refuses every tool call there. A hook's `powershell` field, which Copilot runs instead of `command`, can start Git Bash by its path (about 340 ms per hook). `COPILOT_GITHUB_TOKEN` doesn't reach the agent's shell.

Also seen: a claude.ai login applies its organization's synced plugins and settings even to a fresh configuration folder; Copilot connects its GitHub MCP server by default, whose tool calls the spike didn't exercise.

With Copilot CLI:
- Trust the folder when asked; in this repo don't use `--allow-all`/`--yolo` (the wikis' Copilot setup is in the plan), and never `--enable-all-github-mcp-tools` here: the built-in GitHub MCP server is read-only by default, and its write tools would commit on GitHub, past the push hook. The same goes for `/delegate`.
- `/instructions` shows the instruction files it loaded, `/skills list` the skills.

## Tests

The tests are pytest modules (`tests/test_*.py`, helpers in `tests/conftest.py`, `tests/codebase_story.py` for the three codebase modules and `tests/save_wiki.py` for the three save modules). They never call a real source CLI or account; they use fakes in `tests/sources/<type>/`. Recorded outputs (`tests/fixtures/*/*.out`) are rewritten with `bash tests/run-tests.sh --record`; review the diff. How the tests are built, and why: `docs/adr.md`, 6.

A test pyramid:
- **In-process, every case.** The full behaviour of a script, hook or guard is tested in-process, through its module's `main`: fast, and one test per case.
- **The boundary, a few chosen cases.** `--e2e` and the end-to-end tests check only the process boundary, with a few cases per launcher or script, each with a one-line reason: success, a refusal and its exit code, the stdout/stderr split, quoting and non-ASCII text, Windows and Git Bash specifics. The guard's are `BOUNDARY` and the `hooks.json` tests in `tests/test_guard.py`, run through the launcher in both modes; the guard, save and sources run their other cases in-process under `--e2e` too.
- **A new test goes in-process** unless it tests the boundary itself; a boundary case says which boundary risk it covers.

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
