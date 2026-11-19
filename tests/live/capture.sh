#!/usr/bin/env bash
# Capture-only hook for the Copilot compatibility spike
# (docs/plans/copilot-wiki-support.md, step 1). Installed by setup.sh into
# a test copy of the plugin, never into plugins/wiki itself.
#
#   bash <plugin>/scripts/spike-capture.sh <tag> [<default mode>]
#
# Logs one hook call to $SPIKE_CAPTURE (default ~/spike/capture): the input
# as <stamp>-<tag>.json, and the hook's environment (names that matter to
# hooks; nothing named like a token, key or secret) with its timing as
# <stamp>-<tag>.env, with the run ID run.sh exports (SPIKE_RUN), so a late
# hook from an earlier run can't pass as this one's. Then behaves as the
# mode file $SPIKE_CAPTURE/mode.<tag> says, or as <default mode>, or allows:
#
#   allow       exit 0, no output
#   exit2       reason on stderr, exit 2
#   exit1       reason on stderr, exit 1
#   json-deny   exit 0 with Claude's PreToolUse JSON deny and a reason
#   missing     exec a program that doesn't exist (exit 127)
#   sleep       sleep $SPIKE_SLEEP seconds (default 30), then allow
#   guard       pass the input to the plugin's real guard (py-launch.sh
#               guard) and return what it returns
#
# The reason texts carry the word in $SPIKE_CAPTURE/reason-word, if any, so
# a run can tell whether the reason reached the model.

tag=${1:-untagged}
out=${SPIKE_CAPTURE:-$HOME/spike/capture}
mkdir -p "$out"
t0=$(date +%s%N)
stem="$out/$t0-$$-$tag"
input=$(cat)
printf '%s\n' "$input" > "$stem.json"
mode=$(cat "$out/mode.$tag" 2>/dev/null || printf '%s' "${2:-allow}")
word=$(cat "$out/reason-word" 2>/dev/null || true)
# Sourced by a hook (". spike-capture.sh <tag>"), $0 is the shell: use the
# plugin root the client passes.
plugin=${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
{
  printf 'tag=%s\nmode=%s\nrun=%s\nscript=%s\npwd=%s\nparent=%s\n' \
    "$tag" "$mode" "${SPIKE_RUN:-}" "$0" "$PWD" "$(ps -o args= -p "$PPID" 2>/dev/null | cut -c1-200)"
  printf 'bash=%s %s\nostype=%s\n' "${BASH:-}" "${BASH_VERSION:-}" "${OSTYPE:-}"
  env | grep -E '^(CLAUDE|COPILOT|PLUGIN|PROJECT|GITHUB_COPILOT|AGENT|SESSION|HOOK)[A-Z0-9_]*=' \
    | grep -v -i -E '^[^=]*(TOKEN|KEY|SECRET|AUTH|PASS)[^=]*=' | sort
} > "$stem.env"

done_() {
  printf 'rc=%s\ndur_ms=%s\n' "$1" "$(( ($(date +%s%N) - t0) / 1000000 ))" >> "$stem.env"
  exit "$1"
}

case $mode in
  allow) done_ 0 ;;
  exit2) printf 'spike: denied by exit 2 (%s) %s\n' "$tag" "$word" >&2; done_ 2 ;;
  exit1) printf 'spike: failed with exit 1 (%s) %s\n' "$tag" "$word" >&2; done_ 1 ;;
  json-deny)
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"spike: JSON deny (%s) %s"}}\n' "$tag" "$word"
    done_ 0 ;;
  missing)
    printf 'rc=127\ndur_ms=0\n' >> "$stem.env"
    exec /nonexistent/spike-interpreter ;;
  sleep) sleep "${SPIKE_SLEEP:-30}"; done_ 0 ;;
  guard)
    gout=$(printf '%s\n' "$input" | bash "$plugin/scripts/py-launch.sh" guard 2>"$stem.guard-err")
    rc=$?
    printf '%s' "$gout" > "$stem.guard-out"
    [ -n "$gout" ] && printf '%s\n' "$gout"
    [ -s "$stem.guard-err" ] && cat "$stem.guard-err" >&2
    done_ "$rc" ;;
  *) printf 'spike: unknown mode %s\n' "$mode" >&2; done_ 2 ;;
esac
