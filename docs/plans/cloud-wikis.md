# Research: running a wiki in a Claude Code cloud session

Status: research, 2026-11-20, reviewed the same day (one round, folded in); **spike run 2026-11-21: option 2's second variant works** (**Spike results**), written up as a guided setup in `plugins/wiki/cloud/SETUP.md`. Nothing here is built beyond that page. Facts marked **(docs)** come from the Claude Code documentation as fetched that day (`code.claude.com/docs/en/`: `claude-code-on-the-web`, `cloud-environments`, `routines`, `settings`, `plugins/install`, `plugins/org`, `plugins/loading`, `hooks`, `mcp`, `skills`, `remote-control`); nothing was tried in a real cloud session. Cloud scheduled tasks are a research preview, so the facts may change.

## The question

Can a wiki run where the user's machine is off: a session at claude.ai/code (web or phone), or a scheduled cloud task that runs `/wiki:ingest all --unattended` (`docs/adr.md`, 14)?

## Finding: not as the wikis are set up today

**A cloud session doesn't load the plugins a repo's `.claude/settings.json` turns on, nor the ones installed on the user's machine (docs).** The only documented way to get a plugin into one is an organisation's server-managed settings. A wiki opened in the cloud today is therefore a plain repo: no `/wiki:*` skills, no guard, no schema at session start. Everything else follows from that.

## What a cloud session is (docs)

- **Machine:** a fresh Ubuntu 24.04 VM per session, with the repo cloned from GitHub. Python 3, git, `gh` and `jq` are there. PowerShell, `pdftotext`, LibreOffice and `ocrmypdf` aren't listed.
- **What loads from the repo:** `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/rules/`, `.mcp.json`, and the hooks and permission rules in `.claude/settings.json`. Hooks, rules and `.mcp.json` load only when the session has one repository; with several, only `enabledPlugins` and `extraKnownMarketplaces` are read from each, and "the marketplaces and plugins those two keys declare still don't load". A cloud thread inside a claude.ai Project loads none of the repo's settings, hooks or skills.
- **What doesn't:** the user's `~/.claude/settings.json`, `~/.claude/skills/` and local `claude mcp add` servers.
- **Setup script:** per environment, bash, runs as root before Claude Code starts. If it finishes in about five minutes the filesystem is snapshotted and reused; the snapshot is rebuilt when the script or the allowed hosts change, and after about seven days. Environment variables aren't set yet when it runs. If it exits non-zero the session fails to start, or starts without what failed to install.
- **Hooks:** the same events fire as locally. `CLAUDE_CODE_REMOTE` is `true` there and never `true` in the local CLI.
- **Persistence:** an idle VM is paused and may be reclaimed; a reopened session then gets a fresh VM. Only what was pushed to GitHub is sure to last.
- **Network:** an allowlist by default (package registries, GitHub, `*.microsoftonline.com`, `*.googleapis.com`; not `graph.microsoft.com`), extendable per environment. Connector traffic and GitHub go around it.
- **GitHub:** through a proxy that holds the credentials outside the VM. Only the session's repositories are reachable; API and archive requests for another repository get a 403, a public one included (a plain `git clone` of one isn't described). It refuses tag pushes and branch deletions but doesn't limit which branches a push updates, and branch rules the connected GitHub account can bypass don't stop a push. GraphQL is refused, so `gh pr` and `gh issue` fail; `gh api repos/…` works.
- **Commits** carry the user's GitHub identity and a `Claude-Session:` trailer unless `attribution.sessionUrl` is `false`.
- **Credentials:** no local logins exist, and interactive sign-in isn't supported. Environment variables are readable by the model. A "network secret" is added to requests for named hosts outside the VM, which suits a static API key.
- **Connectors:** claude.ai connectors work in cloud sessions and scheduled tasks; a task includes every connected connector by default. This answers the roadmap's "unknown whether claude.ai connectors load under cron" for cloud tasks (not for local cron).
- **Scheduled tasks:** a saved prompt, repositories, an environment and connectors; hourly at most; each run clones the default branch afresh and is a full session in the history. The prompt "is not live user input". Runs start in auto mode; a prompt that does appear waits until someone opens the run. Claude's changes go to `claude/`-prefixed branches (described, not enforced).
- **Cloud-only tools:** `SearchPlugins` and `SuggestPluginInstall` at least, and built-in GitHub tools that can post comments (names unknown).
- **Not available** to organisations with zero data retention, the HIPAA configuration or customer-managed keys; on Team and Enterprise an Owner enables it.

Not documented: whether a setup script can install a plugin, or whether `claude` is on its `PATH`; whether a plugin turned on for the claude.ai account (the cloud UI's "Plugin suggestions" add to it) loads in a cloud session; whether a user can type a repo or plugin skill's `/name` in the web or phone UI; whether a scheduled task's prompt can start a manual-only skill (a session-scoped scheduled task can't, and the prompt isn't user input, so probably not); where the clone lands; whether uncommitted files survive a reclaimed VM.

## What that means for the wiki plugin

- **Plugin, guard, schema:** absent unless one of the options below brings them. Worse than absent: the wiki's permission rules and every connector are still there, so a wiki opened in the cloud without the plugin runs unguarded.
- **`git push`:** the guard refuses it and the settings template denies it, but in the cloud nothing lasts unless pushed. A cloud wiki needs a push exception, and the wiki's content then lives on GitHub in branches the user merges.
- **Protected files:** `.claude/settings.json` and `.claude/sources/` are written only by the user, in a terminal (`install-source-file.sh`). That stays a local step; a cloud session uses what is committed.
- **Rules in user settings:** a reader's allow and deny rules kept in `~/.claude/settings.json` don't reach the cloud; they would have to be in the wiki's settings.
- **The cache** (`~/.cache/wiki-sources/<wiki>/<key>/`) starts empty in every VM. Downloads and research run folders are working files, so that costs only time. Two types keep state there: `onenote` its page snapshots (it doesn't work in the cloud anyway, below), and `ms-teams` its folder snapshot (`file-snapshot.sh`'s, used only when the reader's folder listing has no modified times). Teams channels and chats use the cursor in the sync log and are unaffected, but the folder walk would fall back to the citations check on every run and no longer see changed or moved files.
- **Reading files:** fetched PDFs and Office files are read with `pdftotext` and LibreOffice (`skills/ingest/reading-files.md`), which the VM lacks until the setup script installs them (`poppler-utils`, `libreoffice`).
- **Manual-only skills** (`ingest`, `clarify`, `lint`, …): usable only if the user can type them in the cloud UI, and by a scheduled task only if its prompt can start one. The first is unknown, the second doubtful.
- **Unknown tools:** the guard refuses any tool it hasn't classified, so the cloud-only tools above would be refused until added to `hookjson.py`.
- **Auto mode:** runs start in it, where the wikis today rely on the user's answer to a permission prompt (e.g. the reader binding, `docs/adr.md`, 12).

### Sources

| Source | In the cloud |
|---|---|
| `raw` | Only what is committed: Markdown and text, `raw/ocr/*.txt`. `/wiki:init`'s `.gitignore` keeps PDFs, Office files and images out of the repo, so those never reach the VM; ingesting and auditing them stays local. |
| `gmail` | Should work: claude.ai connector. To check: the tool names match the contract's (`mcp__claude_ai_…`). |
| `google-drive` | Should work with the claude.ai Google Drive connector, if the instance's binding names the same tools and its rules are in the wiki's settings. |
| `ms-teams` | Should work with the claude.ai Microsoft 365 connector, if the instance's binding names the session's tools (`mcp__Microsoft_365__*` in a cloud session: re-bind there) and its rules are in the wiki's settings; folders only in part (the cache, above). |
| `jira` | Should work with the Atlassian connector, if the instance's binding names the same tools and its rules are in the wiki's settings. |
| `codebase` | No, as built. The clone would be a second repository in the session, which turns off the wiki's hooks and rules; the root in the instance is a per-machine path; `gh.sh` first asks `gh auth token -u <gh_user>`, which has no login to answer (`git.sh`'s fetch likewise), and its `gh pr` and `gh issue` calls are refused by the proxy. |
| `local-folder` | No: the folders are on the user's machine. |
| `proton-files`, `onenote` | No: their readers need a local sign-in. |

So a cloud wiki is a connector wiki, plus the committed text in `raw/`. A wiki with other sources can still ingest those locally; `/wiki:ingest all` already skips a source that isn't available on the platform, but "platform" would need to know about the cloud.

## Options

1. **Remote Control: no change.** The session runs on the user's machine and is steered from the web or phone (docs). Plugin, guard, every source and every login work as today. The machine must be on and the `claude` process running. Desktop scheduled tasks and `/loop` are the local ways to schedule. A variant: a machine that is always on (a home server or VPS) with the wiki, the logins and local scheduling.
2. **The setup script brings the plugin.** One plugin and one guard, as ADR 1 has it, but on behaviour the docs don't describe, which may stop working. Variants, all untested:
   - `claude plugin marketplace add draitchbar/wiki-tools` and an install. Needs `claude` on the script's `PATH` and the proxy to let a repository outside the session be cloned. The copy lands under `.claude/plugins/`, which the guard refuses in commands; plain calls of the guard's own scripts are exempt before that check (`guard.py`, `protected_shell`), but no fixture pins a core script under a cache path.
   - The plugin's files fetched from `raw.githubusercontent.com` (on the allowlist) into a folder named by `CLAUDE_CODE_PLUGIN_SEED_DIR` or `CLAUDE_CODE_PLUGIN_DIRS`, set on the environment (`plugins/org`, "Seed containers and CI").
3. **The plugin inside each wiki.** Two forms:
   - A plugin folder in the wiki's `.claude/skills/` (with `.claude-plugin/plugin.json`), which loads in place as `wiki@skills-dir` with its skills, hooks and agents (`plugins/loading`). The names stay `/wiki:x`, and locally the installed marketplace plugin wins the name, so nothing runs twice. Whether a skills-dir plugin loads in a cloud session isn't stated.
   - Plain vendoring: skills in `.claude/skills/`, hooks in the wiki's settings. Documented to load; skills become `/x` and the hooks would also run locally beside the plugin's.
   - Either way, against ADR 1: a copy per wiki to keep in step; `/wiki:init` gitignores `.claude/*` and `wiki-check` expects that; the guard blocks commands naming the wiki's `.claude/skills` and assumes the plugin sits outside the wiki.
4. **Server-managed settings** (docs: the one documented route). An organisation Owner turns the plugin on for every member's sessions, which is the user scope ADR 1 rules out, and a personal wiki has no organisation.

The organisation's self-hosted environment is mentioned in the docs but wasn't researched.

## Recommendation

- **Reaching a wiki away from the desk:** Remote Control, today.
- **Runs with the machine off:** a spike before any design, because whether option 2 or the skills-dir form of option 3 works decides the shape. If neither does, stay with option 1 and local scheduling; plain vendoring isn't worth its cost.

### The spike

A throwaway private wiki on GitHub with made-up content, set up as `/wiki:init` leaves one (its `.gitignore` included), and a cloud environment of its own. Before the cloud steps, locally: the first ingest of `raw` done and pushed, then a new committed text file in `raw/` and `last_checked_raw` before today, so that an unattended run has something it is allowed to ingest.

1. **No setup script.** Confirm the plugin is absent: no skills, no schema, and `eval "git push …"` isn't refused by the guard's message. List the tools the session offers that `hookjson.py` doesn't know, and the connector tool names against the contracts'.
2. **Each way of bringing the plugin** (option 2's two variants, option 3's skills-dir form), one at a time. Passes when: the skills appear; the SessionStart schema arrives; a push and a write to `.claude/settings.json` are refused with the guard's own message ("git push is not allowed in wiki sessions"; the settings deny rule also refuses a plain `git push`, so use `eval "git push …"` or read the message); the core-script exceptions pass (`sources.sh list`). Note `${CLAUDE_PLUGIN_ROOT}`, `CLAUDE_PROJECT_DIR`, the git identity and the commit trailer.
3. **Again in a second session,** which starts from the snapshot rather than a live run of the script.
4. **The script failing** (exit 1): does the session start, and is it unguarded?
5. **Typing skills:** `/wiki:sync-status` and `/wiki:ingest raw` in the web UI and on the phone.
6. **Permissions:** do the wiki's rules apply, and is there a prompt nobody can answer?
7. **A scheduled task** with the prompt `/wiki:ingest all --unattended`: does it start the skill, is the guard there, does the connector load? With the guard working it can't push, so what counts is the run's transcript.

Record the results where the other live checks are (`tests/live/results.md`), with the Claude Code version.

### Spike results (2026-11-21, Claude Code 2.1.330)

Run through one-off routines created with the routines API, which the session's own tools can do; the user only created the environment. Runs and outcomes: `tests/live/results.md`, "Cloud sessions"; the setup they proved: `plugins/wiki/cloud/SETUP.md`.

- **Option 2, second variant, works:** a setup script clones the public wiki-tools (a plain `git clone` of a repository outside the session is allowed) into `/opt`, and `CLAUDE_CODE_PLUGIN_DIRS` set on the environment loads it. Steps 1 to 3 and 7 passed: skills, schema, sync status, the guard's own refusals, `sources.sh`, a reused snapshot, and a routine prompt starting a manual-only skill (`/wiki:lint`, `/wiki:ingest all --unattended`). Step 7 in a real wiki: Gmail skipped (Check needed), Proton failed cleanly, nothing committed.
- **Option 2, first variant:** `claude plugin marketplace add draitchbar/wiki-tools` works in the setup script, but was not taken further; the guard refuses commands naming `.claude/plugins/`, where it installs.
- **Not tried:** option 3 (a plugin folder in the wiki); the docs say repo-shared plugins need the trust dialog, which cloud sessions never show. Steps 4 (failing script), 5 (typing skills) and 6 (permissions) remain, with the design list below: **Still to test** in the setup page.
- **New facts:** a routine's `enabled_plugins` field can't be set through the API; plugins synced from the claude.ai account do load in cloud sessions (a route ADR 1's user scope rules out); a second repository makes the session start above both clones, so the wiki's settings and sync status are lost; commits are made as `Claude <noreply@anthropic.com>`; nine cloud-only tools are unclassified in `hookjson.py`.
- **GitHub Copilot's cloud agent, compared from its docs:** a plugin from another repository is a documented repo setting there (`.github/copilot/settings.json`), but plugin hooks in its sandbox are contradicted by the docs, hook timeouts fail open, manual-only skills don't work, OAuth MCP servers aren't supported and there are no Gmail or Google Drive connectors. Not a better home for these wikis today.
- **Proton Drive:** the CLI signs in only through a browser (completable on another device) and its refresh tokens work once, so a session stored read-only in the environment lasts one run. Workable routes, both with read access limited to one folder: a password-protected public link read through Proton's SDK without an account (`experimental.authURLAccess`), or the session in a 1Password vault (a service account, its token in the environment) written back after each refresh, with a viewer-only Proton account. A network secret can't carry either: Proton and 1Password decrypt on the machine.

### If the spike passes: what a design must settle

- **Never unguarded.** A wiki opened in an environment without the script, or after a failed setup, has no guard but every connector. Something in the repo itself must notice (a project hook in the wiki's settings that refuses when `CLAUDE_CODE_REMOTE` is `true` and the plugin isn't there, say).
- **Push.** An exception to the guard's first rule when `CLAUDE_CODE_REMOTE` is `true`. Text matching can't hold a push to a `claude/` branch (`git push origin HEAD:main` is one refspec away), so branch protection on the default branch that the owner can't bypass is a prerequisite, if pushes are to stay off it; whether a private repository on a free plan has it needs checking. The settings deny rule can't be conditional, so it would go altogether. This weakens a guard (irreversible harm is why it is guarded, `docs/adr.md`, 3) and must say so in its commit.
- **State and branches.** Each run starts from the default branch, so a run whose branch isn't merged is repeated by the next, and two unmerged branches both change `raw/sync-log.md` and `open-questions.md`. Gmail's `wiki-ingested` label is written at Gmail, so a discarded branch loses those threads silently. Weigh pushing straight to the default branch against this.
- **Starting the skill.** How a scheduled run starts a manual-only skill, if its prompt can't.
- **Setup script.** Where it lives (a file in wiki-tools the user pastes into the environment), what it installs (the plugin, `poppler-utils`, LibreOffice), and how a plugin update reaches a cached snapshot (it is rebuilt when the script changes and after about seven days).
- **Platform.** A way for contracts and `sources.sh due` to say "not available in the cloud" (`platforms` today names operating systems).
- **Cache-held state:** the `ms-teams` folder snapshot (`file-snapshot.sh`'s).
- **Tools and connectors.** Classifying the cloud-only tools in `hookjson.py`; which connectors a task includes (all, by default).
- **Settings.** Reader rules in the wiki's settings rather than the user's; `attribution.sessionUrl` off if the trailer isn't wanted.
- **Auto mode** in place of the user's answer to a prompt.
- **Privacy.** A cloud wiki's content is on GitHub and in an Anthropic-hosted VM. A decision per wiki; a work wiki also needs its organisation to allow cloud sessions.
