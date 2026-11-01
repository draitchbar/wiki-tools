# Source type `codebase` and `/wiki:research`

Status: intents grilled, design approved and built on 2026-10-31 (on main); tested in ai-wiki on Windows 2026-11-01 (section 8, results below). Remaining: the graphify/SCIP decision after ~10 real runs.

## Context
Some sources are too large and change too fast to ingest: a monorepo like `festina-life/components` (50k tracked files, 2.4M lines of Java/Kotlin, ~280 commits a week on main). We still want the wiki to know about it. So the code is not ingested; it is **researched on demand**, and what a run learns is consolidated into wiki pages with commit-pinned citations that can be re-checked later.

## Settled intents
1. A research run writes its findings into wiki pages, merged into existing pages where possible (no page explosion).
2. Instance parameters are given at instantiation; the example repo is only an example; the instance may point at a subfolder. The repo is always under GitHub control.
3. New source-neutral core skill `/wiki:research <key> "<question>" [--critique]`, invocable by the user and by Claude. "Wiki first" is a general schema rule, not part of the skill.
4. ReAct: the main session reasons; action agents (subagents) act. At most 10 agents in parallel per step, at most 5 steps per run (critique not counted), then ask. Report steps and agents at the end.
5. The main session never reads the code (enforced). Agents return capped structured findings; full notes go to a scratchpad.
6. Scratchpads persist per instance outside the repo and may be reused; notes on older SHAs are re-verified before use.
7. Agents may use the repo's own CLAUDE.md, AGENTS.md, skills and agents as knowledge, strictly read-only (no builds, tests, debugger, git writes).
8. Critique is off by default (`--critique`). The critic checks every claim against the code (also claims taken from wiki pages), has its own agents, is independent of the reasoning; at most 3 revise rounds, then ask the user. Pages are written only after accept or the user's decision.
9. Staleness is not in sync-status. When the wiki answers from pages that cite code, it checks drift for the cited code and re-researches only what changed.
10. Ask the user whenever unsure. Linux and Windows (Git Bash); git required, gh optional.
11. `git fetch` allowed for agents; `git clone`/`git worktree add` only after asking the user; all other writes to the clone forbidden.

## Research findings (2026-10-31)
- **Local vs GitHub.** Local wins for reading code: `git grep` over all Java/Kotlin at a given SHA takes <1 s on this machine; GitHub code search is 10 req/min, default branch only, no regex, legacy engine; REST reads cost one round trip per file. GitHub has what the clone lacks: PRs, reviews, issues, commit→PR. The GitHub MCP server adds nothing over `gh` and would bypass the guard. → **Hybrid: the local clone for code, `gh` (read-only, optional) for PR/issue context.**
- **The example clone** is on `main`, 174 commits behind `origin/main`, and **shallow** (history from 2026-08-10). Shallow breaks `log`/`blame` before that date and fetching into a shallow clone is expensive. A blobless clone (`--filter=blob:none`) is the recommended long-lived form.
- **gh accounts.** The active `gh` account (`draitchbar`) gets 404 on the repo; `mvb_festina` can read it. The wrapper must pick the account per call (`GH_TOKEN=$(gh auth token -u <user>)`), never `gh auth switch`.
- **graphify** (Graphify-Labs, PyPI `graphifyy` 0.9.99, Python): local tree-sitter extraction, no LLM for code. For this repo: likely hundreds of thousands of nodes, no published figures at this size, stale within hours (~1,200 files change a week), not SHA-pinned, name-based Java edges without type resolution, blind to Spring wiring, Gradle, BPMN, XML; its git hooks would write to the clone. → **Not in v1.** Revisit (head to head with SCIP) if runs keep spending steps on cross-module "who uses X". Cursor's numbers say an index helps as a *lead generator* on top of grep, never as evidence.
- **Best practices** (Anthropic multi-agent research system, CoVe, CRITIC, Self-Refine, SWE-agent ACI, aider repo map, DeepWiki): fixed subagent brief (objective, output format, tools, boundaries incl. what siblings cover); effort scaled to the question (1 agent for a lookup, 2–4 for a comparison, up to 10 for broad questions); a sufficiency check after every step; workers write to files and return short summaries plus paths; bounded tools that print citations themselves so line numbers can't be invented; a cached orientation map; claim-level, factored verification (verifiers get neutral questions, not "confirm X"); a fresh critic each round; deterministic citation checks; full SHAs stored.
- **Claude Code mechanics** (docs, 2026-10-31): PreToolUse hooks fire for subagent tool calls too, and carry `agent_id` only inside a subagent → the guard can deny code reads to the main session and allow them to agents (to be verified with a logging hook in the test). Subagents can spawn subagents (3 levels by default) → the critic dispatches its own checkers. Plugins can ship agents (`wiki:<name>`) with a restricted `tools` list. Permission rules can't differ between main session and subagents; only a hook can. The Workflow tool can't take mid-run user input and doesn't suit an interleaved ReAct loop; plain parallel Agent calls do.

## Design

### 1. The contract `plugins/wiki/sources/codebase/SOURCE.md`
- `type: codebase`, `access: filesystem`, `cite_prefix: Codebase`, platforms linux + windows.
- Parameters:
  - `roots` (required): the clone, or a folder in it (`C:/src/components` or `C:/src/components/life`). As for local-folder, the guard treats it as read-only (no Write/Edit inside, no Bash mentioning it).
  - `ref` (optional, default the remote's default branch, e.g. `origin/main`): what "the code" means for this instance.
  - `gh_user` (optional): the gh account that can read the repo; without it the PR/issue ops are off.
- State: `last_checked` only (date of the newest research run). Excluded from sync-status (see 5).
- New flat contract key `mode: research` (default `ingest`): `/wiki:ingest` refuses such a key and points to `/wiki:research`; sync-status skips it; the body has a **Research** section, and **List new**, **Fetch**, **Mark ingested** say "not supported (research type)".
- New flat contract key `agent_only: yes`: the main session may not read the roots at all (see 3).
- `read_tools`: `Bash(bash */sources/codebase/git.sh *)`, `Bash(bash */sources/codebase/gh.sh *)`. `forbidden_tools`: `Bash(gh pr create *)`… (all gh writes) and the git writes. No guard word for `gh` (substring matching would hit "high", "ghost"); the roots rule already blocks raw git on the clone.

### 2. Wrapper scripts (POSIX bash, modelled on local-folder/proton-drive)
`git.sh <key> <op> <args>`: resolves the clone from the instance, never takes a path to the repo from the caller, runs git with `GIT_PAGER=cat`, `--no-ext-diff --no-textconv`, no `-c`, `-O`, `--output`, `--upload-pack`; every listing capped; every line it prints that points at code is already a citation (`<path>#L<n> @<sha12>`).

| op | what | who |
|---|---|---|
| `status` | branch, HEAD, `ref` SHA, ahead/behind, dirty, shallow, fetched-at | main + agents |
| `fetch` | `git fetch --prune <remote>` (refs only; plain) | agents |
| `resolve <ref>` | full SHA; refuses an unknown ref | main + agents |
| `grep <sha> <regex> [pathspec]` | `git grep -n -E` at that SHA, capped | agents |
| `show <sha> <path> [Lx-Ly]` | numbered lines at that SHA, capped | agents |
| `ls <sha> [path]` | `git ls-tree` | agents |
| `log <ref> [path]` | `git log --oneline`, capped; `-L` form for a line range | agents |
| `blame <sha> <path> Lx-Ly` | | agents |
| `branches [pattern]` / `contains <sha>` | remote branches; is the SHA on a remote branch (pushed) | agents |
| `drift <sha> <path> Lx-Ly` | against `ref`: `unchanged` (same blob) / `moved` / `changed-elsewhere` / `changed-overlap` / `renamed <new>` / `deleted`; metadata only | main + agents |
| `verify <sha> <path> Lx-Ly` | the citation resolves (`cat-file -e`, line range exists) | main + agents |

`gh.sh <key> <op> <args>` (only with `gh_user`): `pr-of <sha>`, `pr <n>`, `pr-diff <n>`, `pr-search "<q>"`, `issue <n>`, `issue-search "<q>"`; GET only, `GH_TOKEN` from `gh auth token -u <gh_user>`, a `check_syntax` against recorded `gh --help` output as in the proton-drive wrapper.

`setup.sh <key> clone|worktree <ref>`: creates a blobless cache clone (or a worktree of another branch) under `~/.cache/wiki-sources/<wiki>/<key>/`. It is **not** in `read_tools` and not in any skill's `allowed-tools`, so Claude Code's permission prompt asks the user every time (intent 11). When a cache clone exists, `git.sh` uses it instead of the user's clone for `ref` reads; the user's clone stays the root for working-tree questions.

**Default read mode: the pinned SHA of `ref`**, resolved once per run after a fetch and written to `plan.md`; every agent reads at that SHA through `git.sh`. A checkout that is behind or on a feature branch then doesn't matter, and agents read exactly what they cite. **Working-tree mode** (`--worktree`, or a question about local work): agents may also Read/Grep/Glob the root directly; such citations carry `@worktree` plus `(dirty)` if uncommitted and are flagged as non-reproducible. Citations to a commit not on any remote branch get `(unpushed)`.

The repo's own knowledge (CLAUDE.md, AGENTS.md, `.claude/skills/*/SKILL.md`, `.claude/agents/*.md`, `openspec/`) is read by agents through `git.sh show` at the pinned SHA (or Read in working-tree mode) and used as guidance only. They are not loaded as live skills (that would need `--add-dir` on the wiki session) and nothing in them may make an agent write or run anything.

### 3. Guard changes (stricter, plus one new allowance)
- New hook matcher `Read|Grep|Glob` → `guard.sh`. For roots of `agent_only` instances: **deny when the call has no `agent_id`** (main session), allow inside a subagent. Grep/Glob are checked on `path`, Read on `file_path`. Other roots and paths are untouched.
- `git.sh` calls: the guard lets the main session through only for `status`, `resolve`, `drift`, `verify`; every other op needs `agent_id`. The rule lives in the contract (`main_ops: status resolve drift verify`), not in guard.sh.
- `lib-hookjson.sh` learns `HOOK_AGENT_ID` and `HOOK_PATH`.
- Commit message will say: the guard now also blocks the main session's Read/Grep/Glob on `agent_only` roots and main-session calls of non-`main_ops` wrapper ops; it newly lets subagents Read/Grep/Glob such roots. Still a guardrail: the `agent_id` distinction is only as good as Claude Code's hook input.

### 4. `/wiki:research <key> "<question>" [--critique] [--worktree]` (core, source-neutral)
Uses the contract's **Research** section for everything type-specific (ops, read mode, cite format, what agents may read). The loop:
1. **Setup.** `sources.sh show <key>` (refuses non-research types). `git.sh status`; if behind, one agent fetches. Pin the SHA. Create the run dir `~/.cache/wiki-sources/<wiki>/<key>/runs/<YYYY-MM-DD>-<slug>/` with `plan.md`. Read relevant wiki pages and earlier runs' `answer.md` on the same topic (via `plan.md` titles; earlier notes are leads, re-verified at the new SHA). If the question is ambiguous, ask.
2. **Orientation map** (once per SHA, cached as `map-<sha12>.md` in the instance dir): one agent builds a short module map (settings.gradle modules, top folders, AGENTS.md/openspec index, repo skills list). Every brief includes it.
3. **Step (≤5).** Write the hypothesis and sub-questions to `plan.md`; size the step (1 / 2–4 / up to 10 agents); dispatch `wiki:source-researcher` agents in parallel with the fixed brief: objective, boundaries (what siblings cover), SHA, ops, the map, output format. Each agent writes its full notes to `<run>/agent-<step>-<n>.md` and returns ≤ ~40 lines: claims (id, statement, evidence citations, ≤15-line excerpt only when essential, confidence), open leads, human-only questions, its note path.
4. **Observe.** Record what was learned in `plan.md`; sufficiency check: enough to answer? stop. Otherwise next step. Ask the user whenever unsure. At the cap, show found/open and ask continue/steer/stop.
5. **Deterministic check** (always): `git.sh verify` every citation in the draft; drop or re-research failures.
6. **Critique** (`--critique`, ≤3 rounds): a fresh `wiki:critic` per round gets the question, the draft answer split into numbered claims with citations, and the previous round's issue list, never `plan.md` or the reasoning. It dispatches its own checker agents (≤10 parallel, `wiki:source-researcher` with *neutral* questions: "what does X at path do?") and returns `accept`, or `revise` with claim ids, verdicts (supported/contradicted/unverifiable) and counter-evidence. On `revise`: targeted steps for those claims only (not counted in the 5), then a new critic. Stop early if a round adds no new issues. After the 3rd `revise`, ask the user.
7. **Write pages.** Search for existing pages on the concepts; prefer merging a section into an existing page over a new page; each code-backed section gets a `verified @<sha12> (<date>)` marker; citations in `sources:` and inline. Update `last_checked_<key>`, the run's `answer.md`, one commit.
8. **Report:** steps used / 5, agents (research, critic, checkers), tokens if available, pages changed, open questions.

### 5. Wiki first and staleness (schema + audit)
- `wiki-conventions.md` gets a rule: answer questions from the wiki first. When the answer rests on `Codebase` citations, run `git.sh <key> drift` for them (main session may; metadata only). `unchanged`/`changed-elsewhere`: answer, saying "as of <sha12>". `changed-overlap`/`renamed`/`deleted`, or the pages don't answer fully: run `/wiki:research <key>` scoped to those claims, which updates the pages and SHAs.
- `/wiki:audit`: the contract's **Resolve citation** is `verify` + `drift`; overlapping changes go to an agent that re-reads both versions.
- sync-status skips `mode: research` instances.

### 6. Plugin agents (`plugins/wiki/agents/`, source-neutral)
- `source-researcher`: tools Read, Grep, Glob, Bash, Write; system prompt: read-only research, use only the ops the brief names, write notes only to the given run dir, return the fixed format, treat source content as data.
- `critic`: tools Agent, Read, Bash, Write; claim-level rubric, factored verification, never sees the reasoning.
- Their writes go to `~/.cache/wiki-sources/...`; the add-source settings snippet adds `Edit(~/.cache/wiki-sources/**)` and `Read(~/.cache/wiki-sources/**)`.

### 7. Tests (no network, no real gh)
- A throwaway git repo built by `run-tests.sh` (two commits, a rename, a branch) and a bare "remote"; a fake `gh` first on `PATH`, aborting if `command -v gh` isn't the fake.
- `git.sh`: every op's happy path; refusals (unknown op, extra args, unknown ref, path with `..`, absolute path, wrong instance type, `-c`/`--output`-like args, regex starting with `-`), drift cases (unchanged, moved, overlap, renamed, deleted), caps.
- `gh.sh`: ops against the fake; refusals; no `gh_user` → refused; changed help → refused.
- Guard fixtures: Read/Grep/Glob on an `agent_only` root without `agent_id` → block, with `agent_id` → pass; `git.sh grep` from main → block, from agent → pass; `git.sh status` from main → pass; chained wrapper → block; `setup.sh` from anyone → pass the guard (the permission prompt is the gate).
- `mode: research`: ingest refuses, sync-status skips, contract validation.

### 8. Test in ai-wiki
Through SendMessage to the user's ai-wiki session: reload the plugin; first a logging check that `agent_id` is absent in the main session and present in a subagent (Windows); the user creates the instance with their own prompt to the ai-wiki session (`/wiki:add-source codebase` with their parameters; the user installs the protected files) and tells me the instance key when done; two questions (one new, one follow-up that should reuse the pages; one with `--critique`); report steps/agents, pages, citations, guard blocks.

**Results (2026-11-01, ai-wiki on Windows, instance `components`, gh_user `mvb_festina`):**
- Guard split confirmed: the main session's Read of the root and `git.sh grep` were blocked; a `wiki:source-researcher` Read and `git.sh show` passed with no prompt. `agent_id` behaves as documented on Windows.
- Run 1 (moneyin → paymenthub, no critique): 2/5 steps, 8 agents, 28 claims, 27 line citations all `verify ok`, 49 min (9 min fetch). The question's premise was wrong (paymenthub/ is a customer layer); agents raised it through HUMAN, and the user re-scoped.
- Run 2 (paymenthub validations, `--critique`): 1/5 steps, 8 research agents, 3 critics (10, 10, 0 checkers), 3 revise rounds then user accept, 62 claims all verified, about 71 min. Critique caught a wrong citation, precision errors and missing validation paths; splitting wide citations caught a factual error.
- No wiki pages (the user's choice for the test); answers stay in the run folders, runs logged in `wiki/log.md`.
- Fixed from the test: the orientation map reads `.agents/` and other agent folders (88be1dd); fetch never prompts, uses the gh_user token, records completion (0bb49df); grep pattern files for `|`, `$`, `(` (0bb49df); exact-citation, re-scope, secrets and no-pages rules (0a2d501); `verify-all`/`drift-all`, the `revise-prose` verdict, delta re-checks in later rounds, scope carry-over and critic-supplied citations.
- Found in the source: clear-text SFTP/PGP keys in a dev `application.conf`; reported to the user, values not copied.

## Decisions after research (2026-10-31)
- Default read mode = pinned SHA of `ref`; the working tree only with `--worktree`.
- Shallow clones: live with them in v1. The contract's Caveats say history before the shallow boundary isn't available and point to `gh` for older PR context; `setup.sh` (cache clone, asks the user) stays for later.
- gh PR/issue ops in v1, behind `gh_user`.
- graphify not in v1, but prepared for: the names `setup.sh <key> graph` and `git.sh` ops `graph-query`/`graph-path`/`graph-explain` are reserved; run reports note steps spent on cross-module "who uses X" searches. After ~10 real runs, decide with data (graphify vs SCIP head to head). If adopted: user-installed, `--code-only`, built in the cache at a recorded SHA, never in the clone, results are leads only (every claim re-read and cited at the pinned SHA).

## Open for approval
- The design as a whole.

Approved 2026-10-31.

## Implementation plan
Order matters: library and guard first (everything else leans on them), then the type, the skill and agents, docs, and last the ai-wiki test. One commit at the end (`Add source type codebase and /wiki:research`), after a green `bash tests/run-tests.sh`.

1. **lib-hookjson.sh**: also extract `agent_id` (`HOOK_AGENT_ID`), `path` (`HOOK_PATH`, Grep/Glob), `pattern` and `glob` (`HOOK_PATTERN`).
2. **lib-source.sh** `src_validate_contract`: new optional keys `mode` (`ingest` default | `research`), `agent_only` (`yes` | `no`, only with `access: filesystem`), `main_ops` (list); `mode: research` requires a `## Research` section. Template documents the keys.
3. **guard.sh** + **hooks.json**:
   - new matcher `Read|Grep|Glob` → guard.sh; fast exit when the wiki has no `agent_only` instance;
   - collect `AGENT_ROOTS` (roots of instances whose contract says `agent_only: yes`); Read/Grep/Glob whose `file_path`, `path`, `pattern` or `glob` touches one: block without `agent_id`, pass with it;
   - Bash: an allowed wrapper of an `agent_only` type, called without `agent_id`, passes only if its op (2nd argument) is in the contract's `main_ops`.
4. **sources.sh / sync-status.sh / ingest**: `list` shows `research` instances as such; sync-status skips them; ingest refuses them and points to `/wiki:research`.
5. **sources/codebase/**: `SOURCE.md`, `git.sh` (status resolve drift verify fetch grep show ls log blame branches contains), `gh.sh` (pr-of pr pr-diff pr-search issue issue-search; syntax recorded from gh 2.103.2). `setup.sh` and the graph ops are reserved, not built.
6. **plugins/wiki/agents/**: `source-researcher.md`, `critic.md`.
7. **skills/research/SKILL.md** (model- and user-invocable).
8. **schema/wiki-conventions.md**: "Answer from the wiki first" with the drift rule; **audit**: nothing type-specific (it uses Resolve citation), but its subagents may need the cache rules.
9. **Tests**: throwaway git repo + bare remote; fake `gh` with abort guard; git.sh/gh.sh happy paths and refusals; drift cases; guard fixtures (main vs agent Read/Grep/Glob, main_ops); `mode: research` in sources.sh/sync-status; guard-wiki gets a `code` instance.
10. **Docs**: README Sources line + setup row; CLAUDE.md open plans; this doc's status.
11. **ai-wiki test** via SendMessage (section 8 of the design).
