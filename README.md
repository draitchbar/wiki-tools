# wiki-tools

Shared tooling for my Karpathy-style LLM wikis (udbygning, carleasing), used from Claude Code on both Linux and Windows.

It is two things in one repo:

1. **A local-directory plugin marketplace** with one plugin, `wiki`, containing:
   - source-neutral skills `/wiki:init`, `/wiki:add-source`, `/wiki:ingest`, `/wiki:sync-status`, `/wiki:commit-themes`, `/wiki:lint` and `/wiki:audit`;
   - a standard set of **source types** (`gmail`, `proton-drive`, `local-folder`), each a `SOURCE.md` contract plus an optional read-only wrapper; see [Sources](#sources);
   - guard hooks that block `git push`, keep every source read-only as its contract says, and protect the guard machinery itself;
   - a SessionStart hook that reports how stale each source in `raw/sync-log.md` is.
2. **The shared wiki schema**, imported by each wiki's CLAUDE.md:
   - `schema/wiki-conventions.md`: universal rules (both wikis);
   - `schema/wiki-layout.md`: raw/wiki layout, frontmatter, ingest workflow (udbygning).

The plugin is **enabled per wiki** (in each wiki's `.claude/settings.json`), never at user scope. So the guards apply only in wiki sessions.

Design and rationale: `~/wiki-tier1-implementation-plan.md` (revision 2); source redesign: `docs/sources-design.md`.

## Layout

```
.claude-plugin/marketplace.json   marketplace "wiki-tools"
.claude/skills/new-source-type/   repo-local skill: add or promote a standard source type
schema/                           shared CLAUDE.md content (@-imported)
plugins/wiki/
  skills/{init,add-source,ingest,sync-status,commit-themes,lint,audit}/SKILL.md
  skills/ingest/reading-files.md  core rules for reading fetched files (pdftotext, LibreOffice, OCR)
  hooks/hooks.json                PreToolUse guards + SessionStart status
  sources/                        standard source types
    gmail/SOURCE.md               Gmail via the claude.ai connector (MCP)
    google-drive/SOURCE.md        Google Drive folders via the claude.ai connector (MCP)
    proton-drive/{SOURCE.md,read.sh}  Proton Drive via a read-only CLI wrapper
    local-folder/{SOURCE.md,read.sh}  folders outside the wiki, read-only
  scripts/
    lib-hookjson.sh               jq-free hook-input parsing (fails closed)
    lib-source.sh                 jq-free parsing of source contracts and instances
    block-push.sh                 blocks git push
    guard.sh                      source/guard protection (Bash + Write/Edit), rules from the contracts
    sources.sh                    read-only view of a wiki's sources (list, show, catalog, contract, settings)
    sync-status.sh                staleness report from raw/sync-log.md
    pd-read.sh                    transition shim for proton-drive/read.sh (until the wikis are migrated)
    ocr.sh                        ocrmypdf wrapper (Linux)
    lint.sh                       deterministic wiki checks for /wiki:lint (read-only)
    wiki-check.sh                 setup check for /wiki:init check mode (read-only)
templates/project-settings.json   core of a wiki's .claude/settings.json (source rules come from the types)
templates/source-type/SOURCE.md   the source contract template
templates/pages/entity.md         shared page template for people and organisations
tests/                            guard fixtures and fixture wikis, per-source tests, run-tests.sh
docs/                             design notes and reviews
```

## Setup per machine

The clone path **must be `~/src/wiki-tools`** on every machine. The skills, the guard's exception, the source contracts and the wikis' `allowed-tools` use that literal path.

| | Linux | Windows |
|---|---|---|
| Prerequisites | git, bash | Git for Windows (Git Bash); Claude Code runs hooks in Git Bash |
| OCR | `sudo apt install ocrmypdf tesseract-ocr-dan` | none; scans are read as page images |
| Sources | whatever the wikis' source types need, listed in each type's Caveats; e.g. Proton Drive: `~/.local/bin/proton-drive` from [proton.me/download/drive/cli](https://proton.me/download/drive/cli/index.html) and `proton-drive auth login` by hand | the same; Proton's Windows build on PATH, check `proton-drive version` in Git Bash |

```bash
git clone git@github.com:draitchbar/wiki-tools.git ~/src/wiki-tools
bash ~/src/wiki-tools/tests/run-tests.sh          # must end "0 failed"
claude plugin marketplace add ~/src/wiki-tools     # registers the marketplace only
```

Don't install or enable the plugin at user scope. Each wiki enables it in its own committed `.claude/settings.json` (see `templates/project-settings.json`).

## Setting up a wiki

1. Create the folder (e.g. `mkdir ~/wikis/<name>`) and `cd` into it.
2. `claude plugin install wiki@wiki-tools --scope project`. This enables the plugin for this folder only, in `.claude/settings.json`.
3. Start `claude` and run `/wiki:init <what the wiki is for>`.

`/wiki:init` works in three modes:
- **New** (empty folder): grills you on scope, researches the domain, shows the full plan (CLAUDE.md, page types and templates, sources) and creates the raw/wiki layout after your go.
- **Adopt** (folder with content): the same, plus a move table that brings existing notes into `wiki/` (with `git mv` and frontmatter) and source files into `raw/`.
- **Check** (already set up): runs `scripts/wiki-check.sh` and reports what's missing; for a wiki from before source types, it proposes the migration to `.claude/sources/`.

`raw/` is the only built-in source. Every other source is chosen during init with the same flow as `/wiki:add-source`.

It ends with a guide for the steps only you can do, because the guard blocks Claude from them: pasting `.claude/settings.json` (from `templates/project-settings.json` plus the sources' rules) and the files under `.claude/sources/`, committing them, restarting `claude` and approving the shared-schema imports. Setting up the NAS remote and pushing is also yours.

Sources start at `last_checked_<key>: never`. The first `/wiki:ingest <key>` of each source checks it, asks for a starting point and reviews the data model (folders, page types, templates) against the wiki's purpose.

The shared starting template for people and organisations is `templates/pages/entity.md`; every other page type is designed per wiki by `/wiki:init`.

## Sources

The wiki skills know no particular source. They talk to every source through its **contract**.

- **Source type**: a `SOURCE.md` contract (template: `templates/source-type/SOURCE.md`). Frontmatter (flat, bash-parseable): access kind, platforms, the parameters an instance must supply, the state it needs, `cite_prefix`, allowed read and bookkeeping tools, forbidden tools, guard words and wrapper scripts. Body: one section per operation, **Check**, **List new**, **Fetch**, **Mark ingested**, **Cite**, **Resolve citation**, plus **Caveats**.
  - **Standard types** live in `plugins/wiki/sources/<type>/`: `gmail`, `google-drive`, `proton-drive`, `local-folder`. `gmail` and `google-drive` need their claude.ai connector connected once (Settings → Connectors); it then works on every platform.
  - **Local types** live in a wiki's `.claude/sources/types/<type>/`. They may ship wrapper scripts and have no test harness. A local type can't reuse a standard type's name.
- **Source instance**: a wiki's use of a type, `.claude/sources/instances/<key>.md` (type, parameters, agreed state fields). The key is the `/wiki:ingest <key>` argument and names the state lines (`last_checked_<key>`, ...) in `raw/sync-log.md`. One wiki may have several instances of one type.
- **Manual key**: a `last_checked_<key>` line with no instance file (carleasing's `web`). Its material enters via `raw/` or as user statements; sync-status and `sources.sh list` show it, `/wiki:ingest` can't read it, and lint accepts citations starting `<key>:`.
- **Read-only by contract.** The only writes a type may declare are narrow bookkeeping (Gmail's `wiki-ingested/<wiki>` label). The guard reads every contract and instance at hook time; `.claude/sources/` and `plugins/wiki/sources/` are protected, so Claude drafts these files and you save and commit them.

**Add a source to a wiki**: `/wiki:add-source <type> [key]` in the wiki. It reads the contract, asks for the parameters, agrees the state, and drafts the instance file, the CLAUDE.md line, the sync-log line and the settings rules (`sources.sh settings <type>`). For a type that doesn't exist, it drafts a local type with you.

**Add or promote a standard type**: in a session here, `/new-source-type <type>` or `/new-source-type promote <wiki path> <type>`. It researches the connector or CLI read-only, fills the contract, writes the wrapper, tests and guard fixtures, and ends with a green `run-tests.sh`. Promotion is your call, when a local type has proved useful.

`bash ~/src/wiki-tools/plugins/wiki/scripts/sources.sh list|show <key>|catalog|contract <type>|settings [<type>...]`, run in a wiki, shows what the skills see.

## Maintenance

Edit this repo in a Claude session opened in `~/src/wiki-tools`. The `wiki` plugin isn't enabled here, so the guards don't get in the way.

1. Change scripts or hooks, adding or adjusting fixtures in `tests/fixtures/<script>/<pass|block>-<case>.json`.
2. `bash tests/run-tests.sh` must pass.
3. Review the diff, commit, push.
4. On the other machine: `git pull`, run the tests, then start a new wiki session or run `/reload-plugins`.

## Proton Drive CLI: recorded syntax (plan step 5.0)

The `proton-drive` type's wrapper, `plugins/wiki/sources/proton-drive/read.sh`, has no version pin. On every call it checks that the CLI's help still shows the syntax below (`check_syntax` in the script), and refuses if it doesn't. If that happens after a CLI update: re-run these commands, paste the new output here, review `read.sh` against it, update `check_syntax` and `tests/sources/proton-drive/fake-proton-drive`, and run the tests.

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

Recorded 16.10.2026 on Linux (linux/x64-baseline build). Notes for the wrapper (`read.sh`):
- `download` prompts on conflicts unless `-f`/`-d` is set, so the wrapper must always pass a strategy (a prompt would hang a Claude Bash call).
- `download` accepts folders as well as files; the wrapper checks the node type with `info` first to stay single-file.
- **Proton Docs and Sheets are skipped by `download`.** Native Docs/Sheets must be exported by hand (Docs → .md, Sheets → .csv) and uploaded next to the originals.
- `filesystem --help` prints the usage but also reports `Command not found: filesystem --help`; that's cosmetic.


## Lint and audit

`/wiki:lint` and `/wiki:audit` reimplement ideas from [kfchou/wiki-skills](https://github.com/kfchou/wiki-skills) (MIT) on our own schema. That plugin isn't installed: it requires its own wiki layout, and its optional cross-model audit sends wiki content to OpenAI or Google. See `docs/kfchou-security-review.md`.

- **`/wiki:lint`:** `lint.sh` runs the structural checks (frontmatter, broken links, orphans, index coverage, dates, stale pages, `status_as_of`). Then one subagent per `wiki/` folder checks for contradictions, VAT ambiguities, superseded statements and missing cross-references. The report goes to `outputs/lint-YYYY-MM-DD.md`, and fixes are only offered.
- **`/wiki:audit <page>`:** extracts every checkable claim, then runs one subagent per cited source (each read as its type's **Resolve citation** says; local files; URLs) to verify it against the source wording. The report goes to `outputs/audit-<slug>-YYYY-MM-DD.md`, and fixes are only offered.

## Guard design and known limits

- **Guardrail, not a security boundary.** The guards match command text. They reliably stop accidental or straightforward misuse, but a deliberately obfuscated command could get through. Anything you run by hand is unaffected. If a Proton change slips through, use Proton's Trash and version history.
- **Rules come from the contracts.** On every call, `guard.sh` reads all standard and local source contracts and the wiki's instances, and collects each type's `guard_words` and `scripts` and every filesystem instance's `roots`.
- **Blocked in wiki sessions (Bash):** commands containing the plugin's `scripts`/`hooks`/`sources` paths, `.claude/sources`, `.claude/settings`, `.claude/plugins/`, `hooks.json`, `claude plugin`, `disableAllHooks`, any contract's guard word (e.g. `proton-drive`), or a filesystem instance's root (e.g. `~/Documents/Scans`). `proton-roots` stays blocked until the wikis are migrated.
  - **Exceptions:** a plain `bash <...>/src/wiki-tools/plugins/wiki/scripts/<pd-read|ocr|sync-status|lint|wiki-check|sources>.sh <args>`, or a plain call of a wrapper a contract lists under `scripts` (`<...>/src/wiki-tools/plugins/wiki/sources/<type>/<script>.sh`, or `.claude/sources/types/<type>/<script>.sh` in this wiki), with no `; & | < > $` or backticks and no `..`.
- **Blocked in wiki sessions (Write/Edit):** the same protected paths, anything inside a filesystem instance's root (also written `C:/…` or `/c/…`), and non-Markdown content containing a guard word.
- **Fails closed:** unparseable hook input is refused, and so is every call while an instance or contract can't be read (no frontmatter, unknown type, a local type shadowing a standard one). Fix the file by hand.
- **Cost:** reading the contracts adds about 0.1 s per tool call on Linux; Windows (Git Bash) is slower and not yet measured.
- **Known false positives:**
  - A commit message containing "push", or mentioning `proton-roots`, `hooks.json` or a guard word, is blocked. Rephrase the message.
  - `git add .claude/settings.json` or `git add .claude/sources` in a wiki is blocked. Commit `.claude/` files yourself.
  - `cat .claude/settings.json` via Bash is blocked. Claude's Read tool still works.
  - A Bash command that mentions a path that merely starts with a root (`~/Scans-old` for root `~/Scans`) is blocked.
- **Sources outside the wikis:** calls from other directories are unguarded, by design.

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
- **Bash rule wildcards (checked 24.10.2026 in the permissions docs):** a `*` may stand anywhere in a Bash rule and matches any text, slashes and spaces included, so `Bash(bash ~/src/wiki-tools/plugins/wiki/sources/*/*.sh *)` in the skills' `allowed-tools` works; the guard rejects `..` in those paths.
- **Hook environment (checked 24.10.2026 in the hooks docs):** hooks get `CLAUDE_PROJECT_DIR` (where the session started) and the input JSON has `cwd`; the guard uses the former and falls back to the git root of the latter.
