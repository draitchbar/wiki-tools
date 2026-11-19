# wiki-tools

A Claude Code plugin for LLM-managed wikis: Claude builds and maintains a wiki of Markdown pages from your own sources (mail, drives, Teams, Jira, local folders, codebases), with every claim cited. It runs on Linux and on Windows (Git Bash).

The plugin, `wiki`, gives each wiki:
- **skills** to set it up, add sources, ingest, research, check and commit (`/wiki:init`, `/wiki:ingest`, … below);
- **source types** for Gmail, Google Drive, Microsoft Teams, Jira, Proton Drive, OneNote, local folders and git codebases, all read-only;
- **guard hooks** that keep the sources read-only and block `git push`;
- **a shared schema**, the wiki's conventions and layout, loaded into every session.

## Install (once per machine)

You need Claude Code, git and Python 3.9 or later. On Windows: Git for Windows (Claude Code runs the hooks in Git Bash) and Python from python.org, with the `python3` App execution alias turned off in Settings.

```bash
claude plugin marketplace add draitchbar/wiki-tools
```

To change the plugin, or to have changes live in every wiki at once, run it from a clone instead (`docs/setup.md`):

```bash
git clone https://github.com/draitchbar/wiki-tools.git ~/src/wiki-tools   # any folder works
claude plugin marketplace add ~/src/wiki-tools
```

Don't install or enable the plugin at user scope: each wiki enables it for itself, so the guards apply only in wiki sessions.

## Create a wiki

```bash
mkdir ~/wikis/<name> && cd ~/wikis/<name>
claude plugin install wiki@wiki-tools --scope project
claude
```

Then run `/wiki:init <what the wiki is for>`. It agrees the wiki's purpose, page types and sources with you, creates the layout, and ends with a few steps only you can do: saving `.claude/settings.json` and the source files, committing them, and restarting `claude`. A folder with existing notes is adopted rather than started fresh.

## Use it

| Command | What it does |
|---|---|
| `/wiki:sync-status` | How stale each source is, and what to ingest next (also shown at session start) |
| `/wiki:ingest <source>` | Bring new material from a source into the pages; `/wiki:ingest all` does every due source in turn |
| `/wiki:add-source <type> [key]` | Add a source; you install the files it drafts with `install-source-file.sh`, in a separate terminal |
| `/wiki:research <source> "<question>"` | Research a codebase (or another research source) with parallel agents |
| `/wiki:lint`, `/wiki:audit <page>` | Check the wiki's health; fact-check a page against its sources |
| `/wiki:commit-themes` | Commit the changes as one commit per theme |

Claude can't push: you push the wiki yourself.

## Update

From GitHub: Claude Code runs its own copy of the plugin, and `git pull` doesn't reach it. Refresh the marketplace, then update the plugin in each wiki:

```bash
claude plugin marketplace update wiki-tools
cd ~/wikis/<name> && claude plugin update wiki@wiki-tools --scope project
```

Then restart `claude` in the wiki (or run `/reload-plugins`). Automatic updates are off for marketplaces outside Anthropic's own; you can turn them on in `/plugin`, tab Marketplaces.

From a clone: `git pull` in the clone; the plugin runs straight from that folder, so changes are live in every wiki; restart `claude` in a wiki (or run `/reload-plugins`) to pick them up.

## More

- `docs/setup.md`: prerequisites in full (OCR, what each source needs), setting up a wiki in detail, known issues
- `docs/skills.md`: every skill, including lint and audit
- `docs/sources.md`: source types and instances, adding a source, adding a source type
- `docs/guard.md`: what the guard blocks, and its known false positives
- `docs/development.md`: changing wiki-tools: tests, lint, pull requests
- `docs/layout.md`: what lives where in this repository
- `docs/adr.md`: the decisions behind the design; `docs/roadmap.md`: plans and parked work
- `CONTRIBUTING.md`: contributing (by invitation); `LICENSE`: MIT
