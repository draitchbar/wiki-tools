---
name: commit-themes
description: Commit the wiki's working-tree changes as separate commits, one per theme, staging only named paths and never pushing.
argument-hint: "[optional hint about the themes]"
disable-model-invocation: true
allowed-tools:
  - Bash(git status *)
  - Bash(git diff *)
  - Bash(git log *)
  - Bash(git add *)
  - Bash(git commit *)
---

# Commit by theme

1. Run `git status --porcelain` and `git diff --stat`, and read the diffs of modified files.
2. Group the **modified tracked files and files you created in this session** into themes: one theme per coherent change, e.g. "Ingest Alice's 14.10 mail", "Record scope decision", "Fix supplier statuses". Use the user's hint if given ($ARGUMENTS). A file that belongs to two themes goes with the larger one.
3. Show the plan as a short list: theme, commit message, files. Then commit each theme in turn:
   - `git add -- <path> <path> ...` with the paths named explicitly. Never `git add -A`, `git add .` or `git add -u`.
   - `git commit -m "<message>"`: imperative, specific, like the repo's existing history (`git log --oneline -10`).
4. Leave alone, and list for the user at the end:
   - untracked files you didn't create (e.g. PDFs or exports the user dropped in);
   - anything under `.claude/` (protected by the guard hooks; the user commits these);
   - files with no clear theme.
5. Never push. Finish with `git log --oneline -<n>` for the new commits.
