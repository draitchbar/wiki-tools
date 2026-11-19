# Plan: binding a tool-neutral source to its reader

Status: planned, not started (2026-11-19). Roadmap item: "Reader binding". The plan was reviewed on 2026-11-19 (a second-opinion subagent with the docs and the code); its findings are folded in below.

## The problem
A tool-neutral type (`access: tools`: `onenote`, `proton-files`, `jira`) lists the operations it needs and names no tools. Today `/wiki:add-source` settles the reader with the user in conversation. The main session works out which tool does each operation and the allow and deny rules, and writes the result in prose in the instance's body. The work is manual, its quality depends on the session, and the output is free text that no script can check, so `sources.sh settings` gives these types no rules. When a reader changes (a new connector version, a different MCP server, a CLI), someone has to redo it by hand. The Jira move on 2026-11-19 is an example: a new connector, a dispatcher tool, different parameters, and a "recently viewed" behaviour that had to be checked against the live site.

## The idea
A plugin agent, `wiki:reader-binder`, does the discovery and probing, and returns a proposed binding: operation → tool and fixed arguments, with the allow and deny rules and what the probes found. The main session shows the proposal, the user chooses, and the binding goes into the instance file. The user installs that file, as they install every source file.

## What Claude Code allows
From the docs (2026-11-19), unless marked otherwise:
- **Plugin agents** (`plugins/wiki/agents/*.md`) support `name`, `description`, `model`, `effort`, `maxTurns`, `tools`, `disallowedTools`, `skills` and a few more. They don't support `hooks`, `mcpServers` or `permissionMode`; these fields are silently ignored.
- **The wiki's agents can't probe today.** `source-researcher` and `critic` list fixed tools (`Read, Grep, Glob, Bash, Write`; `Agent, Read, Bash, Write`), with no MCP tools. A wiki session can't add an agent: the guard protects the plugin folder. The binder must be a new agent with `tools` omitted, which inherits the session's MCP tools.
- **MCP tools:** a subagent inherits the session's MCP tools when `tools` is omitted; `tools` and `disallowedTools` take whole-server wildcards (`mcp__<server>__*`).
- **Deferred tools:** the docs list ToolSearch among the tools a background subagent keeps. Seen once (2026-11-19, a general-purpose subagent in a wiki-tools session, no guard): the Atlassian connector's tool names were listed as deferred, and `ToolSearch select:<name>` loaded their schemas. A keyword query found nothing, so names taken from the session's context are the dependable route. Not yet seen: a plugin agent, inside a wiki, actually calling a tool.
- **Read-only hints aren't visible.** The loaded schemas held name, description and parameters only; MCP annotations such as `readOnlyHint` are used by Claude Code, not shown to the model. Sorting a server's tools into read and write therefore rests on names and descriptions. So the binding allows only the tools it binds, and everything else prompts.
- **Skills:** a subagent can invoke skills with the Skill tool and Read their files. The guard never blocks Read outside agent_only roots; Claude Code may still prompt for a read outside the working directory. A reader under `~/.claude/plugins/cache/` stays blocked for shell calls (`docs/guard.md`).
- **No questions:** a subagent can't use AskUserQuestion; every choice stays with the main session.
- **Guard:** PreToolUse hooks fire for subagent calls, with `agent_id` (recorded in `tests/live/results.md`) and `agent_type`. The guard passes every `mcp__*` call without reading its input, and uses `agent_id` only for agent_only types. A guard check on a dispatcher's operation name needs the real payload of such a call, which nobody has captured yet.
- **Permissions:** a subagent runs in the main session's permission mode. At bind time no allow rule exists yet (the binder is what produces them), so every probe prompts, or in auto mode goes to the classifier. A background subagent's prompts surface in the main session. A "don't ask again" answer may save a standing allow rule outside the install flow; where it is stored for MCP tools is unverified. Settings can't limit a dispatcher's arguments (`mcp__` rules take no parentheses), so only the guard could.
- **Listing tools:** there is no model-callable list of connected MCP tools; `claude mcp list` lists servers only, and the guard blocks `claude` as a command. The main session passes the candidate tool names it sees in its context.

## Design
1. **When binding happens.** `/wiki:add-source` says: "Don't call the source's tools before the instance exists." Binding needs live calls, so it runs after the instance is installed: at the first ingest's Check, or by an explicit re-bind. Check finds no binding (or a tool missing), dispatches the binder, and proposes the `## Reader` section as a new instance file. Add-source only records the user's choice of reader, untested.
2. **The contract says what to probe.** Each tool-neutral contract gets a short `## Bind` section: one harmless probe per operation and how to check each property (Jira: **search** with one result and the fields `key`, `summary`, `updated`; **read issue** on a key the user names; `issueHistory()` before and after a read). The agent stays source-neutral, as skills must (`AGENTS.md`).
3. **The agent** (`plugins/wiki/agents/reader-binder.md`): `tools` omitted, so it inherits MCP tools; `disallowedTools: Write, Edit, NotebookEdit` (it returns a draft and writes nothing; Bash remains, and the guard's protected paths are what stop shell writes to source files). Brief: the contract (`sources.sh contract <type>`), the instance's parameters, the candidate tool and skill names the main session sees, and one item the user named as safe to read. Work: load the candidates' schemas, map each operation to a tool and fixed arguments, run the `## Bind` probes with the smallest limits, and list the server's other tools as likely writes (by name and description) for the deny list. It never uses a detailed view or a user-info tool (they return people's emails). Return: the binding draft, allow and deny rules, each probe's result, and what couldn't be verified.
4. **The binding's format.** Phase 2: a `## Reader` section in the instance's body, one line per operation: `<operation>: <tool>, <fixed arguments>`, written without `<…>` pairs, which the instance validator takes for placeholders. Phase 3: a frontmatter key (`reader:`) validated by `contract.py`, from which `sources.sh settings <type> --key <key>` prints the reader's allow and deny rules.
5. **The guard (phase 3, optional).** With a machine-readable binding, the guard could limit a dispatcher tool to the operation names in the binding (the Jira `executeRead` limit), and allow a reader's commands as plain calls even under `~/.claude/plugins/cache/` (the parked "Readers from installed plugins").

## Phase 1: the spike
In a work wiki with a Jira instance, after the tool-neutral `jira` contract is in (#31). U = the user only; S = the wiki session. For every item, record the Claude Code version, the model, the permission mode, foreground or background, and the result. Results go into "What Claude Code allows" above, scrubbed: no site host, cloud id, issue keys, team or people names.

0. **U, setup.**
   - Note the Claude Code version (the session can't run `claude`).
   - Deny the connector's write tools in the wiki's settings (`executeWrite`, `executeDestructive`, `showConfluenceEditor`).
   - Name one issue key that is safe to read.
   - In the wiki-tools clone the wiki runs from, add an uncommitted stub agent, `plugins/wiki/agents/spike-probe.md`, with `tools` omitted. Then reload plugins in the wiki session.
1. **S: names.** Dispatch the stub and ask which `mcp__…` names it sees and whether it has ToolSearch. Yes = the same names as the main session.
2. **S: schema.** The stub runs `ToolSearch select:<the search tool>`. Yes = the schema is returned. Note whether any read-only annotation is visible.
3. **S: call.** The stub runs **search** with a one-result JQL and the three fields. Yes = a result. If no, repeat with the schema pasted into the brief, to test that fallback. If that fails too, the main session must probe, and the design changes.
4. **S+U: prompts.** For item 3: did a prompt appear, where, and what did "don't ask again" offer? The user declines it. Repeat once with the stub in the background and once in auto mode: is a probe blocked mid-way, or the report flagged?
5. **S: plugin agent or not.** Repeat items 1 to 3 with the general-purpose agent, to see whether a plugin agent behaves differently.
6. **S: guard.** The stub tries to Write an instance file: the guard must refuse it. The stub Reads a skill file under `~/.claude/skills/`: does it prompt?
7. **U, optional, needed only for design point 5.** Add a temporary logging PreToolUse hook to user settings and capture one subagent `executeRead` payload (`agent_id`, `agent_type`, the shape of `tool_input`). Then remove the hook.
8. **S: a property probe.** The stub runs the "recently viewed" check on the named issue (`issueHistory()` before and after one read, key field only). Does it work from a subagent?
9. **S, optional: a CLI or skill reader.** One read-only operation of a OneNote or Proton reader (`status` or similar) from the stub.
10. **S: record.** Write the scrubbed results here and confirm or change design point 1, the timing. Remove the stub agent.

## Phases after the spike
2. **The agent, `## Bind` sections, Check's re-bind step:** the agent file; `## Bind` for `jira`, `onenote` and `proton-files`; Check dispatches the agent when the binding is missing or broken. Tests: a new test for `plugins/wiki/agents/*.md` frontmatter (none exists; `test_agent_files.py` covers the coding agents' files), and every `access: tools` contract has a `## Bind` section. Probing needs a live reader: record a live run in `tests/live/results.md`.
3. **A machine-readable binding:** the `reader:` key in `contract.py`, settings rules from it, and optionally the guard checks in design point 5 (needs the payload from spike item 7). Fixtures and a decision in `docs/adr.md`.

## Open
- Whether a binding belongs in the instance (per wiki) or in a per-machine file shared by all wikis (one connector serves every wiki on a machine; but instance files are where the guard trusts content today).
- Copilot: the same agent file is a Copilot custom agent only if the wikis move to Copilot (`docs/plans/copilot-wiki-support.md`); out of scope here.
