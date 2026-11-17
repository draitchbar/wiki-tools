# Plan: Copilot CLI in existing wikis

Status: part A's Linux evidence collected and reviewed by Copilot (2026-11-17; [results](#results-of-the-spike)); its Windows observations (1.7) and `write_bash` are still open. Parts B and C not started. The [design](../copilot-wiki-design.md) holds the reasons and constraints; this file holds the work, in order, with exit conditions. Indexed in [the roadmap](../roadmap.md).

## Outcome and scope

Users can open the same wiki in Claude Code or GitHub Copilot CLI and switch between sessions without migrating instructions, pages, citations, source instances, caches or sync state. Simultaneous editing is not supported.

The work comes in three parts, each its own pull request or set of them:

| Part | Content | Depends on |
|---|---|---|
| **A. Spike** (step 1) | Real compatibility evidence: a capability matrix and payload fixtures. No runtime change. | nothing |
| **B. First delivery** (steps 2-10) | The base plugin migration plus `raw` and `local-folder`, **Copilot on Linux**. Claude Code stays supported on Linux and Windows, unchanged. | A; steps 2-10 are **revised from A's matrix** before any of them starts |
| **C. Copilot on Windows** | The PowerShell-to-Git-Bash route and its guard checks. | B shipped |

Raw and local-folder are the two easiest sources: raw is built in, and local-folder already has a tested, read-only Bash wrapper. The other seven standard source types are parked ([below](#deferred-sources-parked)); their Claude support stays intact.

DRY: one plugin package, schema, skill set, agent-role definitions, contract parser and guard policy. Keep a wiki's `CLAUDE.md` and `.claude/sources/`. Accept the instruction-based manual-only restriction in Copilot; do not build an invocation tracker. Keep Bash/Python launchers and the existing pytest conventions. No generic connector framework, copied instruction trees, new runtime dependencies or broad permission grants.

## What is known

Read-only investigation on 2026-11-15 with this repository, Copilot CLI 1.0.112's shipped documentation and command help, and Claude Code 2.1.325's command help; plus the hook tests recorded in `docs/development.md`, "Agents" (Copilot 1.0.112 on Windows, a `PreToolUse` hook in a throwaway repo's `.claude/settings.json`). No wiki session, plugin installation, source or guard validation has been run.

| Finding | Consequence |
|---|---|
| `copilot --plugin-dir <plugin> plugin list --json` recognizes `wiki` as an external plugin. | Package discovery works; it does not prove hooks, activation scope or skill execution. |
| Skill enumeration loads seven skills but rejects `skills/research/SKILL.md`: its unquoted description contains `mode: research`, invalid YAML for Copilot's parser. | Quote it in the shared skill; make client discovery a regression check. |
| Copilot supports Claude-style manifests, project activation/hooks and legacy hook keys; its hook environment aliases the Claude plugin/project paths. | Start with native compatibility; capture real payloads and denial behavior before choosing adapters. |
| `COPILOT_CLI=1` is documented in Copilot's hooks and agent shell commands. | A documented signal for client selection; no host-name or path guessing. |
| Both clients have `--plugin-dir`, `-p`, machine-readable output and explicit session resume. | Both can drive opt-in real-client tests. `--plugin-dir` is one test lane, not proof of project installation. |
| Copilot does not use Claude `permissions.allow/deny`; repository settings cannot supply its enterprise permission policy. | No fictitious permission JSON, no narrow rules translated into broad shell allows. Restrictions come from the common guard and the readers. |
| In prompt mode, both clients deny requests that would need approval. | A denied request alone is not evidence that the wiki guard worked. |
| `hooks.json` matches a fixed tool list (`Bash\|PowerShell\|Write\|Edit\|MultiEdit\|Read\|Grep\|Glob`), and `guard.py` allows any tool it does not know. | A Copilot tool with another name never reaches the guard. Needs a decision ([step 3](#3-extend-the-common-guard)), not only a live test. |
| Tested on Windows: Copilot's hook input has Claude's field names (`tool_name`, `tool_input`, `cwd`), and the main session sends no `agent_id`. | `hookjson.py` should parse it as is. Open: whether a child agent's calls carry `agent_id`, and the same on Linux and for plugin hooks. |
| Tested: exit 2 denies, but the reason reaches the model only with Claude's JSON deny reply; a hook that errors denies the call; exit 0 without output allows. | The guard needs the JSON reply for Copilot (step 3). Fail-closed on error holds without `onFailure`. |
| Tested: in a folder that is not trusted, Copilot skips repo hooks with a warning and the command runs. | Check whether plugin hooks are skipped the same way; if so, readiness must detect an untrusted wiki, since the guard is silently off. |
| Tested on Windows: `"shell": "bash"` is ignored and `bash` comes from PATH (WSL on the test machine); a PowerShell command arrives as `tool_name: "Bash"`. | The guard's PowerShell refusal does not fire for Copilot, and it would parse PowerShell text as Bash. Copilot on Windows needs its own route: part C; until then it must be refused outright, not half-checked. |
| `bash tests/run-tests.sh --e2e` exercises launchers, not a model running in a wiki. | Keep that layer; add a small opt-in live-client layer with a separate result. |

Not yet verified, and so the spike's subject: the same hook behavior for plugin hooks and on Linux, matcher coverage, timeout denial, SessionStart context and its survival of resume and compaction, skill `!` injections, plugin-root substitution, skill `allowed-tools` frontmatter, file/image tools, and child-agent hook coverage and identity. Client documentation is not runtime proof.

## Part A: the spike

### 1. Collect real compatibility evidence

A deliverable of its own. It changes no runtime code; it adds fixtures and a short matrix, and it ends with this plan being revised.

1. Run the normal and launcher suites plus lint; record the baseline.
2. Provision a disposable git wiki, a separate source folder, isolated client configuration/cache roots (`COPILOT_HOME`, Claude configuration, HOME) and a test copy of the plugin. Made-up content, no source connectors, never the developer's personal profile. Write the minimal capture-only driver here; step 8 adds assertions to it rather than a second driver.
3. Use native CLI discovery to check all eight skills and both agent definitions. Record the skill command names each client exposes; do not assume Copilot uses `/wiki:` names. Record what Copilot does with a skill's `allowed-tools` frontmatter (ignored, honored, or a load error) and how often a wrapper call then prompts.
4. In real Copilot and Claude sessions on Linux, capture the hook event and input for shell execution, shell follow-up input, read/search, write/edit and multi-file patch, from the main session and from a dispatched child agent. For each, record:
   - the tool name, and whether `tool_name`, `cwd` and `agent_id` (or an equivalent) are present, with their exact spelling;
   - whether a catch-all matcher fires for every tool, and what one hook invocation costs in time;
   - the plugin/project/data variables;
   - what the client does on exit 2, another non-zero exit, a missing interpreter and a timeout: is the tool call actually stopped?
5. Prove schema injection with run-specific canaries in the test copy's schema, without the actor reading the schema files. Check start and resume; exercise compaction/reset interactively.
6. Try shared project activation without `--plugin-dir`, and separately a local-directory mount. Check for exactly one guard invocation per relevant call and none in an unrelated folder.
7. On Windows, only observe: Copilot's native shell, plugin-root substitution and how Git Bash can be invoked. This feeds part C; nothing is built for it now.

**Who:** Claude Code implements the spike; Copilot CLI (local, never `/delegate`) reviews it, the capture driver, the matrix and the fixtures in particular, before part B starts. The implementing agent is then not the client under test, so the captured sessions don't inherit its environment, profile or approvals, and the client whose behavior is recorded checks the record. The review checks the evidence; it doesn't replace it.

**Exit:** a compact capability matrix (in `docs/development.md`, beside the existing agent table), normalized synthetic payload fixtures under `tests/fixtures/`, and the list of unsupported or gating cases. Then **revise steps 2-10 against the matrix** in the same pull request: drop what the evidence makes unnecessary, and settle the decision in step 3.

Stop conditions, decided here rather than discovered later:

- Hook denial must cover child-agent calls. If child calls are unguarded, the supported configuration has no child dispatch (no audit/lint subagents in Copilot) until that is solved.
- If SessionStart cannot inject the schema, look for another automatic context hook that runs the same `schema.sh`. No duplicated schemas, no wiki imports.
- If there is no reliable guard route or no reliable context route, stop the migration rather than ship a degraded mode. Do not retry a blocked action another way.

### Results of the spike

Run on Linux on 2026-11-17 with Copilot CLI 1.0.112 and Claude Code 2.1.326; the matrix is in `docs/development.md`, "Agents", the payloads in `tests/fixtures/clients/`, the driver in `tests/live/` (`Dockerfile`, `setup.sh`, `capture.sh`, `run.sh`), and one line per run, with its flags, hook modes and what the guard returned, in `tests/live/results.md`. Baseline at `94456e8` in the container: all tests, `--e2e`, ruff and shellcheck green. About 50 prompt-mode sessions, about 31 Copilot premium requests and $1.90 of Claude usage. Copilot CLI (1.0.113, Windows) reviewed the evidence; its findings are folded in below and in the matrix, and a second round of runs answered the ones that needed a run.

No stop condition holds:

- **Child calls are guarded.** Both clients send every child tool call through the plugin's PreToolUse hooks with an `agent_id`, the main session's calls without one, and a deny stops a child's call with its reason shown. Audit/lint dispatch can stay on in Copilot.
- **There is a context route,** but not today's: Copilot ignores SessionStart's plain stdout and Claude's `hookSpecificOutput.additionalContext`, and reads only a top-level `additionalContext`. One JSON object with both keys reached the model in both clients, at start and after resume, and in Copilot it survived automatic compaction.
- **There is a guard route,** with work: Copilot uses Claude's tool names but its own argument names, so the guard needs normalization (step 3); today it refuses every Copilot Write and Edit, and lets Copilot's Grep and Glob reach a source only subagents may read (their `paths` isn't read).
- **The guard holds in the mode Copilot will be used in.** Under `--autopilot --allow-all` the plugin's hook still ran on every call: the real guard refused `git push` and a write to `.claude/settings.json`, from the main session and from a subagent, and the remote's refs and the file were unchanged.

Gating cases found, now in the steps below: a hook timeout lets the call through in Copilot even with `onFailure: "block"` (Claude then refuses it); a hook exit other than 2 lets it through in Claude (py-launch.sh already maps those to 2); Copilot's patch tool sends several files as one string, and its hook runs before Copilot parses the patch; Copilot's Grep and Glob take `paths` as a string or a list; `read_bash` fires no hook; Copilot in `-p` silently loads no plugin in a folder that isn't saved as trusted; skill bodies get no `` !`cmd` `` and no `${CLAUDE_PLUGIN_ROOT}` in Copilot; in autopilot nobody answers the skills' questions.

**Copilot in autopilot with `--allow-all`** is how the owner runs it, so it is the supported Copilot configuration, and the steps below are written for it. What that changes: Copilot's own permission checks are off (tools, paths outside the wiki, URLs), so the guard is the only check on a tool call; a question the agent asks gets "the user is not available" back, and the agent guesses and goes on; each automatic continuation is a premium request (5 by default, `--max-autopilot-continues`). `--deny-tool` rules still win over `--allow-all` and are the one second layer that survives it; they can only be given on the command line.

Not run, still owed before part B: **1.7 (Windows)**, which needs a Copilot login that can't land in the Windows credential store the developer's own login uses (a fine-grained token in `COPILOT_GITHUB_TOKEN` for the spike's processes only); **`write_bash`**, which prompt mode doesn't offer: one interactive session. Owed in part B, where the steps below use them: background and nested subagents (only a synchronous child was captured); Claude's automatic compaction (only `/compact` run); MCP tool calls (Copilot connects its GitHub MCP server by default, and has a separate `preMcpToolCall` event: whether PreToolUse fires for MCP tools at all); whether Copilot ignores SessionStart matchers or maps them (it runs the `startup` group on resume, and its `source` at start is `new`, not `startup`); `COPILOT_CLI=1` in the agent's shell on Linux (the review saw it on Windows); a hook whose interpreter is missing (only a script's exit 127 was run); the interactive trust prompt (from the review and Copilot's docs: an interactive start in an untrusted folder asks, and No exits).

For the driver, learned the hard way: the container needs `--init` (a test waits on a killed process, and a `sleep` PID 1 never reaps it); Copilot crashed before its first hook on about 1 start in 9 (SIGSEGV, once "Failed to load package index"): `run.sh` retried one, the earlier ones were rerun by hand, and it now retries both kinds once; `--resume` can't be combined with `--trust-folder`; a claude.ai login brings the organization's synced plugins and settings into a fresh profile, so isolation is per machine, not per account; captures now carry the run's ID, so a late hook from an earlier run is set aside rather than counted; a prompt-mode permission denial looks like a hook denial, so every deny probe allows its command with `--allow-tool` (or runs under `--allow-all`) and reads the result from the hook's own record and the side effect.

## Part B: first delivery (Copilot on Linux)

Each step names its files and an exit condition. Details below are the current best guess and are expected to shrink after part A.

### 2. Package loading and wiki-scoped activation

Files: the marketplace/plugin manifests, `templates/project-settings.json`, `wiki_check.py`, setup docs; tests in `test_wiki_check.py` and the live module.

1. Keep the package layout. Quote the research skill's description (Copilot rejects it today). Check the other frontmatter with both clients' loaders; the agents' `effort:` only draws a Copilot warning and stays.
2. `.claude/settings.json` is the shared activation declaration: the spike saw Copilot load the plugin from `enabledPlugins` and `extraKnownMarketplaces` alone, and nothing in an unrelated folder or wiki-tools. Claude in `-p` needed the marketplace registered for the user first; check whether that holds interactively, and keep the setup docs' registration step either way. Verify in a fresh wiki, not on a preconfigured machine.
3. ~~A derived `.github/copilot/settings.json` fragment~~: not needed, per the spike.
4. Registration and authentication are per machine and client; activation is per wiki. No invented `--scope project` flag, no global guard.
5. Resolve scripts against the executing plugin, never a fixed clone path, in local-directory and installed-copy modes. Both clients run a directory marketplace in place and fill in `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` for hooks (Copilot's data root is `~/.copilot/plugin-data/`). Teach the readiness check the activation mode.
6. **Trust:** an interactive Copilot start in an untrusted folder asks whether to trust it, and No exits. But `copilot -p` in a folder not saved as trusted loads none of the plugin and says nothing, so no guard runs; `-p --resume` can't take `--trust-folder`. Nothing of the plugin can detect this from inside. The setup docs say: answer the trust prompt with "remember", or a later `copilot -p` in the wiki runs unguarded; missing skills mean an untrusted folder.
7. **A start command for Copilot in a wiki,** given in the setup docs as a shell function: `copilot --autopilot --allow-all` plus `--deny-tool` rules for what the guard also refuses and Copilot can name (`shell(git push)` first). The rules are a second layer under `--allow-all`, never a replacement for the guard, and the live tests run without them (step 8) so they can't hide a guard miss.

**Exit:** fresh project activation loads the plugin, its schema and its skills in both clients; an unrelated folder and wiki-tools itself remain unguarded. `--plugin-dir` alone does not satisfy this.

### 3. Extend the common guard

Files: `hooks/hooks.json`, `scripts/hookjson.py`, `guard.py`, `py-launch.sh`; fixtures and `test_guard.py`, `test_py_launch.py`, `test_contract_parity.py`.

**How an unknown tool is handled: option a, proposed from the spike's numbers, for the owner to confirm with this plan's review.** Today a tool outside the matcher list never reaches the guard, and the guard allows a name it does not know. Adding Copilot's names to the list keeps that hole for every later tool. The spike saw Copilot reuse Claude's names for its file and shell tools, add its own (`skill`, `stop_bash`, `tool_search_tool`), and fire no hook at all for `read_bash`; one guard run costs 20-33 ms on Linux, and Copilot runs a call's hooks one after another, Claude in parallel. The options:

| Option | Effect | Cost |
|---|---|---|
| **a. Catch-all matcher, classified list in the guard** (recommended) | Every tool call reaches the guard. Known shell/file/read tools are checked as today; a known-harmless list and MCP tools (`mcp__*`, governed by contracts as today) pass; any other name is refused with a message naming the tool. | One hook launch per tool call in both clients. A new built-in tool in either client is refused until it is classified: a deliberate change to Claude behavior, to be said in the commit message. |
| b. Catch-all matcher, unknown names pass with a logged warning | Visibility without refusals. | The hole stays; only detection improves. |
| c. Fixed list plus Copilot's names | Smallest change. | The hole stays and is found only by re-running live tests. |
| d. Like a, but the matcher leaves out the known-harmless names | Unknown names still reach the guard and are refused; known-harmless tools start no process. | A negative-lookahead matcher: Claude's matchers are regexes, Copilot's support for one is unchecked. The list lives in two places (matcher and guard), kept in step by a test. |

Under `--allow-all` the guard is the only check on a tool call (results above), which weighs for a or d over b and c. Before choosing between a and d, measure one guard run on Windows in a real wiki session (Linux: 20-33 ms; Windows is estimated at 150-300 ms from ADR 4's process-start numbers) and count from a real session's transcript how many extra calls a catch-all adds.

Then:

1. Apply the decision. Every enabled file-mutation, shell-execution and protected-source read/search capability reaches the guard or stays outside the supported configuration. Shell follow-up input (`write_bash`) is checked as a command; whether it fires a hook at all is the interactive check still owed from step 1. `read_bash` and `stop_bash` touch only a shell the guard already let start.
2. Normalize the observed payloads (`tests/fixtures/clients/`) into the guard's current representation (`hookjson.py`). `tool_name`, `cwd`, `agent_id` and `session_id` are already Claude's; the arguments are not: `path` for `file_path`, `file_text` for `content`, `old_str`/`new_str` for `old_string`/`new_string`, `paths` for Grep's and Glob's `path`, as a string or a list (the spike saw both; every entry is checked). Today an `agent_only` root given as Grep or Glob `paths` passes the main session: the spike's rerun showed it with a codebase instance. Copilot's patch tool arrives as `Edit` whose `tool_input` is the patch text, with absolute paths: parse its `*** Add File:`, `*** Update File:`, `*** Delete File:` and `*** Move to:` lines and check every target and every added line. Add and Update/Move were captured; Delete is from the format. The hook runs before Copilot parses the patch (the spike's malformed patch reached the hook, then failed to apply), so the guard parses it itself and blocks a patch it can't parse. A missing or malformed field in a checked tool's payload blocks, as now. No second policy engine. The fixtures become `pass-`/`block-` cases.
3. Child identity: a missing or untrusted `agent_id` is treated as the main session, so it never grants `agent_only` access.
4. Copilot on Windows is part C. Until then the guard refuses every shell call from Copilot on Windows (`COPILOT_CLI=1` on a Windows platform), because its PowerShell commands arrive as `tool_name: "Bash"` and must not be checked as Bash text. Claude's PowerShell refusal stays as it is. `COPILOT_CLI` is inherited: a Claude session started from a Copilot shell sees it too, so on Windows such a session's shell calls are refused as well; name that edge case rather than guess the client another way.
5. Preserve push blocking, root protection, wrapper lookalike/chaining checks, broken-contract behavior and diagnostics. Where Copilot cannot inherit Claude's permission denials, cover the contract-declared shell denials in the guard; combine denials, never client grants.
6. Protected paths: **parity, not expansion.** Today the guard protects `.claude/sources`, `.claude/settings*` and `.claude/plugins/` (with the cached Python). Add only Copilot's direct equivalents: its project settings and hook files (`.github/copilot/settings*.json`, `.github/hooks/`) and, under `COPILOT_HOME`, `plugin-data/` (where the cached Python lands, since Copilot sets `CLAUDE_PLUGIN_DATA` there) and `installed-plugins/`. User-level profiles, extensions, MCP configuration and agent/skill folders are not added: the guard is a guardrail, not a security boundary. They are named in the docs as outside the supported configuration instead. (Copilot also reads `disableAllHooks` from `.claude/settings*.json`, which the guard already protects.)
7. Reply with Claude's JSON deny (`hookSpecificOutput.permissionDecision: "deny"` and the reason): the spike saw it deny with the reason shown in both clients, where exit 2 shows Copilot no reason. Keep exit 2 as the fallback when the JSON cannot be produced; py-launch.sh's mapping of every other exit to 2 stays, since Claude lets a call through on exit 1 or 127.
8. **A hook that times out lets the call through in Copilot,** even with `onFailure: "block"`, which the guard hook has: the spike's hook was killed at its `timeout` (10 s; Copilot honors Claude's key) and the command ran. Claude refuses the call in that case ("timed out; blocking because onFailure is \"block\""); without `onFailure` it runs it too. So Copilot has no fail-closed timeout. Give the guard hook an explicit, generous `timeout` in `hooks.json`, keep the guard's own time far below it, and name the gap in `docs/guard.md`. Under `--allow-all` nothing else stops such a call.
9. ~~`wiki-check` reports an untrusted folder~~: in one, Copilot loads no plugin at all, so nothing of ours runs to report it (step 2, item 6).

**Exit:** all existing Claude guard cases pass, and real Copilot tool calls are refused for the same covered actions before any side effect. A hook log that says "block" while the command runs is a failure.

### 4. Shared skills, context and client readiness

Files: skill/agent bodies, `schema.sh` and a new `session_start.py`, `hooks/hooks.json`, `sync_status.py`, `sources.py`, `sourcelib.py`, `wiki_check.py`, the contract template and parser only as needed; tests in their existing modules.

1. Add the established "Run only when the user typed ..." line to the manual-only plugin skills. Keep Claude's frontmatter restriction; name arguments in descriptions.
2. Where a skill names a Claude-only tool API (`Agent` calls with `subagent_type`, question handling), replace it with a short shared capability binding: plain Bash execution, asking the user, named subagent dispatch, awaiting results. Preserve confirmations and named-path commits.
   **Questions in autopilot:** Copilot answers an agent's question with "the user is not available", and the agent guesses and goes on. Every confirmation a skill asks for (the first ingest's data-model review, page-model approval, `add-source` choices, themed commits, the manual-only line in item 1) says what to do when no one can answer: stop before writing, and report what was waiting for the user. This is an instruction, not enforcement: a wrong guess can reach a commit, never the remote (the guard refuses `git push`). Step 8 tests it.
3. **One SessionStart hook, in Python:** a new `session_start.py` behind `py-run.sh` reads both schema files, fills in the plugin root, adds the sync status, and prints one JSON object carrying all of it as both `additionalContext` (Copilot) and `hookSpecificOutput.additionalContext` (Claude), the form the spike saw reach both. `json.dumps` does the escaping that bash would have had to do by hand, and one Python start replaces three hook processes. It keeps the 9,000-byte budget check per schema file, and still prints the other parts when one fails. Without Python, the launcher prints the schema as plain text, which Claude still reads (Copilot is unsupported without Python anyway: its guard needs it). `schema.sh` stays as the plain-text printer the launcher and the tests use. Record the change in `docs/adr.md`, 4, which lists `schema.sh` among the scripts that stay bash. Check Copilot's size limit for that context. The sync status no longer depends on the `startup` matcher, which Copilot runs on resume too.
4. Skill bodies, from the spike: Copilot runs no `` !`cmd` `` and fills in no `${CLAUDE_PLUGIN_ROOT}`. So the skills keep their `` !`cmd` `` lines, which Claude runs before the model reads the skill at no model turn, and add one line after them: if the blocks above are still command lines rather than their output, run them first, with `${CLAUDE_PLUGIN_ROOT}` replaced by the plugin root named in the schema context. Claude keeps today's speed; Copilot makes the calls. The schema context states the resolved plugin root, which the skills' other `${CLAUDE_PLUGIN_ROOT}` mentions rely on too. Step 8 checks that Claude doesn't run the scripts a second time, and records what text Copilot's model gets for a `` !`cmd` `` line. `allowed-tools` is ignored, not an error: accept the extra approval prompts in Copilot. Copilot names the skills without `wiki:`; the docs give both spellings.
5. Add `--client claude|copilot` only to the diagnostics and source views that need client readiness. Explicit selection wins; otherwise `COPILOT_CLI=1` selects Copilot (the spike saw Copilot set it in hooks and Claude not; the review saw it in Copilot's agent shell on Windows, still to be seen on Linux; it is inherited by anything started from that shell), and a plain terminal keeps the Claude default. Sanitize these variables in test environments. The guard's rules do not depend on the client.
6. One small declarative source opt-in, `clients:`, in the existing flat contract format: absent means Claude only (today's behavior, so older local types stay valid), local-folder declares both, built-in raw is handled by the core. Validate it like `platforms:`, with parser parity.
7. `sources.sh list/show/catalog`, sync status, init/check and add-source show a source as unavailable in Copilot without calling a valid instance broken. Ingest and research refuse it; audit reports its claims as unresolved. Its sync state and cache are untouched. **This refusal is an instruction, not enforcement:** a wrapper-based source is also refused by the guard where its contract says so, but nothing stops a user's own MCP server in Copilot. Say so in `docs/guard.md` rather than imply protection.
8. Copilot readiness checks never report Claude permission strings as effective protection, and the installer reports do not tell Copilot users to add permissions it ignores.
9. Version drift: each client may run its own installed copy of the plugin against the same wiki. This delivery changes no page, state, cache or contract format, and `clients:` is optional, so an older copy still reads the wiki. Make `wiki-check` print the executing plugin's root and commit (or content hash), so two copies can be compared. A later change that an older copy cannot read needs its own decision in `docs/adr.md`.
10. The two research roles stay authored once and discoverable. Audit/lint subagent dispatch stays on in Copilot: the spike saw child calls guarded and identified by `agent_id` in both clients, for a synchronous child; background and nested subagents are checked in step 8 before this is claimed for them. Codebase research, `agent_only` and nested critique stay parked with the codebase source.

**Exit:** the supported routines work in both clients, unavailable sources do not block them, no state migration is introduced, and client selection is covered without changing standalone Claude defaults.

### 5. Raw ingestion

Files: `skills/ingest/SKILL.md`, `reading-files.md`, shared schema/skill prose only where needed; focused tests and the live story.

1. Keep raw's listing, state, privacy, citation, page-model review, log and commit semantics.
2. In each client, ingest a short text document with a verbatim figure and date, then a changed document. Check source evidence, named-path commit, frontmatter, index, append-only log and `last_checked_raw`.
3. Re-run without new material: no duplicated facts, no spurious ingest entries.
4. Check text PDF, Office conversion and image/scanned-PDF routes where the prerequisites exist, and mark what is missing. No OCR/rendering dependency added to hide a client difference; raw text is the mandatory case.

**Exit:** both clients maintain the same raw-backed pages and state. The release states the supported formats precisely.

### 6. Local-folder ingestion

Files: the local-folder contract and wrapper and shared source helpers only if the evidence requires; `tests/test_install.py`, path/guard fixtures and the live story.

1. Add the contract's `clients:` declaration once the guard and the wrapper invocation work; do not fork the type.
2. Use an external source root with spaces, a subfolder and a single-file root. Exercise `new`, `list`, `info` and `copy` through the exact allowed wrapper.
3. Copies stay in `~/.cache/wiki-sources/<wiki>/<key>/`, never in the repo; the `Folder <key>:` citation format is unchanged.
4. Ingest, update a document, switch clients. The instance, source key, date semantics and shared cache/state are preserved.
5. Cover out-of-root, sibling-prefix, relative/dot-segment and unsupported-operation refusals; snapshot source hashes and assert no source mutation.

**Exit:** identical root, copy, citation and state semantics in Copilot and Claude on Linux.

### 7. Deterministic regression

Add focused cases to the existing test modules and fixtures for every changed script, hook and launcher. Preserve the seven parked sources' Claude parsing, rules, settings, sync and guard behavior; `clients:` must not invalidate older local types.

Required before runtime commits, on Linux and Windows as CI runs them:

```bash
bash tests/run-tests.sh
bash tests/run-tests.sh --e2e
ruff check .
git ls-files -z '*.sh' | xargs -0 shellcheck -S warning
```

**Exit:** the existing regression plus the focused migration cases pass on both platforms. This layer, not the live one, carries the detailed cases: fail-closed launcher paths, malformed payloads, wrapper lookalikes, protected paths.

### 8. A small live smoke set through the real clients

Extend `tests/conftest.py` and add `tests/test_live_clients.py`, reusing the git, file, normalization and argv helpers. No second runner, browser harness or SDK dependency. The spike's `tests/live/` (container, setup, capture hook, prompt-mode runner) is where this starts: its lessons (an init process, a retry only for a crash before the first hook, no `--trust-folder` on resume, org-synced Claude settings) carry over, and its shell runner becomes the pytest module's helper or goes.

Planned interface, not an existing command (a change to `run-tests.sh`, so it needs its own test and a green `--e2e`):

```bash
bash tests/run-tests.sh --live-clients both -k live_clients
```

`--live-clients copilot|claude|both`; omitted means no model calls. A requested client with a missing binary, login or model fails preflight rather than being skipped as green.

The set is deliberately small: paid, slow and non-deterministic tests that nobody re-runs prove nothing.

| Scenario | Evidence, for both clients |
|---|---|
| Start, resume, schema | Both schema canaries arrive through hooks; no direct schema read explains the answer. Resume by explicit ID. |
| Guard deny probe | A real shell and a real file-tool attempt (push to a local disposable bare remote; a write to a protected setting) from the main session, from a synchronous and a background child agent, and a nested one if the client offers it: the guard event, and unchanged refs and files. A Grep and a Glob with `paths` (string and list) into an `agent_only` root from the main session. |
| Raw story | First ingest, update, no-new-material run; evidence and dates preserved. |
| Local-folder story | Wrapper list/copy/ingest, changed file, untouched source, stable citations. |
| Cross-client handoff | Claude then Copilot, and Copilot then Claude, in one wiki: shared state consumed, no duplicated facts. |
| Unavailable source | A valid Claude-only instance beside the two supported sources: Copilot reports it unavailable, leaves its state alone and continues. |
| Nobody to ask (Copilot, autopilot) | A first ingest that needs the data-model review: the skill stops before writing and says what is waiting for the user; no page, state or commit changes. |
| Skill blocks | In Claude a skill's `` !`cmd` `` scripts run once (no second call by the model); in Copilot the model runs them itself. |

Rules for the driver:

- Real initialized wiki repositories and real CLI sessions, synthetic local material only; no source accounts.
- Isolated `COPILOT_HOME`, Claude configuration, HOME and cache roots; no personal profiles copied, no tokens printed. No unrelated plugins, MCP servers or extensions.
- Copilot runs as it is used: `--autopilot --allow-all`, without the start command's `--deny-tool` rules, so the guard alone is under test. Claude: no `--bare`, no permission bypass, narrow case-specific approvals for positive work. No fixture-supplied denies that mask the guard under test.
- The direct `--plugin-dir` lane tests the checkout. The normal-user lane (plugin registered from the release-candidate commit, wiki opened through its committed declaration) is run once per release in step 9, with the executing plugin's commit asserted.
- Explicit model IDs, per-process timeouts, a finite scenario count, at most two attempts per scenario. Record client versions and model IDs.
- Compare observed tool names with the guard's classified list; an unclassified name fails the run.
- **A model refusing to attempt an operation is not a guard pass.** Classify each deny probe as attempted-and-denied, attempted-and-executed, not-attempted or infrastructure-failed; only the first, with unchanged side effects, passes. Do not rephrase until it passes.

**Exit:** the eight scenarios pass in both clients on Linux (the autopilot one in Copilot only), with independent filesystem and git assertions.

### 9. One existing wiki, interactively

The disposable set does not show that a real wiki works.

1. The owner picks a non-sensitive existing wiki, or a sanitized copy, and approves exposing its instructions and content to each provider before either client starts: a read-only start already sends them to the model. Wiki identity, paths and content stay out of public evidence.
2. Through the normal-user lane, in each client: start, source inventory/status and `wiki-check`. The schema loads, existing instructions are honored, sources are classified correctly, files and state are unchanged. No external sources are run.
3. On a disposable copy with synthetic source material: user-typed init/check, ingest, lint/audit and themed commits, with approve and decline paths, then resume and compaction followed by a schema-dependent question and a wrapper call.
4. In Claude, the same release candidate with a wiki that still declares parked sources: start, readiness and local routines have not regressed.

**Exit:** Linux x Copilot and Linux x Claude signed off; Windows x Claude checked for regression (step 7's CI plus item 4). A check that was not run is "not run", not a pass.

### 10. Document and deliver the bounded claim

Update README, the setup/skills/sources/guard/development docs and the source template with: the supported client/platform/source/format matrix, native setup and update steps, the accepted invocation difference, what the guard does not cover in Copilot, and unavailable-source behavior.

**The support claim names versions:** "tested with Copilot CLI x.y.z and Claude Code a.b.c on <date>", in `docs/setup.md`. Re-run the smoke set (step 8) and update that line when a client release changes hooks, plugins or tool names according to its release notes, when `wiki-check` or a user reports a guard miss or an unclassified tool, and before any release that touches `hooks/` or the guard. Between runs the claim is the stated versions, not "current".

Normal PR CI stays deterministic and account-free. The live set is opt-in and is required evidence for this migration's merge; a protected manual CI job may run it later if both clients' credentials are provisioned, never on arbitrary PR code.

Record the built decisions in `docs/adr.md`. Push only through the personal-data hook and the normal branch/PR workflow.

When this plan is retired, move the remaining part C and the parked-source briefs into their roadmap rows before deleting the file. The parked "Guard hook for both agents" item concerns developing wiki-tools itself; do not enable wiki guards in this repo by accident. Coordinate fresh-clone activation checks with the Clone-anywhere layout item.

**Exit:** only the base, raw and local-folder capabilities that passed are advertised, for Copilot on Linux; the existing Claude claim for the other sources stands.

## Part C: Copilot on Windows

Its own delivery after part B, with its own short design once step 1's Windows observations exist. Until then the docs say Copilot is supported on Linux only, and the guard keeps refusing wiki scripts through PowerShell.

What it must settle:

- Whether Copilot on Windows can be given a Bash tool or shell setting at all; if so, most of this part disappears. First candidate: `COPILOT_BASH_PATH` (Copilot 1.0.112's `copilot help environment`: the bash used for the agent's shell commands and for command hooks; on Windows, otherwise bash from PATH). Step 1.7 tries it with Git Bash.
- Otherwise a single source-neutral invocation form, `& "<Git Bash executable>" "<native absolute script>" <args>`, that the guard recognizes only in that exact shape, rejecting WSL, `-c`/`-lc`, extra commands or operators and lookalike executables.
- **How the Git Bash executable is found and trusted in plugin code.** Today only the test suite resolves it; "from the trusted Git installation" needs a definition (which registry key or path, who may write it) before the guard relies on it.
- How the resolved executable and plugin root reach the skills (schema context, not a user-maintained registry, not a PowerShell `${CLAUDE_PLUGIN_ROOT}`).
- Tests: guard fixtures for the accepted form and each rejected one, launcher e2e on Windows, and the step 8 smoke set plus step 9 on Windows x Copilot.

## Deferred sources (parked)

One parked roadmap row covers all seven, with the trigger "the first delivery has shipped and a user needs this source in Copilot". Each depends on part B, not on another source. These briefs are scope notes, not approved plans: a source that is picked up gets its own design, which must choose a real reader, state/citation equivalence, enforcement, fake-source cases and live acceptance.

### Codebase

Expected effort: medium when named research agents and child identity work; otherwise blocked.

Native researcher dispatch, tool restrictions, trustworthy child identity, `agent_only` root enforcement and critic-to-checker nesting. Keep the git/gh wrappers, pinned citations, drift/verify operations and cache layout. Test raw gh write denials. Separate ordinary research from `--critique` if nesting is missing; the main session never reads the source as a fallback.

### OneNote

Expected effort: low-to-medium if a compatible reader exists; high otherwise.

A reader with created timestamps, section modification times, fresh text/HTML, group paths, read-only scope and attachments. Preserve snapshot/cursor/citation semantics and their known limits. Reuse the reader-neutral contract rather than create a Copilot type.

### Proton files

Expected effort: medium with a compatible external reader; high if it needs porting.

External plugin compatibility, registration/loading paths, read-only operation allowlists, roots on every call and download/cache behavior. Do not allow the underlying writable CLI or weaken protected cache rules to make an installed reader run.

### Jira

Expected effort: medium-to-high.

A Copilot-capable reader; compare JQL, fields, pagination, comment/link behavior and `updateHistory: false`. Preserve named scopes, backfill completeness, cursor precision and citations. Replace the "different MCP means different type" caveat only with a verified same-semantics reader.

### Gmail

Expected effort: medium, after the `gws` reader plugin ([roadmap](../roadmap.md)).

Reader: the `gws` reader plugin, the Google Workspace CLI behind a separate plugin like the `proton` reader, with only the `gmail.readonly` scope. The claude.ai connector doesn't exist in Copilot, and an MCP reader would need guard coverage of MCP calls first. Read-only is then enforced by Google, not by the guard: send, draft, delete and label writes fail in either client. The contract becomes tool-neutral (`access: tools`) with `guard_words: gws`, so the session reaches Google only through the reader, never `gws` directly or `gws auth`.

`gmail.readonly` can't apply the wiki-ingested label, so state moves to dates: search from the day before `last_checked` with an overlap window for late arrivals, and skip threads the sync log or a page's `sources:` already names by thread ID. This replaces labels for safety, not portability, and applies in Claude too once the reader serves both. Preserve thread retrieval, the instance's labels/senders/recipients/exclude filters and citations. Wikis with label state need a one-time transition.

Ready when the reader exists and passes in Claude, its status reports the granted scopes, and Copilot runs it through part B's shell route and guard. Tests: late-arriving mail inside and outside the window, an already-ingested thread, a token with broader scopes (Check warns), and direct `gws` / `gws auth` refused in both clients.

### Google Drive

Expected effort: medium, after the `gws` reader plugin ([roadmap](../roadmap.md)).

Reader: the same `gws` reader plugin, with only the `drive.readonly` scope, so sharing, editing and deleting fail at Google in either client. Contract as for Gmail: tool-neutral, `guard_words: gws`. State already needs no writes. Establish folder ID/path equivalence, recursive paging, modification dates, Docs/Sheets/Slides export and download shape against the current connector; preserve citations and cache behavior and explain formats the reader cannot export.

Ready when the reader exists and passes in Claude with traversal/export/citation equivalence, and Copilot runs it through part B's shell route and guard. Tests: paged trees, changed documents, missing formats, a token with broader scopes (Check warns), and direct `gws` refused.

### Microsoft Teams

Expected effort: highest.

Channels, replies, chat-day fetching, SharePoint trees, resource URIs, auth scopes, conversation ordering and tenant-wide result filtering, each evaluated separately. Reuse `snapshot.sh`/`snapshot.py`; no broad Microsoft 365 grants.

## Evidence references

- Repository mechanisms: [ADR 1-7 and 10](../adr.md), [development](../development.md), [setup](../setup.md), [guard](../guard.md), [skills](../skills.md), [layout](../layout.md).
- Copilot hook tests: `docs/development.md`, "Agents"; `docs/adr.md`, "Two coding agents, one set of rules".
- Guard dispatch: `plugins/wiki/hooks/hooks.json` (matcher), `plugins/wiki/scripts/guard.py` (`main`: unknown tools pass; PowerShell refusal), `hookjson.py` (required fields).
- Discovery defect: `plugins/wiki/skills/research/SKILL.md`, description frontmatter.
- Test reuse: `tests/conftest.py`, `test_guard.py`, `test_py_launch.py`, `test_install.py`, `test_sources.py`, `test_sync_status.py`, `test_wiki_check.py`, `test_agent_files.py`, `.github/workflows/ci.yml`.
- Client contracts: Copilot 1.0.112 shipped docs (Claude compatibility, environment aliases and `COPILOT_CLI`, project activation, plugin mounting, prompt-mode permissions, JSONL, resume, isolated configuration); Claude 2.1.325 command help.
