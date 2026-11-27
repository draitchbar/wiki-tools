# Plan: OneNote ingested unattended, without the user's machine

Status: design, 2026-11-27. Researched by three agents (a connector, a script in the cloud VM, an export made elsewhere), merged, reviewed once, then narrowed with the user: the point of running a wiki in the cloud is unattended ingest that doesn't depend on the user's machine. Nothing built, nothing tried live. Indexed in [the roadmap](../roadmap.md).

## The question

The `onenote` source (`plugins/wiki/sources/onenote/SOURCE.md`, `access: tools`) is read through a reader the user's machine supplies (e.g. a PowerShell script around the Microsoft Graph SDK, signed in interactively with delegated `Notes.Read`). How can a scheduled run ingest it while that machine is off? A cloud session ([research](cloud-wikis.md), `plugins/wiki/cloud/SETUP.md`) has no such reader, no interactive sign-in, and an empty `~/.cache` in each VM, where the contract keeps its page snapshots.

## Facts that decide it

1. **No app-only access.** The Graph OneNote API stopped accepting app-only tokens on 2025-03-31 (learn.microsoft.com/graph/integrate-with-onenote). Client credentials, certificates, federated identity and every proxy secret type that fetches tokens itself are app-only, so all are out. Only a **delegated** token (`Notes.Read` + `offline_access`) works, so an unattended reader needs a stored refresh token.
2. **Refresh tokens** last 90 days; a refresh returns a new one and doesn't revoke the old (learn.microsoft.com/entra/identity-platform/refresh-tokens). Conditional Access is evaluated at every refresh, so a tenant's policies may refuse a refresh from a datacenter IP.
3. **The claude.ai Microsoft 365 connector can't read OneNote:** its `read_resource` has no OneNote scheme, and notebooks are binary `.one` packages Graph won't convert (from its tool schemas; not tried live).
4. **A cloud environment's network secrets** are fixed values, changed only by deleting and re-adding them in the UI; none stores and refreshes a delegated token (code.claude.com/docs/en/cloud-environments). A "Body parameter" secret could add a refresh token to the token request, but every token response carries a new refresh token into the VM, readable by the model.
5. **In a cloud session, anything the reader can read, the model can read:** environment variables, files, the setup script's output.

## Options weighed

| Option | Verdict |
|---|---|
| **Claude Code in a GitHub Actions workflow, token kept by a pre-step** | **Chosen** for `onenote` (below). |
| A reader script in the cloud VM, token in an environment variable | Works, but the model can read a refresh token good for all notebooks for up to 90 days; static, so a new sign-in every ~60–80 days; a refresh from Anthropic's IPs may meet Conditional Access. Fallback 1. |
| The same, token as a "Body parameter" network secret | Hides the stored token from `env` and logs, but a session gets a fresh refresh token with one request (fact 4). Fallback 1's better form. |
| A token broker the user hosts (a small Azure Function, refresh token in Key Vault, read-only OneNote GET proxy), its API key a Bearer network secret | No secret ever in the VM; the refresh happens in the user's Azure. Fallback 2. |
| A custom MCP connector the user hosts | Like the broker plus MCP and claude.ai OAuth glue; no suitable server exists. Parked. |
| A mirror exported by the user's machine to a branch | Depends on the user's machine: rejected (the point is not to). It would also put raw notes in git history for good. |
| GitHub Copilot instead of Claude | The Actions benefits come from Actions, not the agent. Copilot CLI can't run the wikis yet ([plan](copilot-wiki-support.md), part B), `onenote` is parked there, and `--allow-all` leaves the guard as the only check (with a fail-open hook timeout). The Copilot coding agent delivers pull requests from its own branch, past `save.sh` and the guard. Later: the workflow below carries over to Copilot CLI unchanged once part B ships. |

## The design

**Split by source.** Cloud routines keep the connector sources (`gmail`, `jira`, `ms-teams`), which work there through the claude.ai connectors. A GitHub Actions workflow on the wiki repo runs `onenote`. Both save to the default branch through `save.sh`; its merge handles an overlap, and the schedules are set apart.

### The workflow (in the wiki repo, `.github/workflows/`)

1. **Token step** (before Claude runs, own process):
   - signs in to Azure through GitHub's OIDC (a federated credential on a managed identity or app that may only read and write one Key Vault secret); nothing long-lived is stored in GitHub;
   - reads the OneNote refresh token from Key Vault, redeems it for an access token (`Notes.Read`, about an hour), and writes the rotated refresh token back, so no new sign-in is ever needed while it runs at least every 90 days;
   - passes on **only the access token**, masked (`::add-mask::`), to the next step.
   The Entra app for OneNote is dedicated: delegated `Notes.Read` + `offline_access` only, never an app with other scopes (a refresh token is bound to user and client, so it can redeem every scope the client was granted). The user seeds the first refresh token once, locally, with authorization code + PKCE (device code is often blocked by Conditional Access).
2. **Cache step:** `actions/cache` restores `~/.cache/wiki-sources/<wiki>/<key>`, so the contract's snapshots persist between runs (kept up to 7 days unused, 10 GB per repo) and List new's edit detection works as locally.
3. **Claude step:** Claude Code headless with the `wiki` plugin and a OneNote reader that takes an access token (PowerShell 7 is preinstalled on Ubuntu runners, so a pwsh reader may run with `Connect-MgGraph -AccessToken`; otherwise a stdlib Python reader), prompt `/wiki:ingest <key> --unattended`. The guard runs as in any wiki session. Claude's credential is an Actions secret (an API key, or a subscription token from `claude setup-token`).
4. **Save:** `save.sh` from the run (the unattended ingest saves at its end). The runner's `origin` is the plain `https://github.com/<owner>/<repo>` that `save.sh` pins; the job token needs `contents: write`, and the ruleset must let that account push to the default branch, not force push.

**Protecting the token step.** Any branch pushed to the wiki repo with a workflow file can request the repo's OIDC token or secrets, and a cloud session's proxy doesn't limit which branches a push updates ([research](cloud-wikis.md)). So the federated credential trusts only the default branch's workflow (subject `repo:<owner>/<repo>:ref:refs/heads/<base>`, or a GitHub environment limited to the default branch), and `.github/` stays a protected path for saves (it already needs the user's permission, `save.py`).

### In wiki-tools

- `plugins/wiki/cloud/` (or a sibling page): the workflow template and its setup page (Entra app, Key Vault, federated credential, the first token, the schedule), linked from `SETUP.md`.
- The reader that takes an access token: a fixed read-only script (the contract's operations), where it lives decided with the reader-plugin pattern ([Teams spike](teams-reader-plugin.md)); tests with a fake Graph (paging over 100 pages, section groups, link targets, resources only from Graph hosts).
- The token step as a small script with tests (fake token endpoint and fake Key Vault): refresh, write-back, masking, an expired or revoked token failing the job with a clear message.
- `docs/adr.md`: the decision (Actions for sources a cloud session can't hold a credential for; why not the alternatives) when built.
- **Separately, now:** `sources.sh` reports `onenote` as available in a cloud session although its reader is a local command; in a cloud session an `access: tools` instance whose reader isn't a connector tool should be reported unavailable (`platform_ok` compares the OS only, `sources.py`).

## Spike: live checks, in order

1. **Tenant:** a refresh of a `Notes.Read` token from a GitHub-hosted runner passes the tenant's Conditional Access, and the user may consent to the dedicated app. If not: a self-hosted runner the tenant trusts, or fallback 2 (the broker refreshes from the user's own Azure).
2. **Headless skill start:** `claude -p "/wiki:ingest <key> --unattended"` starts the manual-only skill, as a routine's prompt does.
3. **The plugin and its guard load on the runner** (the schema at session start, the guard refusing `git push`).
4. **The reader** runs with the access token and passes the contract's Bind tests.
5. **`save.sh` pushes** with the job token under the ruleset; a force push is refused.
6. **OIDC trust:** a workflow on another branch can't get the Azure token.
7. **The cache** carries the snapshots from one run to the next.
8. Whether a subscription token brings the claude.ai connectors to the runner; if it does, the connector sources could move to the same workflow.

## Open questions

- Claude usage and Actions minutes per run on a private repo; the schedule.
- Whether the wiki repo's data passing GitHub's runners is acceptable per wiki (it already passes Anthropic's VMs in the cloud).
- Teams' snapshot loss in cloud sessions has the same cure (the cache) if `ms-teams` moves to the workflow.
