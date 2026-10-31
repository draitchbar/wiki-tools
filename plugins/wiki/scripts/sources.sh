#!/usr/bin/env bash
# sources.sh: read-only view of a wiki's sources for the wiki skills.
#
#   bash <plugin>/scripts/sources.sh list
#   bash <plugin>/scripts/sources.sh show <key>
#   bash <plugin>/scripts/sources.sh catalog
#   bash <plugin>/scripts/sources.sh contract <type>
#   bash <plugin>/scripts/sources.sh settings [<type>...]
#
# list      the wiki's instances: key, type, standard/local, platform, state
# show      one instance: checks, its instance file and its type's contract
# catalog   every source type this wiki can use (standard and local)
# contract  one type's SOURCE.md
# settings  the permission rules (allow, deny) for the given types, or for
#           the types of all instances
#
# Run it from inside a wiki (any directory of its git repo). Writes nothing.

set -u

. "$(dirname "$0")/lib-source.sh"

die() { printf 'sources: %s\n' "$1" >&2; exit 1; }

op=${1:-}
root=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
plat=$(src_platform)
log="$root/raw/sync-log.md"

state_of() { # KEY: the last_checked value in raw/sync-log.md
  [ -f "$log" ] || { echo "no sync-log"; return; }
  v=$(sed -n "s/^last_checked_$1:[[:space:]]*//p" "$log" | tr -d '\r' | head -n 1)
  echo "${v:-no last_checked_$1 line}"
}

platform_ok() { src_list "$1" platforms | grep -qx "$plat"; }

# print_contract FILE: the contract with ${CLAUDE_PLUGIN_ROOT} filled in, as
# Claude Code does for the skills.
print_contract() { tr -d '\r' < "$1" | sed "s#\${CLAUDE_PLUGIN_ROOT}#$SRC_PLUGIN#g"; }

case "$op" in
  list)
    [ $# -eq 1 ] || die "usage: sources.sh list"
    printf 'Sources of %s (platform: %s):\n' "$(basename "$root")" "$plat"
    printf -- '- raw: built in (raw/), last checked: %s\n' "$(state_of raw)"
    for k in $(src_instances "$root"); do
      f="$(src_instance_dir "$root")/$k.md"
      t=$(src_field "$f" type)
      if c=$(src_contract "$root" "$t" 2>/dev/null); then
        case "$c" in "$SRC_PLUGIN"/*) kind=standard ;; *) kind=local ;; esac
        if src_validate_instance "$root" "$k" 2>/dev/null; then ok=valid; else ok="INVALID (run: sources.sh show $k)"; fi
        platform_ok "$c" && p=yes || p="no (only $(src_list "$c" platforms | paste -sd, -))"
        printf -- '- %s: type %s (%s), %s, available here: %s, last checked: %s\n' "$k" "$t" "$kind" "$ok" "$p" "$(state_of "$k")"
      else
        printf -- '- %s: type %s: UNKNOWN TYPE\n' "$k" "${t:-?}"
      fi
    done
    for k in $(src_manual_keys "$root"); do
      printf -- '- %s: manual key (no source file; enters via raw/ or user statements; /wiki:ingest cannot read it), last checked: %s\n' "$k" "$(state_of "$k")"
    done
    ;;
  show)
    [ $# -eq 2 ] || die "usage: sources.sh show <key>"
    k=$2
    if [ "$k" = raw ]; then
      printf 'raw is built in: new or changed files in raw/ that the raw/sync-log.md history does not list. Last checked: %s\n' "$(state_of raw)"
      exit 0
    fi
    printf '%s' "$k" | grep -Eq "$SRC_NAME_RE" || die "invalid key '$k'"
    f="$(src_instance_dir "$root")/$k.md"
    [ -f "$f" ] || die "no source '$k' in this wiki (no $f). Known: raw $(src_instances "$root" | paste -sd' ' -). Add one with /wiki:add-source."
    errs=$(src_validate_instance "$root" "$k" 2>&1) || die "source '$k' doesn't validate:
$errs"
    c=$(src_contract "$root" "$(src_field "$f" type)")
    platform_ok "$c" || die "source '$k' (type $(src_field "$f" type)) isn't available on $plat; it supports: $(src_list "$c" platforms | paste -sd' ' -)."
    printf 'Source %s: valid, available on %s, last checked: %s\n' "$k" "$plat" "$(state_of "$k")"
    # The instance file changed since the last ingest (a new root or label):
    # its parameters haven't met reality yet.
    last=$(state_of "$k")
    case "$last" in
      [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
        rel=${f#"$root"/}
        if [ -n "$(git -C "$root" status --porcelain -- "$rel" 2>/dev/null)" ]; then
          printf 'Check needed: the instance file has uncommitted changes since the last ingest (%s).\n' "$last"
        else
          # Exact commit times: the instance file vs the last commit that
          # changed its last_checked line; by date if that line was never
          # committed.
          changed=$(git -C "$root" log -1 --format='%ct %cs' -- "$rel" 2>/dev/null)
          stamped=$(git -C "$root" log -1 --format=%ct -G"^last_checked_$k:" -- raw/sync-log.md 2>/dev/null)
          if [ -n "$changed" ]; then
            if [ -n "$stamped" ]; then
              [ "${changed%% *}" -le "$stamped" ] || need=1
            else
              [ "${changed#* }" \< "$last" ] || need=1
            fi
            [ -z "${need:-}" ] ||
              printf 'Check needed: the instance file changed (%s) since the last ingest (%s).\n' "${changed#* }" "$last"
          fi
        fi
        ;;
    esac
    printf '\n'
    printf '===== Instance file %s =====\n' "${f#"$root"/}"
    tr -d '\r' < "$f"
    printf '\n===== Contract %s =====\n' "$c"
    print_contract "$c"
    ;;
  catalog)
    [ $# -eq 1 ] || die "usage: sources.sh catalog"
    printf 'Source types (platform: %s):\n' "$plat"
    src_catalog "$root" | while IFS="$(printf '\t')" read -r t kind title; do
      c=$(src_contract "$root" "$t" 2>/dev/null) || { printf -- '- %s (%s): BROKEN (shadows a standard type?)\n' "$t" "$kind"; continue; }
      platform_ok "$c" && p="" || p=", not available on $plat"
      printf -- '- %s (%s, %s%s): %s\n' "$t" "$kind" "$(src_field "$c" access)" "$p" "$title"
    done
    ;;
  contract)
    [ $# -eq 2 ] || die "usage: sources.sh contract <type>"
    c=$(src_contract "$root" "$2") || exit 1
    errs=$(src_validate_contract "$c" 2>&1) || printf 'WARNING: contract does not validate:\n%s\n\n' "$errs"
    printf '===== Contract %s =====\n' "$c"
    print_contract "$c"
    ;;
  settings)
    shift
    types="$*"
    if [ -z "$types" ]; then
      types=$(for k in $(src_instances "$root"); do src_field "$(src_instance_dir "$root")/$k.md" type; done | LC_ALL=C sort -u)
    fi
    allow="" deny=""
    for t in $types; do
      c=$(src_contract "$root" "$t") || exit 1
      allow="$allow
$(src_list "$c" read_tools)
$(src_list "$c" bookkeeping_tools)"
      deny="$deny
$(src_list "$c" forbidden_tools)"
    done
    json_list() { grep -v '^$' | awk '!seen[$0]++' | sed 's/\\/\\\\/g; s/"/\\"/g; s/.*/      "&"/' | sed '$!s/$/,/'; }
    printf '{\n  "permissions": {\n    "allow": [\n%s\n    ],\n    "deny": [\n%s\n    ]\n  }\n}\n' \
      "$(printf '%s\n' "$allow" | json_list)" "$(printf '%s\n' "$deny" | json_list)"
    ;;
  *)
    die "usage: sources.sh <list|show <key>|catalog|contract <type>|settings [<type>...]>"
    ;;
esac
