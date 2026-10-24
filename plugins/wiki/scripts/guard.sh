#!/usr/bin/env bash
# PreToolUse(Bash) and PreToolUse(Write|Edit|MultiEdit): keep the sources
# read-only and keep Claude away from the guard machinery.
#
# What the guard knows about sources comes from the contracts at hook time:
# every standard type (plugins/wiki/sources/*/SOURCE.md), every local type of
# this wiki (.claude/sources/types/*/SOURCE.md) and every instance
# (.claude/sources/instances/*.md). From them it collects:
#   guard_words  words blocked in Bash and in non-Markdown files;
#   scripts      wrapper scripts allowed as a plain `bash <path> <args>` call;
#   roots        of filesystem instances: blocked in Bash, read-only for
#                Write/Edit.
# A source file that can't be read blocks every call (fail closed).
#
# Bash: blocks commands that mention a protected path, a core keyword, a
# guard word or a filesystem root. Exceptions: a plain invocation of one of
# the plugin's core scripts, or of a script a contract lists, with no
# chaining, redirection or substitution.
#
# Write/Edit: blocks writes to protected paths and inside filesystem roots,
# and non-Markdown content that contains a guard word (a helper script
# around a CLI).
#
# This is a guardrail, not a security boundary: an obfuscated command can
# still get through.

. "$(dirname "$0")/lib-hookjson.sh"
. "$(dirname "$0")/lib-source.sh"

[ "$HOOK_PARSE_OK" = 1 ] || block "could not parse hook input; refusing (fail closed)."

# Substrings (lowercase, forward slashes) of protected paths.
PROTECTED_PATHS='wiki-tools/plugins/wiki/scripts
wiki-tools/plugins/wiki/hooks
wiki-tools/plugins/wiki/sources
.claude/sources
.claude/proton-roots
.claude/settings
.claude/plugins/'

# Core Bash-only keywords. proton-drive and proton-roots stay here until the
# wikis have moved to .claude/sources/ (proton-drive is also a guard word of
# the proton-drive type).
PROTECTED_WORDS='proton-drive
hooks.json
proton-roots
claude plugin
disableallhooks'

# Characters that make a command more than one plain call.
NOCHAIN='[^;&|<>`$]'

contains_any() { # TEXT LIST
  printf '%s\n' "$2" | while IFS= read -r needle; do
    [ -n "$needle" ] || continue
    case "$1" in *"$needle"*) echo "$needle"; break ;; esac
  done
}

# The wiki: where the session started, else the repo Claude is in.
wiki_root=""
if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -d "$CLAUDE_PROJECT_DIR" ]; then
  wiki_root=$CLAUDE_PROJECT_DIR
elif [ -n "$HOOK_CWD" ] && [ -d "$HOOK_CWD" ]; then
  wiki_root=$(src_wiki_root "$HOOK_CWD")
fi

broken() { block "source file '$1' can't be read ($2). Fix or remove it yourself, outside Claude; until then every tool call is refused (fail closed)."; }

# Collect guard words from every contract, roots from filesystem instances.
GUARD_WORDS=""
for c in "$SRC_PLUGIN"/sources/*/SOURCE.md ${wiki_root:+"$wiki_root"/.claude/sources/types/*/SOURCE.md}; do
  [ -f "$c" ] || continue
  src_has_fm "$c" || broken "$c" "no frontmatter"
  GUARD_WORDS="$GUARD_WORDS
$(src_list "$c" guard_words | tr '[:upper:]' '[:lower:]')"
done
ROOTS=""
if [ -n "$wiki_root" ]; then
  for k in $(src_instances "$wiki_root"); do
    f="$(src_instance_dir "$wiki_root")/$k.md"
    src_has_fm "$f" || broken "$f" "no frontmatter"
    t=$(src_field "$f" type)
    c=$(src_contract "$wiki_root" "$t" 2>&1) || broken "$f" "$c"
    [ "$(src_field "$c" access)" = filesystem ] || continue
    while IFS= read -r r; do
      [ -n "$r" ] || continue
      # As written, expanded, and with Git Bash's /c/ as c:/ and back.
      x=$(norm "$(src_expand "$r")")
      ROOTS="$ROOTS
$(norm "$r" | sed 's#\(.\)/$#\1#')
$x
$(printf '%s' "$x" | sed -n 's#^/\([a-z]\)/#\1:/#p')
$(printf '%s' "$x" | sed -n 's#^\([a-z]\):/#/\1/#p')"
    done <<EOF
$(src_values "$f" roots)
EOF
  done
fi

# allowed_source_script CMD: true if CMD is a plain call of a script that its
# contract lists. CMD is normalised (lowercase, forward slashes).
allowed_source_script() {
  re='^[[:space:]]*bash[[:space:]]+"?([^[:space:]";&|<>`$]*)(/src/wiki-tools/plugins/wiki/sources|\.claude/sources/types)/([a-z0-9-]+)/([a-z0-9_-]+\.sh)"?([[:space:]]'"$NOCHAIN"'*)?$'
  printf '%s' "$1" | grep -Eq "$re" || return 1
  parts=$(printf '%s' "$1" | sed -E "s#$re#\\1|\\2|\\3|\\4#")
  prefix=${parts%%|*}; rest=${parts#*|}
  kind=${rest%%|*}; rest=${rest#*|}
  t=${rest%%|*}; s=${rest#*|}
  case "$kind" in
    /src/*)
      src_has_dots "$prefix" && return 1
      c="$SRC_PLUGIN/sources/$t/SOURCE.md"
      ;;
    *)
      [ -n "$wiki_root" ] || return 1
      case "$prefix" in ''|.|./|"$(norm "$wiki_root")"/|"$(norm "$wiki_root")") ;; *) return 1 ;; esac
      c="$wiki_root/.claude/sources/types/$t/SOURCE.md"
      ;;
  esac
  [ -f "$c" ] || return 1
  src_list "$c" scripts | tr '[:upper:]' '[:lower:]' | grep -qxF -- "$s"
}

# under_root PATH: the root PATH is in, if any. PATH is normalised.
under_root() {
  printf '%s\n' "$ROOTS" | while IFS= read -r r; do
    [ -n "$r" ] || continue
    case "$1" in "$r"|"$r"/*) echo "$r"; break ;; esac
  done
}

case "$HOOK_TOOL" in
  Bash)
    [ -n "$HOOK_COMMAND" ] || block "Bash call without a command; refusing (fail closed)."
    cmd=$(norm "$HOOK_COMMAND")
    # Allowed: bash [quoted] <path>/src/wiki-tools/plugins/wiki/scripts/<script>.sh [args]
    # with no ; & | < > ` $ anywhere.
    if printf '%s' "$cmd" | grep -Eq '^[[:space:]]*bash[[:space:]]+"?[^[:space:]";&|<>`$]*/src/wiki-tools/plugins/wiki/scripts/(pd-read|ocr|sync-status|lint|wiki-check|sources)\.sh"?([[:space:]][^;&|<>`$]*)?$'; then
      exit 0
    fi
    allowed_source_script "$cmd" && exit 0
    hit=$(contains_any "$cmd" "$PROTECTED_PATHS
$PROTECTED_WORDS
$GUARD_WORDS")
    [ -z "$hit" ] || block "command touches protected '$hit'. Sources are read only through their wrapper scripts; guard and source files are edited by the user."
    hit=$(contains_any "$cmd" "$ROOTS")
    [ -z "$hit" ] || block "command mentions the read-only source folder '$hit'. Use the source's wrapper script (see its SOURCE.md)."
    exit 0
    ;;
  Write|Edit|MultiEdit)
    [ -n "$HOOK_FILE" ] || block "$HOOK_TOOL call without file_path; refusing (fail closed)."
    path=$(norm "$HOOK_FILE")
    hit=$(contains_any "$path" "$PROTECTED_PATHS")
    [ -z "$hit" ] || block "'$HOOK_FILE' is protected ('$hit'). The user edits it themselves."
    hit=$(under_root "$path")
    [ -z "$hit" ] || block "'$HOOK_FILE' is inside the read-only source folder '$hit'."
    case "$path" in
      *.md) ;;
      *)
        hit=$(contains_any "$(norm "$HOOK_CONTENT")" "proton-drive
$GUARD_WORDS")
        [ -z "$hit" ] || block "non-Markdown content calling '$hit' is not allowed; use the source's wrapper script."
        ;;
    esac
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
