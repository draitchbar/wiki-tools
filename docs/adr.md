# Architecture decisions: the wiki plugin

The decisions behind how wiki-tools is built, and why. Plans and parked work are in `docs/roadmap.md`; how to use the plugin is in README.md and the pages it links. Other files cite a decision as `docs/adr.md, N`; when a change earns a new decision rather than an amendment: `docs/development.md`, "Recording a decision".

| # | Decision | In one line |
|---|---|---|
| 1 | One plugin, enabled per wiki, runnable from any clone | Everything under `plugins/wiki/`, enabled in each wiki, no fixed path. |
| 2 | Source-neutral skills and pluggable sources | Types and instances; the core names no source, server or tool. |
| 3 | The guard: a guardrail that fails closed | One hook checks every tool call, only for what settings rules can't express. |
| 4 | Python behind bash launchers | Python 3.11+ standard library, started by bash launchers that keep their names. |
| 5 | Codebase research | `/wiki:research` answers from code through capped Opus agents, with no code index. |
| 6 | Tests: pytest in two layers, in parallel | In-process and end-to-end layers, xdist by module, test modes as separate CI jobs. |
| 7 | Changes through pull requests, checked on both platforms | Lint and tests on Linux and Windows before every merge. |
| 8 | Public from a fresh history, with a personal-data check | No personal data anywhere; checked before the push and in CI. |
| 9 | Two coding agents, one set of rules | Claude Code and Copilot CLI read the same files. |
| 10 | Tool-neutral source types | A type lists operations; each instance binds the reader on its machine. |
| 11 | Reader binding: a skill and a machine-readable binding | `/wiki:bind-reader` tests the reader and drafts `reader` and `reader_deny`. |
| 12 | Unattended ingest defers its questions to a file | Never asks, never guesses; questions go to `open-questions.md`. |
| 13 | Agent pull request flows | `/fix-issues-ai` and `/implement-feature-ai` hand back pull requests, never merge. |
| 14 | The review writes a reviewer guide | The Claude review tells the approver where to look. |
| 15 | Dev tools in a locked venv, type-checked strictly | `uv sync --locked` into `.venv`; `mypy --strict` on the plugin's Python. |
| 16 | Functional style where it fits | Comprehensions for pure transforms, loops for the rest. |
| 17 | Connector names per surface come from a plugin table | Each connector rule is emitted under its local and its cloud name. |
| 18 | Saving to the wiki's remote through a core script | `save.sh` pushes to a pinned URL; the model never gets `git push`. |
| 19 | The plugin updates itself at the start of a cloud session | A `SessionStart` hook fast-forwards the cloud clone to `main`; the guard protects the clone. |

## 1. One plugin, enabled per wiki, runnable from any clone
**Decision.** wiki-tools is a local-directory marketplace with one plugin, `wiki`, enabled in each wiki's `.claude/settings.json`, never at user scope; everything the wikis need lives under `plugins/wiki/`, and nothing names a fixed clone path.

**Why.** The guards must apply only in wiki sessions, the clone must work wherever it lives on each machine, and Claude Code may run an installed copy of only the plugin folder.

**Consequences.**
- Skills and hooks name plugin files through `${CLAUDE_PLUGIN_ROOT}`; scripts find their own folder; the wikis' settings use path-free wildcard rules (`Bash(bash */sources/<type>/<script>.sh *)`).
- The shared schema is loaded by SessionStart hooks (`schema.sh`, one file per hook, each under the 10,000-character cap on hook context), not imported by a wiki's CLAUDE.md.
- The repo itself is edited in sessions where the plugin is off, so the guards don't get in the way.

## 2. Source-neutral skills and pluggable sources
**Decision.** The core (skills, schema, scripts, the guard, templates) knows nothing about any particular source or reader. A source is a **type**, whose contract is `SOURCE.md` (flat, bash-parseable frontmatter and prose per operation), and **instances**, one guard-protected file each in the wiki's `.claude/sources/instances/`, keyed by `/wiki:ingest`'s argument.

**Why.** New sources shouldn't need changes to the skills or the guard, and a wiki must be able to add a source of its own without a wiki-tools release.

**Consequences.**
- Standard types live in `plugins/wiki/sources/<type>/`; wiki-local types in the wiki's protected `.claude/sources/types/`, may ship wrappers and may not shadow a standard type. Promotion to standard happens in wiki-tools, with fixtures and tests.
- Every type is read-only by contract, plus narrowly declared bookkeeping writes (no standard type declares one). Operations: check, list new, fetch, optional mark ingested, cite and resolve citation. Each source declares its state (at least `last_checked`), stored generically in `raw/sync-log.md`. A key with state but no instance file is a manual key.
- A type whose read-only property tool permissions can't keep ships a wrapper with an allowlist of operations.
- The protected `.claude/sources/` tree is written only by the user: Claude drafts, `install-source-file.sh`, run in a terminal outside Claude, checks, shows the diff and installs.
- The test of neutrality: core may read any contract or instance key and act on it, but may not branch on a type, server or tool name, nor hold a list of them ("e.g." examples are fine). A reader's names and behaviour go in the type's `SOURCE.md`, the instance's binding, or a reader plugin. `tests/test_source_neutral.py` checks the core's code.
- Known exceptions: the shared reader-data file `sources/connectors.md` (17), read like a contract; two generic mechanisms with one user each, candidates for reader plugins: the dispatcher limit (11) and the folder snapshot (10); the guard's refusal of GitHub MCP tools (3), a protection, not a reader. Hosts are outside the rule: `save.py` calls GitHub's API for a `github.com` remote (18). User guides may name types.

## 3. The guard: a guardrail that fails closed
**Decision.** One PreToolUse hook, `guard.py`, sees every tool call (matcher `*`) and refuses what could write into a source, push past the user, or change the guard's own machinery; it fails closed. A protection goes into the wiki's permission rules when it can be expressed there reliably; a guard check is added only when it can't, and only when the harm justifies its upkeep.

**Why.**
- The sources must stay read-only and the guard machinery protected from the session it guards. Matching command text is not a security boundary, but it reliably stops accidental and straightforward misuse.
- Rules can't do what the kept checks do: a committed rule can't name the per-machine plugin folder; `Bash(...)` rules match a command's shape and miss `git -C x push`, `env …`, `sh -c` and `eval "git push …"` (checked 2026-11-19, `docs/guard.md`); rules don't see written content, apply to subagents alike (so can't express agent_only), and are static, while contracts change at hook time.
- Irreversible harm (`git push`, writes into a source) stays guarded by a deterministic check even where a rule also covers it. `git push` is checked first, so no later exception can let one through.
- A GitHub MCP server's write tools push past git (seen in a cloud session, 2026-11-24), and a list of them would keep growing, so every tool of a server whose name contains `github` is refused.
- Fail closed: a check that can't read its input or its contracts must not wave calls through.

**Consequences.**
- What it blocks, the exceptions (plain calls of core scripts and contract wrappers), the known false positives and the cost per call are in `docs/guard.md`.
- A new built-in tool is refused until `hookjson.py` classifies it. While any contract or instance can't be used, every shell and write call is refused except read-only diagnostics.
- A contract's `forbidden_tools` for MCP tools become deny rules through `sources.sh settings`, with no guard check; no second-layer rules were added.
- Left to Claude Code's permission prompt on purpose: `git config` and `git -c` (the keys that run commands are a long, growing list), and a Monitor WebSocket watch.
- The user's own `~/.claude/skills` is not protected, since a source's reader may live there; accepted, as it is outside every wiki.
- `save.sh` is a second push path, `save.sh --allow` gets an "ask" reply, and `gh` with a subcommand that writes past git is refused (18).
- A plugin that runs from `plugins/wiki` of a git clone has the whole clone protected, as the plugin folder is (19).
- A guard must never be weakened without saying so in the commit message.

## 4. Python behind bash launchers
**Decision.** The guard and the scripts' work are Python 3.11 or later, standard library only. Hooks run only through `py-launch.sh`, which fails closed; scripts keep their `.sh` names as launchers and run their module through `py-run.sh`.

**Why.** On Windows every process start in Git Bash costs about 25 ms and a Python start 100–250 ms, so pipelines of `sed`, `awk` and `grep` took seconds per call; one Python process does the same work in milliseconds. The names stay because contracts, settings and the guard name them. PowerShell would have meant a second implementation and platform-specific skills.

**Consequences.**
- `py-launch.sh` finds Python (a cache named after the floor, `python-3.11`, so a cache from an older floor is never read; rejects the Windows Store alias and older versions), runs it with `-I -S -X utf8`, and turns any exit but 0 or 2 into a block. `guard.py` checks the version first and blocks with "Python 3.11 or later is needed"; it parses on an old Python up to that check.
- Launchers keep what touches the terminal or the shell (`install-source-file.sh`'s paste and prompt, `decode-download.sh`'s argument checks, `sync-status.sh`'s exit 0). Bash also stays for `lib-source.sh`, `schema.sh`, `ocr.sh`, `local-folder/read.sh` (the model for local types) and the `codebase` wrappers.
- On Windows, Python gets its arguments unconverted (`MSYS2_ARG_CONV_EXCL='*'`) and refuses Git Bash mount paths; callers pass `pwd -W` paths.
- Annotations cost nothing at run time: `from __future__ import annotations`; in the guard's modules `typing` only under `TYPE_CHECKING` (importing it adds about 3 ms to every guard start; a test checks it stays out).
- `scripts/pii_check.py` follows the same rules behind `pii-check.sh`.
- No other Python without a decision recorded here. Python is a prerequisite for every wiki; `/wiki:init` checks for it. Users on an older Python get a blocking guard until they upgrade.

## 5. Codebase research
**Decision.** A `codebase` instance points at a local git clone and is a research type: `/wiki:ingest` refuses it, and `/wiki:research <key> "<question>" [--critique] [--worktree]` answers on demand through `wiki:source-researcher` agents on Opus at `medium` effort, with no code index. The main session reasons and never reads the code (`agent_only`).

**Why.** The code is too large for the main session's context and changes too fast to copy into the wiki; capped agents keep the context small, and citations at a pinned SHA keep claims checkable. Cheaper settings (Sonnet, Opus at low effort) gave thinner and some wrong answers; a cheaper setup must cost at least 15% less at equal quality. Search is too small a share of research time for an index to reach the bar of 25% less time or cost.

**Consequences.**
- At most 10 agents per step and 5 steps per run, then the session asks. Agents read through `git.sh` (read-only, at a pinned SHA; the working tree only with `--worktree`) and `gh.sh` (behind the instance's `gh_user`). `git fetch` is allowed; clone and worktree only after asking.
- Findings merge into existing pages, cited with path, lines and SHA. `--critique` adds an independent `wiki:critic`, at most 3 rounds. Staleness is checked when the wiki answers from cited code (`drift`).
- Run notes live in `~/.cache/wiki-sources/<wiki>/<key>/runs/`, re-verified before reuse on another SHA.
- If an index ever comes, it is a lead generator only, built in the cache, never in the clone; `setup.sh <key> graph` and the `git.sh` operations `graph-query`, `graph-path` and `graph-explain` are reserved for it.

## 6. Tests: pytest in two layers, in parallel
**Decision.** The suite is pytest, started with `bash tests/run-tests.sh` from the repo's `.venv` (15), in two layers: in-process through each module's `main(argv)`, and end to end through a real bash (Git Bash on Windows); `--e2e` runs the in-process tests through the launchers. Modules run in parallel with pytest-xdist, one module per worker (`--dist loadfile`), and CI runs the plain and `--e2e` modes as separate jobs.

**Why.** In-process tests are fast and free of shell quoting; the end-to-end layer and `--e2e` cover the process boundary, where Windows differs. The Windows jobs set how long every PR waits; most modules run one ordered story in a module-scoped fixture, which xdist's default distribution would rerun on every worker.

**Consequences.**
- `--e2e` is required before a commit that touches a launcher or another `.sh` file. Tests use fakes (`tests/sources/<type>/`), never a real source CLI or account. Recorded outputs are compared byte for byte and rewritten with `--record`.
- One normaliser (`norm`) maps every spelling of a path to `@TMP@` and `@PLUGIN@`. Arguments to bash go NUL-separated through a file to a fixed driver, since Git Bash re-parses its command line on Windows; there a restricted `PATH` still has Git's folders in front.
- The required checks are `test (<os>, plain)` and `test (<os>, e2e)`. Print debugging and `--pdb` need `-n 0`; `--check-names` runs serially.
- The slowest story bounds a run: a story that grows past the others is split into modules (as `test_codebase*.py`, over `tests/codebase_story.py`, and the save tests over `tests/save_wiki.py`, which builds each wiki once and copies it per test). In CI, `run-tests.sh` adds `--durations=20` and the summary lists each module's summed time; no time limit is checked.

## 7. Changes through pull requests, checked on both platforms
**Decision.** `main` changes only through pull requests. CI (`ci.yml`) runs lint (`bash scripts/dev-lint.sh`: ruff, mypy, shellcheck, no CRLF) and the suite, plain and with `--e2e`, on Linux and Windows; Claude reviews each pull request (`claude-review.yml`).

**Why.** Every script must run under Linux bash and Git Bash on Windows, and most Windows problems only show on Windows.

**Consequences.** Lint must also be clean before committing, through the same script. Line endings are LF everywhere (`.gitattributes`). Real use in a wiki is still checked by hand for changes that affect sessions.

## 8. Public from a fresh history, with a personal-data check
**Decision.** The public repo started from one commit of the cleaned files; the earlier history, which holds personal data, stays private. Nothing in the repo, its commits, branches, PRs or issues carries personal data, and `scripts/pii-check.sh` checks it in a pre-push hook and in CI. MIT licence; issues and pull requests are for collaborators, who push branches to the repo, not to forks.

**Why.** A push to a public repo can't be taken back: pull request refs survive deleted branches and force pushes, and forks and clones keep everything. So the check runs before the push where it can, and CI catches the rest.

**Consequences.**
- Three layers: the check (committed patterns plus a private denylist, `PII_DENYLIST` in CI; a hit names its place and entry number, never the term); `.githooks/pre-push`, switched on per clone with `git config core.hooksPath .githooks`; and CI (`pii.yml`, a required check, plus an advisory section in the review). Rules: `docs/development.md`, "Personal data", and `CONTRIBUTING.md`.
- The `main` ruleset requires a PR and the checks, allows squash merges only, blocks force pushes and deletion, with no bypass. Secret scanning and push protection are on.
- The PII job and the review run with the secrets on a PR's own workflow code, so the owner reviews every change to `.github/workflows/` and the check. Edits in the GitHub web UI skip the hook; issues and comments aren't scanned. A clone made before the release must never push here.

## 9. Two coding agents, one set of rules
**Decision.** The repo is developed with Claude Code and with GitHub Copilot CLI, and rules and skills are written once for both: `CONTRIBUTING.md` holds the policy, `AGENTS.md` imports it and adds the code and agent rules, `CLAUDE.md` is the one line `@AGENTS.md`, and skills live in `.claude/skills/`. No file only one agent reads, no symlinks, no agent hooks or committed permissions.

**Why.** Collaborators may use either agent, and rules kept in two places drift. The `@` import is the one mechanism both document (a symlink fails on Windows, where `core.symlinks` is often off). `CLAUDE.md` stays because older or telemetry-off Claude Code sessions read only it, and `claude-review.yml` names it. Enforcement stays where both agents meet it: the pre-push hook, CI and the review.

**Consequences.**
- `tests/test_agent_files.py` checks the layout. Copilot loads the rules twice; accepted.
- Copilot's coding agent, `/delegate` and GitHub MCP write tools are not used, since they commit on GitHub past the push hook (narrowed for sessions without `gh`, 13).
- Copilot enforces `disable-model-invocation`, but a model can still read a refused skill and follow it by hand, so a manual-only skill opens with a line telling the agent to stop unless the user typed the command.
- What both agents support, and how Copilot runs hooks (a guard hook for both would need Claude's JSON deny reply, a trusted folder, and on Windows a `powershell` field): `docs/development.md`, "Agents".

## 10. Tool-neutral source types
**Decision.** A type whose reader is a tool on the user's machine is `access: tools`: its contract lists the operations it needs (`required`, `recommended` or `optional`) and names, allows and denies no tools; each instance binds a reader with `/wiki:bind-reader` (11). The standard types `jira`, `google-drive`, `ms-teams` and `gmail` are tool-neutral, like `onenote` and `proton-files`.

**Why.** The contracts named one connector's tools, so when the claude.ai Atlassian connector was replaced, every Jira wiki stopped until the contract changed (2026-11-19); another connector version, server, CLI or reader plugin would each have needed a new type. What a type defines (scopes, cursor, citations) doesn't depend on the tool; which tool reads the source is a fact about the machine.

**Consequences.**
- The readers seen working, their operation names, the write tools to deny and their quirks are notes in each type's `SOURCE.md` (`## Bind`, Caveats), not rules.
- A weaker guardrail until an instance is bound: `sources.sh settings <type>` gives no reader rules, and the denies come from each instance's `reader_deny`. An unbound instance can't ingest: Check starts `/wiki:bind-reader`, which has the user add the denies before any test call.
- Read-only rests on the connection's scope and those denies; with no **show scope**, Check reports it as not verified.
- A tool-neutral contract can't declare a write, so Gmail is read-only and keeps date state plus the thread IDs in `raw/sync-log.md` instead of a label (the `gmail` contract has the rules).
- Generic mechanisms any such type may use: Check requires the operations a used parameter needs (a table in the contract; `ms-teams`); `/wiki:bind-reader` hands over a contract's `## Bind` extras; the core `file-snapshot.sh` finds changed files when a reader's list folder has no modified times, until a reader plugin takes it (`docs/roadmap.md`, **Reader plugins for connector workarounds**).

## 11. Reader binding: a skill and a machine-readable binding
**Decision.** `/wiki:bind-reader <key>` binds a tool-neutral instance to the reader on this machine: it runs in the main session (Check may start it), has the user deny the reader's write tools, runs the contract's read-only tests on an item the user names as safe, and drafts the instance's frontmatter lists `reader` (`<operation>: <tool>`, optionally with one `<field>=<value>` limit) and `reader_deny`. It writes nothing itself.

**Why.**
- A binding in prose went unchecked (the first live run missed an allow line, `tests/live/results.md`). A subagent can't reach MCP tools or ask the user; the main session sees and calls the tools.
- Settings can't limit an MCP tool by its input, so a dispatcher such as Atlassian's `executeRead`, which reaches every Atlassian product, was held to the contract's operations only by text. The limit keeps a session to the source; no rule can, so the guard checks it.
- Deny rules express `reader_deny` exactly, so the guard doesn't repeat them (3).

**Consequences.**
- Instance validation checks the binding against the contract's `operations:`; `sources.sh settings` and `check-settings` turn it into allow and deny rules, in the wiki's settings or the user's. `check-settings` flags misspelled settings keys, since one silently drops every rule in the file.
- The guard refuses a call to a tool bound only with limits unless its input has one of their values, and, while a source file can't be used, every MCP tool a `reader` list names. A tool bound without a limit anywhere in the wiki is unlimited for every instance.
- The binding lives per instance: a wiki on another machine with other tool names is re-bound (Check finds the tools gone); a listed claude.ai connector also serves cloud sessions (17).
- Read-only during the tests rests on the denies added first and on plain "Yes" answers. Readers from an installed plugin's cache aren't covered (`docs/roadmap.md`, parked).

## 12. Unattended ingest defers its questions to a file
**Decision.** `/wiki:ingest <key|all> --unattended` never asks and never guesses: what it would ask becomes a question in `open-questions.md` at the wiki root (`unclear`, `conflict` or `filing`), with a marker `^[open: <id>]` on each page, and `/wiki:clarify` (manual-only) walks them with the user.

**Why.** A scheduled ingest is only useful if it can't stall on a question and can't write a guess into the wiki. One file, with markers where the facts belong, keeps what is missing visible and brings every answer back through the user. The format is fixed bullets so scripts can count it; IDs avoid source names, since commit messages carry them and the guard refuses those words.

**Consequences.**
- A run starts only on a clean `wiki/`, `raw/sync-log.md` and `open-questions.md`; it refuses first ingests and **Check needed**, and where a contract asks the user it takes the choice that fetches and writes nothing extra.
- One commit and one `clarify` log entry per answered or dismissed question. Any ingest closes a question its material settles; none applies a typed `answer:` line, and such an uncommitted edit makes scheduled runs refuse until `/wiki:clarify` applies it.
- `sourcelib.open_questions` parses the file for the sync status (also after `/clear`) and lint.
- The skills are prose, checked by a live run, not by the suite. Scheduling itself is parked (`docs/roadmap.md`).

## 13. Agent pull request flows
**Decision.** Two manual-only repo skills hand work back as pull requests for the user to approve and never merge: `/fix-issues-ai <numbers or titles>` (one branch and pull request per issue worth fixing) and `/implement-feature-ai <goal>` (one pull request per goal, built from tasks on an integration branch). Both decide what they can and flag it in the pull request; they share `docs/agent-pr-flow.md` (models, brief, pull request text, following a pull request).

**Why.** The user's time goes to the few choices only they can make and to the merge; a wrong call costs a closed pull request, not a migration. One pull request per issue or goal keeps each squash commit and review about one thing. Fresh-context reviewers catch what an implementer missed.

**Consequences.**
- `/fix-issues-ai` triages by severity against the cost of maintenance (above all closer coupling), closes what isn't worth fixing with reasons in a comment, and puts an issue that needs a plan on `docs/roadmap.md`.
- `/implement-feature-ai` asks only what it can't settle with confidence and would be hard to revert; a goal that needs a design stops at a design pull request with `docs/plans/<slug>.md` until it is merged.
- Subagents work in worktrees, which share the clone's git config and run its push hook. Where a session has no `gh` (a cloud session), GitHub MCP tools may open pull requests, comment and close issues, since that commits nothing; tools that write files, commits or branches, or merge, stay unused, because they pass the push hook (9). A cloud session has no personal denylist; the `pii` job runs the same check.
- The skills are prose, checked by use; `tests/test_agent_files.py` checks their frontmatter and guard line.

## 14. The review writes a reviewer guide
**Decision.** Once a pull request has no blocking finding open, the Claude review (`claude-review.yml`) starts its summary with a reviewer guide for the approver: the goal, a description, an assessment table (blast radius from a fixed set, risk of a bug, cost of maintenance), what to focus on, and a demo. A title or description that doesn't match the diff is a blocking finding.

**Why.** Most pull requests are written by an agent and approved by one person, who needs to know where a few minutes of attention should go. Blast radius and risk are kept apart, since a wide change can be unlikely to break. Judgment with named reasons rated better than a count of risk factors in a trial on merged pull requests. A wrong description blocks because the squash merge makes it the commit on `main`.

**Consequences.**
- The guide is derived from the diff, says what it did not assess, holds no findings and no advice on merging, and is rewritten only when a push changes it.
- A fixed set of emojis marks ratings and status; others are the agent's choice. The exact wording is in the workflow's prompt; a summary for contributors in `docs/development.md`, "Pull requests and CI".
- A pull request that changes `claude-review.yml` gets no review, so a change to the guide's wording is tried locally (`claude -p` against merged pull requests) first.

## 15. Dev tools in a locked venv, type-checked strictly
**Decision.** The dev tools (pytest, pytest-xdist, ruff, mypy 2.x, shellcheck-py) are the `dev` group in `pyproject.toml`, pinned with hashes in a committed `uv.lock`, and installed into a gitignored `.venv` only by an explicit `uv sync --locked`; never `uv run`. Every module behind a launcher and `scripts/pii_check.py` pass `mypy --strict`, and ruff's `ANN` rules keep every function annotated.

**Why.**
- The same tool versions on laptops, in CI and in agent sessions, and nothing installed into the user's or the system's Python. `[dependency-groups]` with a `uv.lock` is the common layout; one lock serves Linux, Windows and CI.
- `uv run` installs whatever a changed script declares (`docs/kfchou-security-review.md`, finding 3); a sync from a committed, hashed lock does not. Wheels only (`no-build`), so no package's build code runs; uv never downloads a Python.
- A stale venv that only warned would give "green locally, red in CI", so the scripts stop instead.
- Wrong shapes had shipped unseen (`None` reaching a string method, `bytes | str` used as `str`). Strict, because a checker that skips unannotated code checks little; `ANN` checks that annotations exist, mypy that they are right.

**Consequences.**
- uv 0.13.7 or later is a prerequisite for developing the repo, not for the wikis; without it, `WIKI_TOOLS_DEV_VENV=off` takes the tools from PATH and the run is reported as outside the lock. Setup and lock bumps: `docs/development.md`, "Dev environment".
- CI pins `setup-uv` by commit SHA at `required-version` (a test checks). Lock bumps are a collaborator's pull request; Dependabot security updates stay off, since their pull requests get no secrets and their notes carry third parties' names.
- mypy and ruff check against 3.11 (4); CI tests on 3.13 only, and a test job on the floor is parked (`docs/roadmap.md`). A new module in scope goes into `mypy.ini` strict from its first line; `tests/` is out of scope.

## 16. Functional style where it fits
**Decision.** In Python, a value built from an iterable with no side effects is a comprehension, a generator expression or `any`/`all`; a loop stays when its body does I/O, carries state, reports several different errors, or would need a nested or multi-condition comprehension. No fluent wrappers; bash stays builtin-first.

**Why.** Most loops here validate in order, track state, exit early or do I/O, and read better as loops (a 2026-11-23 survey found about 6 to 11% plain maps or filters). Python has no chainable collection API, and the standard-library rule (4) excludes libraries that add one. The guard fails closed, so a change in evaluation order can wrongly block or allow a call. In bash each pipeline stage is a process (4), no script sets `pipefail`, and a piped `while` loses its variables.

**Consequences.** ruff enforces the simple cases (`C4`, `PERF401`; `C408` off). The guard's modules are exempt from `PERF401` and aren't rewritten for style alone. Which loops count as stateful stays a judgement for the author and the reviewer.

## 17. Connector names per surface come from a plugin table
**Decision.** The plugin ships a pair table, `plugins/wiki/sources/connectors.md` (`servers:`, one `local=<server> cloud=<server>` item per claude.ai connector seen live on both surfaces), and `sources.sh settings` emits each binding rule under its cloud name too. Bindings stay in local names; only `sourcelib.py` reads the table, and the guard is unchanged.

**Why.** A cloud session sees other tool names (`mcp__Gmail__*` for `mcp__claude_ai_Gmail__*`), and settings rules are literal, so in the cloud nothing denied the write tools while routines run in auto mode. A cloud session reads only the committed `.claude/settings.json`, a deny beats an allow, and a rule can't constrain input, so both names in the committed settings is the one place that holds. Rejected (2026-11-25): a binding per environment in each instance; a binding overlay written by the setup script; generated `settings.local.json` or user settings (not read in the cloud); per-environment settings files; glob-server deny rules; a guard that maps names (a second layer over rules, 3).

**Consequences.**
- Servers match exactly, never as a prefix; mapping goes local to cloud. A tool bound only with limits is denied under its cloud name, since the guard's limits hold only under the bound name. Cloud-name rules count only from the wiki's own settings.
- Fails closed: a broken table makes the instance invalid; a bound instance whose cloud-name lines are missing gets **Check needed**. In a cloud session, an unbound instance or a tool with no known cloud name stops with a message.
- Accepted gap: the guard's "sources are broken" block knows only bound names, so a read tool passes under its cloud name then; write tools stay denied by settings.
- Not covered: Google Drive (cloud name not seen) and the Desktop app's `mcp__<uuid>__*` names. A pair is added by pull request once both surfaces were seen. Open live checks: `docs/plans/cloud-wikis.md`; if a cloud-name deny doesn't hold, this decision is revised.

## 18. Saving to the wiki's remote through a core script
**Decision.** The model never gets a push. One core script, `save.sh` (`save.py`), opt-in per wiki, saves the wiki's commits to the URL and branch pinned in the committed, guard-protected `save` section of `.claude/settings.wiki.json`: never forced, merging the remote's branch rather than rebasing, and relying on the host to refuse force pushes and deletion of that branch (checked on `github.com` before every save). Where `origin` equals the pinned URL, a save and `--update` also move `refs/remotes/origin/<base>` to the remote's base (a cloud session's `origin/<base>` lagged after a save, 2026-11-26); a failure there is only a warning.

**Why.**
- In a cloud session only what is pushed lasts, so a routine is worth running only if its commits are saved.
- A `git push` let through the guard was rejected: git takes the remote, refspec and URL from config a session can change. With force pushes and deletion refused by the host, the danger left is a push to the wrong place, an injected instruction sending the wiki elsewhere; the script takes no URL and reads the pin from HEAD, which the model can't change without the user's permission.
- Paths outside the content paths (control files, the config itself) need the user's permission, since they change what later sessions run or where they save.
- Rejected: a pre-push hook, a Stop hook, a branch and pull request per run, rebase, a content check (`docs/plans/wiki-save.md`, removed when built; see commit 3295ff4).

**Consequences.**
- How it works (path tiers, `--allow`, holding branches, conflicts, host checks): `docs/setup.md`, "Optional: saving from Claude"; the guard's side: `docs/guard.md`.
- **A guard is weakened** (3): `save.sh` is a second push path. `no_push` stays first and unchanged in what it matches. `save.sh --allow <plain paths>` gets an "ask" reply, denied in a headless run, so unattended runs use a holding branch. Any other form naming `save.sh`, and its test settings, is refused. A tightening beside it: `gh` with `api`, `pr`, `repo`, `release`, `workflow`, `secret`, `variable` or `gist` is refused, as these write past git.
- Core code calls a host: `save.py` calls `gh api` on `github.com` (REST only); other hosts get a reminder, not a check (2).
- Left open: an obfuscated command can push anywhere, as before; transport config (`core.sshCommand`, proxies) can redirect the connection, as a config denylist was rejected for its upkeep; a config change between check and push; an approval given without reading the diff. Personal data once pushed stays in the history; lint findings never block a save, since an unpushed cloud commit is lost. Open live checks: `docs/plans/cloud-wikis.md`.

## 19. The plugin updates itself at the start of a cloud session
**Decision.** In a Claude Code cloud session the plugin runs straight from the wiki-tools clone the setup script makes (`/opt/wiki-tools`, loaded with `CLAUDE_CODE_PLUGIN_DIRS`), and its first `SessionStart` hook, `cloud-update.sh`, fast-forwards that clone to `origin/main` at the start of each session. It acts only when `CLAUDE_CODE_REMOTE` is `true` and the clone is on `main`, and it fails open: exit 0 on every path, the fetch stopped after 15 s, and any failure leaves the clone as it was. The guard protects the clone as it protects the plugin folder (3).

**Why.**
- A setup script runs only when the environment's snapshot is built, about once a week, so a session could otherwise run a plugin a week old while the plugin changes often (live tests, 2026-11-26).
- A fast-forward does what a copy has to do by hand (replace, remove, record the commit). Rejected: refreshing a copy at `/opt/wiki-plugin` (about three times the code, review 2026-11-27); a Python hook (joins the allowed Python, 4, and pays for a launcher every start); a pinned commit bumped per environment; following another branch (dropped for now, owner's review 2026-11-27); a hook per wiki; checking for updates on every tool call.
- Without the clone protected, a session could check out another commit or edit `.git/` and change the guard it runs under.

**Consequences.**
- Every cloud session runs the latest `main`: a bad commit reaches the next session at once; there is no pin for now.
- **Version skew:** sessions start with the snapshot's `hooks.json` until it is rebuilt, so a `hooks.json` change must keep working with the previous launch lines for a week (`docs/development.md`, "Workflow"). The guard fails closed, so a mismatch blocks calls, never leaves a session unguarded.
- Git runs in a cleaned environment, as `save.py`'s (18); `HOME` and the proxy variables are inherited, since the cloud fetch needs them.
- **The guard is tightened** (3): a shell command naming the clone is refused, `git -C /opt/wiki-tools rev-parse HEAD` included; Read, Grep and Glob still read it. A local install that loads the plugin from a wiki-tools checkout gets the same protection. The hook isn't in the guard's `CORE_SCRIPTS`, so the model can't start it.
- Locally it does nothing. Environments made with the first setup script must replace it; guide and open live checks: `plugins/wiki/cloud/SETUP.md`.
