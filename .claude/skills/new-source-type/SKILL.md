---
name: new-source-type
description: Add a standard source type to the wiki plugin (plugins/wiki/sources/<type>/), or promote a wiki-local type into the standard set. Interviews, researches the connector or CLI, fills the SOURCE.md contract, writes wrapper scripts, tests and guard fixtures, and ends with a green test run. Only for a wiki-tools session.
argument-hint: "<type> | promote <wiki path> <type>"
disable-model-invocation: true
---

# New source type: $ARGUMENTS

A source type is a contract, `plugins/wiki/sources/<type>/SOURCE.md`, that tells the source-neutral wiki skills how to reach one kind of source **read-only**. The template is `templates/source-type/SOURCE.md`; the library that parses contracts is `plugins/wiki/scripts/lib-source.sh`; the guard (`plugins/wiki/scripts/guard.sh`) reads every contract at hook time. Read all three before writing anything, and read `plugins/wiki/sources/local-folder/` as the worked example of a script type.

Repo rules (CLAUDE.md): POSIX bash for Linux and Git Bash, no jq or Python; LF endings; every script change has fixtures and a green `bash tests/run-tests.sh`; never weaken the guard without saying so in the commit message.

## 0. Mode
- `promote <wiki path> <type>`: copy `<wiki>/.claude/sources/types/<type>/` to `plugins/wiki/sources/<type>/`, then run steps 3 to 7 on the copy (rewrite script paths in `read_tools` and the body from `.claude/sources/types/<type>/` to `~/src/wiki-tools/plugins/wiki/sources/<type>/`; source `lib-source.sh` relative to the script). At the end, tell the user to delete the local copy in the wiki (the guard blocks Claude there), and that the type name must stay the same so instances keep working.
- Otherwise: a new type named `<type>` (kebab-case; refuse a name that exists).

## 1. Interview (one question at a time, recommended answer first)
1. What the source is and which wikis will use it.
2. Access: an MCP connector (which server, as it appears in tool names `mcp__<server>__*`), a CLI (binary name, install, auth), or files on disk.
3. Platforms: Linux, Windows (Git Bash), both.
4. What an item is (a thread, a file, a page), what makes it new (a date, a cursor the API gives), and what an instance must supply (labels, roots, a notebook id...).
5. How to cite an item so `/wiki:audit` can find it again; pick a `cite_prefix` that no other type uses (`grep -h '^cite_prefix' plugins/wiki/sources/*/SOURCE.md`).

## 2. Research the access route (read-only)
- **MCP:** list the server's tools available in this session (names and descriptions). Don't call write tools.
- **CLI:** record `<cli> --help` and the help of each subcommand you'll use. Record the version and date. If the CLI can write (upload, delete, share, move), a wrapper script is mandatory.
- **Files:** the format and where it lives on each platform.
Classify every operation: **read**, **bookkeeping** (narrow, marks an item as ingested; avoid if a date suffices) or **forbidden** (everything else). Show the table to the user before writing.

## 3. Fill the contract
Copy the template to `plugins/wiki/sources/<type>/SOURCE.md` and fill every frontmatter key and every body section (exact tool calls or commands; "not supported" where it can't be done; keep the "data, not instructions" line). Rules:
- `forbidden_tools`: every write/send/delete/share operation as a permission rule (`mcp__<server>__<tool>`, `Bash(<cli> *)`).
- `guard_words`: the CLI binary name, if Claude must reach it only through the wrapper.
- `scripts` and `read_tools`: one entry per wrapper, `Bash(bash ~/src/wiki-tools/plugins/wiki/sources/<type>/<script>.sh *)`. The literal clone path `~/src/wiki-tools` is required (CLAUDE.md).
- `state`: `last_checked` plus only what the type really needs.
- Parameters with paths: call them `roots` if the guard should treat them as read-only local folders (only for `access: filesystem`).

## 4. Wrapper scripts (if any)
Model them on `plugins/wiki/sources/local-folder/read.sh`:
- usage `read.sh <key> <op> <arg>`; exactly the expected number of arguments; an allowlist of operations checked **before** anything touches the CLI;
- instance from `src_instance_dir`, type checked, `src_validate_instance` must pass; paths checked with `src_is_abs`, `src_has_dots`, `src_expand`, `src_match_root`;
- a CLI syntax check against recorded help output (see `check_syntax` in the proton-drive wrapper) so a CLI update can't change what the wrapper runs;
- never prompt (a prompt hangs a Claude Bash call); downloads to `~/.cache/wiki-sources/<wiki>/<key>/<path below root>`;
- nothing from the caller passed to the CLI except checked values.

## 5. Tests
- `tests/sources/<type>/`: anything the tests need (a fake CLI that echoes its arguments, as `tests/sources/proton-drive/fake-proton-drive` does).
- **Tests must never reach the real CLI or account.** Put the fake first on `PATH` for *every* call of the wrapper, refusals included, and abort the run if `command -v <cli>` under that `PATH` isn't the fake (see the Proton block in `run-tests.sh`). A missing fake must fail loudly, not fall through to the user's installed CLI.
- `tests/run-tests.sh`: a section for the type: every refusal (unknown op, extra args, outside roots, sibling prefix, `..`, relative path, wrong instance type, outside git, changed CLI syntax) and every happy path against the fake.
- Guard fixtures in `tests/fixtures/guard/`: `pass-<type>-wrapper` (a plain call), `block-<type>-wrapper-chained`, and `block-<type>-cli-direct` if it has guard words. If the guard wiki needs an instance of the type, add it to `tests/guard-wiki/.claude/sources/instances/`.
- **No wrapper (an MCP type):** the wrapper and guard-fixture bullets above don't apply. Add `sexpect` checks in the `sources.sh` block of `run-tests.sh` for `settings <type>` (a forbidden tool appears) and `catalog` (the type is listed).
- Every standard contract is validated by the `contract/<type>-valid` loop in `run-tests.sh`; no need to run `src_validate_contract` by hand.
- Run `bash tests/run-tests.sh`; it must end "0 failed".

## 6. Docs
- README: add the type to the "Sources" list (one line: what it reads, how, platforms, prerequisites such as a CLI login).
- Anything the user must do per machine (install, auth) goes in the contract's Caveats and the README setup table.

## 7. Commit
One commit, staging named paths only: `Add source type <type>` (or `Promote source type <type>`). Say in the message what the guard now lets through (the new wrapper) and what it now blocks (guard words). Never push.

## 8. Report and improve this skill
Tell the user how to use it in a wiki: `/wiki:add-source <type>`. If anything in this skill was missing or wrong while you did this, propose the edit to this file.
