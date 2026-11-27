# Plan: the remaining live checks for wikis in a cloud session

Status: 2026-11-27. Wikis run in Claude Code cloud sessions and routines: the plugin comes from the environment (`docs/adr.md`, 20) and updates itself (19), connector rules carry both names (17), and saving pushes through `save.sh` (18). The guided setup and its user-facing "Still to test" are in `plugins/wiki/cloud/SETUP.md`. This page is only what is left to check live, with how each is run and when it passes. Indexed in [the roadmap](../roadmap.md).

Record each run in `tests/live/results.md`, "Cloud sessions", with the Claude Code version, and tick it off here; a check that fails gets an issue, and a decision it changes is amended in `docs/adr.md`. When every check is done or moved to an issue, this page is deleted.

Most checks need the user: a new session or a routine started at claude.ai/code, or a resume. A cloud session can run the in-session checks itself.

## Setup and the guard (20, 19)

1. **A failing setup script.** An environment whose setup script exits 1. Passes if the session doesn't start, or starts with the plugin's absence obvious and every tool call refused. If it starts unguarded, build the decision's open item (a project hook in the wiki that refuses everything when `CLAUDE_CODE_REMOTE` is `true` and the plugin isn't loaded) and check again.
2. **Self-update from a stale snapshot.** After a commit lands on wiki-tools `main`, a new session in an environment whose snapshot is older. Passes if `/opt/wiki-tools/.git/refs/heads/main` (or `packed-refs`) is the new `main`, the session start shows `wiki plugin updated <old> -> <new>` once, and `/opt/wiki-tools/.git/logs/HEAD` has a merge entry after the clone. (2026-11-27: a fresh clone was already current, so nothing was updated and no line printed, as designed.) If the session shows a fresh clone instead, the snapshot was rebuilt: try again later.
3. **Resume.** The same session resumed after it went idle: no second update line when `main` hasn't moved; one when it has.
4. **Skills read at startup.** A skill added or removed by an update appears or disappears only from the next session; a changed skill body is used at once.

## Saving (18)

5. **Force push.** With the ruleset on the default branch and no bypass actors, a force push from the session's proxy account is refused. Run with a throwaway wiki only.
6. **The draft pull request.** An unattended save of a change that needs permission opens a draft pull request through `gh api -X POST …/pulls` via the proxy.
7. **The API past the guard.** Whether `curl` or Python reach GitHub's API from a session (the guard's text-matching limit). In auto mode Claude Code's classifier refused a read-only `curl` first (2026-11-27), so run it in a session in default mode, read-only, against the wiki's own repository.
8. **Prompt with an allow rule.** The guard's "ask" reply for `save.sh --allow` still prompts when `settings.local.json` has a matching allow rule.
9. **A routine saves.** A routine's `/wiki:ingest <key> --unattended` updates at its start and saves at its end with no prompt that stalls it; a change needing permission goes to a holding branch with a draft pull request; the next run stops while that branch is there.

## Connectors (17)

10. **Deny in a routine.** A cloud-name deny rule in the committed `settings.json` holds in an auto-mode routine. (2026-11-27, in a session: every tool the wiki denies under its cloud name was missing from the tool list.)
11. **Short names, local side.** Each pair's short tool names in `plugins/wiki/sources/connectors.md` match, compared in both directions: the cloud side was compared 2026-11-25 and again 2026-11-27; the local tool lists are still to compare.
12. **No settings warning** locally for an allow rule naming a tool that exists only in the cloud.
13. **End to end.** A wiki bound locally ingests each connector source in a cloud routine, with no stalled prompt and a save.
14. **Google Drive's cloud name,** once the connector is attached in a cloud session; then its pair is added by pull request.

## Sessions and routines

15. **Typing skills on the phone:** `/wiki:sync-status`, `/wiki:ingest <key>`. (The web UI ran `/wiki:ingest` and `/wiki:save`, 2026-11-27.)
16. **Permission prompts in a routine:** what happens where a skill relies on the user's answer (e.g. the reader binding, 11) when nobody can answer.
17. **Git identity.** `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME` and `GIT_COMMITTER_EMAIL` set as the environment's variables make the session's commits carry the user's identity. (Today they are `Claude <noreply@anthropic.com>` from the VM's `/root/.gitconfig`; a merge made with `--no-edit` has no `Claude-Session:` trailer.)
18. **Reading fetched files.** `pdftotext` and LibreOffice are in the VM (2026-11-27); an ingest reads a fetched PDF and an Office file with them.

## Not checks

Open work found by the checks, tracked in the roadmap item and issues rather than here: classifying the cloud-only tools in the guard; `platforms` and `sources.sh` in the cloud (a source with a local reader is reported available); the `ms-teams` folder snapshot lost with each VM; two machines ingesting the same source; the environment's Stop hook asking to push the session branch; Proton Drive (routes in `SETUP.md`); OneNote ([plan](onenote-cloud.md)).
