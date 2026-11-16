# Design: one wiki plugin for Claude Code and Copilot CLI

Status: proposed, independently reviewed by an Opus 5.5 rubber-duck sub-agent. The [implementation plan](plans/copilot-wiki-support.md) includes subsequent client research and the first-delivery scope. Neither document claims implemented or runtime-verified Copilot wiki support.

## Intent

Wiki users can choose either local CLI and switch between sessions in the same wiki without migrating instructions, pages, source instances, citations, caches or sync state. Simultaneous editing and transcript transfer are outside scope.

Minimal one-time, user-approved setup adjustments are acceptable. Preserve existing Claude Code behavior. DRY and minimum extra complexity are constraints: one plugin, one authored set of skills and agent roles, one schema, one contract parser and one guard policy.

Accept instruction-based manual-only invocation in Copilot; do not emulate Claude's enforced `disable-model-invocation`. Approval prompts, command presentation and model configuration may differ. Source support can arrive incrementally, with unavailable sources reported explicitly.

This concerns local Copilot CLI, not VS Code, the cloud coding agent or `/delegate`. Linux and Windows with Git Bash remain the supported platforms.

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

Use native marketplace registration and updates per machine/client, with activation only in the wiki. Prefer the shared `.claude/settings.json` declaration. If that cannot provide Copilot's required scope, derive a minimal `.github/copilot/settings.json` activation fragment; its documented project semantics are the fallback. No independently maintained plugin list or invented Copilot `--scope project` flag.

An enabled wiki must load its plugin while an unrelated folder and wiki-tools itself remain unguarded. A direct `--plugin-dir` mount is useful for development/testing but does not prove normal project activation. Each client may keep a different installed copy; resolve paths from the executing plugin and verify the release candidate rather than presume simultaneous updates or Claude's observed live-clone behavior.

Keep `schema.sh` as the sole schema loader/substituter. Both schema bodies must be available before wiki work and after resume/context reset. A verified compatible automatic hook may supply them if lifecycle behavior differs; no per-wiki schema imports or second loader. If no reliable context route exists, core support is blocked.

Keep all eight skills and the two research roles authored once. A short shared capability binding supplies native tool equivalents where necessary. Use the established manual-only instruction guard and name arguments in descriptions. If command injections fail, call the existing script explicitly; if skill-root substitution fails, use the resolved root from schema context.

Scripts remain Bash. Copilot's Windows native shell may require a precisely validated invocation of an explicitly resolved Git Bash executable and absolute script path. Never rely on bare `bash` resolving to Git Bash or use Bash environment-variable syntax in PowerShell. The plan specifies that invocation and its guard tests.

File-reading guidance describes capabilities, not Claude-only API parameters. Existing text extraction and OCR remain shared; image/PDF capabilities must be demonstrated or reported unavailable. Missing extraction is never an empty successful document.

## Guard and permissions

**One policy, with small measured runtime normalization.** Reuse `guard.py`, `hookjson.py`, `contract.py` and `py-launch.sh`.

Coverage comes before parsing: every enabled command, file mutation or protected-source read must reach the guard or remain outside the supported configuration. This includes input to running shells, multi-file patches, relevant MCP calls and child-agent tools. Validate all affected targets. Unknown protected-capability payloads block rather than use the current unrecognized-tool allow path.

Preserve push blocking, protected paths/roots, wrapper lookalike/chaining checks, broken-contract behavior and diagnostics. A PowerShell invocation can be recognized as an approved Bash-wrapper call only in the exact validated form; arbitrary PowerShell/Bash programs do not gain that exception.

Protect both clients' guard-affecting configuration and registered plugin/cache/data paths from either client's wiki session, including the cached Python executable. Protect plugin/hook-disabling operations and new execution-definition locations. Experimental extension loading/augmentation is outside the supported surface until its tools have equivalent coverage; do not introduce an extension portability layer.

Missing Python, malformed input, hook failure and timeout must actually deny the tool. Adapt response encoding only if client evidence requires it. A log message saying "block" while the command runs is a failure. The guard remains a guardrail, not a security boundary.

Copilot does not read Claude's `permissions.allow/deny`. Its native shell patterns are coarser, and its similarly named repository policy is not user-configurable enterprise policy. Do not translate narrow Claude rules into broad grants or generate fictitious permission JSON. Native approval prompts are acceptable; `--allow-all`, unrestricted shell grants, GitHub MCP write tools and `/delegate` are not portability solutions.

Existing enforced source restrictions need a real route in Copilot: a read-only reader/connection or precise checks in the common guard. Invocation-only deny flags may supplement tests but are not durable per-wiki enforcement. Reuse contract shell denials, including raw gh write restrictions; combine denials, never client grants.

## Research agents

Keep `source-researcher.md` and `critic.md` as the authored roles, retaining pinned revisions, exact citations, cache notes, budgets, independent verification and acceptance before page writes. Adapt native dispatch/tool/model bindings only where needed; no orchestration service or duplicated role bodies.

Child-agent tools must inherit guards. Missing trustworthy identity never grants `agent_only` access. Codebase research remains unavailable if researcher dispatch or that identity boundary cannot work. Missing critic-to-checker nesting gates `--critique` separately; do not implement a second main-session relay workflow.

General lint/audit dispatch for supported sources also requires demonstrated child guard coverage. Discovery of a role is not proof that its dispatch or tool restrictions work.

## Incremental source readiness

Separate valid instance, supported client, available reader and enforceable restrictions. A valid but unavailable source is not a broken contract that blocks ordinary wiki work.

Leave its cursor, labels, snapshots and `last_checked` untouched. Do not silently route it to raw. Pages stay readable; audits report unresolved evidence rather than unsupported claims being declared true or false. Status must not recommend ingesting unavailable sources.

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
| Gmail | High: thread semantics and essential narrowly permitted wiki-label creation/application |
| Google Drive | High: recursive listing, exports/downloads, timestamps and restrictions |
| Microsoft Teams | Highest expected: channels/replies/chats/SharePoint, ordering, URIs, scopes and tenant-wide filtering |

Raw is built in; local-folder is one of eight standard types. The plan delivers those two sources and leaves the seven other types as independent design-phase tasks. Reader-neutral contracts are easier only if the external reader actually works.

## Readiness and evidence

Reuse `wiki-check.sh`, `sources.sh` and sync-status, not a second diagnostic tool. The plan's explicit client selector and documented runtime marker distinguish client readiness while preserving standalone Claude defaults. The guard's protected paths and applicable denials do not depend on guessing the host.

Static checks can verify contracts and bindings but cannot prove that hooks ran or denies were honored. A supported binding is not an installed/authenticated reader; the source's Check operation establishes that before state changes.

The [plan's acceptance matrix](plans/copilot-wiki-support.md#8-add-opt-in-end-to-end-tests-through-the-real-clients) covers native installation, lifecycle context, actual guard denials, source ingestion, cross-client handoff and existing-wiki regression in both clients on both platforms. Not-attempted model refusals are inconclusive, not guard passes.

## Alternatives rejected

- Second plugin, copied skills/agents or duplicate complete source types: maintenance drift.
- Renaming wiki instruction/source directories: migration without functional benefit.
- Translating all permissions: non-equivalent rule models.
- Universal connector framework or replacement service clients: speculative complexity.
- Instruction-only substitutes for existing enforced restrictions: weaker protection.
- All sources required before Copilot use: incompatible with incremental support.
- New manual-invocation enforcement machinery: explicitly outside scope.

## Review and references

An Opus 5.5 rubber-duck reviewer found four substantive draft gaps: hook coverage before normalization, cross-client guard tampering, unspecified client readiness and existing connector caveats conflicting with shared source types. The revised design addresses them. Subsequent plan research/review refines Windows invocation, client-support metadata, child coverage, installed-candidate verification and live acceptance without changing the single-authoring decision.

Evidence: [ADR 1-7 and 10](adr.md), [development](development.md), [setup](setup.md), [guard](guard.md), existing plugin hooks/scripts/skills/agents and all eight source contracts; the client documentation and read-only discovery findings recorded in the plan. Neither independent review certifies runtime compatibility.
