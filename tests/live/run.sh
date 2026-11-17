#!/usr/bin/env bash
# Run one prompt-mode session for the Copilot compatibility spike and keep
# its record (docs/plans/copilot-wiki-support.md, step 1). Container only.
#
#   bash run.sh <copilot|claude> <case> "<prompt>" [client flags...]
#
# Environment:
#   SPIKE_CWD     folder to start in (default $SPIKE/wiki)
#   SPIKE_LANE    plugindir (default: --plugin-dir the test copy) or project
#                 (no --plugin-dir: only what the folder and profile enable)
#   SPIKE_RESUME  session ID to resume
#
# Writes $SPIKE/runs/<client>-<case>/: out.jsonl (the client's JSON
# stream), err.txt, meta.txt (argv, rc, seconds) and capture/ (what the
# capture hook logged during the run). Mode files in $SPIKE/capture stay.
# Explicit model IDs; never --allow-all, --yolo, --bare or a permission
# bypass.

set -u
SPIKE=${SPIKE:-$HOME/spike}
client=$1 case=$2 prompt=$3
shift 3
cap=$SPIKE/capture
out=$SPIKE/runs/$client-$case
plugin=$SPIKE/mkt/plugins/wiki
cwd=${SPIKE_CWD:-$SPIKE/wiki}
lane=${SPIKE_LANE:-plugindir}
rm -rf "$out"
mkdir -p "$out/capture" "$cap" "$SPIKE/runs/stray"
# Leftovers from an earlier run don't belong to this one.
find "$cap" -maxdepth 1 -type f ! -name 'mode.*' ! -name reason-word -exec mv {} "$SPIKE/runs/stray/" \;

pd=()
[ "$lane" = plugindir ] && pd=(--plugin-dir "$plugin")
case $client in
  copilot)
    argv=(copilot -p "$prompt" "${pd[@]}" --model "${SPIKE_COPILOT_MODEL:-claude-sonnet-5.5}"
          --output-format json --no-ask-user --no-auto-update)
    # --trust-folder is for new sessions only; Copilot refuses it with --resume.
    if [ -n "${SPIKE_RESUME:-}" ]; then argv+=("--resume=$SPIKE_RESUME")
    elif [ "${SPIKE_TRUST:-1}" = 1 ]; then argv+=(--trust-folder); fi ;;
  claude)
    argv=(claude -p "$prompt" "${pd[@]}" --model "${SPIKE_CLAUDE_MODEL:-claude-sonnet-5-5}"
          --output-format stream-json --verbose --include-hook-events)
    [ -n "${SPIKE_RESUME:-}" ] && argv+=(--resume "$SPIKE_RESUME") ;;
  *) echo "run.sh: client must be copilot or claude" >&2; exit 1 ;;
esac
argv+=("$@")

t0=$(date +%s)
# At most two attempts, and a second only when the client crashed before
# its first hook (an infrastructure failure, not a result).
for attempt in 1 2; do
  (cd "$cwd" && timeout "${SPIKE_TIMEOUT:-600}" "${argv[@]}") > "$out/out.jsonl" 2> "$out/err.txt" < /dev/null
  rc=$?
  grep -q SIGSEGV "$out/err.txt" && [ -z "$(find "$cap" -maxdepth 1 -name '*.json' -print -quit)" ] || break
  cp "$out/err.txt" "$out/err-attempt$attempt.txt"
done
{
  printf 'client=%s\ncase=%s\ncwd=%s\nlane=%s\nrc=%s\nattempts=%s\nseconds=%s\n' \
    "$client" "$case" "$cwd" "$lane" "$rc" "$attempt" "$(( $(date +%s) - t0 ))"
  printf 'argv:'; printf ' [%s]' "${argv[@]}"; printf '\n'
  printf 'modes:'; for m in "$cap"/mode.*; do [ -f "$m" ] && printf ' %s=%s' "${m##*/mode.}" "$(cat "$m")"; done; printf '\n'
  printf 'version=%s\n' "$("$client" --version 2>/dev/null | head -1)"
} > "$out/meta.txt"
find "$cap" -maxdepth 1 -type f ! -name 'mode.*' ! -name reason-word -exec mv {} "$out/capture/" \;
printf '%s rc=%s %ss captures=%s\n' "$client-$case" "$rc" "$(( $(date +%s) - t0 ))" "$(find "$out/capture" -name '*.json' | wc -l)"
