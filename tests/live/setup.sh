#!/usr/bin/env bash
# Provision the Copilot compatibility spike (docs/plans/copilot-wiki-support.md,
# step 1) inside the disposable container (tests/live/Dockerfile). Never run
# on a developer machine: it writes under $HOME.
#
#   bash setup.sh all       everything below, from the checkout at $SPIKE_SRC
#   bash setup.sh canary    new schema canaries in the test plugin copy only
#   bash setup.sh reset     empty the capture folder and its mode files
#
# Layout under $SPIKE (default ~/spike):
#   mkt/      test copy of the marketplace; plugins/wiki gets the capture
#             hook (scripts/spike-capture.sh), a capturing hooks.json and
#             canary lines in both schema files
#   wiki/     a disposable git wiki with one local-folder instance (notes)
#   wiki2/    the same, activated through .claude/settings.json only (1.6)
#   source/   the notes instance's root, outside every wiki
#   other/    an unrelated git folder: no captures expected there
#   capture/  what spike-capture.sh logs
#   sidefx/   files the deny probes try to create
# Made-up content only.

set -eu
here=$(cd "$(dirname "$0")" && pwd)
SPIKE=${SPIKE:-$HOME/spike}
SRC=${SPIKE_SRC:-/src}
mkt=$SPIKE/mkt
plug=$mkt/plugins/wiki

hooks_json() {
  cap='bash \"${CLAUDE_PLUGIN_ROOT}/scripts/spike-capture.sh\"'
  cat <<EOF
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash|PowerShell|Write|Edit|MultiEdit|Read|Grep|Glob",
        "hooks": [ { "type": "command", "shell": "bash", "timeout": 20, "command": "$cap guard guard" } ] },
      { "matcher": "*",
        "hooks": [ { "type": "command", "shell": "bash", "timeout": 10, "command": "$cap pre-star" } ] },
      { "hooks": [ { "type": "command", "shell": "bash", "timeout": 10, "command": "$cap pre-nomatcher" } ] }
    ],
    "PostToolUse": [ { "hooks": [ { "type": "command", "shell": "bash", "command": "$cap post" } ] } ],
    "UserPromptSubmit": [ { "hooks": [ { "type": "command", "shell": "bash", "command": "$cap prompt" } ] } ],
    "Stop": [ { "hooks": [ { "type": "command", "shell": "bash", "command": "$cap stop" } ] } ],
    "SubagentStart": [ { "hooks": [ { "type": "command", "shell": "bash", "command": "$cap subagent-start" } ] } ],
    "SubagentStop": [ { "hooks": [ { "type": "command", "shell": "bash", "command": "$cap subagent-stop" } ] } ],
    "PreCompact": [ { "hooks": [ { "type": "command", "shell": "bash", "command": "$cap precompact" } ] } ],
    "SessionEnd": [ { "hooks": [ { "type": "command", "shell": "bash", "command": "$cap session-end" } ] } ],
    "SessionStart": [
      { "hooks": [
          { "type": "command", "shell": "bash", "command": "bash \"\${CLAUDE_PLUGIN_ROOT}/scripts/schema.sh\" wiki-conventions" },
          { "type": "command", "shell": "bash", "command": "bash \"\${CLAUDE_PLUGIN_ROOT}/scripts/schema.sh\" wiki-layout" },
          { "type": "command", "shell": "bash", "command": "$cap start" } ] },
      { "matcher": "startup",
        "hooks": [
          { "type": "command", "shell": "bash", "command": "bash \"\${CLAUDE_PLUGIN_ROOT}/scripts/sync-status.sh\"" },
          { "type": "command", "shell": "bash", "command": "$cap start-startup" } ] }
    ]
  }
}
EOF
}

canary() {
  for f in wiki-conventions wiki-layout; do
    c="SPK-$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    cp "$SRC/plugins/wiki/schema/$f.md" "$plug/schema/$f.md"
    printf '\nSpike canary for %s: %s\n' "$f" "$c" >> "$plug/schema/$f.md"
    printf '%s %s\n' "$f" "$c" >> "$SPIKE/canaries.log"
  done
  tail -2 "$SPIKE/canaries.log"
}

reset() {
  rm -rf "$SPIKE/capture" "$SPIKE/sidefx"
  mkdir -p "$SPIKE/capture" "$SPIKE/sidefx"
}

mkwiki() {  # mkwiki <dir> <settings json>
  d=$1
  rm -rf "$d"
  mkdir -p "$d"/raw "$d"/wiki "$d"/templates "$d"/outputs "$d"/.claude/sources/instances
  cat > "$d/CLAUDE.md" <<'EOF'
# Spike wiki

A disposable wiki about the made-up Example Garden Club, used to test the
wiki plugin. Page types: `entity` (a person, group or place). Pages live in
`wiki/`; sources in `raw/` and the `notes` local-folder instance.
EOF
  cp "$SRC/plugins/wiki/templates/pages/entity.md" "$d/templates/entity.md"
  cat > "$d/raw/sync-log.md" <<'EOF'
# Sync log

last_checked_raw: never
last_checked_notes: never

| Date | Source | Note |
|---|---|---|
EOF
  printf '# Index\n\n## Entities\n\n| Page | Summary | Updated |\n|---|---|---|\n' > "$d/wiki/index.md"
  printf '# Log\n\n## 2026-11-17 | init | Spike wiki\n\nCreated for the spike.\n' > "$d/wiki/log.md"
  cat > "$d/.claude/sources/instances/notes.md" <<EOF
---
key: notes
type: local-folder
roots:
  - $SPIKE/source
state:
  - last_checked
---
EOF
  printf '%s\n' "$2" > "$d/.claude/settings.json"
  git -C "$d" init -q -b main
  git -C "$d" add -A
  git -C "$d" -c user.name=Spike -c user.email=spike@example.com commit -q -m "Spike wiki"
}

all() {
  reset
  rm -rf "$mkt"
  mkdir -p "$mkt"
  cp -r "$SRC/.claude-plugin" "$mkt/"
  mkdir -p "$mkt/plugins"
  cp -r "$SRC/plugins/wiki" "$plug"
  find "$plug" -name __pycache__ -prune -exec rm -rf {} +
  cp "$here/capture.sh" "$plug/scripts/spike-capture.sh"
  hooks_json > "$plug/hooks/hooks.json"
  : > "$SPIKE/canaries.log"
  canary
  rm -rf "$SPIKE/source"
  mkdir -p "$SPIKE/source/sub folder"
  printf 'Example Garden Club minutes, 2026-10-04.\nThe club planted 37 apple trees on the north field.\n' \
    > "$SPIKE/source/sub folder/minutes one.txt"
  printf 'Spring fair is planned for 2027-04-18.\n' > "$SPIKE/source/fair.txt"
  plugin_settings='{ "permissions": { "deny": [ "Bash(git push *)" ] } }'
  mkwiki "$SPIKE/wiki" "$plugin_settings"
  mkwiki "$SPIKE/wiki2" "$(cat <<EOF
{
  "permissions": { "deny": [ "Bash(git push *)" ] },
  "enabledPlugins": { "wiki@wiki-tools": true },
  "extraKnownMarketplaces": {
    "wiki-tools": { "source": { "source": "directory", "path": "$mkt" } }
  }
}
EOF
)"
  rm -rf "$SPIKE/other"
  mkdir -p "$SPIKE/other"
  printf 'Unrelated folder.\n' > "$SPIKE/other/README.md"
  git -C "$SPIKE/other" init -q -b main
  git -C "$SPIKE/other" add -A
  git -C "$SPIKE/other" -c user.name=Spike -c user.email=spike@example.com commit -q -m other
  echo "spike: set up under $SPIKE"
}

case "${1:-}" in
  all) all ;;
  canary) canary ;;
  reset) reset ;;
  *) echo "usage: setup.sh all|canary|reset" >&2; exit 1 ;;
esac
