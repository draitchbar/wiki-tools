# Proton Drive plan: stay on the CLI, harden the wrapper

Status: **not started**, plan only (2026-11-01).

## Decision
`proton-drive` stays `access: script`: the official `proton-drive` CLI, reached only through `plugins/wiki/sources/proton-drive/read.sh`, with `guard_words: proton-drive` blocking every other use of the CLI. We are not switching to a tools-based contract (`access: tools`, like `onenote`) or to an MCP server.

Why:
- **Read-only.** Proton has no scoped credentials: a signed-in CLI session can upload, move, trash and delete. OneNote can rest read-only on Graph `Notes.Read`; Proton can rest it only on the wrapper's operation allowlist and the guard. `access: tools` requires empty `guard_words`, so the raw CLI would become callable.
- **Roots.** The wrapper refuses paths outside the instance's roots. A generic reader sees the whole drive.
- **List new.** `read.sh new` is one deterministic call. Folder modified times don't move when a file inside changes (confirmed again by googlarz's README, measured 2026-11-01), so a model-driven walk can't prune and would cost one 5–40 KB listing per folder.
- **Cache layout.** Resolving a citation that gives only a file name (`9f8640a`) relies on the wrapper's fixed `<cache>/<path below root>`.
- **Windows.** Both wikis run on Windows; the only MCP server that covers our needs doesn't support it (below).

## Research record: Proton Drive MCP servers (2026-11-01)
All are third-party; Proton doesn't make one.

| Server | Access | Read-only | Remote roots | Windows | Notes |
|---|---|---|---|---|---|
| googlarz/proton-drive-mcp | official CLI | `PROTON_DRIVE_MODE=readonly` | `PROTON_DRIVE_REMOTE_ROOTS` | not supported | `drive_recent_changes since=`, `drive_search modifiedAfter`; walks stop waiting after 25 s (`partial: true`); 18–48 KB of tool descriptions; 3 stars, single maintainer, Linux tested only with a fake CLI |
| 3lgr/proton-drive-mcp | official CLI (fork of googlarz) | no, confirmation prompts only | local paths only | not supported | created 2026-10-12 |
| borealstack/proton-drive-cli-mcp | official CLI | unknown | unknown | unknown | last push 2026-06-12 |
| lucasoishi/proton-mcp | desktop sync folder | yes | the sync folder | likely | equivalent to a `local-folder` instance |
| anyrxo/proton-drive-mcp | desktop sync folder | no | the sync folder | — | last push 2026-03 |
| jorgenclaw/proton-mcp | Proton suite | no | — | — | includes upload and delete tools |

## Work: harden `read.sh`
Things googlarz's README reports about the CLI that `read.sh` doesn't handle yet; not yet seen by us, hence step 0. Each change needs a fake-CLI case in `tests/sources/proton-drive/fake-proton-drive`, `check` lines next to the `proton-drive/*` ones in `tests/run-tests.sh`, and a green `bash tests/run-tests.sh` (CLAUDE.md). Read-only rules and the guard don't change. Size: about 40–60 lines in `read.sh`, as much in the fake and tests, a few lines in SOURCE.md and the README.

0. **Reproduce first** (manual, wiki-tools session, real CLI): download a missing file, an undecryptable one and a Proton Doc, and record exit code and `--json` output; run 3–4 `list --json` calls at once and record the lock message and exit code. Put the results in README "Proton Drive CLI: recorded syntax" and make the fake imitate them. Drop any item below that doesn't reproduce on cli-drive@0.9.0.
1. **Don't trust exit code 0 from `download`.** Today it exits only on a non-zero code, then prints `downloaded to …`; a silently failed item leaves a stale cached copy or nothing. Note the cached file's modified time before the call (`-f remove` replaces it); afterwards require the file to exist and be new or newer, and, if the `--json` output gives per-item results, that the item succeeded. Otherwise refuse with the CLI's message (first 200 characters). Test: the fake's download creates the file in `localFolder` (it only echoes today); a `FAKE_PD_FAIL=silent` mode exits 0 and writes nothing.
2. **Retry `database is locked`.** Parallel Bash calls (several `download`s at once in an ingest or audit) can collide in the CLI's local database. A `run_cli` helper wraps the `list`, `info`, `size` and `download` calls (not the `--help` checks): on failure with the lock message from step 0, wait 1, 2, 4 s and retry; give up after three retries with a clear message. Test: `FAKE_PD_LOCKED=N` fails N times, then succeeds; passes with N=2, refused with N=5.
3. **`list` prints lines, not JSON** (decided 2026-11-01). The CLI returns items in random order, and its JSON is 5–40 KB per folder. `list` runs the output through `nodes` and prints `<f|p|d> <YYYY-MM-DD HH:MM> <bytes> <remote path>`, one line per item, sorted by path (`LC_ALL=C`), folders included as `d`; undecryptable names go to stderr as in `new`, and a changed JSON shape refuses. `info` and `size` stay JSON. Update SOURCE.md (the output paragraph and "use it sparingly"), the fake's canned tree (serve `list` from it, not only in `FAKE_PD_TREE=1`) and the `proton-drive/list*` checks.
4. **Record** the CLI behaviour from step 0 in the README section, and the new `list` format in `read.sh`'s header comment.

## Possible: a faster `new`
The walk lists one folder at a time, about 3 s each. googlarz walks with concurrency 12 (about 21 s per 1,200 files). Running a few `list` calls at once in `read.sh` would cut `new` sharply, but it depends on item 2 (lock retries), and it's awkward in POSIX bash under Git Bash. Decide together with the Python port (CLAUDE.md, "Speed and Python"): measure the walk in step 1 there and fold it in if it dominates.

## Not doing, with triggers to revisit
| Item | Trigger |
|---|---|
| `access: tools` contract with googlarz in read-only mode | googlarz (or another CLI-backed server) supports Windows, is tested live on Linux, and has a track record; then also decide whether `lib-source.sh` lets an `access: tools` type keep `guard_words` so the raw CLI stays blocked. |
| Desktop sync folder as a `local-folder` instance | A machine already syncs Proton Drive locally and the CLI is unavailable or too slow there. Citations would need the `Proton:` prefix kept (an alias in the contract). |
| rclone `protondrive` backend | Never planned; check how far it can be held read-only first. |
