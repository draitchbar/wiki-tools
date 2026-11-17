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
