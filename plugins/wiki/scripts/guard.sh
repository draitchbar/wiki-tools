#!/usr/bin/env bash
# PreToolUse(Bash|PowerShell) and PreToolUse(Write|Edit|MultiEdit): keep the sources
# read-only and keep Claude away from the guard machinery.
#
# What the guard knows about sources comes from the contracts at hook time:
# every standard type (plugins/wiki/sources/*/SOURCE.md), every local type of
# this wiki (.claude/sources/types/*/SOURCE.md) and every instance
# (.claude/sources/instances/*.md). From them it collects:
#   guard_words  words blocked in shell commands and in non-Markdown files;
#   scripts      wrapper scripts allowed as a plain `bash <path> <args>` call;
#   roots        of filesystem instances: blocked in shell commands,
#                read-only for Write/Edit.
# A source file that can't be used (no frontmatter, unknown type, a
# filesystem instance without roots) blocks every shell command and
# Write/Edit call (fail closed), except read-only diagnostics: git
# status/log/diff/show and sources.sh list/show.
#
# Bash and PowerShell: block commands that mention a protected path, a core
# keyword, a guard word or a filesystem root. Exceptions (Bash only, since the
# scripts run in Git Bash): a plain invocation of one of the plugin's core
# scripts, or of a script a contract lists, with no chaining, redirection or
# substitution.
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

# Core keywords, blocked in shell commands only. proton-drive and proton-roots stay here until the
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

# A source file the guard can't read: remember the first one. Bash and
# Write/Edit are then refused, except the read-only diagnostics below.
BROKEN=""
broken() { # FILE REASON
  [ -z "$BROKEN" ] || return 0
  BROKEN="source file '$1' can't be used: $2. Until it is fixed, shell commands and Write/Edit are refused (fail closed), except git status/log/diff/show and sources.sh list/show; Read still works on the file. The user fixes it with install-source-file.sh or an editor, outside Claude."
}
first_line() { printf 'its first line is "%s"' "$(head -n 1 "$1" 2>/dev/null | tr -d '\r' | cut -c1-60)"; }

# Collect guard words from every contract, roots from filesystem instances.
GUARD_WORDS=""
for c in "$SRC_PLUGIN"/sources/*/SOURCE.md ${wiki_root:+"$wiki_root"/.claude/sources/types/*/SOURCE.md}; do
  [ -f "$c" ] || continue
  src_has_fm "$c" || { broken "$c" "no frontmatter block ($(first_line "$c"))"; continue; }
  GUARD_WORDS="$GUARD_WORDS
$(src_list "$c" guard_words | tr '[:upper:]' '[:lower:]')"
done
ROOTS=""
if [ -n "$wiki_root" ]; then
  for k in $(src_instances "$wiki_root"); do
    f="$(src_instance_dir "$wiki_root")/$k.md"
    src_has_fm "$f" || { broken "$f" "no frontmatter block ($(first_line "$f"))"; continue; }
    t=$(src_field "$f" type)
    c=$(src_contract "$wiki_root" "$t" 2>&1) || { broken "$f" "$c"; continue; }
    [ "$(src_field "$c" access)" = filesystem ] || continue
    # The guard can't protect folders it can't read.
    [ -n "$(src_values "$f" roots)" ] || { broken "$f" "a filesystem instance (type $t) with no roots"; continue; }
    while IFS= read -r r; do
      [ -n "$r" ] || continue
      # As written, expanded, and with Git Bash's /c/ as c:/ and back; a ~
      # also as PowerShell's $home and $env:userprofile.
      x=$(norm "$(src_expand "$r")")
      w=$(norm "$r" | sed 's#\(.\)/$#\1#')
      ROOTS="$ROOTS
$w
$(printf '%s' "$w" | sed -n 's#^~/#$home/#p')
$(printf '%s' "$w" | sed -n 's#^~/#$env:userprofile/#p')
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

# diagnostic_ok CMD: read-only calls allowed while a source file is broken:
# a plain git status/log/diff/show (no --output) or sources.sh list/show.
diagnostic_ok() {
  case "$1" in *--output*) return 1 ;; esac
  printf '%s' "$1" | grep -Eq '^[[:space:]]*git[[:space:]]+(status|log|diff|show)([[:space:]]'"$NOCHAIN"'*)?$' && return 0
  printf '%s' "$1" | grep -Eq '^[[:space:]]*bash[[:space:]]+"?[^[:space:]";&|<>`$]*/src/wiki-tools/plugins/wiki/scripts/sources\.sh"?[[:space:]]+(list|show)([[:space:]]'"$NOCHAIN"'*)?$'
}

# under_root PATH: the root PATH is in, if any. PATH is normalised.
under_root() {
  printf '%s\n' "$ROOTS" | while IFS= read -r r; do
    [ -n "$r" ] || continue
    case "$1" in "$r"|"$r"/*) echo "$r"; break ;; esac
  done
}

case "$HOOK_TOOL" in
  Bash|PowerShell)
    [ -n "$HOOK_COMMAND" ] || block "$HOOK_TOOL call without a command; refusing (fail closed)."
    cmd=$(norm "$HOOK_COMMAND")
    if [ -n "$BROKEN" ]; then
      diagnostic_ok "$cmd" && exit 0
      block "$BROKEN"
    fi
    if [ "$HOOK_TOOL" = Bash ]; then
      # Allowed: bash [quoted] <path>/src/wiki-tools/plugins/wiki/scripts/<script>.sh [args]
      # with no ; & | < > ` $ anywhere.
      if printf '%s' "$cmd" | grep -Eq '^[[:space:]]*bash[[:space:]]+"?[^[:space:]";&|<>`$]*/src/wiki-tools/plugins/wiki/scripts/(pd-read|ocr|sync-status|lint|wiki-check|sources|decode-download)\.sh"?([[:space:]][^;&|<>`$]*)?$'; then
        exit 0
      fi
      allowed_source_script "$cmd" && exit 0
      ps=""
    else
      ps=" The wiki's scripts run only through the Bash tool (Git Bash), not PowerShell."
    fi
    hit=$(contains_any "$cmd" "$PROTECTED_PATHS
$PROTECTED_WORDS
$GUARD_WORDS")
    [ -z "$hit" ] || block "command touches protected '$hit'. Sources are read only through their wrapper scripts; guard and source files are edited by the user.$ps"
    hit=$(contains_any "$cmd" "$ROOTS")
    [ -z "$hit" ] || block "command mentions the read-only source folder '$hit'. Use the source's wrapper script (see its SOURCE.md)."
    exit 0
    ;;
  Write|Edit|MultiEdit)
    [ -n "$HOOK_FILE" ] || block "$HOOK_TOOL call without file_path; refusing (fail closed)."
    [ -z "$BROKEN" ] || block "$BROKEN"
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
