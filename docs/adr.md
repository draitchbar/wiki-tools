# Architecture decisions: the wiki plugin

The decisions behind how wiki-tools is built, and why. Plans and parked work are in `docs/roadmap.md`; how to use the plugin is in README.md and the pages it links.

## 1. One plugin, enabled per wiki, runnable from any clone
**Decision.** wiki-tools is a local-directory marketplace with one plugin, `wiki`. Each wiki enables it in its own `.claude/settings.json`, never at user scope. Everything the wikis need lives under `plugins/wiki/`. Skills and hooks name plugin files through `${CLAUDE_PLUGIN_ROOT}`; scripts find their own folder; the wikis' settings use path-free wildcard rules (`Bash(bash */sources/<type>/<script>.sh *)`). The shared schema (`schema/wiki-conventions.md`, `schema/wiki-layout.md`) is loaded by SessionStart hooks (`schema.sh`, one file per hook, each under the 10,000-character cap on hook context), not imported by a wiki's CLAUDE.md.

**Why.** The guards must apply only in wiki sessions, the clone must work wherever it lives on each machine, and Claude Code may run an installed copy of only the plugin folder.

**Consequences.** No fixed clone path anywhere. The repo itself is edited in sessions where the plugin is off, so the guards don't get in the way.

## 2. Source-neutral skills and pluggable sources
**Decision.** The skills, the guard, the settings template and `/wiki:init` know nothing about any particular source. A source has two levels:
- a **type**: its contract, `SOURCE.md`, with bash-parseable frontmatter (flat `key: value` lines and `- item` lists, no YAML or JSON library) and prose per operation for Claude;
- an **instance**: a key with parameters, one file per instance in the wiki's guard-protected `.claude/sources/instances/`; a wiki may have several instances of one type, and the key is `/wiki:ingest`'s argument.

Standard types live in wiki-tools (`plugins/wiki/sources/<type>/`); wiki-local types live in the wiki's protected `.claude/sources/types/` and may ship wrapper scripts. A local type may not shadow a standard one. Promotion of a local type to standard happens in a wiki-tools session, with fixtures and tests.

Every type is read-only by contract, plus narrowly declared bookkeeping writes (e.g. Gmail's `wiki-ingested` label). The contract lists the allowed and forbidden tools; `/wiki:add-source` drafts the settings snippet. The operations are check, list new, fetch, optional mark ingested, cite and resolve citation; reading file formats is a shared core step. Each source declares the state it needs (at least `last_checked`), which the core stores generically in `raw/sync-log.md`. Platforms are declared per type and checked up front. A key with a `last_checked_<key>` line but no instance file is a manual key: its material enters through `raw/` or user statements.

The protected `.claude/sources/` tree is written only by the user: Claude drafts a file, and `install-source-file.sh`, run in a terminal outside Claude, checks it in a scratch copy, shows the diff, and installs it.

**Why.** New sources shouldn't need changes to the skills or the guard, and a wiki must be able to add a source of its own without a wiki-tools release.

**Consequences.** Anything specific to one source belongs in its `SOURCE.md`, never in a skill. A type whose read-only property can't be kept by tool permissions alone ships a wrapper with an allowlist of operations.

## 3. The guard: a guardrail that fails closed
**Decision.** One PreToolUse hook, `guard.py`, covers Bash, PowerShell, Write, Edit, MultiEdit, Read, Grep and Glob. On every call it reads all standard and local contracts and the wiki's instances, and collects each type's `guard_words` and `scripts` and every filesystem instance's `roots`. It blocks `git push` (first, so no later exception can let one through); commands naming the plugin's folder in any spelling, `.claude/sources`, `.claude/settings`, `.claude/plugins/`, `hooks.json`, `claude plugin` or `disableAllHooks`; a contract's guard word; and a filesystem root. Exceptions, Bash only: a plain call of a core script or of a wrapper a contract lists, with no `; & | < > $`, backticks or `..`. Write/Edit may not touch protected paths or anything inside a root, and non-Markdown content may not contain a guard word. For types with `agent_only: yes` (e.g. `codebase`), the main session's Read, Grep and Glob on the root are blocked, and its wrapper calls are limited to the contract's `main_ops`; subagents (hook input with `agent_id`) pass.

The guard fails closed: unparseable input blocks, and while any contract or instance can't be used, every Bash and Write/Edit call is refused except read-only diagnostics (`git status`/`log`/`diff`/`show`, `sources.sh list`/`show`/`contract`), with a message naming the file.

**Why.** The sources must stay read-only and the guard machinery protected from the session it guards. Matching command text can't be a security boundary, but it reliably stops accidental and straightforward misuse.

**Consequences.** Known false positives (a commit message containing "push", `git add .claude/...`) are accepted and documented. A guard must never be weakened without saying so in the commit message.

## 4. Python behind bash launchers
**Decision.** The guard and the scripts' work are Python 3.9 or later, standard library only:
- **Hooks** run only through `py-launch.sh`, which fails closed: it finds Python (a cached path, else `python`, `python3`, `py -3`, rejecting the Windows Store alias), runs it as a child with `-I -S -X utf8`, and turns any exit other than 0 (allow) or 2 (block) into a block. Inside the script, everything sits in a `try` whose exceptions block. A script that imports a sibling adds its own folder to `sys.path` (`-I` removes it).
- **Scripts** keep their `.sh` names as launchers and run their module through `py-run.sh`: `sources.py`, `lint.py`, `wiki_check.py` (lint in-process), `sync_status.py`, `install_source.py`, `decode_download.py`, `sources/ms-teams/snapshot.py`. Contract validation and settings parsing are `sourcelib.py` on top of `contract.py` (the guard's lean parser). A launcher keeps what touches the terminal or the shell: `install-source-file.sh` keeps the paste, the diff and the y/n prompt; `decode-download.sh` keeps its argument and path checks; `sync-status.sh` (a SessionStart hook) exits 0 on every path and reports a missing Python on stdout.
- **On Windows,** a Python started from Git Bash gets its arguments unconverted (`MSYS2_ARG_CONV_EXCL='*'` for that one command). Python refuses Git Bash mount paths (`/tmp`, …) rather than report them missing; callers pass them as `pwd -W` prints them. Messages show paths as they were given.
- **Bash stays** for the launchers, `py-launch.sh` and `py-run.sh` (they find Python), `lib-source.sh` (the wikis' local types use its helpers), `schema.sh`, `ocr.sh`, `local-folder/read.sh` (the model for local types, and it works on paths the user typed) and the `codebase` wrappers `git.sh` and `gh.sh`.

**Why.** On Windows every process start in Git Bash costs about 25 ms and a Python start 100–250 ms, so pipelines of `sed`, `awk` and `grep` made the guard and the scripts take seconds per call; one Python process does the same work in milliseconds. The names stay because contracts, settings and the guard name them. PowerShell would have meant a second implementation beside bash and platform-specific skills.

- **Repo tooling** follows the same rules outside the plugin: `scripts/pii_check.py` behind `scripts/pii-check.sh`, which finds Python through the plugin's `py-run.sh` (the wikis never run it).

**Consequences.** No other Python without a decision recorded here. Python is a prerequisite for every wiki; `/wiki:init` checks for it.

## 5. Codebase research: `/wiki:research` and the `codebase` type
**Decision.** A `codebase` instance points at a local git clone (or a folder in it). It is a research type (`mode: research`): too large or fast-moving to ingest, so `/wiki:ingest` refuses it and sync-status leaves it out. `/wiki:research <key> "<question>" [--critique] [--worktree]` answers on demand:
- the main session reasons and never reads the code (enforced by `agent_only`); `wiki:source-researcher` agents act, at most 10 in parallel per step and at most 5 steps per run, then the session asks;
- agents read through `git.sh` (read-only operations at a pinned SHA of `ref`; the working tree only with `--worktree`) and `gh.sh` (PRs and issues, behind the instance's `gh_user`, never switching the active `gh` account); they may use the repo's own CLAUDE.md, skills and agents as knowledge, read-only;
- findings are merged into existing wiki pages where possible and cited verbatim with path, lines and SHA;
- critique is off by default; with `--critique`, an independent `wiki:critic` checks every claim through its own agents, for at most 3 rounds, then asks; pages are written only after acceptance;
- staleness is checked for cited code when the wiki answers from it (`drift`), not in sync-status;
- `git fetch` is allowed for agents; clone and worktree only after asking; no other writes to the clone. Shallow clones are accepted (no history before the boundary; `gh` gives older PR context).

**Why.** The code is too large for the main session's context and changes too fast to copy into the wiki; agents with capped, structured findings keep the main session's context small, and citations at a pinned SHA keep claims checkable.

**Consequences.** Run notes live per instance in `~/.cache/wiki-sources/<wiki>/<key>/runs/`, outside the repo, and notes on older SHAs are re-verified before reuse.

## 6. Research agents on Opus at medium effort; no code index
**Decision.** `source-researcher` runs on Opus at `medium` effort. `/wiki:research` uses no code index (graphify, SCIP, ctags, LSP and the like).

**Why.** Cheaper settings (Sonnet; Opus at low effort) gave thinner answers and some wrong ones. A cheaper setup must cost at least 15% less at unchanged quality. Exploration and search are too small a share of research time and cost for an index to reach the bar of 25% less time or cost at equal quality.

**Consequences.** If an index ever comes, it is a lead generator only: user-installed, built in the cache at a recorded SHA, never in the clone, and every claim re-read and cited at the pinned SHA. The names `setup.sh <key> graph` and the `git.sh` operations `graph-query`, `graph-path` and `graph-explain` are reserved for it.

## 7. Tests: pytest in two layers
**Decision.** The suite is pytest (`tests/test_*.py`, `tests/conftest.py`), started with `bash tests/run-tests.sh`, which finds Python as the scripts do. pytest is unpinned and the test runner's only dependency, never the plugin's. Two layers:
- **in-process:** a script's module is called through its `main(argv)`, the contract its launcher runs, with stdout and stderr captured in write order (`cli`, `guard_run`);
- **end to end:** the launchers and the bash scripts through a real bash (Git Bash on Windows).

`--e2e` runs the in-process tests through the launchers instead; it is required before a commit that touches a launcher or another `.sh` file. Tests never call a real source CLI or account; they use fakes (`tests/sources/<type>/`, e.g. a fake `gh`). Sections that build on one wiki step by step run as one ordered story and report each check as its own test. Recorded outputs (`tests/fixtures/*/*.out`) are compared byte for byte and rewritten with `--record`.

Windows paths get no special treatment: every test uses `tmp_path` with forward slashes, and one normaliser (`norm`) maps every spelling a path can come back in (native, forward slashes, `/c/...`, Git Bash's own mounts) to `@TMP@` and `@PLUGIN@`. On Windows, Git Bash started from native Python parses its own command line (globbing `*`, reading `@file`, mishandling `\"`), and Git's `bin/bash.exe` is a native launcher that parses it again and puts its own folders before a test's `PATH`. So arguments to bash go NUL-separated through a file, read by a fixed driver that execs `<git>/usr/bin/bash.exe`.

**Why.** Testing logic in-process makes the suite fast and free of shell quoting, while the end-to-end layer and `--e2e` keep the process boundary covered, which is where Windows differs.

**Consequences.** On Windows a restricted `PATH` still has Git's folders in front; a test can't assume bash sees only what it was given.

## 8. Changes through pull requests, checked on both platforms
**Decision.** `main` changes only through pull requests. CI (`.github/workflows/ci.yml`) runs lint (`ruff check .`, `shellcheck -S warning` on every `*.sh`, no CRLF) and the suite, normally and with `--e2e`, on Linux and Windows; Claude reviews each pull request (`claude-review.yml`). Lint must also be clean before committing. Line endings are LF everywhere (`.gitattributes`).

**Why.** Every script must run under Linux bash and Git Bash on Windows, and most Windows problems only show on Windows.

**Consequences.** Real use in a wiki on each machine is still checked by hand for changes that affect sessions.

## 9. Public from a fresh history, with a personal-data check
**Decision.** The public repo `draitchbar/wiki-tools` started from one commit of the cleaned files, not from the earlier history, which holds personal data (names, emails, addresses, hostnames) and stays private. Everything in the repo, commits included, is free of personal data: no real names, emails, places, hostnames, employer details, third parties or real wiki names, and commits carry only noreply emails and no `Claude-Session:` trailers. The rules are in `docs/development.md` ("Personal data") and `CONTRIBUTING.md`. MIT licence. Anyone can read, fork and install; issues and pull requests are for collaborators, who push branches to the repo, not to forks.

The check runs in three layers:
- `scripts/pii-check.sh` (stdlib Python behind `py-run.sh`): committed general patterns plus a private denylist (a local file, the secret `PII_DENYLIST` in CI), matched with folded case, Danish letter spellings, separators and encodings. A hit names its place and the entry's number, never the term.
- A committed pre-push hook (`.githooks/pre-push`), switched on per clone with `git config core.hooksPath .githooks`.
- CI: `pii.yml` on every PR event (a required check) and on push to `main`; an advisory section in `claude-review.yml` for what patterns miss.

The `main` ruleset requires a PR, the checks lint, tests on Linux and Windows, and pii; it allows squash merges only and blocks force pushes and deletion, with no bypass. Secret scanning and push protection are on.

**Why.** Rewriting history and flipping visibility leaves old commits reachable on GitHub, and a push to a public repo can't be taken back: pull request refs survive deleted branches and force pushes, and forks and clones keep everything. So the check runs before the push where it can, and CI catches the rest.

**Consequences.** Collaborators are trusted: the PII job and the review run with the secrets on a PR's own workflow code, so the owner reviews every change to `.github/workflows/` and the check. Edits in the GitHub web UI skip the hook. Issues and comments aren't scanned. A clone made before the release must never push here; every machine re-cloned.

## 10. Two coding agents, one set of rules
**Decision.** The repo is developed with Claude Code and with GitHub Copilot CLI, and every change must work in both (`CONTRIBUTING.md`). Rules and skills are written once. `CONTRIBUTING.md` holds the contribution rules for people and agents (workflow, personal data, push hook, identities, trailers); `AGENTS.md` imports it with `@CONTRIBUTING.md` and adds how to change the code and what only agents need; `CLAUDE.md` is the one line `@AGENTS.md`. Skills stay in `.claude/skills/`, which both agents read. No instruction or skill file only one agent reads, and no symlinks; `tests/test_agent_files.py` checks the layout. Enforcement stays where both agents meet it: the pre-push hook, CI and the review, with no agent hooks or committed permissions. Copilot's coding agent, `/delegate` and GitHub MCP write tools are not used, since they commit on GitHub past the hook; VS Code agent mode and Copilot code review are not set up.

**Why.** Collaborators may use either agent, and rules kept in two places drift. The `@` import is the one mechanism both agents document (Claude Code's docs recommend `@AGENTS.md` in `CLAUDE.md` and advise against a symlink on Windows, where `core.symlinks` is often off); both find skills in `.claude/skills/`. `CLAUDE.md` stays, although Claude Code 2.1.277 and later reads `AGENTS.md` on its own, because older or telemetry-off sessions read only `CLAUDE.md` and `claude-review.yml` names it. People follow links, agents follow imports, so each rule lives in the file of its main readers: `CONTRIBUTING.md` for policy, `AGENTS.md` for code and agent rules.

**Consequences.** Copilot reads `AGENTS.md` and `CLAUDE.md` both and so loads the rules twice; accepted (identical text, a few KB). Tested in Copilot CLI 1.0.112 (2026-11-15): its `Co-authored-by` trailer uses a GitHub noreply address and passes the personal-data check; `$ARGUMENTS` works; `argument-hint` isn't shown, so a skill names its arguments in `description`; `disable-model-invocation` is ignored, even when a prompt only matches the description, so a manual-only skill starts with a guard line telling the agent to stop unless the user typed the command. That line relies on the agent obeying it, a weaker check than Claude Code's. The built-in GitHub MCP server is read-only by default. Copilot also reads hooks from `.claude/settings.json`, so a later guard hook for both agents could live in one file; its reply format for Copilot is unconfirmed.
