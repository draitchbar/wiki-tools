# wiki-tools

Shared tooling for my Karpathy-style LLM wikis (udbygning, carleasing), used from Claude Code on both Linux and Windows.

It is two things in one repo:

1. **A local-directory plugin marketplace** with one plugin, `wiki`, containing:
   - skills `/wiki:ingest`, `/wiki:sync-status`, `/wiki:commit-themes`, `/wiki:lint` and `/wiki:audit`;
   - guard hooks that block `git push`, keep Proton Drive read-only and protect the guard machinery itself;
   - a SessionStart hook that reports how stale each source in `raw/sync-log.md` is.
2. **The shared wiki schema**, imported by each wiki's CLAUDE.md:
   - `schema/wiki-conventions.md`: universal rules (both wikis);
   - `schema/wiki-layout.md`: raw/wiki layout, frontmatter, ingest workflow (udbygning).

The plugin is **enabled per wiki** (in each wiki's `.claude/settings.json`), never at user scope. So the guards apply only in wiki sessions.

Design and rationale: `~/wiki-tier1-implementation-plan.md` (revision 2).

## Layout

```
.claude-plugin/marketplace.json   marketplace "wiki-tools"
schema/                           shared CLAUDE.md content (@-imported)
plugins/wiki/
  skills/{ingest,sync-status,commit-themes,lint,audit}/SKILL.md
  hooks/hooks.json                PreToolUse guards + SessionStart status
  scripts/
    lib-hookjson.sh               jq-free hook-input parsing (fails closed)
    block-push.sh                 blocks git push
    guard.sh                      Proton/guard protection (Bash + Write/Edit)
    sync-status.sh                staleness report from raw/sync-log.md
    pd-read.sh                    read-only Proton Drive wrapper
    ocr.sh                        ocrmypdf wrapper (Linux)
    lint.sh                       deterministic wiki checks for /wiki:lint (read-only)
templates/project-settings.json   starting point for a wiki's .claude/settings.json
tests/                            guard fixtures, fake proton-drive, lint fixture wiki, run-tests.sh
docs/kfchou-security-review.md    review of kfchou/wiki-skills (inspiration for lint/audit)
```

## Setup per machine

The clone path **must be `~/src/wiki-tools`** on every machine. The skills, the guard's exception and the wikis' `allowed-tools` use that literal path.

| | Linux | Windows |
|---|---|---|
| Prerequisites | git, bash | Git for Windows (Git Bash); Claude Code runs hooks in Git Bash |
| Proton Drive CLI | `~/.local/bin/proton-drive` from [proton.me/download/drive/cli](https://proton.me/download/drive/cli/index.html) | Windows build on PATH; check `proton-drive version` in Git Bash |
| OCR | `sudo apt install ocrmypdf tesseract-ocr-dan` | none; scans are read as page images |

```bash
git clone git@github.com:draitchbar/wiki-tools.git ~/src/wiki-tools
bash ~/src/wiki-tools/tests/run-tests.sh          # must end "0 failed"
claude plugin marketplace add ~/src/wiki-tools     # registers the marketplace only
proton-drive auth login                            # by hand; session goes to the OS keychain
```

Don't install or enable the plugin at user scope. Each wiki enables it in its own committed `.claude/settings.json` (see `templates/project-settings.json`).

## Setting up a wiki

1. Create the folder (e.g. `mkdir ~/wikis/<name>`) and `cd` into it.
2. `claude plugin install wiki@wiki-tools --scope project`. This enables the plugin for this folder only, in `.claude/settings.json`.
3. Start `claude` and run `/wiki:init <what the wiki is for>`.

`/wiki:init` works in three modes:
- **New** (empty folder): grills you on scope, researches the domain, shows the full plan (CLAUDE.md, page types and templates, sources) and creates the raw/wiki layout after your go.
- **Adopt** (folder with content): the same, plus a move table that brings existing notes into `wiki/` (with `git mv` and frontmatter) and source files into `raw/`.
- **Check** (already set up): runs `scripts/wiki-check.sh` and reports what's missing.

It ends with a guide for the steps only you can do, because the guard blocks Claude from them: pasting `.claude/settings.json` (from `templates/project-settings.json`) and `.claude/proton-roots`, committing those two, restarting `claude` and approving the shared-schema imports. Setting up the NAS remote and pushing is also yours.

Sources start at `last_checked_<source>: never`. The first `/wiki:ingest` of each source checks it, asks for a starting point and reviews the data model (folders, page types, templates) against the wiki's purpose.

The shared starting template for people and organisations is `templates/pages/entity.md`; every other page type is designed per wiki by `/wiki:init`.

## Maintenance

Edit this repo in a Claude session opened in `~/src/wiki-tools`. The `wiki` plugin isn't enabled here, so the guards don't get in the way.

1. Change scripts or hooks, adding or adjusting fixtures in `tests/fixtures/<script>/<pass|block>-<case>.json`.
2. `bash tests/run-tests.sh` must pass.
3. Review the diff, commit, push.
4. On the other machine: `git pull`, run the tests, then start a new wiki session or run `/reload-plugins`.

## Proton Drive CLI: recorded syntax (plan step 5.0)

`pd-read.sh` has no version pin. On every call it checks that the CLI's help still shows the syntax below (`check_syntax` in the script), and refuses if it doesn't. If that happens after a CLI update: re-run these commands, paste the new output here, review `pd-read.sh` against it, update `check_syntax` and `tests/fake-proton-drive`, and run the tests.

```
$ proton-drive version
Proton Drive CLI cli-drive@0.9.0+75612299
Proton Drive SDK js@0.22.2+75612299
You are running the latest version.

$ proton-drive filesystem --help
Usage:
    filesystem list [-t TYPE] path
    filesystem info path
    filesystem size path
    filesystem create-folder parentPath name
    filesystem upload [-f STRATEGY] [-d STRATEGY] [-t] localPath... parentPath
    filesystem download [-f STRATEGY] [-d STRATEGY] path... localFolder
    filesystem rename path newName
    filesystem copy [-n NAME] sourcePath... targetParentPath
    filesystem move sourcePath... targetParentPath
    filesystem trash path...
    filesystem restore path...
    filesystem delete path...
    filesystem empty-trash

General options:
    -h|--help: Show extended help for a command (example fs upload --help)
    -j|--json: Output in JSON format
    -v|--verbose: Enable verbose output

Any short names are supported (as long as they are unique):
    filesystem upload -> fs up
    sharing invite -> s inv
Command not found: filesystem --help

$ proton-drive filesystem download --help
Usage:
    filesystem download [-f STRATEGY] [-d STRATEGY] path... localFolder

Downloads files and folders. It prompts for conflict resolution unless a
strategy option is set. Proton Docs or Sheets will be skipped.

Options:
    -f, --file-conflict-strategy STRATEGY
                             Conflict strategy applied to files. Values:
                             * rename: Add a unique suffix to the name.
                             * remove: Delete the local file or folder and
                             download the remote copy.
                             * skip: Skip the conflicting file or folder.
    -d, --folder-conflict-strategy STRATEGY
                             Conflict strategy applied to folders. Values:
                             * merge: Merge folder contents.
                             * rename: Add a unique suffix to the name.
                             * remove: Delete the local file or folder and
                             download the remote copy.
                             * skip: Skip the conflicting file or folder.

Remote paths:
    Posix paths are always used, regardless of the host OS.
    Node names are used for paths if available. When name cannot be decrypted
    or conflicts with other node(s), node UIDs can be used instead.
    Escape / in node names with a backslash.

    Examples:
    - /my-files/folder/file.txt
    - /my-files/folder/foo\/bar
    - /shared-with-me/NODE-UID/file.txt

$ proton-drive filesystem list --help
Usage:
    filesystem list [-t TYPE] path

Use / to list top-level sections. Your root folder is /my-files.

Options:
    -t, --type TYPE          Type of the node to filter by. Values: file,
                             folder, album, photo.

Remote paths:
    Posix paths are always used, regardless of the host OS.
    Node names are used for paths if available. When name cannot be decrypted
    or conflicts with other node(s), node UIDs can be used instead.
    Escape / in node names with a backslash.

    Examples:
    - /my-files/folder/file.txt
    - /my-files/folder/foo\/bar
    - /shared-with-me/NODE-UID/file.txt

$ proton-drive filesystem info --help
Usage:
    filesystem info path

Shows full node metadata including latest revision details.

Remote paths:
    Posix paths are always used, regardless of the host OS.
    Node names are used for paths if available. When name cannot be decrypted
    or conflicts with other node(s), node UIDs can be used instead.
    Escape / in node names with a backslash.

    Examples:
    - /my-files/folder/file.txt
    - /my-files/folder/foo\/bar
    - /shared-with-me/NODE-UID/file.txt
```

Recorded 16.10.2026 on Linux (linux/x64-baseline build). Notes for `pd-read.sh`:
- `download` prompts on conflicts unless `-f`/`-d` is set, so the wrapper must always pass a strategy (a prompt would hang a Claude Bash call).
- `download` accepts folders as well as files; the wrapper checks the node type with `info` first to stay single-file.
- **Proton Docs and Sheets are skipped by `download`.** Native Docs/Sheets must be exported by hand (Docs → .md, Sheets → .csv) and uploaded next to the originals.
- `filesystem --help` prints the usage but also reports `Command not found: filesystem --help`; that's cosmetic.


## Lint and audit

`/wiki:lint` and `/wiki:audit` reimplement ideas from [kfchou/wiki-skills](https://github.com/kfchou/wiki-skills) (MIT) on our own schema. That plugin isn't installed: it requires its own wiki layout, and its optional cross-model audit sends wiki content to OpenAI or Google. See `docs/kfchou-security-review.md`.

- **`/wiki:lint`:** `lint.sh` runs the structural checks (frontmatter, broken links, orphans, index coverage, dates, stale pages, `status_as_of`). Then one subagent per `wiki/` folder checks for contradictions, VAT ambiguities, superseded statements and missing cross-references. The report goes to `outputs/lint-YYYY-MM-DD.md`, and fixes are only offered.
- **`/wiki:audit <page>`:** extracts every checkable claim, then runs one subagent per cited source (Gmail via `get_thread`, Proton via `pd-read.sh`, local files, URLs) to verify it against the source wording. The report goes to `outputs/audit-<slug>-YYYY-MM-DD.md`, and fixes are only offered.

## Guard design and known limits

- **Guardrail, not a security boundary.** The guards match command text. They reliably stop accidental or straightforward misuse, but a deliberately obfuscated command could get through. Anything you run by hand is unaffected. If a Proton change slips through, use Proton's Trash and version history.
- **Blocked in wiki sessions (Bash):** commands containing `proton-drive`, the plugin's `scripts`/`hooks` paths, `hooks.json`, `proton-roots`, `.claude/settings`, `.claude/plugins/`, `claude plugin` or `disableAllHooks`.
  - **Single exception:** a plain `bash <...>/src/wiki-tools/plugins/wiki/scripts/<pd-read|ocr|sync-status|lint>.sh <args>`, with no `; & | < > $` or backticks.
- **Blocked in wiki sessions (Write/Edit):** the same protected paths, plus non-Markdown content containing `proton-drive`.
- **Fails closed:** unparseable hook input is refused.
- **Known false positives:**
  - A commit message containing "push", or mentioning `proton-roots` or `hooks.json`, is blocked. Rephrase the message.
  - `git add .claude/settings.json` in a wiki is blocked. Commit `.claude/` files yourself.
  - `cat .claude/settings.json` via Bash is blocked. Claude's Read tool still works.
- **Proton outside the wikis:** calls from other directories are unguarded, by design.

## Known issues

- **No OCR on Windows (deliberately out of scope for now).** `ocr.sh` needs `ocrmypdf` and Tesseract's Danish data, which are installed on Linux only.
  - **Normal case:** OCR scanned PDFs on Linux. The text is committed as `raw/ocr/<file>.txt`, so Windows reads it after `git pull`.
  - **A new scan ingested first on Windows:** `ocr.sh` exits with "ocrmypdf not installed", and `/wiki:ingest` falls back to Claude reading the PDF pages as images. That uses more tokens and leaves no `raw/ocr/` text. Re-run the ingest of that file on Linux to produce it.
  - **If Windows OCR is needed later:**
    - *Native:* Tesseract (UB Mannheim installer, with Danish language data), Ghostscript and `pip install ocrmypdf`, all on PATH. `ocr.sh` should then work unchanged from Git Bash. Untested.
    - *WSL:* `apt install ocrmypdf tesseract-ocr-dan` inside WSL, but `ocr.sh` would need to call `wsl ocrmypdf …`.

## Open checks (plan step 9)

- **Plugin loading:** does `enabledPlugins` in a wiki's project settings load the plugin, with the marketplace registered only at user scope? If Claude Code asks for an install, run `claude plugin install wiki@wiki-tools --scope project` once per machine and note it here.
- **Imports on Windows:** do `@~/src/wiki-tools/...` imports resolve on Windows?
- **Skill injections:** do `` !`…` `` injections in skills pass the guard? They run `sync-status.sh` through an absolute path, which the exception allows.
