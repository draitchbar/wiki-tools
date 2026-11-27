# Setup

Installing wiki-tools on a machine, setting up a wiki, and the known limits.

## Per machine

Install from GitHub: `claude plugin marketplace add draitchbar/wiki-tools`. Claude Code keeps its own copy of the plugin. To update it, run `claude plugin marketplace update wiki-tools` (refreshes the marketplace's listing), then `claude plugin update wiki@wiki-tools --scope project` in each wiki, and restart `claude` there. Automatic updates are off by default for a marketplace like this one; `/plugin`, tab Marketplaces, turns them on. To change the plugin, run it from a clone instead (`docs/development.md`, "Running the plugin from a clone").

| | Linux | Windows |
|---|---|---|
| Prerequisites | git, bash, Python 3.11 or later (`python3`; standard library only) | Git for Windows (Git Bash), Claude Code runs hooks in Git Bash; Python 3.11 or later from python.org, with the `python3` App execution alias turned off in Settings |
| OCR | `sudo apt install ocrmypdf` plus the Tesseract language packs your documents need (e.g. `tesseract-ocr-dan`); `/wiki:ingest` passes the languages from the wiki's CLAUDE.md | none; scans are read as page images |
| Sources | whatever the wikis' source types need, listed in each type's Caveats; e.g. codebase: a git clone of the repository, and `gh auth login` for the account in `gh_user`; Proton Drive: a Proton Drive reader, e.g. the `proton` plugin from `aitchbar-ai-tools` loaded from a local clone, with the CLI and its sign-in as its README says, and its rule in your user settings; Jira: a Jira reader, e.g. the claude.ai "Atlassian MCP" connector connected, its read tools allowed and its write tools denied in your settings; Google Drive: a Drive reader, e.g. the claude.ai Google Drive connector connected, its read tools allowed and its write tools denied in your settings (`/wiki:bind-reader` drafts the rules); Gmail: a Gmail reader, e.g. the claude.ai Gmail connector connected, its read tools allowed and its write and draft tools denied in your settings (`/wiki:bind-reader` drafts the rules); Microsoft Teams: a Microsoft 365 reader, e.g. the claude.ai Microsoft 365 connector connected (Graph permissions in `docs/sources.md`), its read tools allowed and its write, Outlook and people tools denied (`/wiki:bind-reader` drafts the rules); OneNote: a OneNote reader (CLI, skill or MCP server) signed in with Graph `Notes.Read` or `Notes.Read.All`, its read operations allowed in your settings | the same |

Don't install or enable the plugin at user scope. Each wiki enables it in its own committed `.claude/settings.json` (see `plugins/wiki/templates/project-settings.json`).

## Setting up a wiki

1. Create the folder (e.g. `mkdir ~/wikis/<name>`) and `cd` into it.
2. `claude plugin install wiki@wiki-tools --scope project`. This enables the plugin for this folder only, in `.claude/settings.json`.
3. Start `claude` and run `/wiki:init <what the wiki is for>`.

`/wiki:init` works in three modes:
- **New** (empty folder): grills you on scope, researches the domain, shows the full plan (CLAUDE.md, page types and templates, sources) and creates the raw/wiki layout after your go.
- **Adopt** (folder with content): the same, plus a move table that brings existing notes into `wiki/` (with `git mv` and frontmatter) and source files into `raw/`.
- **Check** (already set up): runs `scripts/wiki-check.sh` and reports what's missing; it also lists Markdown files outside the layout (INFO, not a failure). Run outside a git repo in a folder whose settings enable the plugin, it says the wiki isn't initialised yet and points to `/wiki:init`.

In new and adopt mode, before asking or writing anything, `/wiki:init` checks that git has a commit identity (`git config user.name`, `user.email`) and stops with the fix if not, since setup ends with a commit. Check mode skips this.

Only you can start `/wiki:init` (`disable-model-invocation`). Claude can run its check itself: `bash ${CLAUDE_PLUGIN_ROOT}/scripts/wiki-check.sh` (read-only; the guard allows it). A test plan sent to a wiki session therefore uses `wiki-check.sh`, or marks `/wiki:init` as a step the user runs.

`raw/` is the only built-in source. Every other source is chosen during init with the same flow as `/wiki:add-source`.

It ends with a guide for the steps only you can do, because the guard blocks Claude from them: pasting `.claude/settings.json` (from `plugins/wiki/templates/project-settings.json` plus the sources' rules) and the files under `.claude/sources/`, committing them and restarting `claude`. Setting up the git remote and pushing is also yours (Optional: the wiki on GitHub, below), unless you turn on saving, which lets `/wiki:save` push for you (Optional: saving from Claude, below).

Sources start at `last_checked_<key>: never`. The first `/wiki:ingest <key>` of each source checks it, asks for a starting point and reviews the data model (folders, page types, templates) against the wiki's purpose.

The shared starting template for people and organisations is `plugins/wiki/templates/pages/entity.md`; every other page type is designed per wiki by `/wiki:init`.

### Optional: the wiki on GitHub

A private GitHub repository gives the wiki an offsite copy, and a ruleset stops anyone from force-pushing over its history or deleting its main branch by accident. You run every step in a terminal; the guard stops Claude from pushing. The ruleset is also what saving from Claude requires on GitHub (below).

1. **Create the repository and push:** `gh repo create <org>/<wiki> --private --source=. --remote=origin --push` (just `<wiki>` for your personal account). Private, because a wiki is meant for you alone or a chosen group of contributors, never for everyone.
2. **Add the ruleset.** Save this as `ruleset.json`, outside the wiki or deleted afterwards:
   ```json
   {
     "name": "protect-default-branch",
     "target": "branch",
     "enforcement": "active",
     "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
     "rules": [ { "type": "deletion" }, { "type": "non_fast_forward" } ],
     "bypass_actors": []
   }
   ```
   Then: `gh api repos/<org>/<wiki>/rulesets --method POST --input <path>/ruleset.json`.
   - `non_fast_forward` refuses force pushes, and `deletion` refuses deleting the branch. Ordinary pushes work as before; there's no pull-request flow.
   - With an empty `bypass_actors`, the rules apply to admins too. That's deliberate: an admin who really means to force-push turns the ruleset off under Settings → Rules first.
   - `~DEFAULT_BRANCH` means whatever the default branch is, so it still applies if `master` is renamed to `main`.
   - **Plan:** GitHub documents rulesets on private repositories for Pro, Team and Enterprise Cloud only. On a Free plan, the ruleset may be saved without being enforced, so check that Settings → Rules doesn't say it isn't enforced. Saving from Claude checks it, so it isn't available for such a repository.
3. **Force-push deny rules (optional).** The settings template already denies every `git push` (`Bash(git push *)`), and the guard refuses pushes too, so today these add nothing (saving from Claude pushes through `save.sh`, never `git push` by Claude, and keeps the blanket rule). If a wiki ever lets Claude push, keep these in `permissions.deny` in `.claude/settings.json`, in place of the blanket rule:
   ```
   "Bash(git push --force*)",
   "Bash(git push -f*)",
   "Bash(git push * --force*)",
   "Bash(git push * -f*)",
   "Bash(git push *+*)"
   ```
   The last rule catches a force push written as a refspec (`git push origin +main`). Bash rules only match how a command is written, so `eval "git push --force"` gets past them (`docs/guard.md`, "Checked against Claude Code"). The ruleset is what actually holds.

**What a ruleset can't do:** stop someone deleting the repository. An org owner can restore a deleted org repository within 90 days. Your local clone is a full copy, and an occasional `git bundle create <path> --all` (stored outside the wiki) is a single-file backup.

### Optional: saving from Claude

With saving on, Claude saves the wiki's commits to its remote with `/wiki:save`, and a scheduled `/wiki:ingest … --unattended` brings in the remote's changes at its start and saves at its end. Claude still never runs `git push`: the core script `save.sh` pushes, only to the default branch at the URL pinned in the wiki's committed `.claude/settings.wiki.json`, never forced (`docs/adr.md`, 26). In a cloud session it is what keeps a session's work: an idle VM is thrown away with every commit not pushed. In a wiki session, `/wiki:init` (check mode) walks you through these steps.

1. **The remote, with the default branch on it.** Create it and push once yourself (`save.sh` refuses a remote that has no such branch yet).
2. **The host refuses force pushes and deletion of that branch.** `save.sh` relies on it: a save merges, so its pushes are fast-forwards, and the host is what stops anything else.
   - **GitHub:** the ruleset above. `save.sh` checks it before every save with `gh api repos/<owner>/<repo>/rules/branches/<base>`: it wants the `non_fast_forward` and `deletion` rules, and you mustn't be able to bypass them (`current_user_can_bypass` is `never`, so no bypass actors); otherwise it refuses and points here. `gh` must be installed and signed in wherever saving runs (a cloud session's proxy supplies the login). A private repository on GitHub Free: the ruleset isn't enforced, the check fails, and saving isn't available there until the plan or the visibility changes.
   - **GitLab:** protect the default branch (Settings → Repository → Protected branches) with "Allowed to force push" off; a protected branch can't be deleted.
   - **Gitea, Forgejo:** a branch protection rule for the default branch (Settings → Branches), with force pushes off; a protected branch can't be deleted.
   - **A bare repository you host** (a server or a shared folder): `git -C <repo.git> config receive.denyNonFastForwards true` and `git -C <repo.git> config receive.denyDeletes true`.
   - On these other hosts `save.sh` can't check and prints a reminder with each save: confirm the setting once, when you turn saving on.
3. **Two lines in the wiki.** `.gitignore`: `!.claude/settings.wiki.json` (without it the config can't be committed); `.gitattributes`: `wiki/log.md merge=union` (both sides of a merge prepend to the log; git's built-in union driver keeps both, with no setup on any machine). `/wiki:init` writes both into new wikis; in an older wiki Claude adds them and commits them.
4. **The config,** which you write (it is protected; Claude shows the content): the `save` section of `.claude/settings.wiki.json`, the wiki's settings file (one section per feature; other top-level keys are left for later features)
   ```json
   {
     "save": {
       "enabled": true,
       "url": "https://github.com/<owner>/<wiki>",
       "base": "main"
     }
   }
   ```
   Here `main` stands for the repository's default branch: write `master` (or whatever it is) if that is the default branch.
   - `url`: the remote's full URL, `https://…`, `ssh://…` or the scp-like form (`git@github.com:<owner>/<repo>.git`). A wiki that runs in a cloud session needs the `https://github.com/<owner>/<repo>` form: there it must equal the session's `origin`.
   - `base`: the default branch (`main`, `master`, …).
   - `content_paths` (optional): the paths a save pushes freely, default `["wiki/", "raw/", "outputs/", "open-questions.md"]`; a trailing `/` is a folder. A save takes them from the remote branch's config when it has one, so a local change to them takes effect only once you have pushed it.
   - `enabled: false`, no `save` section, or no file turns saving off. A file in the first, flat format (`enabled`, `url`, `base` at the top level) counts as no `save` section; wiki-check says to move them under `save`.
5. **Commit and push it yourself:** `git add -- .claude/settings.wiki.json && git commit -m "Turn on saving" && git push`. The script reads the config from the commit, never from the working tree, and refuses a working-tree copy that differs; a later change to the file, to any of its sections, is a path that needs your permission, and a pin the remote doesn't share is refused.
6. **Check:** `/wiki:init` (check mode, or Claude runs `wiki-check.sh`) reports `saving is on`; `/wiki:save --check` says what a save would push and pushes nothing.

What a save does with each path, and how you give permission:
- **Content** (`content_paths`): pushed.
- **Everything else** (`CLAUDE.md`, `.gitignore`, `.gitattributes`, `templates/`, `.claude/…`, `.github/…`, `.githooks/…`, `.mcp.json`), and these control files at any depth even inside the content folders (`CLAUDE.md`, `CLAUDE.local.md`, `.claude/`, `.mcp.json`, `.gitattributes`, `.gitignore`, `.github/`, `.githooks/`), and the save config itself: needs your permission. `/wiki:save` shows you the diff and runs `save.sh --allow <those paths>`; the guard then asks you, with Claude Code's permission prompt. Answer a plain Yes if the diff is what you want saved, never "don't ask again". An unattended run can't ask: it pushes to a holding branch `claude/wiki-<12 hex>` instead (on GitHub with a draft pull request), and merging it is your permission. While such a branch is on the remote and its last commit isn't in the default branch, unattended runs neither start nor save: merge it, then delete the branch (after a squash merge its commits aren't in the default branch, so it still counts until deleted). Tip: on GitHub, turn on Settings → General → "Automatically delete head branches", so a merged holding branch is deleted with its pull request; rejecting a change still means closing the pull request and deleting the branch yourself. Only `claude/wiki-<12 hex>` names count. A path `--allow` can't carry (spaces, quotes, glob or other special characters, a leading `-`; the word `push` when the call also holds the word `git`, as in a plugin folder named `git`, which the guard refuses as a git push) can't be allowed interactively: rename it, or let it go through a holding branch. One `--allow` call carries at most 50 paths and 2000 characters (the guard's limits); a larger change goes through a holding branch.
- **Symlinks and submodules:** never saved.

Conflicts are merged, never rebased: Claude resolves them by fixed rules and logs each merge in `wiki/log.md` (`docs/skills.md`, "Saving"). Personal data in the pushed content is an accepted risk (the wiki is private); lint and wiki-check findings never block a save.

## Cloud sessions

A wiki can run in a Claude Code cloud session (claude.ai/code on the web or phone, or a routine on a schedule) when its environment brings the plugin: a setup script clones wiki-tools and `CLAUDE_CODE_PLUGIN_DIRS` loads `plugins/wiki/`. The guided setup, what was checked and what is still untested: `plugins/wiki/cloud/SETUP.md`. In a wiki session, ask Claude to walk you through it; it reads the page from the plugin. A cloud session's commits last only once saved: turn on saving (Optional: saving from Claude, above). To reach a wiki on your own machine from the web or phone instead, Remote Control works unchanged.

## Known issues

- **No OCR on Windows (deliberately out of scope for now).** `ocr.sh` needs `ocrmypdf` and Tesseract's language data, which are installed on Linux only.
  - **Normal case:** OCR scanned PDFs on Linux. The text is committed as `raw/ocr/<file>.txt`, so Windows reads it after `git pull`.
  - **A new scan ingested first on Windows:** `ocr.sh` exits with "ocrmypdf not installed", and `/wiki:ingest` falls back to Claude reading the PDF pages as images. That uses more tokens and leaves no `raw/ocr/` text. Re-run the ingest of that file on Linux to produce it.
  - **If Windows OCR is needed later:**
    - *Native:* Tesseract (UB Mannheim installer, with the language data your documents need), Ghostscript and `pip install ocrmypdf`, all on PATH. `ocr.sh` should then work unchanged from Git Bash. Untested.
    - *WSL:* `apt install ocrmypdf` and the language packs inside WSL, but `ocr.sh` would need to call `wsl ocrmypdf …`.

## Open checks

- **Plugin loading (checked 31.10.2026 on Linux, both wikis):** with the marketplace registered at user scope and a project-scope install in the wiki (Setting up a wiki, step 2), `enabledPlugins` in the wiki's settings loads the plugin, its skills and its hooks. **Without that install (checked 20.11.2026 on Windows, a fresh clone of a wiki at a new path, headless session):** `enabledPlugins` alone loads it, from `plugins/wiki/` of the marketplace folder: the model-invocable `wiki:` skills, both schema files and the sync status. The clone's `permissions.allow` rules are ignored until the folder is trusted (start `claude` there once and accept the trust dialog). The guard was not exercised in that run.
- **Skill injections (checked 31.10.2026 on Linux, both wikis):** `${CLAUDE_PLUGIN_ROOT}` is filled in inside `` !`…` `` injections, and they pass the guard without a permission prompt (`/wiki:sync-status`).
- **Schema hook and wrapper rules (checked 31.10.2026 on Linux, both wikis):** the SessionStart hooks load both schema files on start and resume, with `${CLAUDE_PLUGIN_ROOT}` filled in. A wiki's settings rule `Bash(bash */sources/<type>/<script>.sh *)` matched the wrapper's absolute path without a prompt. **Windows (Git Bash), 20.11.2026:** the schema hooks load both files with the plugin root filled in (as `/c/...` in the schema text, `C:/...` in skill bodies); the wrapper rule is unchecked, since it needs an interactive session outside auto mode that runs a wrapper the wiki's settings allow by such a rule.
- **Plugin variables (checked 27.10.2026 in the skills, hooks and plugins-reference docs):** `${CLAUDE_PLUGIN_ROOT}` is substituted in a plugin skill's body and in Bash rules in its `allowed-tools`, and set for hooks. It is not available to commands Claude runs through the Bash tool, so scripts find their own folder. Project settings and CLAUDE.md imports expand no variables.
- **Bash rule wildcards (checked 24.10.2026 in the permissions docs):** a `*` may stand anywhere in a Bash rule and matches any text, slashes and spaces included, so `Bash(bash ${CLAUDE_PLUGIN_ROOT}/sources/*/*.sh *)` in the skills' `allowed-tools` and `Bash(bash */sources/<type>/read.sh *)` in a wiki's settings work; the guard rejects `..` and lookalikes.
- **Hook environment (checked 24.10.2026 in the hooks docs):** hooks get `CLAUDE_PROJECT_DIR` (where the session started) and the input JSON has `cwd`; the guard uses the former and falls back to the git root of the latter.
