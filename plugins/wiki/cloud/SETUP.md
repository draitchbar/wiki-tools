# Running a wiki in a Claude Code cloud session

A guided setup for opening a wiki at claude.ai/code (web or phone) or running it from a routine (a scheduled cloud task) while the user's machine is off. Written for the agent in a local wiki session that walks the user through it; the user can follow it alone just as well.

**Status, 2026-11-21 (Claude Code 2.1.330):** it works. A spike loaded the plugin, the schema, the sync status and the guard in cloud sessions and ran a scheduled `/wiki:ingest all --unattended` in a real wiki (**What was checked**). It rests on `CLAUDE_CODE_PLUGIN_DIRS`, which Claude Code documents for containers and CI, not for cloud sessions, so a Claude Code update may break it. Several things are still untested (**Still to test**). A cloud session's commits last only once saved to GitHub: with saving turned on (Setup step 6), `/wiki:save` and an unattended ingest save them through the plugin's `save.sh`; its cloud checks are still partly untested. The research behind it: `docs/plans/cloud-wikis.md` in wiki-tools.

## For the agent guiding the setup

- `${CLAUDE_PLUGIN_ROOT}` on this page is the plugin's folder, the parent of the `cloud/` folder this page is in; nothing fills it in here, so write the path out.
- Go through **Is this wiki a fit?** with the user first, then **Setup**, one step at a time; check each step before the next.
- Steps marked **user** are the user's: pushing, creating the GitHub repo, GitHub app access, the save config, and everything in the claude.ai settings. The guard refuses `git push` (saving goes through `save.sh` only), and a session can't change claude.ai settings.
- Fill in the setup script's `REF` with the user, and show the script whole, ready to paste.
- Never put secrets into the wiki or the script. If the user asks about a source this page marks as not available in the cloud, say so and point to **Still to test**.

## How it works

- A cloud session is a fresh Ubuntu VM per session, with the wiki's repository cloned from GitHub into `/home/user/<repo>`. It ignores the plugins a repository's `.claude/settings.json` enables, so the wiki's `enabledPlugins` does nothing there.
- The cloud **environment** brings the plugin instead: its setup script (run as root before Claude Code starts) clones the public wiki-tools repository and copies `plugins/wiki/` to `/opt/wiki-plugin`, and its environment variable `CLAUDE_CODE_PLUGIN_DIRS=/opt/wiki-plugin` loads it, as `--plugin-dir` would. The plugin then shows as `wiki@inline`.
- From there it runs as locally: the guard on every tool call, the schema and the sync status at session start, the `/wiki:*` skills, with `${CLAUDE_PLUGIN_ROOT}` filled in as `/opt/wiki-plugin`.
- The environment caches the setup script's result as a filesystem snapshot when it finishes within about five minutes, and rebuilds it when the script changes and after about seven days.
- With `REF` a branch, the plugin updates itself at the start of each session from the setup script's clone, so a snapshot's plugin is never a week old (**Keeping the plugin current**).
- The wiki's own `.claude/settings.json` (permission rules) applies as long as the wiki is the session's **only** repository. With a second repository attached, the session starts in the folder above both and the wiki's settings and sync status are lost.

## Is this wiki a fit?

1. **Sources.** Run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/sources.sh list` and compare with the table. `sources.sh list` still reports every source as available on Linux, but `sources.sh show <key>` says `this session: cloud` and gives each bound connector tool's cloud name; it reports **Check needed** (and the source stops) while the wiki's committed `.claude/settings.json` lacks a cloud-name line `sources.sh settings` prints.

   | Source type | In a cloud session |
   |---|---|
   | `raw` | Only what is committed: Markdown and text, `raw/ocr/*.txt`. PDFs, Office files and images are gitignored, so they stay local. |
   | `gmail`, `google-drive`, `jira`, `ms-teams` | Through the claude.ai connector, bound locally: `sources.sh settings` gives each rule under the cloud name too (`mcp__Gmail__*`, `mcp__Microsoft_365__*`, `mcp__Atlassian_MCP__*`), and those lines are committed in the wiki's settings (`docs/adr.md`, 25, in wiki-tools); no binding in the cloud. Google Drive's cloud name isn't known yet, so a Drive instance can't run in a cloud session yet (Check says so and stops). Jira's find project and list remote links are unavailable there (their dispatcher is denied under its cloud name). Live checks pending (**Still to test**). Gmail is read-only, so an unsaved run writes nothing at Gmail and the next run repeats those threads. |
   | `proton-files` | No: the reader needs a local sign-in. Options are in the research. |
   | `local-folder`, `onenote` | No: local folders, local sign-in. |
   | `codebase` | No: the clone would be a second repository, and `gh` has no login there. |

   A source that isn't available is skipped by `/wiki:ingest all --unattended` with a note; the spike saw a Proton source fail cleanly because its reader wasn't there.
2. **Privacy.** The wiki's content goes to a private GitHub repository and into Anthropic-hosted VMs. That is the user's decision per wiki. A work wiki also needs its organisation to allow cloud sessions (on Team and Enterprise an Owner turns them on; they aren't available with zero data retention, the HIPAA configuration or customer-managed keys).
3. **What it is for, today.** Reading, querying and researching the wiki from the web or the phone, and checks (`/wiki:sync-status`, `wiki-check.sh`, lint). Ingests run; their commits last only with saving turned on (Setup step 6), otherwise they stay in the VM and are lost with it.

## Setup

1. **user: the wiki on GitHub, private.** Check with `git remote -v`. If there is no remote, the user creates a private repository and pushes from a terminal, e.g. `gh repo create <name> --private --source . --push`. A ruleset against force pushes and branch deletion: `docs/setup.md` in wiki-tools, "Optional: the wiki on GitHub".
2. **user: GitHub access for Claude.** If the Claude GitHub app is installed for selected repositories only, add this one (GitHub, Settings, Applications, Claude, Repository access).
3. **user: a cloud environment** at claude.ai/code (the environment selector, add environment). One environment can serve several wikis.
   - **Name:** e.g. `wikis`.
   - **Network access:** the default. It allows GitHub.
   - **Environment variables:** `CLAUDE_CODE_PLUGIN_DIRS=/opt/wiki-plugin`
   - **Setup script:** the script below, with `REF` set. A branch (`main`) is followed: each new session updates the plugin to the branch's latest commit (**Keeping the plugin current**). A commit pins it (the user gets the current one with `git ls-remote https://github.com/draitchbar/wiki-tools refs/heads/main`); to update a pinned plugin, change `REF`: a changed script rebuilds the snapshot.
4. **user: a first session** at claude.ai/code, with this wiki as the only repository and the new environment. Ask Claude there to check, and stop if any check fails:
   - the session started with the wiki schema (`wiki-conventions`, `wiki-layout`) and the sync status;
   - `/wiki:sync-status` runs;
   - `eval "git push --dry-run origin HEAD"` is refused with "wiki guard: git push is not allowed in wiki sessions". **If not, the plugin didn't load and the session is unguarded: stop using it.**
   - `bash /opt/wiki-plugin/scripts/wiki-check.sh` passes, except for rules that name a reader by a path on the user's machine (expected: that reader isn't in the cloud);
   - which plugin it runs: Read `/opt/wiki-plugin/.wiki-tools-ref` (the commit the setup script checked out, or the one the session updated to: with `REF=main` the current wiki-tools `main`). The script's own output isn't shown to the session; the update's is, as one line in the session start context.
   - GitHub's tools (`mcp__github__*`, among them `push_files`) are refused by the guard itself. A cloud session has every connector of the account, in auto mode, and nothing yet denies the write tools of connectors no source uses (Google Calendar, Meetings, Claude Docs, Claude Data): add deny rules for those you don't want, until the roadmap's "Connector tools opt-in" is built.
5. **user, optional: a routine** at claude.ai/code/routines: this wiki as its repository, the environment, only the connectors the wiki's sources need (none for a `raw`-only wiki), the prompt `/wiki:ingest all --unattended`, a schedule of hourly or slower. A routine's prompt starts the manual-only `/wiki:ingest`. Each run is a session in the user's history; its results are saved only with step 6.
6. **user, recommended: turn on saving**, locally, as `/wiki:init`'s **Turning saving on** says (`${CLAUDE_PLUGIN_ROOT}/skills/init/SKILL.md`; wiki-tools `docs/setup.md`, "Optional: saving from Claude"): the ruleset on the default branch (a private repository needs a paid GitHub plan for it to be enforced), the two lines in `.gitignore` and `.gitattributes`, and the committed and pushed `.claude/settings.wiki.json`. In the cloud:
   - `url` must be the plain `https://github.com/<owner>/<repo>` form: `save.sh` refuses unless the session's `origin` is the pinned URL (seen 2026-11-25: `origin` is that form, and the session's proxy supplies git's and `gh`'s credentials).
   - A session saves to the default branch, not to its own `claude/…` branch: `/wiki:save` merges the default branch in and pushes there. An unattended run updates at its start and saves at its end; changes that need the user's permission (anything outside `wiki/`, `raw/`, `outputs/`, `open-questions.md`, and control files such as `CLAUDE.md` anywhere) go to a `claude/wiki-<12 hex>` branch with a draft pull request: the user merges it, then deletes the branch; until then the next unattended run stops (after a squash merge, until the branch is deleted).
   - Commits made in the cloud carry `Claude <noreply@anthropic.com>` and a `Claude-Session:` trailer (**Still to test**, git identity).
   - The cloud environment's own Stop hook asks, after a save, to push the session's branch ("There are N unpushed commit(s) on branch 'claude/…'. Please push…"). That is expected: decline it. Session branches are never pushed (the guard refuses `git push`); only `save.sh` pushes, to the default branch or a holding branch.
   - Check in a session: `bash /opt/wiki-plugin/scripts/wiki-check.sh` says `saving is on`, and `/wiki:save --check` names what a save would push.

### The setup script

```bash
#!/bin/bash
# wiki-tools: puts the wiki plugin at /opt/wiki-plugin for
# CLAUDE_CODE_PLUGIN_DIRS=/opt/wiki-plugin. Fails loudly: a session
# without the plugin would be unguarded.
set -eu
REF=main   # or a commit, for the same plugin every time
SRC=/opt/wiki-tools
DEST=/opt/wiki-plugin
rm -rf "$SRC" "$DEST"
git clone -q https://github.com/draitchbar/wiki-tools.git "$SRC"
git -C "$SRC" checkout -q "$REF"
cp -r "$SRC/plugins/wiki" "$DEST"
test -f "$DEST/.claude-plugin/plugin.json"
test -f "$DEST/hooks/hooks.json"
git -C "$SRC" rev-parse HEAD > "$DEST/.wiki-tools-ref"
# For the plugin's self-update: the clone, and whether REF is a branch
# (followed) or a commit (pinned).
KIND=commit
if git -C "$SRC" symbolic-ref -q HEAD >/dev/null; then KIND=branch; fi
printf 'clone=%s\nkind=%s\n' "$SRC" "$KIND" > "$DEST/.wiki-tools-setup"
echo "wiki plugin at $DEST from wiki-tools $(git -C "$SRC" rev-parse --short HEAD)"
```

### Keeping the plugin current

The snapshot keeps the plugin of the day it was built, for up to about seven days. So the plugin updates itself: its first `SessionStart` hook, `${CLAUDE_PLUGIN_ROOT}/scripts/cloud-update.sh` (at startup, not on resume or `/clear`), acts only in a cloud session (`CLAUDE_CODE_REMOTE=true`), only in a plugin copy the setup script made (it has `.wiki-tools-ref`), and only when the setup script's clone is there (`clone=` in `/opt/wiki-plugin/.wiki-tools-setup`, else `/opt/wiki-tools`).

- **A branch** (`kind=branch` in `.wiki-tools-setup`; an environment set up before that file existed: the clone is on a branch): it fetches the branch from GitHub, resets the clone to it, copies `plugins/wiki/` over `/opt/wiki-plugin` in place and writes the commit to `.wiki-tools-ref`. The session start then shows `wiki plugin updated <old> -> <new>` (short commits); nothing when the plugin is already current.
- **A commit** (`kind=commit`, or a detached clone): pinned, nothing happens.
- **Fails open, fast:** the fetch stops after 15 s; any failure leaves the snapshot's plugin, says `wiki plugin: update check failed; this session runs the snapshot's <old>` and the session goes on. It never deletes the plugin folder first (the guard runs on every tool call), so files deleted upstream linger until the snapshot is rebuilt; nothing loads them.
- **Limit:** in the session where the update happens, the plugin's other `SessionStart` hooks (the schema, the sync status) start alongside it and may run the old version, and Claude Code has already read the old `hooks.json`; from the first tool call on, the guard and the skills are the new version.
- **Trust:** every cloud session runs the latest commit of the setup script's branch, the same trust as `REF=main` without the week's delay: a bad commit on that branch reaches the next cloud session at once. Pin a commit to rule that out, and update it by hand.

Decision: `docs/adr.md`, 27, in wiki-tools.

## What was checked

A spike on 2026-11-21, Claude Code 2.1.330, in an environment with this setup (its script also tried other ways of fetching the plugin), in a throwaway session and in a real wiki; results in `tests/live/results.md` in wiki-tools.

- The setup script took about 10 s; a later session reused the snapshot ("Setup script cached from previous run").
- A public repository outside the session can be cloned (`git clone`, `raw.githubusercontent.com`, and `claude plugin marketplace add`); in a session, `codeload` archives get 403.
- With the variable set, the plugin loaded as `wiki@inline`: the model-invocable `wiki:` skills, both schema files (about 1,500 and 1,300 words), the sync status in a wiki, `${CLAUDE_PLUGIN_ROOT}` filled in.
- The guard refused `git push` (plain and through `eval`), writing `.claude/settings.json`, and any command naming `claude`; it let an ordinary Write through. `sources.sh list` and `due` and `wiki-check.sh` ran.
- A routine whose prompt is `/wiki:lint` or `/wiki:ingest all --unattended` started the skill. The unattended ingest skipped a Gmail source (Check needed), failed a Proton source cleanly (reader missing), wrote and committed nothing, and sent a push notification with its summary.
- Repo-declared plugins and the routines API's `enabled_plugins` field don't bring a plugin in; a session can't start a nested `claude` to test one (auto mode refuses it).

## Still to test

- **The plugin's self-update** (built 2026-11-26, **Keeping the plugin current**): in a session of an environment with `REF=main`, `.wiki-tools-ref` shows the current wiki-tools `main`, not the snapshot's commit, and the session start shows the update line once; the hook may write `/opt/wiki-plugin` and fetch through the proxy.
- **A failing setup script.** The script exits non-zero on purpose. Untested: whether the session then fails to start, or starts without the plugin and so unguarded. A project hook in the wiki that refuses everything when `CLAUDE_CODE_REMOTE` is `true` and the plugin is missing would close the gap; not built.
- **Saving results** (built 2026-11, `save.sh`, Setup step 6; decision: `docs/adr.md`, 26, in wiki-tools). Checked in a cloud session (2026-11-25): `origin`'s URL form, the proxy's git settings, the shallow clone and the session's own branch, which the script is built for. Still to check live: a save to the default branch through the proxy, and whether the ruleset stops a force push from the proxy's account; `gh api` through the proxy for the ruleset check and the draft pull request (and whether `curl` or Python reach GitHub's API too); whether the guard's permission prompt for `save.sh --allow` appears in auto mode and in the web UI (if not, interactive cloud sessions need the holding branch too); and whether a routine saves without a prompt that stalls it. The GitHub connector's tools (`push_files`, `create_pull_request`, `merge_pull_request`) stay refused by the guard, as do `gh api` and `gh pr`.
- **Connector sources.** Gmail, Microsoft 365 (Teams) and Jira through claude.ai connectors in a cloud session or routine: built (2026-11): the committed settings carry both names from `${CLAUDE_PLUGIN_ROOT}/sources/connectors.md`, and Check falls back to the cloud name (decision and reasons: `docs/adr.md`, 25, in wiki-tools). The live checks are pending: a cloud-name deny holds in a session and in an auto-mode routine; each connector's short tool names match on both surfaces (the cloud side was compared on 2026-11-25); no settings warning for an allow rule naming a tool absent locally; a locally bound wiki ingests in a cloud routine. Atlassian connects since 2026-11-24. A plugin synced from the claude.ai account failed to reach its own MCP server through the session's network proxy.
- **Typing skills** (`/wiki:ingest`, `/wiki:clarify` and the other manual-only skills) in the web UI and on the phone.
- **Permission prompts.** Routines run in auto mode; the wikis rely on the user's answer in a few places (e.g. the reader binding).
- **Git identity.** Commits are made as `Claude <noreply@anthropic.com>`, not the user. Untested: `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME` and `GIT_COMMITTER_EMAIL` as environment variables.
- **Cloud-only tools.** The guard doesn't classify `ListConnectors`, `ListPlugins`, `ListSkills`, `SearchMcpRegistry`, `SearchPlugins`, `SearchSkills`, `SuggestConnectors`, `SuggestPluginInstall` and `SuggestSkills`, so it refuses them (fail closed).
- **Sources and the cloud.** The contracts' `platforms` don't know the cloud (`sources.sh show` does); source files that name a reader by a local path fail there.
- **Reading fetched files.** `pdftotext` and LibreOffice aren't in the VM; the setup script could install `poppler-utils` and `libreoffice`.
- **Proton Drive.** Researched, not built: a password-protected public link read through Proton's SDK without an account, or the reader's session kept in a 1Password vault (a service account) and written back after each refresh, with a viewer-only Proton account. A session stored read-only in an environment variable lasts one run at most, since Proton's refresh tokens work once.
