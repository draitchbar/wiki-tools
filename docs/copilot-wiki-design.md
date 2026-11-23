# Design: one wiki plugin for Claude Code and Copilot CLI

Status: proposed. This file holds the intent, the constraints and the rejected alternatives; the [plan](plans/copilot-wiki-support.md) holds the client research, the steps, the open guard decision and the tests, and is the one to follow where the two differ in detail. Neither claims implemented or runtime-verified Copilot wiki support.

## Intent

Wiki users can choose either local CLI and switch between sessions in the same wiki without migrating instructions, pages, source instances, citations, caches or sync state. Simultaneous editing and transcript transfer are outside scope.

Minimal one-time, user-approved setup adjustments are acceptable. Preserve existing Claude Code behavior. DRY and minimum extra complexity are constraints: one plugin, one authored set of skills and agent roles, one schema, one contract parser and one guard policy.

Accept instruction-based manual-only invocation in Copilot; do not emulate Claude's enforced `disable-model-invocation`. Approval prompts, command presentation and model configuration may differ. Source support can arrive incrementally, with unavailable sources reported explicitly.

This concerns local Copilot CLI, not VS Code, the cloud coding agent or `/delegate`. Linux and Windows with Git Bash remain the supported platforms for Claude Code. Copilot comes first on Linux; Copilot on Windows is a separate, later delivery (plan, part C).

## Architecture

**Extend the existing plugin through Copilot's Claude compatibility, not a second plugin or a portability framework.**

```text
Claude Code                    Copilot CLI
       \                        /
        existing wiki plugin package
        shared skills, schema and agent roles
        shared parser, guard policy and scripts
                       |
          existing reader / source transport
          (small client-specific binding if needed)
                       |
          unchanged wiki pages, citations and state
```

Extend [ADR 10](adr.md)'s single-authoring pattern from development of this repo to the plugin itself. Keep a wiki's `CLAUDE.md` and `.claude/sources/`; Copilot reads Claude instructions, and folder names do not justify migration. Keep the manifests and everything the wiki needs under `plugins/wiki/`. No copied skills, generated instruction trees, symlinks or alternate PowerShell/Python implementation.

Copilot's shipped documentation establishes Claude-style package discovery, project settings/hooks, legacy hook fields and plugin/project environment aliases. It does not establish equivalent tool arguments, deny responses, context injection or child-agent behavior. The plan records observed discovery results separately from runtime gates.

## Installation and context

Use native marketplace registration and updates per machine/client, with activation only in the wiki. Each client may therefore run a different copy of the plugin against the same wiki; formats stay readable by an older copy, and `wiki-check` shows which copy is running (plan, step 4). Prefer the shared `.claude/settings.json` declaration. If that cannot provide Copilot's required scope, derive a minimal `.github/copilot/settings.json` activation fragment; its documented project semantics are the fallback. No independently maintained plugin list or invented Copilot `--scope project` flag.

An enabled wiki must load its plugin while an unrelated folder and wiki-tools itself remain unguarded. A direct `--plugin-dir` mount is useful for development/testing but does not prove normal project activation. Each client may keep a different installed copy; resolve paths from the executing plugin and verify the release candidate rather than presume simultaneous updates or Claude's observed live-clone behavior.

Keep `schema.sh` as the sole schema loader/substituter. Both schema bodies must be available before wiki work and after resume/context reset. A verified compatible automatic hook may supply them if lifecycle behavior differs; no per-wiki schema imports or second loader. If no reliable context route exists, core support is blocked.

Keep all eight skills and the two research roles authored once. A short shared capability binding supplies native tool equivalents where necessary. Use the established manual-only instruction guard and name arguments in descriptions. If command injections fail, call the existing script explicitly; if skill-root substitution fails, use the resolved root from schema context.

Scripts remain Bash. Copilot's native Windows shell is PowerShell, which the guard refuses for wiki scripts today, so Copilot on Windows needs a precisely validated invocation of an explicitly resolved Git Bash executable and absolute script path. Never rely on bare `bash` resolving to Git Bash or use Bash environment-variable syntax in PowerShell. That route, and how the executable is found and trusted, is the plan's part C, not the first delivery.

File-reading guidance describes capabilities, not Claude-only API parameters. Existing text extraction and OCR remain shared; image/PDF capabilities must be demonstrated or reported unavailable. Missing extraction is never an empty successful document.

## Guard and permissions

**One policy, with small measured runtime normalization.** Reuse `guard.py`, `hookjson.py`, `contract.py` and `py-launch.sh`.

Coverage comes before parsing: every enabled command, file mutation or protected-source read must reach the guard or remain outside the supported configuration. This includes input to running shells, multi-file patches, relevant MCP calls and child-agent tools. Validate all affected targets. In Claude Code the hook now matches every tool and the guard refuses a name it does not classify (#24); for Copilot, the plan's step 3 decides how unknown tools are handled (recommended: the same catch-all matcher and classified list).

Preserve push blocking, protected paths/roots, wrapper lookalike/chaining checks, broken-contract behavior and diagnostics. PowerShell stays refused for wiki scripts until part C; then an invocation is recognized as an approved Bash-wrapper call only in the exact validated form.

Protected paths keep parity with today's rather than grow: the guard protects the wiki's `.claude/sources`, `.claude/settings*` and the registered plugin copy with its cached Python, and gains only Copilot's direct equivalents (its project settings and hook files, its plugin copy and data root). User-level profiles, extensions, MCP configuration and agent/skill folders are outside the supported configuration and documented as such, not guarded; do not introduce an extension portability layer.

Missing Python, malformed input, hook failure and timeout must actually deny the tool. Adapt response encoding only if client evidence requires it. A log message saying "block" while the command runs is a failure. The guard remains a guardrail, not a security boundary.

Copilot does not read Claude's `permissions.allow/deny`. Its native shell patterns are coarser, and its similarly named repository policy is not user-configurable enterprise policy. Do not translate narrow Claude rules into broad grants or generate fictitious permission JSON. Native approval prompts are acceptable; `--allow-all`, unrestricted shell grants, GitHub MCP write tools and `/delegate` are not portability solutions.

Existing enforced source restrictions need a real route in Copilot: a read-only reader/connection or precise checks in the common guard. Invocation-only deny flags may supplement tests but are not durable per-wiki enforcement. Reuse contract shell denials, including raw gh write restrictions; combine denials, never client grants.

## Research agents

Keep `source-researcher.md` and `critic.md` as the authored roles, retaining pinned revisions, exact citations, cache notes, budgets, independent verification and acceptance before page writes. Adapt native dispatch/tool/model bindings only where needed; no orchestration service or duplicated role bodies.

Child-agent tools must inherit guards. Missing trustworthy identity never grants `agent_only` access. Codebase research remains unavailable if researcher dispatch or that identity boundary cannot work. Missing critic-to-checker nesting gates `--critique` separately; do not implement a second main-session relay workflow.

General lint/audit dispatch for supported sources also requires demonstrated child guard coverage. Discovery of a role is not proof that its dispatch or tool restrictions work.

## Incremental source readiness

Separate valid instance, supported client, available reader and enforceable restrictions. A valid but unavailable source is not a broken contract that blocks ordinary wiki work.

Unavailability is an instruction to the skills, not enforcement, and the docs say so. Leave its cursor, labels, snapshots and `last_checked` untouched. Do not silently route it to raw. Pages stay readable; audits report unresolved evidence rather than unsupported claims being declared true or false. Status must not recommend ingesting unavailable sources.

Source-specific transport knowledge stays in that type's directory, never in skills. Keep instance keys, parameters and cite prefixes. Credentials and machine-local registration remain outside the public repo.

Alternate readers join an existing type only when they preserve its scope/state/citation semantics. This intentionally replaces the Gmail/Drive/Jira caveat that every different MCP server needs a new type. Otherwise the source stays unavailable; changing `type:` at each client switch is not a solution.

The first delivery needs only a small client-support declaration in the existing flat format, as refined in the plan; it does not need MCP transport bindings. When an MCP-backed source is picked up, an optional bound server identity and exact read/bookkeeping tool lists may be the minimal extension. No redundant forbidden list: deny undeclared operations of the bound server. Reuse existing parsing/validation; no suffix matching, arbitrary server substitution or accidental union of grants. Conflicting operation classifications block the binding.

### Expected difficulty

These are architectural assessments, not completed migrations or time estimates.

| Source | Difficulty and constraint |
|---|---|
| Raw | Low for text; image/scanned-PDF reading needs capability checks |
| Local-folder | Low after the base guard works; reuse the wrapper, roots, dates, cache and citations |
| Codebase | Medium if researcher identity/dispatch work; nested dispatch separately gates critique |
| OneNote | Low-to-medium with a compatible reader; otherwise high. Fresh HTML/text, timestamps, scope and snapshots matter |
| Proton files | Medium with a compatible external reader; otherwise high. Read-only operations, roots and installation/cache paths matter |
| Jira | Medium-to-high: reader, API/paging differences, JQL, cursor semantics and read-only enforcement |
| Gmail | Medium through the `gws` reader plugin: read-only at Google (`gmail.readonly`), so date state replaces the wiki label (contract and state done in Claude, ADR 23); thread semantics |
| Google Drive | Medium through the `gws` reader plugin: read-only at Google (`drive.readonly`); recursive listing, exports/downloads and timestamps |
| Microsoft Teams | Highest expected: channels/replies/chats/SharePoint, ordering, URIs, scopes and tenant-wide filtering |

Raw is built in; local-folder is one of eight standard types. The plan delivers those two sources and parks the seven other types. Reader-neutral contracts are easier only if the external reader actually works.

## Readiness and evidence

Reuse `wiki-check.sh`, `sources.sh` and sync-status, not a second diagnostic tool. The plan's explicit client selector and documented runtime marker distinguish client readiness while preserving standalone Claude defaults. The guard's protected paths and applicable denials do not depend on guessing the host.

Static checks can verify contracts and bindings but cannot prove that hooks ran or denies were honored. A supported binding is not an installed/authenticated reader; the source's Check operation establishes that before state changes.

The detailed cases live in the deterministic tests. A [small live smoke set](plans/copilot-wiki-support.md#8-a-small-live-smoke-set-through-the-real-clients) covers lifecycle context, actual guard denials, the two sources, cross-client handoff and an unavailable source, and one existing wiki is checked interactively. The support claim names the client versions it was tested with and when to re-run. Not-attempted model refusals are inconclusive, not guard passes.

## Alternatives rejected

- Second plugin, copied skills/agents or duplicate complete source types: maintenance drift.
- Renaming wiki instruction/source directories: migration without functional benefit.
- Translating all permissions: non-equivalent rule models.
- Universal connector framework or replacement service clients: speculative complexity.
- Instruction-only substitutes for existing enforced restrictions: weaker protection.
- All sources required before Copilot use: incompatible with incremental support.
- New manual-invocation enforcement machinery: explicitly outside scope.

## References

[ADR 1-7 and 10](adr.md), [development](development.md), [setup](setup.md), [guard](guard.md), the existing plugin hooks/scripts/skills/agents and all eight source contracts; the client documentation and read-only discovery findings recorded in the plan.
