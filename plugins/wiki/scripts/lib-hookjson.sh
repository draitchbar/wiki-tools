# lib-hookjson.sh: jq-free extraction of Claude Code hook input.
# Source this file; it reads the hook JSON from stdin once.
#
# Sets:
#   HOOK_TOOL       tool_name ("" if absent)
#   HOOK_COMMAND    tool_input.command, unescaped
#   HOOK_FILE       tool_input.file_path, unescaped
#   HOOK_CONTENT    tool_input.content and tool_input.new_string, unescaped
#   HOOK_PARSE_OK   1 if tool_name was found, 0 otherwise
# The "description" field is never read, so prose can't trigger a guard.
#
# Only reliable for the flat, single-object JSON Claude Code sends.

HOOK_RAW=$(cat | tr '\r\n' '  ')

# json_str KEY: print the first string value for KEY, still JSON-escaped.
json_str() {
  printf '%s' "$HOOK_RAW" |
    sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\(\([^\"\\\\]\|\\\\.\)*\)\".*/\1/p" |
    head -n 1
}

# json_unescape: turn JSON string escapes into plain text.
# Escaped newlines become ";" so multi-line commands look chained.
json_unescape() {
  sed -e 's/\\\\/\x01/g' \
      -e 's/\\"/"/g' \
      -e 's/\\\//\//g' \
      -e 's/\\[nr]/;/g' \
      -e 's/\\t/ /g' \
      -e 's/\x01/\\/g'
}

# norm: lowercase and turn backslashes into slashes, for path matching.
norm() {
  printf '%s' "$1" | tr '\\' '/' | tr '[:upper:]' '[:lower:]'
}

HOOK_TOOL=$(json_str tool_name)
HOOK_COMMAND=$(json_str command | json_unescape)
HOOK_FILE=$(json_str file_path | json_unescape)
HOOK_CONTENT="$(json_str content | json_unescape) $(json_str new_string | json_unescape)"

if [ -n "$HOOK_TOOL" ]; then HOOK_PARSE_OK=1; else HOOK_PARSE_OK=0; fi

# block MESSAGE: refuse the tool call (exit 2 blocks PreToolUse).
block() {
  printf 'wiki guard: %s\n' "$1" >&2
  exit 2
}
