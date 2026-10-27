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

# The plugin folder this guard runs from, in every spelling a command may use:
# as Git Bash writes it (/c/...), as Claude Code substitutes it on Windows
# (c:/...), and with ~ for $HOME. Lowercase, forward slashes.
p=$(norm "$SRC_PLUGIN")
h=$(norm "${HOME:-}")
PLUGIN_FORMS="$p
$(printf '%s' "$p" | sed -n 's#^/\([a-z]\)/#\1:/#p')
$(printf '%s' "$p" | sed -n 's#^\([a-z]\):/#/\1/#p')"
if [ -n "$h" ]; then
  PLUGIN_FORMS="$PLUGIN_FORMS
$(printf '%s\n' "$PLUGIN_FORMS" | while IFS= read -r f; do
    for hf in "$h" "$(printf '%s' "$h" | sed -n 's#^/\([a-z]\)/#\1:/#p')" "$(printf '%s' "$h" | sed -n 's#^\([a-z]\):/#/\1/#p')"; do
      [ -n "$f" ] && [ -n "$hf" ] && case "$f" in "$hf"/*) echo "~/${f#"$hf"/}" ;; esac
    done
  done)"
fi

# Substrings (lowercase, forward slashes) of protected paths: the plugin's
# scripts, hooks and sources wherever it is installed, and any clone of it.
PROTECTED_PATHS="$(printf '%s\n' "$PLUGIN_FORMS" | while IFS= read -r f; do
  [ -n "$f" ] && printf '%s/scripts\n%s/hooks\n%s/sources\n' "$f" "$f" "$f"
done)
plugins/wiki/scripts
plugins/wiki/hooks
plugins/wiki/sources"'
.claude/sources
.claude/proton-roots
.claude/settings
.claude/plugins/'

# Core keywords, blocked in shell commands only. proton-drive and
# proton-roots stay here until the wikis have moved to .claude/sources/
# (proton-drive is also a guard word of the proton-drive type).
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

# script_path CMD: the script of a plain `bash <script> [args]` call (the path
# may be in double quotes), with no ; & | < > ` $ anywhere and no "..".
# CMD is normalised (lowercase, forward slashes).
script_path() {
  printf '%s' "$1" | grep -q "^$NOCHAIN*\$" || return 1
  s=$(printf '%s' "$1" | sed -En 's#^[[:space:]]*bash[[:space:]]+"([^"]+)"([[:space:]].*)?$#\1#p; t; s#^[[:space:]]*bash[[:space:]]+([^[:space:]"]+)([[:space:]].*)?$#\1#p')
  [ -n "$s" ] || return 1
  s=${s#./}
  src_has_dots "$s" && return 1
  printf '%s' "$s"
}

# allowed_script CMD: true if CMD is a plain call of one of the plugin's core
# scripts, of a standard type's listed script, or of a listed script of one
# of this wiki's local types.
allowed_script() {
  s=$(script_path "$1") || return 1
  rel=""
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    case "$s" in "$f"/*) rel=${s#"$f"/}; break ;; esac
  done <<EOF
$PLUGIN_FORMS
EOF
  if [ -n "$rel" ]; then
    case "$rel" in
      scripts/pd-read.sh|scripts/ocr.sh|scripts/sync-status.sh|scripts/lint.sh|scripts/wiki-check.sh|scripts/sources.sh|scripts/decode-download.sh) return 0 ;;
      sources/*/*.sh) c="$SRC_PLUGIN/sources/$(printf '%s' "$rel" | cut -d/ -f2)/SOURCE.md" ;;
      *) return 1 ;;
    esac
  else
    [ -n "$wiki_root" ] || return 1
    w=$(norm "$wiki_root")
    rel=$s
    for pre in "$w/" "$(printf '%s' "$w" | sed -n 's#^/\([a-z]\)/#\1:/#p')/" "$(printf '%s' "$w" | sed -n 's#^\([a-z]\):/#/\1/#p')/" ./; do
      [ "$pre" != / ] || continue
      case "$s" in "$pre"*) rel=${s#"$pre"}; break ;; esac
    done
    case "$rel" in .claude/sources/types/*/*.sh) ;; *) return 1 ;; esac
    c="$wiki_root/.claude/sources/types/$(printf '%s' "$rel" | cut -d/ -f4)/SOURCE.md"
  fi
  name=${rel##*/}
  [ "$(printf '%s' "$rel" | tr -cd / | wc -c)" -eq "$(case "$rel" in sources/*) echo 2 ;; *) echo 4 ;; esac)" ] || return 1
  printf '%s' "$name" | grep -Eq '^[a-z0-9_-]+\.sh$' || return 1
  [ -f "$c" ] || return 1
  src_list "$c" scripts | tr '[:upper:]' '[:lower:]' | grep -qxF -- "$name"
}

# diagnostic_ok CMD: read-only calls allowed while a source file is broken:
# a plain git status/log/diff/show (no --output) or sources.sh list/show.
diagnostic_ok() {
  case "$1" in *--output*) return 1 ;; esac
  printf '%s' "$1" | grep -Eq '^[[:space:]]*git[[:space:]]+(status|log|diff|show)([[:space:]]'"$NOCHAIN"'*)?$' && return 0
  allowed_script "$1" || return 1
  case "$(script_path "$1")" in */scripts/sources.sh) ;; *) return 1 ;; esac
  printf '%s' "$1" | grep -Eq 'sources\.sh"?[[:space:]]+(list|show)([[:space:]]'"$NOCHAIN"'*)?$'
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
      allowed_script "$cmd" && exit 0
      # The wikis' settings allow wrappers by wildcard (bash */sources/<type>/
      # <script>.sh *), so a lookalike outside the plugin must not run.
      s=$(script_path "$cmd") && case "$s" in
        */sources/*/*.sh|*/scripts/pd-read.sh|*/scripts/ocr.sh|*/scripts/sync-status.sh|*/scripts/lint.sh|*/scripts/wiki-check.sh|*/scripts/sources.sh|*/scripts/decode-download.sh)
          block "'$s' is not this plugin's copy or not a script its contract lists. Run the wiki's scripts from the plugin folder the skills name." ;;
      esac
      ps=""
    else
      ps=" The wiki's scripts run only through the Bash tool (Git Bash), not PowerShell."
    fi
    # The plugin folder itself is off limits in commands (also as x/../),
    # apart from the plain script calls above.
    hit=$(contains_any "$cmd" "$PROTECTED_PATHS
$PLUGIN_FORMS
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
