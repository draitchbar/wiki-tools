#!/usr/bin/env bash
# lint.sh: deterministic health checks for a raw/wiki-layout wiki.
#
#   bash <plugin>/scripts/lint.sh
#
# Run from inside a wiki (any directory of its git repo). Read-only: prints a
# Markdown findings report to stdout and writes nothing. No LLM involved; the
# /wiki:lint skill adds the judgement checks (contradictions, missing
# cross-references) on top of this output.
#
# Checks (inspired by kfchou/wiki-skills' lint-mechanical.py, adapted to the
# schema in schema/wiki-layout.md):
#   ERROR  missing frontmatter, missing required fields, broken [[links]]
#   WARN   orphan pages, pages missing from index.md, pages without sources,
#          bad or inconsistent dates, stale pages
#   INFO   decision/approval pages without status_as_of, `sources:` entries
#          that match no source of the wiki (only once it has
#          .claude/sources/instances/)
#
# Environment (for tests): WIKI_LINT_TODAY=YYYY-MM-DD overrides today's date.

set -u

die() { printf 'lint: %s\n' "$1" >&2; exit 1; }

root=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null) || die "not inside a git repo; run from a wiki."
wiki="$root/wiki"
[ -d "$wiki" ] || { printf 'lint: no wiki/ folder in %s; this wiki does not use the raw/wiki layout.\n' "$root"; exit 0; }

today=${WIKI_LINT_TODAY:-$(date +%F)}
today_s=$(date -d "$today" +%s) || die "bad WIKI_LINT_TODAY '$today'"
STALE_DAYS=90
REQUIRED="title type sources created updated"
# Words that suggest a claim goes out of date (English and Danish).
STALE_WORDS='pending|awaiting|not yet|currently|latest|expected|upcoming|afventer|venter på|endnu ikke'

tmp=$(mktemp -d) || die "cannot create temp dir"
trap 'rm -rf "$tmp"' EXIT

# Page list, relative to the wiki folder. index.md and log.md are special.
(cd "$wiki" && find . -type f -name '*.md' | sed 's#^\./##' | LC_ALL=C sort) > "$tmp/all"
grep -v -x -e 'index.md' -e 'log.md' "$tmp/all" > "$tmp/pages" || true

slug_of() { # PATH -> lowercase basename without .md
  b=${1##*/}; b=${b%.md}; printf '%s' "$b" | tr '[:upper:]' '[:lower:]'
}
while IFS= read -r p; do printf '%s\t%s\n' "$(slug_of "$p")" "$p"; done < "$tmp/all" > "$tmp/slugs"

# Frontmatter facts, one TSV line per page:
# path, has_fm, title, type, created, updated, status_as_of, n_sources, as_of.
# Fields are separated by \037 (unit separator): unlike a tab it is not
# whitespace, so `read` keeps empty fields instead of merging them.
US=$(printf '\037')
while IFS= read -r p; do
  awk -v path="$p" -v US="$US" '
    function val(s) { sub(/^[^:]*:[[:space:]]*/, "", s); gsub(/^["\047]|["\047][[:space:]]*$/, "", s); return s }
    NR == 1 { if ($0 ~ /^---[[:space:]]*$/) { infm = 1; hasfm = 1; next } else { exit } }
    infm && /^---[[:space:]]*$/ { infm = 0; exit }
    infm {
      if ($0 ~ /^[A-Za-z_]+:/) {
        key = $0; sub(/:.*/, "", key); cur = key
        if (key == "title") title = val($0)
        else if (key == "type") type = val($0)
        else if (key == "created") created = val($0)
        else if (key == "updated") updated = val($0)
        else if (key == "status_as_of") status = val($0)
        else if (key == "as_of") asof = val($0)
        else if (key == "sources") {
          v = val($0); seen_sources = 1
          if (v != "" && v != "[]") { n = split(v, parts, ","); nsrc += n }
        }
      } else if (cur == "sources" && $0 ~ /^[[:space:]]+-[[:space:]]*[^[:space:]]/) nsrc++
    }
    END {
      printf "%s" US "%d" US "%s" US "%s" US "%s" US "%s" US "%s" US "%s" US "%s\n", path, hasfm, title, type, created, updated, status, (seen_sources ? nsrc + 0 : -1), asof
    }' "$wiki/$p"
done < "$tmp/pages" > "$tmp/fm"

# Links: "source-path<TAB>target-slug" for every [[target]], [[target|alias]]
# or [[folder/target#heading]] in any page, index.md and log.md included.
while IFS= read -r p; do
  grep -oE '\[\[[^]]+\]\]' "$wiki/$p" 2>/dev/null |
    sed -e 's/^\[\[//' -e 's/\]\]$//' -e 's/[|#].*//' -e 's#.*/##' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' |
    tr '[:upper:]' '[:lower:]' |
    while IFS= read -r t; do [ -n "$t" ] && printf '%s\t%s\n' "$p" "$t"; done
done < "$tmp/all" > "$tmp/links"

cut -f1 "$tmp/slugs" | LC_ALL=C sort -u > "$tmp/known"

# ---- findings, one file per category ---------------------------------------
: > "$tmp/e_nofm"; : > "$tmp/e_fields"; : > "$tmp/e_broken"
: > "$tmp/w_orphan"; : > "$tmp/w_noindex"; : > "$tmp/w_nosrc"; : > "$tmp/w_dates"; : > "$tmp/w_stale"
: > "$tmp/i_status"; : > "$tmp/i_srcprefix"

days_since() { # YYYY-MM-DD -> days before today, or empty if unparseable
  case "$1" in [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;; *) return 1 ;; esac
  s=$(date -d "$1" +%s 2>/dev/null) || return 1
  echo $(( (today_s - s) / 86400 ))
}

while IFS="$US" read -r p hasfm title type created updated status nsrc asof; do
  if [ "$hasfm" != 1 ]; then
    echo "- \`$p\`: no YAML frontmatter" >> "$tmp/e_nofm"; continue
  fi
  missing=""
  for f in $REQUIRED; do
    case "$f" in
      title) [ -n "$title" ] || missing="$missing $f" ;;
      type) [ -n "$type" ] || missing="$missing $f" ;;
      created) [ -n "$created" ] || missing="$missing $f" ;;
      updated) [ -n "$updated" ] || missing="$missing $f" ;;
      sources) [ "$nsrc" != -1 ] || missing="$missing $f" ;;
    esac
  done
  [ -z "$missing" ] || echo "- \`$p\`: missing${missing}" >> "$tmp/e_fields"
  [ "$nsrc" != 0 ] || echo "- \`$p\`: \`sources:\` is empty; every claim is uncited" >> "$tmp/w_nosrc"

  for d in created updated status_as_of as_of; do
    case "$d" in created) v=$created ;; updated) v=$updated ;; status_as_of) v=$status ;; as_of) v=$asof ;; esac
    [ -n "$v" ] || continue
    if ! age=$(days_since "$v"); then
      echo "- \`$p\`: \`$d: $v\` is not a YYYY-MM-DD date" >> "$tmp/w_dates"
    elif [ "$age" -lt 0 ]; then
      echo "- \`$p\`: \`$d: $v\` is in the future" >> "$tmp/w_dates"
    fi
  done
  if [ -n "$created" ] && [ -n "$updated" ] && [ "$updated" \< "$created" ]; then
    echo "- \`$p\`: updated ($updated) is before created ($created)" >> "$tmp/w_dates"
  fi

  # A page with as_of: is a dated analysis, historical by design.
  if [ -z "$asof" ] && age=$(days_since "$updated") && [ "$age" -gt "$STALE_DAYS" ]; then
    hits=$(awk 'BEGIN{n=0} /^---/{n++; next} n>=2' "$wiki/$p" | grep -ioE "$STALE_WORDS" | tr '[:upper:]' '[:lower:]' | sort -u | paste -sd, -)
    [ -z "$hits" ] || echo "- \`$p\`: updated $age days ago and still says: $hits" >> "$tmp/w_stale"
  fi
  case "$type" in
    decision|approval)
      if [ -z "$status" ]; then
        echo "- \`$p\` ($type): no \`status_as_of\`" >> "$tmp/i_status"
      elif age=$(days_since "$status") && [ "$age" -gt "$STALE_DAYS" ]; then
        echo "- \`$p\` ($type): status_as_of $status is $age days old" >> "$tmp/w_stale"
      fi
      ;;
  esac
done < "$tmp/fm"

# Citations that match no source: an entry must start with a configured
# type's cite_prefix, a manual key ("web: ..."), "raw/" or "raw:",
# "User statement" or a URL.
. "$(dirname "$0")/lib-source.sh"
if [ -n "$(src_instances "$root")" ]; then
  prefixes=$( { for k in $(src_instances "$root"); do
      c=$(src_contract "$root" "$(src_field "$(src_instance_dir "$root")/$k.md" type)" 2>/dev/null) && src_field "$c" cite_prefix
    done; src_manual_keys "$root"; } | LC_ALL=C sort -u)
  while IFS= read -r p; do
    src_list "$wiki/$p" sources | sed -e "s/^[\"']//" -e "s/[\"']\$//" | while IFS= read -r s; do
      case "$s" in raw/*|raw:*|[Ll]ocal\ file:\ raw/*|"User statement"*|http://*|https://*) continue ;; esac
      ls=$(printf '%s' "$s" | tr '[:upper:]' '[:lower:]')
      ok=0
      while IFS= read -r x; do
        [ -n "$x" ] || continue
        x=$(printf '%s' "$x" | tr '[:upper:]' '[:lower:]')
        case "$ls" in "$x:"*|"$x "*) ok=1; break ;; esac
      done <<EOF
$prefixes
EOF
      [ "$ok" = 1 ] || echo "- \`$p\`: source \`$s\` matches no source of this wiki"
    done
  done < "$tmp/pages" > "$tmp/i_srcprefix"
fi

# Broken links (grouped by target, with how many pages reference it).
LC_ALL=C sort -u "$tmp/links" | while IFS="$(printf '\t')" read -r src t; do
  grep -qx -F "$t" "$tmp/known" || printf '%s\t%s\n' "$t" "$src"
done | LC_ALL=C sort > "$tmp/broken_pairs"
cut -f1 "$tmp/broken_pairs" | LC_ALL=C sort -u | while IFS= read -r t; do
  srcs=$(awk -F '\t' -v t="$t" '$1 == t { printf "%s`%s`", (n++ ? ", " : ""), $2 }' "$tmp/broken_pairs")
  echo "- \`[[$t]]\` (no such page) linked from $srcs"
done > "$tmp/e_broken"

# Orphans: no inbound link from any other page (index.md and log.md don't count).
# Not in index: page slug never linked from index.md.
while IFS="$(printf '\t')" read -r s p; do
  case "$p" in index.md|log.md) continue ;; esac
  inbound=$(awk -F '\t' -v s="$s" -v p="$p" '$2 == s && $1 != p && $1 != "index.md" && $1 != "log.md"' "$tmp/links" | wc -l)
  [ "$inbound" -gt 0 ] || echo "- \`$p\`: no inbound links from other pages" >> "$tmp/w_orphan"
  awk -F '\t' -v s="$s" '$1 == "index.md" && $2 == s { f = 1 } END { exit !f }' "$tmp/links" ||
    echo "- \`$p\`: not listed in index.md" >> "$tmp/w_noindex"
done < "$tmp/slugs"

# ---- report -----------------------------------------------------------------
count() { wc -l < "$1" | tr -d ' '; }
n_err=$(( $(count "$tmp/e_nofm") + $(count "$tmp/e_fields") + $(count "$tmp/e_broken") ))
n_warn=$(( $(count "$tmp/w_orphan") + $(count "$tmp/w_noindex") + $(count "$tmp/w_nosrc") + $(count "$tmp/w_dates") + $(count "$tmp/w_stale") ))
n_info=$(( $(count "$tmp/i_status") + $(count "$tmp/i_srcprefix") ))

section() { # FILE TITLE
  [ -s "$1" ] || return 0
  printf '\n### %s (%s)\n\n' "$2" "$(count "$1")"
  cat "$1"
}

printf '## Mechanical checks: %s (%s)\n\n' "$(basename "$root")" "$today"
printf 'Pages: %s. Errors: %s. Warnings: %s. Info: %s.\n' "$(count "$tmp/pages")" "$n_err" "$n_warn" "$n_info"
section "$tmp/e_nofm"     "ERROR: missing frontmatter"
section "$tmp/e_fields"   "ERROR: missing required fields"
section "$tmp/e_broken"   "ERROR: broken links"
section "$tmp/w_orphan"   "WARN: orphan pages"
section "$tmp/w_noindex"  "WARN: not in index.md"
section "$tmp/w_nosrc"    "WARN: no sources"
section "$tmp/w_dates"    "WARN: bad dates"
section "$tmp/w_stale"    "WARN: possibly stale (not updated in ${STALE_DAYS}+ days)"
section "$tmp/i_status"   "INFO: missing status_as_of"
section "$tmp/i_srcprefix" "INFO: citations with no matching source"

# Clusters for the judgement pass: one per top-level folder of wiki/.
printf '\n## Clusters for contradiction checks\n\n'
awk -F/ 'NF > 1 { c[$1] = c[$1] (c[$1] ? ", " : "") "`" $0 "`" } NF == 1 { c["(top level)"] = c["(top level)"] (c["(top level)"] ? ", " : "") "`" $0 "`" }
         END { for (k in c) print "- **" k "**: " c[k] }' "$tmp/pages" | LC_ALL=C sort
