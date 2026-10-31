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
# agent_only types (e.g. codebase): their roots are for subagents only. In
# the main session (hook input without agent_id) Read, Grep and Glob on
# them are blocked, and their wrappers run only the contract's main_ops.
#
# This is a guardrail, not a security boundary: an obfuscated command can
# still get through.

. "$(dirname "$0")/lib-hookjson.sh"
. "$(dirname "$0")/lib-source.sh"

[ "$HOOK_PARSE_OK" = 1 ] || block "could not parse hook input; refusing (fail closed)."

# A subagent may read anything the permissions allow; agent_only roots are
# closed to the main session only (see Read|Grep|Glob below).
case "$HOOK_TOOL" in Read|Grep|Glob) [ -z "$HOOK_AGENT_ID" ] || exit 0 ;; esac

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
.claude/settings
.claude/plugins/'

# Core keywords, blocked in shell commands only. Source CLIs come from the
# contracts' guard_words (e.g. proton-drive), read on every call.
PROTECTED_WORDS='hooks.json
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

# root_forms INSTANCE: each root of the instance as written, expanded, and
# with Git Bash's /c/ as c:/ and back; a ~ also as PowerShell's $home and
# $env:userprofile. Normalised, one per line.
root_forms() {
  src_values "$1" roots | while IFS= read -r r; do
    [ -n "$r" ] || continue
    x=$(norm "$(src_expand "$r")")
    w=$(norm "$r" | sed 's#\(.\)/$#\1#')
    printf '%s\n' "$w" "$x"
    printf '%s\n' "$w" | sed -n 's#^~/#$home/#p'
    printf '%s\n' "$w" | sed -n 's#^~/#$env:userprofile/#p'
    printf '%s\n' "$x" | sed -n 's#^/\([a-z]\)/#\1:/#p'
    printf '%s\n' "$x" | sed -n 's#^\([a-z]\):/#/\1/#p'
  done
}

# abs_path PATH: PATH with ~ expanded, made absolute against the hook's cwd,
# "." and ".." segments folded, so a relative Read can't slip past a root.
# Normalised.
abs_path() {
  p=$(norm "$(src_expand "$1")")
  [ -n "$p" ] || return 0
  if ! src_is_abs "$p"; then p="$(norm "$HOOK_CWD")/$p"; fi
  printf '%s' "$p" | awk -F/ '{
    n = 0
    for (i = 1; i <= NF; i++) {
      if ($i == "" && i > 1) continue
      if ($i == ".") continue
      if ($i == "..") { if (n > 1) n--; continue }
      s[++n] = $i
    }
    out = s[1]; for (i = 2; i <= n; i++) out = out "/" s[i]
    print (out == "" ? "/" : out)
  }'
}

# Read, Grep, Glob: only the roots of agent_only types matter (e.g.
# codebase), and only for the main session; a subagent's call carries
# agent_id. Decided here, before the full scan of every source file, so the
# hook stays cheap on every read. A broken source file doesn't block reads.
case "$HOOK_TOOL" in
  Read|Grep|Glob)
    [ -n "$wiki_root" ] || exit 0
    # Two greps instead of parsing every file: the agent_only types, then
    # the instances of those types.
    # [[:space:]] also takes the CR of a CRLF line.
    types=$(grep -l -E '^agent_only:[[:space:]]*yes[[:space:]]*$' "$SRC_PLUGIN"/sources/*/SOURCE.md "$wiki_root"/.claude/sources/types/*/SOURCE.md 2>/dev/null |
      sed 's#/SOURCE.md$##; s#.*/##' | grep -E "$SRC_NAME_RE" | paste -sd'|' -)
    [ -n "$types" ] || exit 0
    AGENT_ROOTS=""
    for f in $(grep -l -E "^type:[[:space:]]*($types)[[:space:]]*\$" "$(src_instance_dir "$wiki_root")"/*.md 2>/dev/null); do
      AGENT_ROOTS="$AGENT_ROOTS
$(root_forms "$f")"
    done
    [ -n "$(printf '%s' "$AGENT_ROOTS" | tr -d '[:space:]')" ] || exit 0
    for v in "$HOOK_FILE" "$HOOK_PATH"; do
      [ -n "$v" ] || continue
      a=$(abs_path "$v")
      hit=$(printf '%s\n' "$AGENT_ROOTS" | while IFS= read -r r; do
        [ -n "$r" ] || continue
        case "$a" in "$r"|"$r"/*) echo "$r"; break ;; esac
      done)
      [ -z "$hit" ] || block "'$v' is in '$hit', a source only subagents may read (agent_only). Dispatch an agent, as /wiki:research does."
    done
    # Glob and Grep patterns may carry a path of their own.
    hit=$(contains_any "$(norm "$HOOK_PATTERN")" "$AGENT_ROOTS")
    [ -z "$hit" ] || block "the pattern names '$hit', a source only subagents may read (agent_only). Dispatch an agent, as /wiki:research does."
    exit 0
    ;;
esac

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
    ROOTS="$ROOTS
$(root_forms "$f")"
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
  c="" name=""
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
      scripts/ocr.sh|scripts/sync-status.sh|scripts/lint.sh|scripts/wiki-check.sh|scripts/sources.sh|scripts/decode-download.sh) return 0 ;;
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

# main_session_op CMD: the operation of a wrapper call `bash <script> <key>
# <op> ...` (its third word), quotes removed. CMD is normalised.
main_session_op() {
  printf '%s' "$1" | sed -E 's#^[[:space:]]*bash[[:space:]]+("[^"]+"|[^[:space:]]+)##' |
    awk '{ print $2 }' | tr -d '"'"'"
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
      if allowed_script "$cmd"; then
        # An agent_only type's wrapper: the main session may call only the
        # operations its contract lists under main_ops.
        if [ -z "$HOOK_AGENT_ID" ] && [ "$(src_field "$c" agent_only)" = yes ]; then
          wop=$(main_session_op "$cmd")
          src_list "$c" main_ops | tr '[:upper:]' '[:lower:]' | grep -qxF -- "$wop" ||
            block "'${wop:-?}' of $name reads the source itself; only subagents may (the main session may call: $(src_list "$c" main_ops | paste -sd' ' -)). Dispatch an agent, as /wiki:research does."
        fi
        exit 0
      fi
      # The wikis' settings allow wrappers by wildcard (bash */sources/<type>/
      # <script>.sh *), so a lookalike outside the plugin must not run.
      s=$(script_path "$cmd") && case "$s" in
        */sources/*/*.sh|*/scripts/ocr.sh|*/scripts/sync-status.sh|*/scripts/lint.sh|*/scripts/wiki-check.sh|*/scripts/sources.sh|*/scripts/decode-download.sh)
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
        hit=$(contains_any "$(norm "$HOOK_CONTENT")" "$GUARD_WORDS")
        [ -z "$hit" ] || block "non-Markdown content calling '$hit' is not allowed; use the source's wrapper script."
        ;;
    esac
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
