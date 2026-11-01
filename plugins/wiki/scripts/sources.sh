#!/usr/bin/env bash
# sources.sh: read-only view of a wiki's sources for the wiki skills.
#
#   bash <plugin>/scripts/sources.sh list
#   bash <plugin>/scripts/sources.sh show <key>
#   bash <plugin>/scripts/sources.sh catalog
#   bash <plugin>/scripts/sources.sh contract <type>
#   bash <plugin>/scripts/sources.sh settings [<type>... [--key <key>]]
#   bash <plugin>/scripts/sources.sh check-settings
#
# list      the wiki's instances: key, type, standard/local, platform, state
# show      one instance: checks, its instance file and its type's contract
# catalog   every source type this wiki can use (standard and local)
# contract  one type's SOURCE.md
# settings  the permission rules (allow, deny) for the given types, or for
#           all instances. Cache rules (~/.cache/wiki-sources/...) are
#           narrowed to <wiki>/<key>/ per instance, or for --key <key>.
# check-settings  .claude/settings.json: well-formed JSON, the rules the
#           instances need, duplicates, rules in both allow and deny, and
#           broad cache rules. Exit 1 on a problem other than the last.
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
        m=""; [ "$(src_mode "$c")" = ingest ] || m=", research (/wiki:research $k \"<question>\"; not ingested)"
        printf -- '- %s: type %s (%s)%s, %s, available here: %s, last checked: %s\n' "$k" "$t" "$kind" "$m" "$ok" "$p" "$(state_of "$k")"
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
    if ! c=$(src_contract "$root" "$2"); then
      # Shadowed by a local type: still show the standard contract, which is
      # what the instances must be rewritten to.
      printf '%s' "$2" | grep -Eq "$SRC_NAME_RE" && [ -f "$SRC_PLUGIN/sources/$2/SOURCE.md" ] || exit 1
      c="$SRC_PLUGIN/sources/$2/SOURCE.md"
      printf 'WARNING: shown is the standard contract; a local type of the same name shadows it (see above).\n\n'
    fi
    errs=$(src_validate_contract "$c" 2>&1) || printf 'WARNING: contract does not validate:\n%s\n\n' "$errs"
    printf '===== Contract %s =====\n' "$c"
    print_contract "$c"
    ;;
  settings)
    shift
    types="" key=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --key) [ $# -ge 2 ] || die "--key needs an instance key"; key=$2; shift 2 ;;
        *) types="$types $1"; shift ;;
      esac
    done
    if [ -n "$key" ]; then
      printf '%s' "$key" | grep -Eq "$SRC_NAME_RE" || die "invalid instance key '$key'"
    fi
    if [ -z "$types" ]; then
      [ -z "$key" ] || die "--key goes with a type: settings <type> --key <key>"
      rules=$(src_needed_rules "$root")
    else
      rules=$(for t in $types; do
        c=$(src_contract "$root" "$t") || exit 1
        if [ -n "$key" ]; then src_type_rules "$c" | src_narrow_rules "$(basename "$root")" "$key"
        else src_type_rules "$c" | awk -F'\t' 'BEGIN { OFS = "\t" } { print $1, $2, $2 }'; fi
      done) || exit 1
    fi
    json_list() { grep -v '^$' | awk '!seen[$0]++' | sed 's/\\/\\\\/g; s/"/\\"/g; s/.*/      "&"/' | sed '$!s/$/,/'; }
    pick() { printf '%s\n' "$rules" | awk -F'\t' -v l="$1" '$1 == l { print $2 }'; }
    printf '{\n  "permissions": {\n    "allow": [\n%s\n    ],\n    "deny": [\n%s\n    ]\n  }\n}\n' \
      "$(pick allow | json_list)" "$(pick deny | json_list)"
    if printf '%s\n' "$rules" | awk -F'\t' '$2 != $3 { f = 1 } END { exit !f }'; then
      printf '\nCache rules are narrowed to this wiki and instance (~/.cache/wiki-sources/<wiki>/<key>/); a broader rule already in settings.json, e.g. %s, covers them too.\n' \
        "$(printf '%s\n' "$rules" | awk -F'\t' '$2 != $3 { print $3; exit }')"
    fi
    # access: tools types name no tools, so they add nothing above; say so.
    if [ -z "$types" ]; then
      d=$(src_instance_dir "$root")
      types=$(for k in $(src_instances "$root"); do src_field "$d/$k.md" type; done | awk '!seen[$0]++')
    fi
    for t in $types; do
      c=$(src_contract "$root" "$t" 2>/dev/null) || continue
      [ "$(src_field "$c" access)" = tools ] || continue
      printf '\n%s (access: tools) names no tools, so it adds no tool rules here (only its cache rules, if any). Allow the read tools this machine supplies for it yourself (this wiki'"'"'s settings or your user settings; see its Caveats). Read-only rests on the connection'"'"'s scope, not on these settings.\n' "$t"
    done
    ;;
  check-settings)
    [ $# -eq 1 ] || die "usage: sources.sh check-settings"
    sf="$root/.claude/settings.json"
    [ -f "$sf" ] || { printf 'settings.json: missing (%s)\n' "$sf"; exit 1; }
    have=$(src_settings_rules "$sf") || { printf 'settings.json: NOT valid JSON: %s\n' "$(printf '%s' "$have" | cut -f2-)"; exit 1; }
    printf 'settings.json: valid JSON, %s permission rules\n' "$(printf '%s' "$have" | grep -c .)"
    bad=0
    need=$(src_needed_rules "$root")
    miss=$(printf '%s\n' "$need" | while IFS="$(printf '\t')" read -r l r orig; do
      [ -n "$l" ] || continue
      printf '%s\n' "$have" | grep -qxF -- "$l	$r" && continue
      printf '%s\n' "$have" | grep -qxF -- "$l	$orig" && continue
      printf '  %s: %s\n' "$l" "$r"
    done)
    if [ -n "$miss" ]; then bad=1; printf 'missing (rules your sources need):\n%s\n' "$miss"; else printf 'missing: none\n'; fi
    dup=$(printf '%s\n' "$have" | grep . | LC_ALL=C sort | uniq -d | sed 's/	/: /; s/^/  /')
    if [ -n "$dup" ]; then bad=1; printf 'duplicates:\n%s\n' "$dup"; else printf 'duplicates: none\n'; fi
    both=$(printf '%s\n' "$have" | awk -F'\t' '$1 == "allow" { a[$2] = 1 } $1 == "deny" { d[$2] = 1 } END { for (r in a) if (r in d) print "  " r }' | LC_ALL=C sort)
    if [ -n "$both" ]; then bad=1; printf 'in both allow and deny (deny wins):\n%s\n' "$both"; else printf 'conflicts: none\n'; fi
    broad=$(printf '%s\n' "$need" | awk -F'\t' '$2 != $3 { print $1 "\t" $3 }' | awk '!s[$0]++' | while IFS="$(printf '\t')" read -r l r; do
      printf '%s\n' "$have" | grep -qxF -- "$l	$r" && printf '  %s\n' "$r"
    done)
    [ -z "$broad" ] || printf 'note: these rules reach every wiki'"'"'s cache; the per-instance rules (sources.sh settings) would do:\n%s\n' "$broad"
    exit "$bad"
    ;;
  *)
    die "usage: sources.sh <list|show <key>|catalog|contract <type>|settings [<type>... [--key <key>]]|check-settings>"
    ;;
esac
