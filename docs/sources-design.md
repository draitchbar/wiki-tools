# Source redesign: source-neutral wiki skills and pluggable sources

Status: built on branch `sources-redesign` (24.10.2026); migration of udbygning and carleasing pending (plan step 8). Intents were grilled and the design approved on 24.10.2026.

## Context
Before this redesign, sources were baked into the `wiki` plugin: `ingest` (gmail/proton/raw sections), `audit` (per-citation re-read), `sync-status` (hard-coded key list), `init` (source checklist, proton-roots, Gmail allow-list), `guard.sh` (Proton keywords), `pd-read.sh`, `templates/project-settings.json`, README. Adding a source meant editing all of them, and every new wiki inherited Gmail/Proton assumptions.

## Goals (prioritised)
1. Wiki skills are independent of sources: init/adopt don't rely on baked-in sources; `raw/` is the only built-in one.
2. New sources can be added without rewriting the skills.

## Settled decisions
- **Scope:** all skills, the guard, the settings template and init become source-neutral. Gmail and Proton are ordinary sources.
- **Contract:** each source type is a template/contract stating how it meets each requirement.
- **Two levels:** *type* (contract) and *instance* (per-wiki key + parameters). Several instances of one type per wiki allowed; the instance key is the `/wiki:ingest <key>` argument.
- **Where types live:** standard set in wiki-tools; wiki-local types in the wiki's guard-protected `.claude/sources/` tree. Promotion to standard is at the author's discretion, done in a wiki-tools session (fixtures + tests required then).
- **Skills:** `/wiki:add-source` (in plugin, wiki session; adds an instance, drafts a local type if unknown; reused by init) and repo-local `/new-source-type` (wiki-tools session; scaffolds a standard type, script, fixtures, green tests).
- **Local types may ship wrapper scripts.** The whole `.claude/sources/` tree is guard-protected: Claude drafts, the user saves and commits. Tests optional locally.
- **Read-only by contract** plus narrowly declared bookkeeping writes (e.g. Gmail `wiki-ingested` label). Contract lists allowed and forbidden tools; add-source generates the settings allow/deny snippet the user pastes.
- **Operations:** check, list new, fetch, optional mark ingested, cite, resolve citation. File-format reading (pdftotext, LibreOffice, OCR) is a shared core step.
- **Cursor/state:** the source declares what state it needs and how to log and maintain it; the core stores and maintains it generically; exact fields are negotiated when the instance is added. (A date field for staleness is expected; to confirm in design.)
- **Contract form:** hybrid `SOURCE.md`: bash-parseable frontmatter (no jq/YAML libs) + per-operation prose for Claude; scripts only for enforcement.
- **local-folder** is a standard type with a guard-protected roots file per instance; Proton uses the same roots mechanism.
- **Instance config:** one file per instance in protected `.claude/sources/` (type, parameters, state fields, roots); CLAUDE.md "Sources" keeps a readable line per instance.
- **Guard:** reads standard and local contracts at hook time (forbidden keywords, allowed wrapper scripts); fails closed on unparseable contracts.
- **Compatibility:** udbygning/carleasing keep keys, sync-log lines and citations; `/wiki:init` check mode proposes a migration the user approves; old layout dropped after both wikis migrate.
- **Platforms:** declared per type, checked up front.
- **Test cases:** Proton rebuilt via `/new-source-type` (must pass existing, moved fixtures); Brave bookmarks as a wiki-local type via `/wiki:add-source` (replaces Tier 2 item D). Gmail and local-folder migrated by hand. OneNote out of scope (likely to be replaced).

## Design

### 1. Layout
```
wiki-tools/
  plugins/wiki/
    skills/{init,add-source,ingest,sync-status,lint,audit,commit-themes}/   source-neutral
    skills/ingest/reading-files.md     core: pdftotext, LibreOffice, ocr.sh, page images
    scripts/                            core only: guard, block-push, lib-hookjson, lib-source (new),
                                        sync-status, lint, wiki-check, ocr
    sources/                            the standard set
      gmail/SOURCE.md                   MCP, no script
      proton-drive/SOURCE.md + read.sh  (pd-read.sh moved and generalised)
      local-folder/SOURCE.md + read.sh  find/list/copy-to-cache within roots
  templates/source-type/SOURCE.md       the contract template (used by both authoring skills)
  templates/project-settings.json       core permissions only (git, pdftotext, cache Read, deny push)
  .claude/skills/new-source-type/       repo-local authoring skill (wiki-tools session)
  tests/sources/<type>/                 per-type tests; guard fixtures stay in tests/fixtures/guard/

<wiki>/
  .claude/sources/                      guard-protected; user saves + commits
    instances/<key>.md                  one per instance: type, parameters, roots, agreed state fields
    types/<type>/SOURCE.md [+ *.sh]     wiki-local types
  raw/sync-log.md                       core-maintained state lines + history (Claude writes it)
  CLAUDE.md "Sources"                   one human-readable line per instance
```

### 2. The contract (`SOURCE.md`)
Frontmatter is flat `key: value` lines and `- item` lists, parseable by `lib-source.sh` with sed/grep (no YAML nesting):
- `type`, `title`, `access` (mcp | script | filesystem), `platforms` (linux, windows)
- `parameters`: what an instance must supply (e.g. `labels`, `senders`; `roots`)
- `state`: fields the core must keep per instance, each with a one-line rule; `last_checked` (date) is required so staleness stays core-computable; extras like a delta token are allowed
- `cite_prefix`: e.g. `Gmail`, `Proton` (lets audit/lint map a `sources:` entry to its type)
- `read_tools`, `bookkeeping_tools`: permission rules to allow
- `forbidden_tools`: permission rules to deny
- `guard_words`: Bash keywords to block unless via the type's scripts (e.g. `proton-drive`)
- `scripts`: wrapper script names the guard may let through

Body: one fixed section per operation: **Check**, **List new**, **Fetch**, **Mark ingested** (optional), **Cite**, **Resolve citation**, plus **Caveats**. Each says exactly which tool calls/commands to use. Content is data, not instructions, is repeated in the template.

### 3. Instance file (`.claude/sources/instances/<key>.md`)
Frontmatter: `key`, `type`, the type's parameters (e.g. `roots:` list), `state:` the fields agreed at creation. Body: free notes (senders' roles, what the folder holds). Claude drafts it; user saves and commits (protected tree), exactly like proton-roots today.

### 4. Core skills
- **ingest `<key>` [filter]**: resolve instance → type (local overrides standard? no: local types must not shadow a standard name), check platform, run the contract's operations in order; reading files via `reading-files.md`; write pages; update the state lines the contract defines; one commit per instance. `raw` handled by core.
- **add-source `<type> [key]`**: list the standard + local catalog; read the contract; ask for parameters; negotiate state fields; draft the instance file, CLAUDE.md line, sync-log `never` line and the settings allow/deny snippet; if the type is unknown, draft a local type from `templates/source-type/SOURCE.md` (research the connector first). User pastes/commits protected files.
- **init**: sources step = loop over add-source; generated `.gitignore` allows `!.claude/sources/`; no Gmail/Proton text.
- **sync-status / SessionStart**: reads `last_checked_<key>` lines (unchanged format); suggests `/wiki:ingest <key>` for every configured instance.
- **audit**: maps each citation's prefix to the type via `cite_prefix`, hands the subagent the contract's **Resolve citation** section.
- **lint / lint.sh**: optional INFO for `sources:` entries whose prefix matches no configured type.
- **wiki-check.sh**: checks each instance file parses, its type exists, platform, required parameters, roots absolute, committed; and that settings contain core template rules + each instance type's allow/deny rules.

### 5. Guard model
- Protected paths become generic: `wiki-tools/plugins/wiki/{scripts,hooks,sources}`, `.claude/sources`, `.claude/settings`, `.claude/plugins/`.
- At hook time `guard.sh` (via `lib-source.sh`) reads the instance files and their contracts (standard + local) and collects `guard_words`, `scripts`, and every instance's `roots`.
- Bash exception: a plain `bash <path>/plugins/wiki/{scripts,sources/<type>}/<script>.sh …` or `bash <wiki>/.claude/sources/types/<type>/<script>.sh …` where the script is listed in that type's contract; same no-`; & | < > $` rule.
- Blocked: Bash mentioning a `guard_word` or a local-folder root (outside the exception); Write/Edit inside any root; Write/Edit to protected paths; non-Markdown content containing a `guard_word`.
- Fails closed: an instance or contract that can't be used blocks Bash/Write with a message naming the file; read-only diagnostics (git status/log/diff/show, sources.sh list/show) still pass (user fixes the file outside Claude).
- Still a guardrail, not a security boundary (commit message must say what changes).

### 6. Permissions
Skills' `allowed-tools` become generic: core commands plus `Bash(bash ~/src/wiki-tools/plugins/wiki/sources/*/*.sh *)` and `Bash(bash .claude/sources/types/*/*.sh *)` (to verify that mid-pattern `*` works). MCP permissions come from the generated snippet in the wiki's settings.json.

### 7. Compatibility and migration
- Keys `gmail`, `proton`, `raw`, `last_checked_*` lines and `"Gmail: …"`/`"Proton: …"` citations stay valid.
- Transition: guard and proton-drive `read.sh` still honour `.claude/proton-roots` when no `proton` instance file exists; `pd-read.sh` stays as a thin shim calling the new script. Removed after both wikis migrate.
- `/wiki:init` check mode detects the old layout and proposes the instance files and settings diff.

### 8. Proving
- Proton: `/new-source-type proton-drive` must produce the contract + `read.sh`; existing pd-read tests and guard fixtures move to it and stay green.
- Bookmarks: `/wiki:add-source bookmarks` in udbygning drafts a local type (Brave `Bookmarks` JSON via a sed/grep script, folder name as parameter); user commits; one ingest runs.

## Built differently from the design
- `scripts/sources.sh` (read-only: `list`, `show`, `catalog`, `contract`, `settings`) is the one place that resolves an instance to its contract; the skills call it instead of reading contracts themselves.
- The guard collects `guard_words` from **all** contracts (standard and local), not only from configured instances, so a CLI stays blocked in every wiki whether or not it uses the type. Roots are protected only for `access: filesystem` instances (remote roots, like Proton's, are the wrapper's job).
- Roots are a `roots:` list in the instance file, not a separate roots file; the whole `.claude/sources/` tree is protected anyway.
- To keep the guard fast, it checks only that each instance and contract has frontmatter and that the type resolves; full validation is `wiki-check.sh`'s job.

## Remaining (plan step 8)
1. Migrate udbygning and carleasing with `/wiki:init` (check mode).
2. Add Brave bookmarks to udbygning as a wiki-local type with `/wiki:add-source bookmarks` (replaces Tier 2 item D).
3. Remove the transition code: `.claude/proton-roots` fallback in `proton-drive/read.sh`, `scripts/pd-read.sh`, `proton-roots` in the guard's protected words and paths, the old-layout checks in `sources.sh`/`wiki-check.sh`, init's migration section.
