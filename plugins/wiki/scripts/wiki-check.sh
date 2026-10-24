#!/usr/bin/env bash
# wiki-check.sh: read-only setup check for a raw/wiki-layout wiki.
#
#   bash ~/src/wiki-tools/plugins/wiki/scripts/wiki-check.sh
#
# Run from inside a wiki (any directory of its git repo). Used by /wiki:init
# in check mode. Prints a Markdown pass/fail list with a fix for each failure
# and writes nothing. Makes no calls to any source; sources are
# checked at their first ingest.
#
# Exit 0 when every check passes, 1 when any check fails.
#
# Environment (for tests): WIKI_CHECK_TEMPLATE overrides the settings
# template path.

set -u

here=$(cd "$(dirname "$0")" && pwd)
template=${WIKI_CHECK_TEMPLATE:-$here/../../../templates/project-settings.json}

root=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null) || {
  printf 'wiki-check: not inside a git repo; run from a wiki.\n' >&2
  exit 1
}

fails=0
out=""

. "$here/lib-source.sh"
instances=$(src_instances "$root")
pass() { out="$out
- PASS $1"; }
fail() { out="$out
- FAIL $1. Fix: $2"; fails=$((fails + 1)); }
info() { out="$out
- INFO $1"; }

tracked() { git -C "$root" ls-files --error-unmatch -- "$1" >/dev/null 2>&1; }

# 1. Layout.
for d in raw wiki outputs templates; do
  if [ -d "$root/$d" ]; then pass "folder \`$d/\` exists"
  else fail "folder \`$d/\` is missing" "re-run /wiki:init, or create it"; fi
done
for f in raw/sync-log.md wiki/index.md wiki/log.md CLAUDE.md .gitignore; do
  if [ -f "$root/$f" ]; then pass "\`$f\` exists"
  else fail "\`$f\` is missing" "re-run /wiki:init, or create it as described in schema/wiki-layout.md"; fi
done
n=$(find "$root/templates" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l)
if [ "$n" -gt 0 ]; then pass "$n page template(s) in \`templates/\`"
else fail "no page templates in \`templates/\`" "add templates/<type>.md for each page type named in CLAUDE.md"; fi

# 2. CLAUDE.md imports the shared schema.
if [ -f "$root/CLAUDE.md" ]; then
  for s in wiki-conventions wiki-layout; do
    if grep -q "^@~/src/wiki-tools/schema/$s\.md" "$root/CLAUDE.md"; then
      pass "CLAUDE.md imports \`$s.md\`"
    else
      fail "CLAUDE.md doesn't import \`$s.md\`" "add the line \`@~/src/wiki-tools/schema/$s.md\` below the title"
    fi
  done
fi

# 3. Sync log: every last_checked line is a date or "never".
log="$root/raw/sync-log.md"
if [ -f "$log" ]; then
  keys=0
  while IFS= read -r line; do
    line=${line%$'\r'}
    case "$line" in last_checked_*:*) ;; *) continue ;; esac
    keys=$((keys + 1))
    key=${line%%:*}
    val=$(printf '%s' "${line#*:}" | tr -d '[:space:]')
    if [ "$val" = never ]; then
      :
    elif printf '%s' "$val" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' && date -d "$val" >/dev/null 2>&1; then
      :
    else
      fail "\`$key: $val\` in raw/sync-log.md is neither a YYYY-MM-DD date nor \`never\`" "correct the value"
    fi
  done < "$log"
  for k in $instances; do
    grep -q "^last_checked_$k:" "$log" ||
      fail "source \`$k\` has no \`last_checked_$k\` line in raw/sync-log.md" "add \`last_checked_$k: never\`"
  done
  if [ "$keys" -gt 0 ]; then pass "raw/sync-log.md has $keys source line(s)"
  else fail "raw/sync-log.md has no \`last_checked_<source>:\` lines" "add one line per source, value \`never\`"; fi
fi

# 4. .gitignore.
gi="$root/.gitignore"
if [ -f "$gi" ]; then
  for pat in '.obsidian/' '.claude/*' '!.claude/settings.json' ${instances:+'!.claude/sources/'}; do
    if grep -qxF -- "$pat" "$gi"; then pass "\`.gitignore\` has \`$pat\`"
    else fail "\`.gitignore\` lacks \`$pat\`" "add the line \`$pat\`"; fi
  done
fi

# 5. Project settings: plugin enabled, permissions from the template, committed.
st="$root/.claude/settings.json"
if [ ! -f "$st" ]; then
  fail "\`.claude/settings.json\` is missing" "paste the settings shown by /wiki:init, then commit it"
else
  if tr -d '[:space:]' < "$st" | grep -q '"wiki@wiki-tools":true'; then pass "plugin \`wiki@wiki-tools\` is enabled"
  else fail "plugin \`wiki@wiki-tools\` is not enabled" "run \`claude plugin install wiki@wiki-tools --scope project\` in the wiki"; fi
  missing=""
  if [ -f "$template" ]; then
    missing=$(grep -oE '"(mcp__[A-Za-z_]+|Bash\([^"]*\)|Read\([^"]*\))"' "$template" |
      while IFS= read -r rule; do
        grep -qF -- "$rule" "$st" || printf ' %s' "$rule"
      done)
    if [ -z "$missing" ]; then pass "all permission rules from the template are present"
    else fail "permission rules missing from .claude/settings.json:$missing" "paste the settings shown by /wiki:init"; fi
  else
    info "settings template not found at $template; permissions not compared"
  fi
  if [ -n "$instances" ]; then
    missing=$(for k in $instances; do
        c=$(src_contract "$root" "$(src_field "$root/.claude/sources/instances/$k.md" type)" 2>/dev/null) || continue
        src_list "$c" read_tools; src_list "$c" bookkeeping_tools; src_list "$c" forbidden_tools
      done | awk '!seen[$0]++' |
      while IFS= read -r rule; do
        grep -qF -- "\"$rule\"" "$st" || printf ' "%s"' "$rule"
      done)
    if [ -z "$missing" ]; then pass "all permission rules of the sources' types are present"
    else fail "source permission rules missing from .claude/settings.json:$missing" "add them as \`sources.sh settings\` prints (allow: read and bookkeeping tools, deny: forbidden tools)"; fi
  fi
  if tracked .claude/settings.json; then pass "\`.claude/settings.json\` is committed"
  else fail "\`.claude/settings.json\` isn't committed" "\`git add -- .claude/settings.json && git commit\` (you, not Claude)"; fi
fi

# 6. Sources in .claude/sources/: every instance valid, available, committed.
sd="$root/.claude/sources"
if [ -f "$root/.claude/proton-roots" ] && [ ! -f "$sd/instances/proton.md" ]; then
  fail "old source layout: \`.claude/proton-roots\` without \`.claude/sources/instances/proton.md\`" "run /wiki:init (check mode) and follow its migration"
fi
if [ -z "$instances" ]; then
  info "no sources besides \`raw/\` (no files in \`.claude/sources/instances/\`)"
fi
for k in $instances; do
  f=".claude/sources/instances/$k.md"
  t=$(src_field "$root/$f" type)
  if errs=$(src_validate_instance "$root" "$k" 2>&1); then
    pass "source \`$k\` (type $t) is valid"
    c=$(src_contract "$root" "$t")
    src_list "$c" platforms | grep -qx "$(src_platform)" ||
      info "source \`$k\` (type $t) isn't available on $(src_platform); it supports $(src_list "$c" platforms | paste -sd' ' -)"
  else
    fail "source \`$k\` doesn't validate: $(printf '%s' "$errs" | sed "s#$root/##g" | paste -sd';' -)" "correct \`$f\` (you, not Claude)"
  fi
  if tracked "$f"; then pass "\`$f\` is committed"
  else fail "\`$f\` isn't committed" "\`git add -- $f && git commit\` (you, not Claude)"; fi
done
for c in "$sd"/types/*/SOURCE.md; do
  [ -f "$c" ] || continue
  t=${c%/SOURCE.md}; t=${t##*/}
  if errs=$(src_validate_contract "$c" 2>&1); then pass "local source type \`$t\` is valid"
  else fail "local source type \`$t\` doesn't validate: $(printf '%s' "$errs" | sed "s#$root/##g" | paste -sd';' -)" "correct \`.claude/sources/types/$t/\` (you, not Claude)"; fi
  for s in SOURCE.md $(src_list "$c" scripts); do
    tracked ".claude/sources/types/$t/$s" ||
      fail "\`.claude/sources/types/$t/$s\` isn't committed" "\`git add -- .claude/sources/types/$t && git commit\` (you, not Claude)"
  done
done

# 7. Structural lint (errors only; warnings are normal on a young wiki).
if [ -d "$root/wiki" ]; then
  errs=$(cd "$root" && bash "$here/lint.sh" 2>/dev/null | sed -n 's/^Pages: [0-9]*\. Errors: \([0-9]*\)\..*/\1/p')
  case "$errs" in
    0) pass "lint finds no structural errors" ;;
    '') fail "lint.sh didn't run" "run \`bash ~/src/wiki-tools/plugins/wiki/scripts/lint.sh\` and read its error" ;;
    *) fail "lint finds $errs structural error(s)" "run /wiki:lint" ;;
  esac
fi

# 8. Setup files committed.
dirty=$(git -C "$root" status --porcelain -- CLAUDE.md .gitignore raw/sync-log.md wiki/index.md wiki/log.md templates 2>/dev/null)
if [ -z "$dirty" ]; then pass "setup files are committed"
else fail "uncommitted setup files: $(printf '%s' "$dirty" | awk '{print $2}' | paste -sd' ' -)" "review and commit them"; fi

printf '## Wiki check: %s\n\nFailures: %d.\n%s\n' "$(basename "$root")" "$fails" "$out"
[ "$fails" -eq 0 ]
