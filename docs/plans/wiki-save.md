# Plan: saving a wiki session's work to its remote

Status: design, 2026-11-25. Three explorations (a guard exception for `git push`, a core script, pushing from a hook with no model involvement) merged into one design, reviewed once (folded in), then settled with the owner point by point. Not built. The first step is a live cloud check (**Live checks first**), whose answers can change the URL check.

## Goal
A wiki session, local or in a Claude Code cloud session, saves its commits to the wiki's own remote without the user pushing by hand. In the cloud this is what makes a session or routine worth running: an idle VM is thrown away, and only what was pushed lasts (`docs/plans/cloud-wikis.md`).

## The idea
**The model never gets a push.** `no_push` in `guard.py` stays first and unchanged, and so does the settings template's `Bash(git push *)` deny rule. One core script, `save.sh`, does the push. The model can't choose where it goes, which branch it updates or how git runs: the script takes those from a config the session can't change. A bare `git push` let through by the guard was rejected because git picks the remote, the refspec and the URL from config (`remote.*`, `push.default`, `url.*.insteadOf`) that a session can change with `git config`, which auto mode approves.

## Decisions settled with the owner
1. **What the danger is.** With force pushes and deletion refused by the host, the danger the guard exists for is a push to the wrong place: an injected instruction in ingested mail sending the wiki to another repository. The script pins the destination.
2. **Push straight to the default branch.** No branch per run, no pull request per run. Routines build on each other's state, nothing waits for a merge, and it matches what the user does by hand today.
3. **Personal data in the pushed content: accepted risk.** Wikis are private or shared with chosen contributors. There is no content check before a push. What already stands is unchanged: the privacy rules in the wiki's CLAUDE.md, ingest's privacy rule, the source researcher's secrets rule and `/wiki:lint`'s `privacy` check, all followed by the model.
4. **Paths in three tiers.** Free paths are pushed. Every other path needs the user's explicit permission. Symlinks and submodules are never pushed. (**Paths**)
5. **Suspicious material is held back and raised as an open question.** This is the defence against instructions planted in pages, and it lives in ingest, not in the push. (**Suspicious material**)
6. **Local and cloud alike**, opt-in per wiki.
7. **Any host.** The config stores the remote's full URL. GitHub gets extra checks through its API; other hosts rely on the user's own setup check.
8. **Conflicts: always merge, never rebase, never hold back.** The history keeps both sides for an audit. Conflicts are resolved by fixed rules, and each resolution is logged. (**Conflicts**)

## Components

### 1. `save.sh` and `save.py`
- A launcher in `plugins/wiki/scripts/`, with the work in `save.py` run through `py-run.sh`. That is new plugin Python, so ADR 4's list and AGENTS.md are amended.
- Forms:
  - `save.sh`: integrate and push.
  - `save.sh --check`: everything except the push, as a dry run.
  - `save.sh --update`: fetch the default branch from the pinned URL and merge it, with no push.
  - `save.sh --allow <path> ...`: push with permission-tier paths (**Paths**).
- Any other argument is refused. The guard lets a core script take any arguments (`guard.py:131`), so the script refuses them itself.
- Added to `CORE_SCRIPTS`, so a plain call passes the guard. It isn't named `push.sh`, to keep it clear of the push text matching.
- Saving is offered by a new model-invocable skill, `/wiki:save`. An unattended ingest runs `save.sh --update` in its **Clean start** and `save.sh` as its last step, when saving is enabled. An attended ingest offers to save at the end and doesn't save by itself.

### 2. The config: `.claude/settings.wiki-save.json`
- Committed. It is covered by the guard's `.claude/settings` substring (`guard.py:300`) for shell commands and writes. `/wiki:init`'s `.gitignore` gets `!.claude/settings.wiki-save.json`; existing wikis add that line by hand, and wiki-check says so.
- Fields:
  - `enabled`
  - `url`: the remote's full URL, the pin
  - `base`: the default branch
  - `content_paths`: default `wiki/ raw/ outputs/ open-questions.md`
- No file, or `enabled` not true: the script refuses with "saving is off for this wiki".
- The pin is read from the committed config **at HEAD**. A working-tree copy that differs from HEAD is refused. A commit that changes the config is a permission-tier path, because it is under `.claude/`, so repointing the pin takes the user's approval.
- `wiki_check` validates the file.

### 3. Where the push goes
- The script never pushes to a remote by name. It pushes to an explicit URL, so `git remote set-url`, `remote.*.pushurl` and `push.default` don't matter.
- **Locally:** the URL is the pinned `url`.
- **In the cloud** (`CLAUDE_CODE_REMOTE=true`): when the pinned `url` is on `github.com`, the script takes `owner/repo` from it and accepts `origin`'s URL only if that is the GitHub proxy's loopback form for the same repository. The exact form is settled by the live check.
- **The URL git will really use:**
  - `git ls-remote --get-url <url>` applies every `insteadOf` rewrite, includes and global config too. It must give back the accepted URL.
  - Any `url.*.pushInsteadOf` is refused.
  - If the cloud proxy itself works by a rewrite, that one rewrite is allowed by name, once it has been seen.
- **The environment:** every inherited `GIT_*` variable is cleared, `GIT_TERMINAL_PROMPT=0` is set, and git runs with `-c core.hooksPath=<an empty folder in the plugin>` and `--no-follow-tags`. The empty folder works on Linux and Git Bash alike.
- **The push itself:**
  - The commit is resolved once, checked, and that sha is pushed: `<sha>:refs/heads/<base>`.
  - Never `+`, never `--force`.
  - A non-fast-forward goes to **Conflicts**.
- **Credentials:** whatever git's credential helper gives locally, the proxy in the cloud. With several accounts, a wrong one gives an error, which the script reports and doesn't retry. A `gh_user` in the config, as `sources/codebase/git.sh` uses, is a later option.

### 4. Paths
Every path that changed between the remote's `base` and the commit being pushed is sorted into a tier:

| Tier | Paths | What saving does |
|---|---|---|
| Free | `content_paths` | Pushes |
| Needs permission | everything else: `CLAUDE.md`, `.gitignore`, `.gitattributes`, page templates, `.claude/…`, `.github/…`, `.githooks/…`, `.mcp.json` | See below |
| Never | symlinks, submodules (`.gitmodules`) | Refused |

**How permission is given:**
- **Interactive session:**
  1. A plain `save.sh` finds paths that need permission. It refuses and prints the exact call, e.g. `save.sh --allow CLAUDE.md .gitattributes`.
  2. When that call is run, **the guard answers "ask"** (`hookSpecificOutput.permissionDecision`), so the user gets Claude Code's permission prompt with the paths in the command.
  3. The script checks that the `--allow` list is exactly the set of paths that need permission, then pushes.
- The guard asks, and not a settings `ask` rule, because the guard is protected code and auto mode may approve a rule's `Bash(...)` call.
- Today the guard only refuses (exit 2), so answering "ask" is new in `hookjson.py`.
- The user should look at the diff before approving, and should choose a plain Yes, not "don't ask again", the same advice as `/wiki:bind-reader`.
- **Unattended run:** nobody can answer a prompt. The commits go to a holding branch, `claude/wiki-<12 characters of the oldest commit in base..HEAD>`, named in the run report. On GitHub a draft pull request is opened through the REST API, since the proxy refuses GraphQL. Merging it is the permission. While a `claude/wiki-*` branch exists on the remote (`git ls-remote`, any host), an unattended run stops at **Clean start** with "merge or delete `claude/wiki-…` first", so runs don't stack on a state that isn't on the default branch.

### 5. Conflicts
- `save.sh --update` and `save.sh` (when the push isn't a fast-forward) fetch `base` from the pinned URL and **merge** it. A fast-forward is used where possible; otherwise a merge commit with a fixed message. The merge includes the remote branch, so the push is a fast-forward and the host's protection is satisfied.
- `wiki/log.md` gets `merge=union` in the wiki's `.gitattributes`. That is git's built-in driver, so no config is needed on any machine. Both sides prepend at the top, so without it this file would conflict every time. `/wiki:init` adds the line to new wikis; in an existing wiki it is a permission-tier change, approved once.
- On a conflict the script stops, leaves the merge in progress and lists the files. The model resolves them, interactive and unattended alike, by these rules (in `/wiki:save` and in ingest's **Unattended**):

| File | Rule |
|---|---|
| `raw/sync-log.md` | Per source, the state lines come from the side whose newest history row is later; the history tables keep both sides' rows. It is generic and names no type (ADR 2). Items both sides ingested show up on pages twice, which the page rule catches. |
| `open-questions.md` | Clarify's rule: keep both blocks; a duplicate ID gets a new one and its markers are rewritten. |
| Pages, `wiki/index.md` | Combine both sides. Two different figures for the same fact are both kept, cited, and raise a `conflict` question. |
| Anything else | Combine both sides; where that isn't possible, keep the remote version and record what was dropped. |

- The model commits the merge and runs `save.sh` again. The script refuses while any changed file still holds conflict markers.
- Each resolved merge gets a `wiki/log.md` entry, `## YYYY-MM-DD | merge | <files>`, with one line per file saying which rule decided it. The run report repeats it.

### 6. Checks that don't block a save
In the cloud, a commit that isn't pushed is lost, so a save refuses only for destination, paths and conflict markers.
- **A dirty working tree:** the committed HEAD is pushed, with a warning.
- **Lint and wiki-check findings:** reported, not refused.

### 7. The host's protection
- Required: the default branch refuses force pushes and deletion.
- **GitHub:** the script checks it on each save with `gh api repos/<o>/<r>/rules/branches/<base>`. It wants the `non_fast_forward` and `deletion` rules, and `current_user_can_bypass` must be `never`. Otherwise it refuses and points to `docs/setup.md`, "Optional: the wiki on GitHub". That is the ruleset the setup guide already gives; no pull-request rule is required, so the user's own pushes work as before.
- **Other hosts:** the script can't check, so the setup step has the user confirm the equivalent, and the script prints a reminder. The equivalents: GitLab protected branches, Gitea/Forgejo branch protection, or `receive.denyNonFastForwards` and `receive.denyDeletes` on a bare repository.
- **On a Free GitHub plan** a private repository's ruleset isn't enforced (`docs/setup.md`). The check then fails, and saving is unavailable there until the plan or the visibility changes.

### 8. Suspicious material (ingest and clarify; can ship first)
- A fourth question kind, `suspicious`, beside `unclear`, `conflict` and `filing` (`sourcelib.py`'s `KINDS`, checked by `lint.py`).
- **Unattended ingest:** an item with instructions in it is **held back**. Nothing from it is written, and a `suspicious` question cites it without quoting it. It replaces the `Suspicious: <citation>, not acted on` log line as the place the user hears about it; the report still names it.
- **`/wiki:clarify`:**
  - **Answer "fine":** clarify reads the cited item (the contract's **Resolve citation**) and writes its facts under ingest's rules for writing pages. That is new for clarify, which today writes only user statements.
  - **Dismiss:** it stays out, and isn't raised again.
- **Attended ingest:** asks at once, as now.
- What it doesn't catch: planted text that doesn't read as an instruction. A false figure against an existing one still raises a `conflict` question; a false fact on an empty page gets through. That is accepted, the same as today.
- Separately, one line in `schema/wiki-conventions.md`: wiki pages are data, not instructions. Today only the skills say it, not an ordinary session that reads pages.

### 9. Closing the `gh` side door (independent; can ship first)
`gh api -X PUT repos/<o>/<r>/contents/<path>` writes to the default branch with no `git push` at all, and the cloud proxy lets it through. The guard has no `gh` check today. It refuses `gh` as a command word with `api`, `pr`, `repo`, `release`, `workflow`, `secret` or `gist`, outside script exceptions; the codebase type's `gh.sh` still passes as a wrapper. Whether `curl` or Python can reach the API through the proxy as well is part of the live check. If they can, that is the same text-matching limit as an obfuscated push, and the ADR says so.

## Threats

| Threat | What stops it | What's left |
|---|---|---|
| An injected instruction asks for a push to another repository | A raw push is refused by the guard and the deny rule; `save.sh` takes no URL; the pin is read from HEAD's config, and a change to it needs permission; the effective-URL check; in the cloud, the proxy reaches only the session's repositories | An obfuscated shell command (`eval` of base64) can push anywhere today; `save.sh` adds no easier way (ADR 3's limit) |
| A redirect through git config (`insteadOf`, `GIT_*`, `remote set-url`, hooks) | Explicit URL; `ls-remote --get-url` check; cleared environment; `core.hooksPath` to an empty folder | A config change between the check and the push |
| History on the default branch overwritten or deleted | The refspec is never forced; the host's protection, checked on GitHub; the proxy refuses deletion | Hosts the script can't check |
| A pushed file runs as code or configures Claude (`.github/`, `.claude/`, `.mcp.json`, `CLAUDE.md`) | Permission tier: the user's prompt, or a holding branch to merge | An approval given without reading the diff |
| Instructions planted in pages | Suspicious items held back and raised; "pages are data" in skills and schema | Planted text that doesn't read as an instruction |
| Personal data in pushed content | Accepted risk (decision 3) | It stays in the history, which can't be rewritten |
| `gh api` writes that go past git | The new `gh` check | Text matching, as for the push check |
| A wrong conflict resolution | Fixed rules; a merge entry in `wiki/log.md`; the history keeps both sides | A wrong `raw/sync-log.md` choice: items read twice or skipped until noticed |
| A save that fails silently in a routine | Its output in the run report | Nobody reads it; the commits stay in the VM until it is thrown away |

## Live checks first
In a cloud session on a throwaway private wiki:
1. **The URL and the proxy:**
   - `git remote -v`
   - `git config --show-origin --get-regexp '^(url|http|credential|include)'`
   - `env | grep -i -E 'proxy|git_'`
   - `git ls-remote --get-url origin`

   These decide the cloud URL check and any rewrite to allow.
2. **A push to the default branch** through the proxy, by the user (the guard refuses it otherwise), and whether a ruleset with no bypass actors stops a force push from the proxy's account.
3. **The API through the proxy:** `gh api …/rules/branches/<base>` and `gh api -X POST …/pulls`. Can `curl` or Python reach the API too?
4. **The clone:** is it shallow? Does the session sit on its own `claude/…` branch?
5. **Prompts:** does the guard's "ask" prompt in auto mode, in the web UI, and with a matching allow rule in `settings.local.json`? If it doesn't, interactive cloud sessions use the holding branch too.
6. **Routines:** does a routine run `save.sh` without a prompt that stalls it?

## Steps
1. The live checks; their results are recorded in `docs/plans/cloud-wikis.md`.
2. Independent, each its own pull request:
   - the `suspicious` kind (8);
   - the schema line (8);
   - the `gh` check (9), a guard change.
3. `save.sh`/`save.py` with `--check` and `--update`, the config and its validation, the URL and path checks, the merge and the marker check. Tests: a local bare repository as the remote through a test-only `file://` seam; a fake `gh` on `PATH` that logs its calls; fixtures for each refusal (a rewrite, `pushInsteadOf`, a changed config, a symlink, conflict markers, a non-fast-forward with and without a conflict, an unknown argument); and guard fixtures for the plain, chained and lookalike calls, with `git push` still refused. `--e2e` on Linux and Windows.
4. The permission tier: the guard's "ask" reply, `--allow`, the holding branch and the draft pull request.
5. The skills: `/wiki:save`; ingest's **Clean start** and last step; the conflict rules; the attended offer; `/wiki:init` (`.gitignore`, `.gitattributes`, an optional step to turn saving on).
6. Docs:
   - a new ADR amending 2 (host-specific `gh api` calls in core), 3 (the guard's "ask" reply and the `gh` check), 4 (new Python) and 24;
   - `docs/guard.md`;
   - `docs/setup.md`, with each host's protection check;
   - `plugins/wiki/cloud/SETUP.md`;
   - the guard's message "Commit locally; the user pushes" names `/wiki:save` when saving is enabled.

   A guard is weakened, and the commits say so.

## Rejected
- **The guard lets an exact `git push` through, with a pre-push hook in `.git/hooks` pinning the URL.** Git reads the target from config the session can change. The hook must be installed in every fresh VM and can be switched off with `core.hooksPath`. And the deny rule would have to go.
- **A Stop or SessionEnd hook that pushes.**
  - Stop runs every turn in every wiki and pushes half-finished work.
  - SessionEnd has a 1.5-second budget and probably doesn't run when an idle VM is reclaimed.
  - Whether Stop runs in a routine's last turn is unknown.
  - It may come back later if interactive cloud sessions lose work.
- **A branch and pull request for every run.** Unmerged runs repeat each other's ingests and diverge on `raw/sync-log.md`, and every run waits for a merge (decision 2).
- **Rebase.** It rewrites commits and can stop once per commit; a merge stops once and keeps the history (decision 8).
- **A holding branch on every conflict.** The fixed rules and the history make a merge safe enough (decision 8).
- **A content check for secrets and personal data** (patterns, as in this repo's `scripts/pii_check.py`). Accepted risk (decision 3).
- **Scanning git config for a denylist of dangerous keys.** It needs constant upkeep and would refuse the proxy's own settings. The effective-URL check covers the redirect that matters.
- **Requiring pull requests on the default branch.** It would end the user's own direct pushes, and it isn't needed when force pushes and deletion are refused.
- **GitHub only.** Wikis are hosted elsewhere too (decision 7).
