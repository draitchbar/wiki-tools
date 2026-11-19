# Plan: binding a tool-neutral source to its reader

Status: phase 1 done (2026-11-19); phase 2 not started. Roadmap item: "Reader binding". An earlier version planned a plugin agent. A review on 2026-11-19 found that most of its open questions came from running in a subagent, so the binder is now a skill (see **Why a skill**); a second review of the skill version is folded in.

## The problem
A tool-neutral type (`access: tools`: `onenote`, `proton-files`, `jira`) lists the operations it needs and names no tools. Today `/wiki:add-source` settles the reader with the user in conversation. The main session works out which tool does each operation and the allow and deny rules, and writes the result in prose in the instance's body. The work is manual, its quality depends on the session, and the output is free text that no script can check, so `sources.sh settings` gives these types no rules. When a reader changes (a new connector version, a different MCP server, a CLI), someone has to redo it by hand. The Jira move on 2026-11-19 is an example: a new connector, a dispatcher tool, different parameters, and a "recently viewed" behaviour that had to be checked against the live site.

## The idea
A skill, `/wiki:bind-reader <key>`, binds an instance of a tool-neutral type to the tools on this machine. It runs in the main session. It reads the contract's `## Bind` section, finds candidate tools, has the user deny the reader's write tools, tests each operation with one small read-only call, asks the user to confirm, and drafts the instance file with a `## Reader` section. It writes nothing itself; the user installs the file and changes the settings.

## Why a skill
The main session already has what a binder needs; a subagent lacks it or would need testing for each item (docs and sessions, 2026-11-19):
- **Tools.** The main session sees the connected MCP tools' names in its context, loads their schemas with ToolSearch and calls them; that's how the Jira connector was checked for #30. A plugin subagent would need a new agent with `tools` omitted (the wiki's agents list fixed tools without MCP), and whether it can load and call deferred tools was undocumented.
- **Questions.** A skill can ask the user in the same flow; a subagent can't use AskUserQuestion.
- **Skill and CLI readers** (OneNote, Proton) already run from the main session.

The cost: test output lands in the main session's context. With the `## Bind` tests kept tiny (one result, named fields, one item the user names), that is a few KB per source. If a reader proves verbose, one step can be handed to a general-purpose subagent later.

## Design
1. **When binding happens.** `/wiki:add-source` says: "Don't call the source's tools before the instance exists." Binding needs live calls, so it runs after the instance is installed: on demand (`/wiki:bind-reader <key>`), or when Check at an ingest finds no `## Reader` section or a tool it names gone. Add-source records only which reader the user means to use, untested, and says to bind it before the first ingest. When binding starts from Check, **the ingest stops** once the skill has handed over its drafts, and resumes in a new `/wiki:ingest <key>` after the user has installed the instance file and changed the settings. The installed file stays the one record of the binding: a later session reads only that, so an ingest never runs on a binding that exists only in the conversation. Installing the file changes the instance, so `sources.sh show` then reports "Check needed", which that ingest's Check clears.
2. **Invocation: decided in phase 1.** Two options:
   - **Model-invocable** (no `disable-model-invocation`): Check starts it itself. `Skill` is a harmless tool to the guard, and `disable-model-invocation` on `/wiki:ingest` doesn't stop it starting another skill. Unverified: whether a model-started skill inside a manual-only run prompts, and whether its `allowed-tools` apply. It would also be the only model-startable skill that makes live source calls, and its description would sit in every wiki session's context.
   - **Manual-only** (the fallback, like `/wiki:ingest` and `/wiki:add-source`): Check stops and says "type `/wiki:bind-reader <key>`", as add-source hands over to ingest. Since the ingest stops either way, this costs one command.
3. **The contract says what to test.** Each tool-neutral contract gets a short `## Bind` section: one harmless call per operation, with the fields to ask for, and how to check each property. The skill stays source-neutral, as skills must (`AGENTS.md`); everything specific to one source stays in its `SOURCE.md`. Jira:
   - **search** with one result and the fields `key`, `summary` and `updated`;
   - **read issue** on a key the user names as safe, with the fields `summary` and `updated` only (default views may include people);
   - the "recently viewed" property by **search** for `key = <the safe key>` with the field `lastViewed`, before and after that read. Unlike `issue in issueHistory()`, this doesn't put the user's viewing history in the transcript. Unverified that every reader returns `lastViewed`.
   - **Dispatcher operations.** Where an operation is reachable only through a dispatcher (the Atlassian connector's find project and list remote links, behind `executeRead`), the `## Bind` section gives the known operation names per reader. If they're missing or wrong, the skill may make one `discover`-style lookup per unmapped operation, with the user's yes.
4. **The skill's steps.**
   1. Read the contract (`sources.sh contract <type>`) and the instance (`sources.sh show <key>`), including any existing `## Reader` section. Make every `sources.sh` call here: an `allowed-tools` grant lasts only until the user's next message, and the skill asks questions.
   2. Candidates: the MCP tools whose names fit (from the session's context), the user's skills whose description fits (Read their `SKILL.md`), and any reader the instance or the user names. Ask the user which to use when there is more than one. Reading a skill under `~/.claude/` and running a CLI or skill reader will prompt; `allowed-tools` can't cover them.
   3. Load the chosen tools' schemas and map each operation to a tool and its fixed arguments.
   4. **Deny first.** List the server's tools that look like writes, by name and description (MCP read-only hints aren't shown to the model, unverified). Have the user add deny rules for them before any test call. The guard doesn't read MCP call input, so a deny rule or a prompt is all that stops a write; "never call a write tool" alone is only an instruction.
   5. Ask for the item that is safe to read, then run the `## Bind` tests with the smallest limits. At each prompt, tell the user to choose a plain "Yes": a "don't ask again" answer saves a standing rule to `.claude/settings.local.json`, outside the install flow and unchecked by `check-settings`. Never use a detailed view or a user-info tool (they return people's emails); never call a dispatcher with a name the binding doesn't use.
   6. Hand over the drafts:
      - **the binding report:** one row per operation (tool and fixed arguments, the test's outcome), then what couldn't be verified and any warning (a required operation missing, access broader than read-only);
      - **the instance file:** its full content, frontmatter unchanged, with the `## Reader` section added or replaced, and the `install-source-file.sh instances/<key>.md` command, as `/wiki:add-source` hands over files;
      - **the settings lines:** allow only the bound tools; the deny rules from step 4 if not yet added; remove allow rules for a previous reader that are no longer bound.
5. **The binding's format.** First: a `## Reader` section in the instance's body, one line per operation, `<operation>: <tool>, <fixed arguments>`. The instance validator checks placeholders only in the frontmatter's parameter values, so the body passes either way. Later: a frontmatter key (`reader:`) validated by `contract.py`. Frontmatter is flat, so it is a list of `- <operation>: <tool>, <arguments>` items, kept in step with the bash parser by the parity test. From it, `sources.sh settings <type> --key <key>` prints the reader's allow and deny rules.
6. **The guard (later, optional).** With a machine-readable binding, the guard could limit a dispatcher tool to the operation names in the binding (the Jira `executeRead` limit; settings files can't, since they skip `mcp__` rules with arguments), and allow a reader's commands as plain calls even under `~/.claude/plugins/cache/` (the parked "Readers from installed plugins"). The guard passes `mcp__*` calls without reading their input today, so this needs the real payload of an `executeRead` call (phase 1, item 6).

## Phase 1: a live run by hand
In a work wiki with a Jira instance; it doubles as the end-to-end test of the tool-neutral `jira` contract. U = the user only; S = the wiki session.
1. **U, setup.**
   - Note the Claude Code version (the session can't run `claude`).
   - Name one Jira issue that is safe to read.
   - Add a temporary logging PreToolUse hook to user settings for item 6.
2. **S, bind by hand.** Follow design point 4 without the skill: list the write-looking tools, the user adds the deny rules, then run the tests.
3. **S drafts, U installs.** The instance file with the `## Reader` section, and the settings changes. Record whether `sources.sh show` reports "Check needed" after the install.
4. **U, the ingest:** type `/wiki:ingest <key>`. Check, List new, Fetch and Write run on the installed binding.
5. **S, a proxy test for design point 2.** During the ingest, start `wiki:sync-status` (model-invocable) and record whether it prompts.
6. **U, the payload.** From the logging hook, capture one `executeRead` call's input (`tool_input` shape, where the operation name sits). Then remove the hook.
7. **Record** in a "Reader binding" section of `tests/live/results.md`, separate from the Copilot spike's table. Per operation: tool, fixed arguments, output bytes. Also:
   - each prompt's exact options, and where "don't ask again" would save;
   - behaviour in default and in auto mode;
   - whether the dispatcher needed a lookup;
   - whether `sources.sh` prompted after the first turn;
   - the proxy test's result;
   - which contract lines were wrong.

   The repo is public: leave out site, cloud ids, team ids, JQL, project and issue keys, and names, and run `scripts/pii-check.sh` before committing.

**Decision rules.** Phase 2's skill is model-invocable only if the proxy test passed without friction; otherwise it is manual-only. Phase 3's guard work is worth doing only if the dispatcher is actually needed and its payload exposes the operation name.

## Phase 1 results (2026-11-19)
Run in a work wiki with Claude Code 2.1.328 on Windows (Git Bash), in auto mode throughout. The record is in `tests/live/results.md`, "Reader binding". What it decided:
- **Binding by hand works.** Every operation of the tool-neutral `jira` contract mapped to an Atlassian MCP tool; each test call returned 11 to 1,500 characters. The ingest that followed used no Jira tool outside the `## Reader` section, and the sync-log, cursor and batches worked as the contract says.
- **Model-invocation: allowed.** Claude started `wiki:sync-status` during `/wiki:ingest` without a prompt, in auto mode. So phase 2's skill can be started by Check. Default mode wasn't tested; if it prompts there, that is one extra prompt, not a blocker.
- **Phase 3's guard check is possible.** The dispatcher was needed (find project at Check), and the hook payload carries the operation at `tool_input.name`, beside `tool_input.cloudId` and `tool_input.inputs`. Main-session calls carried no `agent_id`.
- **Deny rules hide tools.** Tools denied in settings didn't appear among the session's deferred tools at all. That makes "deny first" (design point 4.4) effective, and gives the skill a check: after the user adds deny rules, the denied tools must be gone from the list.
- **A settings file with an unknown top-level key dropped every rule in it, silently.** When the user pasted the hook under a misspelled key in the wiki's `.claude/settings.json`, the denied write tools came back as loadable, with no error shown. The deny rules took effect again once the key was fixed. This is the largest read-only risk the run found. The skill must verify after every settings change that the denied tools are gone; `sources.sh check-settings` could reject unknown top-level keys (phase 2).
- **The "recently viewed" test needs another route.** `lastViewed` isn't returned in the connector's compact view, and detailed views were off limits (people's emails). The earlier `issueHistory()` check stands; the `## Bind` test must find a field or view that returns `lastViewed` without people, or fall back to `issue in issueHistory() AND key = <the safe key>`, which shows one key only.
- **In auto mode nothing prompted**, not even test calls made before any allow rule existed: the classifier allowed them. The prompt questions (options, "don't ask again") are still open for default mode.
- Contract fixes from the run are in `jira/SOURCE.md`: the assignee's email in Fetch, read-issue sizes, re-listed issues after a bulk edit, component names shared across projects, and the connector's paging names.

## Phases after the run
2. **The skill and the `## Bind` sections.**
   - `plugins/wiki/skills/bind-reader/SKILL.md`, and `## Bind` for `jira`, `onenote` and `proton-files`.
   - Check in each tool-neutral contract points to the skill when the binding is missing or broken.
   - The texts that say add-source settles the reader move to the skill: `/wiki:add-source` step 4, item 2; `jira/SOURCE.md` (the intro, Check, Caveats); `onenote/SOURCE.md`, which says "use whichever available tool" and doesn't mention the instance body; `docs/adr.md` section 11; `docs/skills.md`.
   - `sources.sh check-settings` rejects unknown top-level keys in `.claude/settings.json`, since one silently disables every deny rule in the file (phase 1). A script change: fixture needed.
   - The skill checks, after each settings change, that the denied tools no longer appear among the session's tools.
   - Optionally `sources.sh show` prints "Reader: missing" for an `access: tools` instance without a `## Reader` section (a script change: fixture needed).
   - Tests: every `access: tools` contract has a `## Bind` section; the skill's frontmatter.
3. **A machine-readable binding:** the `reader:` key in `contract.py`, settings rules from it, and optionally the guard checks in design point 6. Fixtures, and a decision in `docs/adr.md`.

## Open
- Whether a binding belongs in the instance (per wiki) or in a per-machine file shared by all wikis. One connector serves every wiki on a machine, and connector tool names are per account (`mcp__claude_ai_<server>__…`); but instance files are where the guard trusts content today.
- Copilot: wikis run only in Claude Code; a Copilot port would need its own check of these assumptions (`docs/plans/copilot-wiki-support.md`).
