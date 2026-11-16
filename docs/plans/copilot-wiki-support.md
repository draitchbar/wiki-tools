# Plan: Copilot CLI in existing wikis

Status: planned, not implemented. Scope and [design](../copilot-wiki-design.md) settled with the user; this file turns the design into work that can be verified. Indexed in [the roadmap](../roadmap.md).

## Outcome and scope

Users can open the same wiki in Claude Code or GitHub Copilot CLI and switch between sessions without migrating instructions, pages, citations, source instances, caches or sync state. Simultaneous editing is not supported.

The first delivery is **the base plugin migration plus `raw` and `local-folder`**. They are the two easiest sources: raw is built in, and local-folder already has a tested, read-only Bash wrapper. Initial live stories use text; supported PDF/image/conversion capabilities are verified and documented separately, not silently presumed.

The other seven sources remain separate **design-phase tasks** below. Raw is built in, so the inventory is raw plus eight standard source types: local-folder in this delivery and seven deferred types. Their current Claude support stays intact. They may be enabled in Copilot one at a time after their reader and enforcement design is settled and tested.

DRY: one plugin package, schema, skill set, agent-role definitions, contract parser and guard policy. Keep a wiki's `CLAUDE.md` and `.claude/sources/`. Accept the existing instruction-based manual-only restriction in Copilot; do not build an invocation tracker. Keep Bash/Python launchers and the existing pytest conventions. No generic connector framework, copied instruction trees, new runtime dependencies or broad permission grants.

## Research and concrete findings

Read-only investigation on 2026-11-15 used this repository, Copilot CLI 1.0.112's shipped documentation and command help, and installed Claude Code 2.1.325's command help.

| Finding | Consequence |
|---|---|
| `copilot --plugin-dir <plugin> plugin list --json` recognizes `wiki` as an external plugin. | Package discovery works; it does not prove hooks, activation scope or skill execution. |
| Plugin skill enumeration loads seven skills, but rejects `skills/research/SKILL.md`: its unquoted description contains `mode: research`, which is invalid YAML for Copilot's parser. | Fix shared frontmatter and make actual client discovery a regression check. Do not claim all eight skills already load. |
| Copilot supports Claude-style manifests, project activation/hooks and legacy hook keys; hook environment aliases include the Claude plugin/project paths. | Start with native compatibility; capture actual tool payloads and denial behavior before choosing adapters. |
| `COPILOT_CLI=1` is documented in Copilot's hooks and agent shell commands. | Runtime client selection has a documented signal; no host-name or executable-path guessing is needed. |
| `--plugin-dir`, `--trust-folder`, `-p`, JSONL output and explicit session resume exist in Copilot. Claude has `--plugin-dir`, `-p`, stream-JSON output and explicit resume. | Both can drive opt-in real-client tests. Forced plugin loading is only one test lane, not proof of project installation. |
| Copilot does not use Claude `permissions.allow/deny`; user repository settings cannot supply Copilot's enterprise permission policy. | Do not generate fictitious permission JSON or translate narrow rules into broad shell allows. Preserve restrictions through the common guard/readers. |
| Copilot prompt-mode requests that would ask for approval are denied. Claude print mode can also deny unapproved requests. | A denied request alone is not evidence that the wiki guard worked. Tests need the attempted call, guard response and side-effect checks. |
| `bash` on Windows PATH can resolve to WSL, whereas the suite already resolves Git Bash. Copilot's native Windows command tool uses PowerShell. | Resolve Git Bash explicitly, use native absolute script paths, and reuse the test suite's NUL-separated argument driver. Do not assume a Claude Bash tool or Bash environment-variable syntax exists in PowerShell. |
| `bash tests/run-tests.sh --e2e` exercises launchers, not a model running in a wiki. | Keep that layer and add opt-in live-client acceptance, with a separate result. |
| Existing local-folder tests cover root boundaries, copying, spaces, dates and refusal cases. | Extend `tests/test_install.py` and guard fixtures rather than duplicate its wrapper logic. |

Unverified gates: hook matcher coverage and input arguments, exit-2/error/timeout denial, `shell: bash`/`onFailure: block`, SessionStart context and compaction behavior, skill injections/root substitution, file/image tools, and custom-agent restrictions/identity. Client documentation is not runtime proof.

## Delivery order

Each step names the files to change and an exit condition. These are implementation steps for a later coding task; this proposal changes only the design, this plan and their roadmap entries.

### 1. Establish a baseline and collect real compatibility evidence

1. Run the existing normal and launcher suites plus lint; record the baseline before editing runtime code.
2. Provision a disposable git wiki, a separate source folder, isolated client configuration/cache roots, and a test copy of the plugin. Use made-up content and no real source connectors. Start the minimal capture-only native driver here, using the isolation, permission and artifact rules under step 8; step 8 extends it with assertions, not a new driver. Do not capture from the developer's personal profile.
3. Use native CLI discovery to check all eight skills and both agent definitions. Record skill command names actually exposed by each client; do not assume Copilot uses `/wiki:` names.
4. In real Copilot and Claude sessions, capture the hook event/arguments for shell execution, shell follow-up input, read/search, write/edit and multi-file patch operations, in both the main session and a dispatched subagent. Capture plugin/project/data variables and hook exit/error behavior. On Windows, record Copilot's actual native shell, plugin-root substitution and Git Bash invocation; test an absolute interpreter path rather than bare `bash`. Inspect native JSON/session events, not just final prose.
5. Prove schema injection using run-specific canaries in the test copy's schema, without letting the actor read the schema files. Check start and resume; exercise native compaction/reset in the interactive lane.
6. Try shared project activation without `--plugin-dir`, and separately a local-directory mount. Verify exactly one guard invocation per relevant call and no activation in an unrelated folder.

**Exit:** a compact capability matrix, normalized synthetic payload fixtures and explicit unsupported/gating cases. Hook denial must cover child-agent calls as well as the main session. If child calls are unguarded, disable their dispatch in the supported configuration; do not claim audit/lint subagent parity or declare the base delivery accepted until resolved. If SessionStart cannot inject schema, investigate another compatible automatic context hook using the same `schema.sh`; no duplicated schemas or restored wiki imports. If no reliable guard/context route exists, stop the base migration rather than ship a degraded mode. Do not retry a blocked action through another route.

### 2. Make package loading and wiki-scoped activation work

Files: the existing marketplace/plugin manifests, `templates/project-settings.json`, `wiki_check.py`, and setup docs; tests in `test_wiki_check.py` and the live module from step 8.

1. Keep the existing package/layout; correct the offending research description by quoting it in the shared skill. Check other frontmatter with both clients' actual loaders.
2. Prefer `.claude/settings.json` as the shared project activation declaration. Verify marketplace resolution in a fresh wiki, not just in a developer's preconfigured machine.
3. If Copilot does not honor that declaration with the required scope, emit the smallest derived `.github/copilot/settings.json` activation fragment containing `enabledPlugins` and `extraKnownMarketplaces`. No separately authored plugin list; no Copilot-only instruction file.
4. Keep registration/authentication per machine/client, activation per wiki. Do not add an invented Copilot `--scope project` flag or enable the guard globally.
5. Inspect installation/update behavior for local-directory and installed-copy modes; resolve scripts against the executing plugin, not a fixed clone path. Teach readiness checks the selected activation mode.

**Exit:** fresh project activation loads the plugin, its schema and its skills in both clients; an unrelated folder and wiki-tools itself remain unguarded. Loading with `--plugin-dir` alone does not satisfy this step.

### 3. Extend the common guard at the runtime boundary

Files: `hooks/hooks.json`, `scripts/hookjson.py`, `guard.py`, `py-launch.sh`; matching fixtures and `test_guard.py`, `test_py_launch.py`, `test_contract_parity.py`.

1. Add the actual client tool names/matchers captured in step 1. Every enabled file-mutation, shell-execution and protected-source read/search capability must reach the guard or stay outside the supported configuration. Shell follow-up input is checked as a command.
2. Normalize observed payloads into the current guard representation. Validate all patch targets and replacement content; refuse unknown/malformed protected-capability payloads instead of using the existing unrecognized-tool allow path. Do not write a second policy engine.
3. Keep PowerShell distinct from Bash. Use a single source-neutral invocation binding: Linux runs `bash "<absolute script>" <args>`; Copilot on Windows runs `& "<verified Git Bash executable>" "<native absolute script>" <args>`. Resolve the interpreter from the trusted Git installation, not a same-named executable on PATH; use the resolved plugin root, never a PowerShell `${CLAUDE_PLUGIN_ROOT}` variable. Recognize the leading PowerShell invocation operator only for this exact, validated wrapper form. Reject WSL, arbitrary Bash `-c`/`-lc`, extra commands/operators and lookalike executables; keep the existing argument/chaining restrictions. Claude's existing native Bash route remains supported.
4. Preserve push blocking, root protection, wrapper lookalike/chaining checks, broken-contract behavior and diagnostics. Cover existing contract-declared shell denials through the same guard where Copilot cannot inherit Claude permissions; combine denials, never client grants.
5. Protect both clients' project/user configuration, registered wiki-plugin copies, cache/data roots and disabling operations from either client's wiki session, including a relocated `COPILOT_HOME` and the cached Python path. Explicitly cover project `.github/copilot/settings*.json`, `.github/hooks/`, guard-affecting `.github/agents/` and `.github/skills/`, `.agents/skills/`, `.claude/skills/`, existing `.claude/settings*`/`.claude/sources/`, and both clients' settings/plugin state. Cover `disableAllHooks`, `disabledHooks` and plugin-disable operations. Keep these as shared protected paths, not duplicate guards; do not create one-client instruction/skill files.
6. Verify the launcher's exit-2, unexpected exit, unavailable interpreter and timeout paths in each native client. Add a response-format adapter only if measured behavior requires one.
7. Keep experimental extension loading/augmentation outside supported wiki configurations until its tools have equivalent coverage. Protect extension definitions/controls; do not use an extension as the compatibility layer. Base Copilot support includes no external source MCP integration, and at most the built-in default read-only GitHub subset. Protect configuration/operations that enable writable MCP tools; do not load user source MCP servers into the supported base profile. Classify the native execution surface and compare observed tool names against it in live tests, so a later client tool cannot silently escape an old matcher list. An unclassified execution/mutation capability blocks that client-version support claim.

**Exit:** all existing Claude guard cases still pass, and actual Copilot tool calls are refused for the same covered actions before any side effect occurs. A hook log that says "block" while the command executes is a failure.

### 4. Adapt shared skills, context and minimal client readiness

Files: existing skill/agent bodies, `schema.sh`, `sync_status.py`, `sources.py`, `sourcelib.py`, `wiki_check.py`, contract template/parser only as needed; tests in their existing modules.

1. Add the established "Run only when the user typed ..." guard to manual-only plugin skills. Retain Claude's frontmatter restriction and name arguments in descriptions; do not simulate manual invocation enforcement.
2. Replace exclusive tool API spelling with a short shared capability binding where necessary: plain Bash execution, native question handling, named subagent dispatch, awaiting results and same-task follow-up. On Windows, publish the resolved Git Bash executable and native plugin root through the existing schema/capability context, and use step 3's precise PowerShell invocation form. Do not require a new user-maintained path registry. Preserve confirmations and named-path commits.
3. Keep `schema.sh` as the schema loader. If `!` injections do not work, use explicit calls to the same scripts in shared skills. If skill-body plugin-root substitution fails, use the resolved root from schema context. No schema copies or wiki imports.
4. Add explicit `--client claude|copilot` only to existing diagnostics/source views that need client readiness. Explicit selection wins; otherwise `COPILOT_CLI=1` selects Copilot in client-launched commands, and an ordinary terminal retains the Claude default. Sanitize these variables in test environments. The guard's protected paths/denials do not depend on guessing the client.
5. Distinguish supported-in-client from valid-contract and installed/authenticated-reader. Use one small declarative source opt-in, `clients:`, in the existing flat contract format: absent means current Claude-only behavior, local-folder declares both clients, and built-in raw is handled by the existing core. Validate known values the same way as `platforms:`, with parser/validation parity and old-local-type cases. Do not hard-code the seven deferred types into skills or implement MCP transport bindings now.
6. `sources.sh list/show/catalog`, sync status, init/check and add-source show unavailable-in-Copilot without declaring a valid instance broken. Ingest/research refuse that source explicitly; audit reports unresolved claims. Its sync state and cache are untouched. Update broken-contract diagnostic exceptions for the new `--client` argument position, so source inspection remains possible when setup is broken.
7. Copilot readiness checks never report Claude permission strings as effective Copilot protection. Installation/source-file handoff remains a user's external-terminal action; adapt the existing installer reports to avoid instructing Copilot users to add ignored permissions.
8. Keep the two research role definitions authored once and discoverable. General audit/lint subagent dispatch must work for supported sources. Codebase research, `agent_only` and nested critique stay gated by the later codebase task, not disguised as working base functionality.

**Exit:** supported wiki routines operate in both clients, unavailable sources do not block them, no state migration is introduced, and explicit/implicit client selection is covered without changing standalone Claude defaults.

### 5. Deliver raw ingestion

Files: `skills/ingest/SKILL.md`, `reading-files.md`, related shared schema/skill prose only where needed; focused tests and live stories.

1. Keep raw's current listing, state, privacy, citation, page-model review, log and commit semantics.
2. In each native client, ingest a short text document with a verbatim figure/date, then a changed document. Check source evidence, named-path commit, frontmatter, index, append-only log and `last_checked_raw`.
3. Re-run without new material: no duplicated facts or spurious ingest entries. Keep actor refusals/failures visible.
4. Check supported text PDF, Office conversion and image/scanned-PDF routes on each platform where prerequisites exist. Mark missing capabilities explicitly. Do not add OCR/rendering dependencies merely to hide a client difference; raw text is the mandatory first-delivery acceptance case.

**Exit:** both clients can maintain the same raw-backed pages and state. The release states supported formats precisely; "source supported" does not imply every document format works.

### 6. Deliver local-folder ingestion

Files: existing local-folder contract/wrapper and shared source helpers only if the live evidence requires changes; `tests/test_install.py`, path/guard fixtures and live stories.

1. Add the contract's Copilot support declaration after its guard and wrapper invocation work; do not fork the type.
2. Use an external source root with spaces, a subfolder and a single-file root. Exercise `new`, `list`, `info` and `copy` through the exact allowed wrapper.
3. Confirm copies remain in `~/.cache/wiki-sources/<wiki>/<key>/`, never in the repo; use the unchanged `Folder <key>:` citation format.
4. Ingest then update a document and switch clients. Preserve the instance, source key, date semantics and shared cache/state.
5. Cover out-of-root, sibling-prefix, relative/dot-segment and unsupported-operation refusals. Snapshot source hashes/metadata and assert no source mutation. Fix only differences caused by the migration.

**Exit:** identical root/copy/citation/state semantics in Copilot and Claude on Linux and Git Bash on Windows.

### 7. Keep deterministic regression coverage green

Add focused cases to the existing test modules and fixtures for every changed script/hook/launcher. Preserve all seven deferred sources' Claude parsing, rules, settings, sync and guard behavior; new client metadata must not invalidate older local types.

Required before runtime commits:

```bash
bash tests/run-tests.sh
bash tests/run-tests.sh --e2e
ruff check .
git ls-files -z '*.sh' | xargs -0 shellcheck -S warning
```

Run the suite normally and with `--e2e` on Linux and Windows as CI does. Do not replace these with the live suite. Keep LF and standard-library-only plugin code.

**Exit:** existing regression plus focused migration cases pass on both platforms.

### 8. Add opt-in end-to-end tests through the real clients

Extend `tests/conftest.py` and add `tests/test_live_clients.py`; reuse its git, file, normalization and Bash/argv helpers. No second test runner, browser harness or new SDK dependency.

Planned interface, not an existing command:

```bash
bash tests/run-tests.sh --live-clients both -k live_clients
```

`--live-clients copilot|claude|both` selects installed native clients; omitted means no model calls and no real-client prerequisites. An explicitly requested client with missing binary/auth/model fails preflight rather than being skipped as a green test.

Use real initialized wiki repositories and real CLI model sessions, not mocked tool calls. This automated layer sends only synthetic local source material to the model clients; no Gmail/Jira/Drive/Teams accounts or third-party source APIs are used. The separately consented existing-wiki check in step 9 is not a synthetic-data test.

#### Native driver and isolation

- Launch CLI processes with argument arrays through existing subprocess helpers. Preserve hooks and normal instructions; do not use Claude `--bare`, permission bypass, Copilot `--allow-all`, or fixture-supplied denies that mask the guard being tested.
- Provision isolated `COPILOT_HOME`, Claude configuration, HOME/cache roots and per-run logs. Authenticate the test profiles through a supported operator/CI credential method; never copy whole personal config/credential directories or print tokens. Limit credential exposure to the CLI; use Copilot's `--secret-env-vars` for tool subprocesses where applicable.
- Explicitly exclude unrelated plugins, source MCP servers, extensions and inherited bypass flags. Preserve required environment for native execution and Git Bash; extend `base_env` sanitization instead of mutating the user's profile.
- Copilot's normal driver uses documented `-p`, `--trust-folder`, `--output-format json`, `--sync-session=off` and `--no-experimental`. Claude uses `-p`, `--output-format stream-json --verbose`, appropriate non-bypass permission mode and explicit session IDs. Confirm the installed version's exact flags during preflight.
- Configure test model IDs explicitly per client, with no silent fallback. Record versions/model IDs, scenario IDs, timestamps and native events. Require an operator-supplied spending ceiling and enforce per-process timeouts, finite scenario count and at most two attempts per scenario. Timeout kills only the processes launched by that test.
- Use narrow case-specific native approvals for positive work. An execution grant for a deny probe is confined to the disposable fixture and its exact operation; do not turn off the guard to make it run.
- Capture both attempted tool input and returned hook/tool events. Retain detailed local artifacts for failures; normalize machine paths in shareable summaries. Never commit/upload private transcripts or real-wiki text. Cleanup only exact owned temporary paths and process IDs.
- Check observed tool names against the classified execution surface from step 1. Fail acceptance on an unclassified tool instead of assuming its calls inherit the existing matcher.

#### Two loading lanes

1. **Direct local plugin lane:** `--plugin-dir` exercises current checkout hooks/skills without changing global registration. Only this lane uses test-copy fault injection.
2. **Normal-user activation lane:** register/install a local-path or local-git marketplace at the exact release-candidate commit through an isolated client profile, then open the wiki through its committed project declaration **without `--plugin-dir`**. Assert the executing plugin's commit/content hash before cases count; do not silently test the published version. Include a fresh wiki clone, enabled wiki, disabled/unrelated folder and update/restart. This is required acceptance, not optional packaging coverage.

#### Scenarios and assertions

| Scenario | Required evidence, for both clients |
|---|---|
| Start/resume/schema | Both run-specific schema canaries arrive through hooks; no direct schema read explains the answer; one guard per relevant tool. Resume by explicit ID, never the user's most-recent session. |
| New/adopt/check | User-approved new/adopt flows create the expected layout without writing protected setup themselves. Established wiki check finds planted faults; Copilot does not mistake Claude permissions for protection. |
| Status/lint/audit/commit | Real skill invocation, correct reports and confirmation boundaries; exact synthetic claims/citations; named-file commits and no pushing. Include a small two-source audit that actually dispatches a checker. |
| Raw story | First ingest, update and no-new-material run; evidence and dates preserved; structural checks pass. |
| Local-folder story | Wrapper list/copy/ingest, root and cache boundaries, changed file, untouched source and stable citations. |
| Cross-client handoff | Claude -> Copilot and Copilot -> Claude sequences in the same wiki. Shared state and snapshots are consumed, not recreated; no duplicated facts or schema/source-key migration. |
| Unavailable source | A valid Claude-only instance/citation coexists with the two supported sources. Copilot explains unavailability, leaves its state/cache untouched and continues supported work. Claude's fixtures still accept it. |
| Guard deny probes | Actual shell/file tool attempts, corresponding guard denial and unchanged source/config/remote. Cover push, protected settings/data, out-of-root write, wrapper lookalike/chaining and multi-file patch where exposed. Include a deny probe from a dispatched child agent to prove inherited hook coverage. |
| Fail-closed probes | Missing interpreter, malformed payload and hook failure/timeout in disposable plugin variants; actual tool request denied with no marker side effect. |
| Scope and installation | Native project activation works; unrelated folders have no wiki guard; direct mount is not used to conceal installation failure. |

For a harmless push probe, use only a local disposable bare remote and inspect its refs. Never test against GitHub or a real wiki remote. For protected settings/cache probes, targets are disposable profiles, never the user's real setup.

**A model refusing to attempt an operation is not a guard pass.** Classify: attempted-and-denied, attempted-and-executed, not-attempted/inconclusive, or infrastructure-failed. Only the first plus unchanged side effects passes a denial case. Prompt-mode permission refusal without the guard event is inconclusive. Do not keep rephrasing until a pass; unresolved conformance blocks signoff.

Where prompt mode cannot deliver an explicit user skill invocation or multi-turn confirmation, use the interactive acceptance in step 9. Feeding a skill's text as a system prompt does not count as testing the installed skill.

**Exit:** real-client results, independent filesystem/git assertions and native traces meet the matrix; deterministic tests alone cannot satisfy it.

### 9. Verify real existing wikis and interactive lifecycle regression

The disposable live suite is necessary but not sufficient for "works in real wikis".

1. On each platform, run the base release candidate in a user-selected existing wiki under Copilot and under Claude. Before launching either model client, the owner must approve exposing that wiki's instructions/content to that provider: use an appropriate non-sensitive wiki or an owner-sanitized copy. Read-only startup still loads real instructions and can send them to the model; it is not a no-disclosure test. Do not use an agent to send sensitive or third-party material. Keep wiki identity, paths, content and account details out of public evidence.
2. First do read-only startup, source inventory/status and `wiki-check`: schema loads, existing instructions are honored, supported/unavailable sources are classified correctly, and existing files/state are unchanged. Do not run external sources.
3. On a disposable copy with synthetic replacement source material, run actual user-typed init/check, ingest, lint/audit and themed commits with normal approval prompts. Exercise approve/decline paths for page-model changes and audit fixes. The actor cannot self-authorize a confirmation merely because a headless prompt said "yes".
4. Exercise native session resume and interactive compaction/context reset, then ask a schema-dependent question and run a supported wrapper. Verify context and guard continuity. Do not promise headless coverage for interactive-only commands.
5. Use the same release-candidate plugin in Claude, including normal installed loading and a wiki that still declares deferred sources. Verify candidate content hashes in both clients. Check that startup/readiness and local routines have not regressed; retain the deterministic fake-source regression for those deferred connectors.
6. Record only sanitized client/platform/version/case verdicts and private local evidence locations. An absent platform/client check is "not run", not a pass.

**Exit:** Linux x Copilot, Linux x Claude, Windows x Copilot and Windows x Claude all have disposable live and existing-wiki/interactive signoff. Failures or inconclusive guard cases block declaring the first delivery supported.

### 10. Document and deliver the bounded support claim

Update README, setup/skills/sources/guard/development docs and the source template with the supported client/platform/source/format matrix, native setup/update instructions, accepted invocation difference, and explicit unsupported-source behavior.

The normal PR CI remains deterministic and account-free. Paid live tests are opt-in and required release/merge evidence for this migration. A future protected manual CI job may run them if both clients' credentials/models are provisioned; do not expose those credentials to arbitrary PR code or add paid tests to every PR by default.

Record the built decisions in `docs/adr.md` after implementation, as repository policy requires. Push only through the enabled personal-data hook and normal branch/PR workflow; do not bypass a failed hook or push.

Before retiring this plan, move each remaining source's scope/readiness brief into its roadmap row and remove the links into this file. Park it with the trigger "base migration shipped and a user needs this source in Copilot". A detailed design gets its own file when picked up. Do not delete this file while the seven rows still depend on its anchors.

Coordinate fresh-clone activation checks with the existing Clone-anywhere layout item. The parked "Guard hook for both agents" item concerns developing wiki-tools itself, whereas this plan's guards run inside wikis; do not accidentally enable wiki guards in the development repo.

**Exit:** advertise only base + raw/local-folder capabilities that actually passed; preserve the existing Claude support claim for the other sources.

## Deferred sources: separate design-phase tasks

Each task depends on the base migration, not on another source task. These are not approved implementation plans or prerequisites for the first delivery. Each later design must choose a real reader, state/citation equivalence, enforcement, fake-source cases and live acceptance before implementation.

### Codebase

Expected effort: medium when named research agents and child identity work; otherwise blocked.

Design and verify native researcher dispatch, tool restrictions, trustworthy child identity, `agent_only` root enforcement and critic-to-checker nesting. Retain existing git/gh wrappers, pinned citations, drift/verify operations and cache layout. Specify models/effort natively without copied role definitions. Test raw gh write bypass denials. Separate ordinary research support from `--critique` if nesting is missing; never let the main session read the source as a fallback.

Ready for implementation when a reviewed design demonstrates dispatch/identity and enforcement, and names both positive research and negative bypass tests on both platforms.

### OneNote

Expected effort: low-to-medium if a compatible reader already exists; high otherwise.

Choose an available reader and verify created timestamps, section modification times, fresh text/HTML, group paths, read-only scope and attachments. Preserve current snapshot/cursor/citation semantics and their known limits. Distinguish reader availability from API capability. Reuse the reader-neutral contract rather than create a Copilot type.

Ready when the reader and scope are explicit, representative fresh-read/snapshot evidence is available, and its design includes missing-reader and changed-page tests.

### Proton files

Expected effort: medium with a compatible external reader; high if that reader needs porting.

Investigate external plugin compatibility, registration/loading paths, read-only operation allowlists, roots on every call and download/cache behavior. Do not allow the underlying writable CLI or weaken protected cache rules to make an installed reader run. Preserve existing exclusions and citation resolution.

Ready when reader compatibility and allowlisted execution are demonstrated and outside-root/direct-CLI refusal tests are specified.

### Jira

Expected effort: medium-to-high.

Choose an actual Copilot-capable reader; compare JQL, fields, pagination, comment/link behavior and `updateHistory: false`. Preserve named scopes, backfill completeness, cursor precision and citations. Replace the current "different MCP means different type" caveat only with a verified same-semantics reader. Do not silently swap connector tool names.

Ready when scopes/paging/state equivalence and read-only enforcement are settled, with fake pages and a consented read-only live test specified.

### Gmail

Expected effort: high.

Choose a reader that supports thread semantics plus narrowly permitted creation/application of the wiki-ingested label. Preserve late-arrival handling, label IDs, thread retrieval and failure recovery. A read-only reader alone is insufficient; do not replace label state with dates just for portability. Keep send/draft/delete operations unavailable.

Ready when exact label permissions, allowed operations and state semantics are designed, including label failure, duplicate-thread and forbidden-write tests.

### Google Drive

Expected effort: high.

Choose a reader and establish folder ID/path equivalence, recursive paging, modification dates, Docs/Sheets/Slides export, base64/download shape, comments and read-only restrictions. Preserve existing citations/cache behavior and explain formats the reader cannot export.

Ready when traversal/export/citation equivalence and enforced write restrictions are settled, with paged trees, changed documents, missing formats and forbidden writes in its test design.

### Microsoft Teams

Expected effort: highest.

Evaluate channels, replies, chat-day fetching, SharePoint trees, resource URIs, auth scopes, conversation ordering and tenant-wide result filtering separately. Preserve snapshot/cursor semantics without assuming a different provider orders conversations the same way. Reuse `snapshot.sh`/`snapshot.py`; no broad Microsoft 365 grants.

Ready when every required operation and scope boundary has an explicit reader mapping and tested semantics, including late replies, foreign-tenant search results, pagination and snapshot failures.

## Evidence references

- Repository mechanisms: [ADR 1-7 and 10](../adr.md), [development](../development.md), [setup](../setup.md), [guard](../guard.md), [skills](../skills.md), [layout](../layout.md).
- Discovery defect: `plugins/wiki/skills/research/SKILL.md`, description frontmatter; actual Copilot plugin/skill enumeration.
- Test reuse: `tests/conftest.py`, `test_guard.py`, `test_py_launch.py`, `test_install.py`, `test_sources.py`, `test_sync_status.py`, `test_wiki_check.py`, `test_agent_files.py`, `.github/workflows/ci.yml`.
- Client contracts: Copilot 1.0.112 shipped docs for Claude compatibility, environment aliases/`COPILOT_CLI`, project activation, plugin mounting, prompt-mode trust/permissions, JSONL, resume and isolated configuration; Claude 2.1.325 command help for local mounting, print/stream-JSON, permission handling, settings and explicit resume.

No live model session, installation migration, source migration or runtime guard validation was performed while preparing this plan. The read-only discovery checks above are the only client behavior already observed.

## Independent review

An Opus 5.5 rubber-duck sub-agent reviewed the draft read-only. Its four must-fix findings were the deferred-source count, the missing precise Git Bash invocation on Windows, child-agent hook coverage and roadmap links when retiring the plan. This revision addresses all four.

It also incorporates candidate-version assertions, early isolated capture-driver provisioning, explicit protected configuration, tool-surface classification and provider-disclosure consent for existing-wiki checks. No implementation or live acceptance was claimed by that review.
