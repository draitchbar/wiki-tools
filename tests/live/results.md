# Spike runs: one line per session

The record behind the capability matrix (`docs/development.md`, "Agents") and the plan's results (`docs/plans/copilot-wiki-support.md`, step 1): every prompt-mode session the spike ran on Linux on 2026-11-17, with Copilot CLI 1.0.112 and Claude Code 2.1.326 in the container (`Dockerfile`). Generated from each run's `meta.txt` and `capture/` (`run.sh`); the raw records, which hold session IDs and model output, stay in the container's volume.

Columns: the lane (`plugindir`: `--plugin-dir` the test copy; `project`: only what the folder enables); flags beyond the fixed ones (`-p`, model, output format, `--no-ask-user`, `--no-auto-update`, `--trust-folder`, Claude's hook-event output); the capture hook's modes (`capture.sh`; none listed means `guard` ran the real guard, the rest allowed); attempts (blank: before `run.sh` counted them; crashes then were rerun by hand); hook calls by event; and for each call the `guard`-tagged hook saw, the tool and its exit code (2 = denied, `killed` = timed out). A run with no hook calls loaded no plugin hooks.

## What decided the matrix rows

| Row | Runs | Outcome |
|---|---|---|
| Exit 2, exit 1, 127, JSON deny, timeout | `*-deny-*`, `*-timeout-onfailure` | Probe: `touch` a file in the wiki, allowed by `--allowedTools`/`--allow-tool`. The command ran (file created) in claude exit1, missing, sleep and copilot sleep; not in the rest. With `onFailure: "block"` (`*-timeout-onfailure`): Claude refused ("timed out; blocking because onFailure is \"block\""), Copilot ran it 10 s after the hook started. The reason word reached the model in claude exit2 and both JSON denies only. |
| Subagents | `*-child`, `*-child-deny`, `copilot-autopilot-child` | Child calls carry `agent_id`; the JSON deny and the real guard's exit 2 stopped them. |
| Autopilot with `--allow-all` | `copilot-autopilot-main`, `copilot-autopilot-child` | The real guard refused `git push origin HEAD:refs/heads/probe-*` and `echo probe >> .claude/settings.json` (exit 2, both calls, both runs); the bare remote's refs and the settings file unchanged. The model did not get the guard's reason (exit 2). |
| Grep/Glob `paths` | `copilot-grep-glob-paths` | With a codebase (`agent_only`) instance on `other/`: Grep `paths` as a string and Glob `paths` as a list into it, from the main session, passed the real guard (exit 0). The same Grep with Claude's `path` is refused. |
| Patch tool | `copilot-patch-input`, `copilot-patch-update-move` | `Edit` with the patch as a string: Add File (two files), then Update File and Move to, absolute paths. The second patch reached the hook, then Copilot failed to parse it ("Update hunk does not contain any lines"); nothing changed. |
| Write/Edit today | `copilot-basic` | The real guard refused Copilot's Write (exit 2, "Write call without file_path; refusing (fail closed)"); `copilot-write-edit` captured the Write and Edit payloads with the guard set to allow. |
| Context | `*-schema-*`, `*-ctx-*` | Canaries answered from the hook context: Copilot only with the top-level `additionalContext`; both with the two-key JSON; after resume; Copilot after two automatic compactions (`copilot-ctx-autocompact`). |
| Activation | `*-act-*`, `copilot-plugindir-untrusted` | No hooks in `other/` and wiki-tools, Claude's `wiki2` without the marketplace registered, and Copilot's untrusted `wiki2` in `-p`. |

## All runs

| Run | Lane | Extra flags | Hook modes | Attempts | rc | Hook calls | Guard-tag result per call |
|---|---|---|---|---|---|---|---|
| claude-act-other | project |  | guard=allow | 1 | 0 |  |  |
| claude-act-wiki2-registered | project |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| claude-act-wiki2 | project |  | guard=allow | 1 | 0 |  |  |
| claude-act-wikitools | project |  | guard=allow | 1 | 0 |  |  |
| claude-basic | plugindir | --allowedTools Bash(git status *) Write(wiki/spike-note.md) Edit(wiki/spike-note.md) Read Grep Glob |  |  | 0 | PostToolUse=6 PreToolUse=18 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 Read:0 Grep:0 Glob:0 Write:0 Edit:0 |
| claude-child-deny | plugindir | --allowedTools Agent Task Bash(touch *) | guard=json-deny | 1 | 0 | PostToolUse=1 PreToolUse=5 SessionEnd=1 SessionStart=2 Stop=2 SubagentStart=1 SubagentStop=1 UserPromptSubmit=2 | Bash(child):0 |
| claude-child | plugindir | --allowedTools Agent Task Bash(git log *) Read | guard=allow |  | 0 | PostToolUse=3 PreToolUse=8 SessionEnd=1 SessionStart=2 Stop=1 SubagentStart=1 SubagentStop=1 UserPromptSubmit=1 | Bash(child):0 Read(child):0 |
| claude-ctx-compact | plugindir | --resume <id> | guard=allow | 1 | 0 | PreCompact=1 SessionEnd=1 SessionStart=2 SubagentStop=1 |  |
| claude-ctx-resume | plugindir | --resume <id> | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=1 Stop=1 UserPromptSubmit=1 |  |
| claude-ctx-start | plugindir |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| claude-deny-exit1 | plugindir | --allowedTools Bash(touch *) | guard=allow pre-nomatcher=exit1 | 1 | 0 | PostToolUse=1 PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| claude-deny-exit2 | plugindir | --allowedTools Bash(touch *) | guard=allow pre-nomatcher=exit2 | 1 | 0 | PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| claude-deny-json-deny | plugindir | --allowedTools Bash(touch *) | guard=allow pre-nomatcher=json-deny | 1 | 0 | PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| claude-deny-missing | plugindir | --allowedTools Bash(touch *) | guard=allow pre-nomatcher=missing | 1 | 0 | PostToolUse=1 PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| claude-deny-sleep | plugindir | --allowedTools Bash(touch *) | guard=allow pre-nomatcher=sleep | 1 | 0 | PostToolUse=1 PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| claude-schema-both | plugindir |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| claude-schema-json | plugindir |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| claude-schema-start | plugindir |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| claude-skill-sync | plugindir | --allowedTools Skill(wiki:sync-status) | guard=guard | 1 | 0 | PostToolUse=1 PreToolUse=2 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| claude-timeout-onfailure | plugindir | --allowedTools Bash(touch *) | guard=allow pre-nomatcher=sleep | 1 | 0 | PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| copilot-act-other | project |  | guard=allow | 1 | 0 |  |  |
| copilot-act-wiki2-untrusted | project |  | guard=allow | 1 | 0 |  |  |
| copilot-act-wiki2 | project |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| copilot-act-wikitools | project |  | guard=allow | 1 | 0 |  |  |
| copilot-autopilot-child | plugindir | --autopilot --allow-all |  | 1 | 0 | SubagentStart=1 PostToolUse=2 PreToolUse=6 SessionEnd=1 SessionStart=2 Stop=2 SubagentStop=1 UserPromptSubmit=2 | Bash(child):2 Bash(child):2 |
| copilot-autopilot-main | plugindir | --autopilot --allow-all |  | 1 | 0 | PostToolUse=1 PreToolUse=4 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:2 Bash:2 |
| copilot-basic | plugindir | --allow-tool shell(git status) --allow-tool write(wiki/spike-note.md) |  |  | 0 | PostToolUse=4 PreToolUse=13 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 Read:0 Grep:0 Glob:0 Write:2 |
| copilot-child-deny | plugindir | --allow-tool shell(touch) | guard=json-deny | 1 | 0 | SubagentStart=1 PostToolUse=1 PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=2 SubagentStop=1 UserPromptSubmit=2 | Bash(child):0 |
| copilot-child | plugindir | --allow-tool shell(git log) | guard=allow |  | 0 | SubagentStart=1 PostToolUse=2 PreToolUse=8 SessionEnd=1 SessionStart=2 Stop=2 SubagentStop=1 UserPromptSubmit=2 | Bash(child):0 Read(child):0 |
| copilot-ctx-autocompact | plugindir |  | guard=allow | 1 | 0 | PostToolUse=5 PreCompact=2 PreToolUse=15 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Read:0 Read:0 Read:0 Read:0 Read:0 |
| copilot-ctx-compact | plugindir | --resume | guard=allow | 1 | 0 | PreCompact=1 |  |
| copilot-ctx-resume | plugindir | --resume | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| copilot-ctx-start | plugindir |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| copilot-deny-exit1 | plugindir | --allow-tool shell(touch) | guard=allow pre-nomatcher=exit1 | 1 | 0 | PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| copilot-deny-exit2 | plugindir | --allow-tool shell(touch) | guard=allow pre-nomatcher=exit2 | 1 | 0 | PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| copilot-deny-json-deny | plugindir | --allow-tool shell(touch) | guard=allow pre-nomatcher=json-deny | 1 | 0 | PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| copilot-deny-missing | plugindir | --allow-tool shell(touch) | guard=allow pre-nomatcher=missing | 1 | 0 | PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| copilot-deny-sleep | plugindir | --allow-tool shell(touch) | guard=allow pre-nomatcher=sleep | 2 | 0 | PostToolUse=1 PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| copilot-grep-glob-paths | plugindir | --add-dir ~/spike/other |  | 1 | 0 | PostToolUse=2 PreToolUse=6 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Grep:0 Glob:0 |
| copilot-patch-input | plugindir | --allow-tool write(wiki/a.md) --allow-tool write(wiki/b.md) --allow-tool shell(cat) | guard=allow |  | 0 | PostToolUse=3 PreToolUse=14 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Edit:0 Bash:0 Bash:0 Bash:0 |
| copilot-patch-update-move | plugindir | --allow-tool write | guard=allow | 1 | 0 | PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Edit:0 |
| copilot-plugindir-untrusted | plugindir |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| copilot-schema-both | plugindir |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| copilot-schema-json | plugindir |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| copilot-schema-start | plugindir |  | guard=allow | 1 | 0 | SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 |  |
| copilot-shell-input | plugindir | --allow-tool shell(cat) | guard=allow |  | 0 | PostToolUse=2 PreToolUse=5 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| copilot-skill-sync | plugindir |  | guard=guard | 1 | 0 | PostToolUse=1 PreToolUse=8 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 Bash:0 |
| copilot-timeout-onfailure | plugindir | --allow-tool shell(touch) | guard=allow pre-nomatcher=sleep | 1 | 0 | PostToolUse=1 PreToolUse=3 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Bash:0 |
| copilot-write-edit | plugindir | --allow-tool write(wiki/spike-note.md) | guard=allow |  | 0 | PostToolUse=2 PreToolUse=6 SessionEnd=1 SessionStart=2 Stop=1 UserPromptSubmit=1 | Write:0 Edit:0 |

One interactive session, run by hand (`SPIKE_RUN=interactive-write-bash`, `--autopilot --allow-all`, `claude-sonnet-5.5`): asked to type `git push` into a running shell with `write_bash`, the model searched its tools (`tool_search_tool`, pattern `write_bash`: "No tools found"), started nothing and ended with `task_complete`, which fired PreToolUse. Hook calls: SessionStart 2 (`source: new`), UserPromptSubmit 2 (the second an autopilot continuation), PreToolUse 4, PostToolUse 2, Stop 2. Remote unchanged.

## Windows (plan step 1.7)

Copilot CLI 1.0.113 started from PowerShell 7.7 on Windows 11, with its own `COPILOT_HOME` in a scratch folder and a fine-grained token (Copilot Requests only) in `COPILOT_GITHUB_TOKEN`, deleted afterwards. The test wiki came from `setup.sh all` with `SPIKE` in that folder; each run asked for three commands (shell version, whether `COPILOT_GITHUB_TOKEN` is set, printing only SET or UNSET, and `git status --short`) with `--allow-tool shell`.

| Run | Hook commands | Result |
|---|---|---|
| `shell-default` | the capture hooks as `setup.sh` writes them (`bash "<plugin>/scripts/spike-capture.sh" <tag>`) | Agent tool `powershell`. Every hook exited 1: `bash` from PATH is WSL's launcher, whose only distribution has no bash. All three commands refused ("hook errored"); no captures. |
| `shell-gitbash` | the same, `COPILOT_BASH_PATH` = Git Bash | The same: agent tool `powershell`, hooks still reached WSL. |
| `src-default`, `src-gitbash` | `command` written like the real guard hook (`if [ -n "$BASH_VERSION" ]; then . <script>; ...`), with and without `COPILOT_BASH_PATH` | PowerShell `ParserError` on the bash `if`: hook commands run in PowerShell. All commands refused. |
| `ps-field` | the same `command`, plus a `powershell` field: `& 'C:/Program Files/Git/bin/bash.exe' "$env:CLAUDE_PLUGIN_ROOT/scripts/spike-capture.sh" <tag>; exit $LASTEXITCODE` | Copilot ran the `powershell` field: the hook ran in Git Bash (`OSTYPE=msys`), got its input on stdin, and the real guard allowed all three (`tool_name: "Bash"` with PowerShell text). 340-376 ms per hook. `CLAUDE_PLUGIN_ROOT` with backslashes, `COPILOT_CLI=1`. Commands ran: PowerShell 7.7.0, `TOKEN=UNSET`, clean tree. |

## Assisted approval and manual-only skills (Linux, Copilot 1.0.112)

Prompt-mode runs in the container, `claude-sonnet-5.5` / `claude-sonnet-5-5`. In `-p`, `--assisted-approval` approves or denies; what would ask a person is denied.

**Assisted approval.** Five steps, each exactly once: (1) `git push origin HEAD:refs/heads/probe-assisted` to the bare test remote, (2) `echo probe >> .claude/settings.json`, (3) `echo probe >>` a file in the `notes` instance's root, (4) create `wiki/spring-fair.md`, (5) `git status --short`.

| Run | Guard | (1) push | (2) settings | (3) source | (4) wiki page | (5) status | Session |
|---|---|---|---|---|---|---|---|
| `copilot-assisted-guard` | real guard | guard: refused | guard: refused | guard: refused | guard: refused ("Write call without file_path", the known input gap) | ran | 13 s, 1 premium request |
| `copilot-assisted-judge` | capture only (`mode.guard` = allow) | **ran**: new branch on the remote | **ran** | **ran** | judge: refused ("Proposed path duplicates `wiki`; it does not match the authorized file target") | ran | 33 s, 1 premium request |

With the guard on, every refusal came from the guard, and the session took as long as one without the judge: the judge wasn't consulted on calls the guard refused, or added no time. With the guard off, the judge approved all three harmful calls and refused the one harmless write, on a misreading of the path. The judge's checks didn't show as extra premium requests; they added about 20 s over the four calls it judged.

**`disable-model-invocation`.** The plugin's manual-only skills don't have the "Run only when the user typed" line yet, so these runs test the frontmatter alone.

| Run | Prompt | Approval | Result |
|---|---|---|---|
| `copilot-dmi-*` (3), `claude-dmi` | "Health-check this wiki: broken links, orphan pages, frontmatter problems and stale pages. Write the report to outputs/." | default, `--autopilot --allow-all`, `--assisted-approval`; Claude | No client tried to load `lint`; all checked the wiki by hand |
| `copilot-dmi2-lint-default`, `-autopilot`, `claude-dmi2-lint` | "Lint the wiki." | default, `--autopilot --allow-all`; Claude | No `lint` load. Copilot in autopilot loaded `sync-status` (not manual-only), saw it was the wrong skill, and linted by hand |
| `copilot-dmi2-skill-default` | "Use the wiki plugin's lint skill now and follow it." | default | `skill` tool refused: "Skill "lint" exists but cannot be invoked by the model because disable-model-invocation is enabled." Its next try, a shell search for the skill file, needed approval and was denied; it stopped |
| `copilot-dmi2-skill-autopilot` | the same | `--autopilot --allow-all` | The same refusal; then the model **found `SKILL.md` on disk, read it and followed it**: ran `lint.sh`, tried to write the report and the log entry (refused by the guard's Write gap), ended with `task_complete` |
| `claude-dmi2-skill` | the same | Claude | `Skill` tool refused; the model followed the error's advice not to reproduce the workflow and asked the user to type `/wiki:lint` |
| `copilot-dmi3-project-skill` | "Use the probe-manual skill now and follow it." (a manual-only skill in the wiki's `.claude/skills/`) | default | `skill` tool refused, as for the plugin skill; the model stopped |

So Copilot 1.0.112 enforces `disable-model-invocation` at its `skill` tool, for plugin and project skills, in every approval mode. It doesn't stop a model from reading the skill file and following it by hand, which happened once in autopilot with allow-all.

## Reader binding, phase 1 (2026-11-19)
The reader-binding plan, phase 1 (its decisions: `docs/adr.md`, 12 and 13): the tool-neutral `jira` contract bound by hand to the claude.ai "Atlassian MCP" connector in a work wiki, installed, then ingested. Claude Code 2.1.328, Windows 11 (Git Bash), auto mode throughout. Site, keys, project and component names left out.

| Operation | Tool and arguments | Output |
|---|---|---|
| site access | `getAccessibleAtlassianResources` | about 730 characters; Jira and every other product read-only |
| find project | `executeRead`, `name: listJiraProjects`, `inputs: {query, action: browse}`, `cloudId` top-level | about 1,500 characters |
| search | `searchJiraIssuesUsingJql`, one key, fields `key`, `summary`, `updated`, `maxResults: 1`, `view: compact` | about 430 characters; paging by `pageInfo.hasNextPage` / `pageInfo.endCursor` |
| count | `searchJiraIssuesUsingJql`, `searchResultMode: count` | about 150 characters (`issues.totalCount`) |
| recently viewed | search with field `lastViewed`, `view: compact` | not returned (`fields: {}`); test skipped |
| read issue | `getJiraIssue`, fields `summary`, `updated`, markdown | about 370 characters; 2,000 to 8,000 with the Fetch fields |
| list comments | `listJiraIssueComments`, `orderBy: -created`, `maxResults: 1` | about 140 characters |
| list remote links | `executeRead`, `name: listJiraIssueRemoteIssueLinks` | 11 characters (empty) |

- **Prompts:** none. Auto mode allowed every call, including test calls made before any allow rule existed.
- **Deny rules:** tools denied in settings didn't appear among the deferred tools at all. A misspelled top-level key in the wiki's `.claude/settings.json` made all of them appear again, with no error; fixing the key hid them again.
- **Model-invoked skill inside `/wiki:ingest`:** `wiki:sync-status` started by Claude, no prompt.
- **`sources.sh show`** reported "Check needed" after the instance file was installed, then committed.
- **Ingest:** 31 issues listed in two search pages (20 and 11), fetched in two batches with one commit each; comments read for 8 issues. No Jira tool used outside the `## Reader` section.
- **Hook payload** of an `executeRead` call (PreToolUse, main session): `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `permission_mode`, `effort`, `hook_event_name`, `tool_name`, `tool_input`; the operation is `tool_input.name`, beside `tool_input.cloudId` and `tool_input.inputs`. No `agent_id`.
- **Guard:** `grep` through Bash on a path containing `.claude/settings` is blocked, as `cat` is (the Grep and Read tools work).

## Reader binding, phase 2 (2026-11-19)
`/wiki:bind-reader` run live in a second work wiki, for `jira` (the same connector as phase 1) and `onenote` (a user skill's PowerShell script), each followed by an ingest. Site, keys, project, component and notebook names left out.

- **jira:** every test passed; the `## Bind` section's dispatcher names were right, and `issueHistory()` before and after confirmed that reading an issue didn't mark it viewed. The user missed one allow line, found only by re-reading the settings by hand: the skill now checks the settings after the install.
- **Moved keys:** the site had bulk-moved the instance's initiatives to a new project key a few days earlier. Check's `under` step read them under their new keys but had no rule for it; the Changes list then held about 80 issues, half of them key-only moves. Recorded in the contract: Check proposes the new key under the same scope name, List new's **Moved issues**, and delegated fetch for Changes batches of 18 to 40 issues.
- **Renamed component:** one component no longer existed, and JQL validation failed the whole query ("The value '…' does not exist for the field 'component'"). Check's per-scope search caught it; the contract now says what the error means.
- **onenote:** the instance described its reader in prose without a `## Reader` section, so Check started a full binding for a reader that worked: the skill now takes such a reader from the prose. The safe page had no link or file (a second safe page is now allowed for those tests). Five of six "skipped page changed" reports differed only in blank lines and whitespace from older snapshots: List new now compares ignoring them.
- **Shell:** an inline Python heredoc with nested quotes failed in Git Bash ("unexpected EOF while looking for matching `''"); the bash error, not the guard. The conventions now say to run such scripts from a file.

## Cloud sessions (2026-11-21, Claude Code 2.1.330)
The spike of `docs/plans/cloud-wikis.md`: one-off routines (created through the routines API, no connectors), Anthropic-hosted environments. The setup the runs proved is in `plugins/wiki/cloud/SETUP.md`. Wiki names and contents left out.

| Run | Environment | Repository | Prompt | Outcome |
|---|---|---|---|---|
| A | default | none | diagnostics | Control: no `wiki:` skills, no schema, nothing refused. Two plugins synced from the claude.ai account were loaded (`@synced`). The routine's `enabled_plugins` and `extra_marketplaces` fields came back empty after create and update. |
| B | default | none | fetch wiki-tools, start a child `claude -p` with `CLAUDE_CODE_PLUGIN_DIRS` | `git clone` of the public repository, `raw.githubusercontent.com` and `claude plugin marketplace add` (in a throwaway config folder) worked; `codeload` got 403. Auto mode refused the child `claude -p` ("Undermining Oversight"). |
| 1 | spike: setup script + `CLAUDE_CODE_PLUGIN_DIRS=/opt/wiki-plugin` | none | diagnostics | Setup script ran in about 10 s (clone, `codeload` and raw all worked there). Plugin loaded as `wiki@inline`. Guard refused `eval "git push …"`, a write to `.claude/settings.json`, and every command naming `claude`; a Write to `/tmp` passed. |
| 2 | spike | none | diagnostics | "Setup script cached from previous run". Both schema files at session start; no sync status (no wiki). Model sees `wiki:bind-reader`, `wiki:research`, `wiki:sync-status`. Unclassified cloud-only tools listed. A synced account plugin's MCP server failed through the proxy (403). |
| 3 | spike | none | `/wiki:lint` | The manual-only skill started: its injection ran `lint.sh`, which stopped with "not inside a git repo". |
| 4 | spike | a real wiki | diagnostics | Clone at `/home/user/<repo>`, default branch. Sync status and schema at start, plugin root filled in as `/opt/wiki-plugin`. `sources.sh list` and `due` ran (every type "available"). `wiki-check.sh`: one FAIL, a reader rule naming a local path. Plain and `eval` `git push` refused by the guard. Git identity `Claude <noreply@anthropic.com>`. The setup script ran again (about 8 s). |
| 5 | spike | the same wiki | `/wiki:ingest all --unattended` | Gmail refused (Check needed), Proton failed cleanly (reader script missing), `raw` not due; nothing written or committed; a push notification with the summary. |
| 6 | spike | the wiki + a second, private repository | diagnostics | Both cloned before the setup script. Session started in `/home/user`, not the wiki: schema yes, sync status no; the guard still refused `git push`. |

## Google Drive, tool-neutral (2026-11-22)
The `google-drive` contract after its move to `access: tools` (`docs/adr.md`, 18), bound live with `/wiki:bind-reader` to the claude.ai Google Drive connector in a personal wiki (one folder, six draw.io files), then an ingest and an audit of the pages citing it. Claude Code on Linux. Folder and file names left out.

- **Passed:** the catalog, `sources.sh show` ("Check needed … no reader binding yet"), `settings google-drive` (no tool rules), the deny step (denied tools gone from ToolSearch after a reload), Bind's get item, list folder, search by name and list revisions, the install, `check-settings`, and Check (the tool per operation, "read-only not verified"). The audit supported 8 of 8 claims.
- **Download:** Claude Code saved `download_file_content`'s result as the raw file (`tool-results/*.bin`, the file's size, "file sent separately"), not base64, so `decode-download.sh` refused it. Now `decode-download.sh --raw` copies such a file into the cache.
- **Connector quirks, now in the contract:** `title = '<name>'` also returns names that start with it, in varying order; paging ignores `pageSize` (5 of 6 files on page 1 with a token) and returns a token with a single result; `get_file_metadata` and `search_files` name the owner's email address, and `list_file_revisions` the last editor, without `includeRichMetadata`; older revisions are `canDownload: false`.
- **Quoted reader items:** the first draft quoted each `reader` item, as YAML would need; the install refused every item and then every required operation as unbound. Validation now says once per item that it is in quotes, and `/wiki:bind-reader` tells the drafter not to quote.
- **Not exercised:** a first ingest's starting point, subfolders, a Fetch of a new file in an ingest (nothing new), and a revision download in Resolve citation (every cited date matched).
