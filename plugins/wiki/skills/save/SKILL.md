---
name: save
description: Save the current wiki's commits to its own remote with save.sh, which pushes to the default branch at the URL pinned in the wiki's committed save config. Merges the remote's changes first and resolves conflicts by fixed rules; paths outside the wiki's content need the user's permission. Use when the user asks to save, push or sync the wiki, or accepts an ingest's offer to save.
argument-hint: "[--check]"
allowed-tools:
  - Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/save.sh)
  - Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/save.sh --check)
  - Bash(git status *)
  - Bash(git diff *)
  - Bash(git log *)
  - Bash(git show *)
  - Bash(git add *)
  - Bash(git commit *)
---

# Save: $ARGUMENTS

Save this wiki's commits to its remote. **You never push yourself**: `git push` and GitHub's tools are refused by the guard, and only `save.sh` pushes, to the URL and branch the wiki's committed `.claude/settings.wiki-save.json` pins. Saving is opt-in per wiki; `/wiki:init` (check mode) says how to turn it on.

**Hard rules**
- Run `save.sh` exactly as written here or as it prints, one call per Bash call, nothing around it (no `;`, `&&`, pipes, variables, redirection).
- **Never work around a refusal.** No `git push`, `gh`, a GitHub tool, `git config`, `git remote`, an edit of the save config or `.git/`, or another argument list to get past it. Report it with its fix; the fixes outside the wiki's content are the user's.
- Only commits are saved. Uncommitted changes stay local (`save.sh` warns); don't commit someone else's work to get it saved: ask.
- The script's output is the record: show its lines to the user, and never claim a save it didn't report.
- The guard matches command text: a commit message (or any command) that names `save.sh`, holds `git` and the word `push`, or starts a line with `gh pr`, `gh api` and the like is refused. Leave those words out; a merge commit uses `--no-edit`.

## 1. Run it
- `$ARGUMENTS` is `--check`: run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/save.sh --check`. It does everything but the merge and the push and says what a save would do. Report that and stop.
- Otherwise run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/save.sh`. It fetches the remote's branch from the pinned URL, merges it when the remote has moved, checks the paths and the host's protection, and pushes.

Then by its exit code:
- **0, done.** Report the first line (`saved <commit> to <branch>`), the `merged <branch> from the wiki's remote first (…)` or `nothing new: <branch> already has it` line after it, and every `save: warning:` or `save: note:` line (uncommitted changes not saved; a host whose protection the script can't check, which the user must confirm refuses force pushes and deletion). `--check` prints `checked: would push <commit> to <branch>` and `would merge …` or `nothing new: …`.
- **3, merge conflict.** The merge is left in progress and stdout lists its files as `conflict: <path>` lines: resolve them (**Conflicts**), then run the same call again.
- **1, refused.** The `save: refused: <reason>` line and the lines after it say why. One exception: `save: internal error after the push (<branches>): …` means the push to those branches went through and something failed afterwards; report it as saved, with the error. By the reason:
  - `these changes need your permission: …`: **Permission** below.
  - `the --allow list isn't the set of paths that need permission`: the paths changed since the diff was shown. Show the diff again (**Permission**, steps 1 to 3) for the paths its `need permission:` line names, then run its `run:` line.
  - `no path needs permission`: run its `run:` line, the plain call.
  - `a merge is in progress`, or `conflict markers left in <paths>`: an earlier merge isn't finished. Resolve the files (`git diff --name-only --diff-filter=U` lists the unmerged ones; markers left in committed files are fixed and committed the same way) by **Conflicts**, then save again.
  - `saving is off for this wiki …`: say so; turning it on is the user's (`/wiki:init` check mode lists the steps). Stop.
  - `… moved meanwhile; run save again`: run the same call once more.
  - `merge or delete claude/wiki-… first`, or `claude/wiki-… already exists on the wiki's remote: merge or delete it first` (unattended forms only): an earlier unattended save waits on that branch for the user; report it.
  - anything else: show the message and its detail lines as they are, with the fix they name, and stop. These are the user's to fix: the config differs from the committed one, is invalid or isn't valid JSON; the remote's config pins another URL; a git setting (`url.*.insteadOf`, `url.*.pushInsteadOf`, a remote named like the URL) could send the push elsewhere; this session's repository isn't the pinned remote; the remote has no such branch yet, or shares no history with the wiki; the host's protection is missing or can't be checked (no `gh`, an API error, a repository or branch name it can't check, too many rules, a rule naming no ruleset, a ruleset that doesn't say or lets you bypass it); symlinks or submodules; a failed push or merge; a missing git identity for a merge; an internal error.

## Permission
Paths outside the wiki's content folders (the config's `content_paths`, as the remote's branch has it), and control files at any depth even inside them (`CLAUDE.md`, `CLAUDE.local.md`, `.claude/…`, `.mcp.json`, `.gitattributes`, `.gitignore`, `.github/…`, `.githooks/…`, the save config itself), can change how Claude, git or the host behave, so a save that changes them needs the user's explicit yes. The refusal prints three lines:
```
save: refused: these changes need your permission: <paths>
look: git diff <from> <to> -- <paths>
run: bash <plugin>/scripts/save.sh --allow <paths>
```
1. **Show the diff.** Run the `look:` line as printed and show the user its output, whole. The guard refuses a command naming `.claude/settings…`, `.claude/sources`, `.claude/skills`, `.claude/agents`, `.mcp.json`, or a path with the word `push` in it. Then name the folder instead: `git diff <from> <to> -- .claude` for any path under `.claude/`, the path's parent folder for another one, `.` for a file at the root such as `.mcp.json` (the diff then shows more than these paths: point the user to theirs). The Read tool reads any of these files as they are now.
2. **Explain** in a few lines what each path's change does, and which commits made it (`git log --oneline <from>..<to> -- <path>`, with the same folder form where the path is refused).
3. **Ask for the permission prompt.** Tell the user that the next call shows Claude Code's permission prompt naming these paths, and that they should choose a plain **Yes** only if the diff is what they want saved, never "don't ask again" (that would save a standing rule outside this flow).
4. **Run the `run:` line** exactly as printed (the script's path may be in double quotes), as its own Bash call. The guard asks the user; on their Yes, `save.sh` checks that the list is exactly the paths that need permission and pushes. Report its result as in step 1.
   Where a `run:` line would be, `save.sh` may print `can't be allowed by --allow: <paths>. Rename it, or save with --unattended …` (a path with a space, a quote, a glob or other special character, or a leading `-`), or that the plugin's own path holds a character the call can't carry. Then there is no call to run: tell the user. A path is renamed by a commit of yours after their go; otherwise the change waits for an unattended run's holding branch, which the user merges.
5. If the user says no (or the call is denied), nothing is pushed. Say that the commits stay local, and that a later save asks again; the user may also undo the change with a new commit.

## Conflicts
`save.sh` (and `save.sh --update`) **merges** the remote's branch, never rebases, and never holds back for a conflict: both sides stay in the history. On a conflict it stops with the merge in progress. Resolve every listed file by the rules below, the same in an attended and an unattended run (`/wiki:ingest`'s **Unattended** follows this section).

1. Read each conflicted file. Between `<<<<<<<` and `=======` is this wiki's side, between `=======` and `>>>>>>>` the remote's. `git show :2:<path>` and `git show :3:<path>` print the whole of each side.
2. Resolve it by the first rule that fits:

| File | Rule |
|---|---|
| `raw/sync-log.md` | For each source key, its state lines (`<field>_<key>: …`) come from the side whose newest history row for that key is later; the history table keeps both sides' rows, by date. Items both sides ingested may now be on pages twice; the page rule handles that. |
| `open-questions.md` | Keep both sides' blocks. Two blocks with the same ID but different questions: the remote's keeps its ID, this side's gets a new one (`-2`, `-3`, as ingest's **Open questions** says), and its `^[open: <id>]` markers on this side's pages are rewritten to it. The same question on both sides is one block, merged as ingest merges questions. |
| Pages under `wiki/`, `wiki/index.md` | Combine both sides: every fact, citation and index row from either. Two different figures for the same fact are both kept, each with its citation, and raise a `conflict` question (`open-questions.md`, as ingest's **Open questions** says), whose marker goes after the two figures. `updated:` takes the later date. |
| Anything else | Combine both sides. Where that isn't possible, keep the remote's version and record what was dropped. |

   `wiki/log.md` doesn't conflict when the wiki's `.gitattributes` has `wiki/log.md merge=union`; without it, "anything else" keeps both sides' entries, newest first.
3. A conflicted file you can't write or stage is the user's: one the guard protects (`.claude/settings…`, `.claude/sources/…`, `.claude/skills/…`, `.claude/agents/…`, `.mcp.json`), or one whose `git add` it refuses (a name with the word `push` in it, say). Attended, ask the user to resolve and stage it from a terminal, and go on when they say it's done; if they can't (a session on the web), run `git merge --abort`. Unattended, run `git merge --abort`. Either way report the file, and that the save waits until the user has resolved it.
4. No conflict markers may remain (`<<<<<<< `, `=======`, `>>>>>>> ` at a line's start); `save.sh` refuses while a changed file holds both a `<<<<<<< ` and a `>>>>>>> ` line.
5. **Log it.** Prepend an entry to `wiki/log.md`: `## YYYY-MM-DD | merge | <files>`, then one line per resolved file, `- <path>: <rule>; <what was combined, kept or dropped>` (a dropped figure or block with its citation; a question raised by its ID).
6. **Commit the merge**: `git add -- <each resolved path> wiki/log.md` (named paths only), then `git commit --no-edit` (the merge's own message).
7. Run the same `save.sh` call again. The report names the merge entry's lines.
