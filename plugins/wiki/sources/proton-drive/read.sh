#!/usr/bin/env bash
# read.sh: read-only access to Proton Drive for the wiki skills.
#
#   bash <plugin>/sources/proton-drive/read.sh <key> list     "<remote path>"
#   bash <plugin>/sources/proton-drive/read.sh <key> info     "<remote path>"
#   bash <plugin>/sources/proton-drive/read.sh <key> size     "<remote path>"
#   bash <plugin>/sources/proton-drive/read.sh <key> download "<remote file>"
#   bash <plugin>/sources/proton-drive/read.sh <key> new      "<YYYY-MM-DD|never>"
#
# new walks every root (one list call per folder, about 3 s each) and prints
# one line per file modified on or after the date (UTC), oldest first:
#   <f|p> <YYYY-MM-DD HH:MM> <bytes> <remote path>
# p marks a Proton Doc or Sheet (it can't be downloaded). The JSON is read
# with awk, one node per line; if its shape changes, the wrapper refuses.
#
# Rules:
# - <key> is a proton-drive instance in <wiki>/.claude/sources/instances/.
#   Until a wiki is migrated, key "proton" without an instance file falls
#   back to the old <wiki>/.claude/proton-roots.
# - Only the read operations in READ_OPS are passed to the CLI.
# - Remote paths must sit under one of the instance's roots.
# - Downloads always go to ~/.cache/wiki-sources/<wiki>/<key>/<path below root>.
# - No version pin: any CLI version works as long as its help output still
#   shows the syntax this wrapper relies on (check_syntax below). If Proton
#   changes that syntax, the wrapper refuses until it is reviewed.
#
# Run it from inside a wiki (any directory of its git repo).
# The syntax was recorded in README.md from cli-drive@0.9.0 (16.10.2026).

set -u

. "$(dirname "$0")/../../scripts/lib-source.sh"

READ_OPS="list info size"    # plus "download", handled separately below
CLI=proton-drive

die() { printf 'pd-read: %s\n' "$1" >&2; exit 1; }

[ $# -eq 3 ] || die "usage: read.sh <key> <list|info|size|download> \"<remote path>\" | read.sh <key> new \"<YYYY-MM-DD|never>\""
key=$1
op=$2
remote=$3

# 1. Operation allowlist (checked before anything touches the CLI).
case " $READ_OPS download new " in
  *" $op "*) ;;
  *) die "operation '$op' is not allowed; read-only ops are: $READ_OPS download new" ;;
esac

# 2. Wiki root and the instance's roots.
root=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
wiki=$(basename "$root")
printf '%s' "$key" | grep -Eq "$SRC_NAME_RE" || die "invalid instance key '$key'"
inst="$(src_instance_dir "$root")/$key.md"
if [ -f "$inst" ]; then
  [ "$(src_field "$inst" type)" = proton-drive ] || die "instance '$key' is not a proton-drive instance."
  src_validate_instance "$root" "$key" 2>/dev/null || die "instance file $inst doesn't validate; run /wiki:init to check it."
  roots=$(src_values "$inst" roots)
  where=$inst
elif [ "$key" = proton ] && [ -f "$root/.claude/proton-roots" ]; then
  roots=$(cat "$root/.claude/proton-roots")      # old layout, until migrated
  where="$root/.claude/proton-roots"
else
  die "no instance '$key' ($inst); this wiki has no such Proton access."
fi

# 3. Normalise and check the remote path (for new: the date).
if [ "$op" = new ]; then
  since=$remote
  case "$since" in
    never) since=0000-00-00 ;;
    [0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]) ;;
    *) die "new takes a date YYYY-MM-DD or never, not '$since'." ;;
  esac
else
  case "$remote" in /*) ;; *) die "remote path must be absolute, e.g. /my-files/..." ;; esac
  remote=$(printf '%s' "$remote" | sed -e 's#//*#/#g' -e 's#/$##')
  ! src_has_dots "$remote" || die "'.' and '..' are not allowed in remote paths."
  matched_root=$(printf '%s\n' "$roots" | src_match_root "$remote") ||
    die "'$remote' is outside the Proton roots of '$key' ($where)."
fi

# 4. CLI present and still speaking the syntax this wrapper was written for.
command -v "$CLI" >/dev/null 2>&1 || die "'$CLI' not found on PATH."

check_syntax() { # TEXT EXPECTED...
  text=$1; shift
  for want in "$@"; do
    case "$text" in
      *"$want"*) ;;
      *) die "proton-drive syntax changed (missing '$want'). Re-record the help output in README.md and review read.sh before using it." ;;
    esac
  done
}
check_syntax "$("$CLI" filesystem --help 2>&1)" \
  "filesystem list [-t TYPE] path" "filesystem info path" "filesystem size path"
if [ "$op" = download ]; then
  check_syntax "$("$CLI" filesystem download --help 2>&1)" \
    "filesystem download [-f STRATEGY] [-d STRATEGY] path... localFolder" \
    "--file-conflict-strategy" "remove:"
fi

export PROTON_DRIVE_LOG_LEVEL=WARNING

# nodes PARENT: read `list --json` (or `info --json`) output on stdin, one
# node per line; print "<f|p|d> <modified> <bytes> <PARENT>/<name>" per node.
# Names are JSON-unescaped, and / in a name is escaped as \/ (CLI path rule).
# An unreadable name is reported on stderr and skipped. Exit 3 if a node line
# lacks the fields this parser relies on (the CLI's JSON changed).
# PARENT goes in through the environment: awk -v would process its escapes,
# and gawk 5.3 turns \/ into /.
nodes() {
  PD_PARENT="$1" awk '
    BEGIN { parent = ENVIRON["PD_PARENT"] }
    function str(key,   s) {   # the JSON string after "key":
      if (!match(line, "\"" key "\":\"([^\"\\\\]|\\\\.)*\"")) return ""
      s = substr(line, RSTART + length(key) + 4, RLENGTH - length(key) - 5)
      gsub(/\\\//, "/", s); gsub(/\\"/, "\"", s); gsub(/\\\\/, "\\", s)
      return s
    }
    /^[[:space:]]*\{/ {
      line = $0
      # Drop the name object first so its text cannot fake other fields.
      name = ""
      if (match(line, /"name":\{"ok":true,"value":"([^"\\]|\\.)*"\}/)) {
        name = substr(line, RSTART + 27, RLENGTH - 29)
        gsub(/\\\//, "/", name); gsub(/\\"/, "\"", name); gsub(/\\\\/, "\\", name)
        line = substr(line, 1, RSTART - 1) substr(line, RSTART + RLENGTH)
      } else if (line ~ /"name":\{"ok":false/) {
        print "pd-read: skipped a node whose name cannot be decrypted, in " parent > "/dev/stderr"
        next
      } else { bad = 1; exit }
      type = str("type"); mod = str("modificationTime")
      if (type == "" || mod !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]/) { bad = 1; exit }
      size = 0
      if (match(line, /"claimedSize":[0-9]+/)) size = substr(line, RSTART + 14, RLENGTH - 14)
      else if (match(line, /"totalStorageSize":[0-9]+/)) size = substr(line, RSTART + 19, RLENGTH - 19)
      k = (type == "folder") ? "d" : "f"
      if (str("mediaType") ~ /^application\/vnd\.proton\./) k = "p"
      esc = name; gsub(/\//, "\\/", esc)
      print k " " substr(mod, 1, 10) " " substr(mod, 12, 5) " " size " " parent "/" esc
    }
    END { exit bad ? 3 : 0 }'
}

# 5. Run. Nothing from the caller is passed through except the checked path.
case "$op" in
  new)
    # Breadth-first over the roots; a root naming a single file is checked
    # with info. Folders are always walked (their times don't change when a
    # file inside does); files print when modified on or after the date.
    queue=$(printf '%s\n' "$roots" | sed -e '/^[[:space:]]*$/d' -e '/^#/d' -e 's#//*#/#g' -e 's#/$##')
    out="" walked=0
    while [ -n "$queue" ]; do
      dir=$(printf '%s\n' "$queue" | head -n 1)
      queue=$(printf '%s\n' "$queue" | sed '1d')
      node=$("$CLI" filesystem info --json "$dir" 2>&1) || die "cannot read info for '$dir': $(printf '%s' "$node" | head -c 200)"
      case "$node" in
        *'"type":"folder"'*)
          json=$("$CLI" filesystem list --json "$dir" 2>&1) || die "cannot list '$dir': $(printf '%s' "$json" | head -c 200)"
          walked=$((walked + 1))
          lines=$(printf '%s\n' "$json" | nodes "$dir") || die "the list JSON of '$dir' no longer has the shape this wrapper reads (name, type, modificationTime). Re-record it in README.md and review read.sh."
          ;;
        *)
          lines=$(printf '%s\n' "$node" | nodes "$(dirname "$dir")") || die "the info JSON of '$dir' no longer has the shape this wrapper reads."
          ;;
      esac
      [ -n "$lines" ] || continue
      out="$out
$(printf '%s\n' "$lines" | grep -v '^d ' | awk -v s="$since" '$2 >= s')"
      sub=$(printf '%s\n' "$lines" | sed -n 's/^d [^ ]* [^ ]* [^ ]* //p')
      [ -z "$sub" ] || queue="$queue
$sub"
      queue=$(printf '%s\n' "$queue" | sed '/^$/d')
    done
    printf '%s\n' "$out" | sed '/^$/d' | LC_ALL=C sort -k2,3
    printf 'pd-read: walked %s folders\n' "$walked" >&2
    ;;
  list|info|size)
    exec "$CLI" filesystem "$op" --json "$remote"
    ;;
  download)
    # Single files only: `info --json` reports one top-level "type"
    # ("file" or "folder"); folders have no activeRevision to mimic it.
    node=$("$CLI" filesystem info --json "$remote" 2>&1) || die "cannot read info for '$remote': $node"
    case "$node" in
      *'"type":"folder"'*) die "'$remote' is a folder; list it and download its files one by one." ;;
      *'"type":"file"'*) ;;
      *) die "'$remote' is not a plain file (info: $(printf '%s' "$node" | head -c 200))" ;;
    esac
    if [ "$remote" = "$matched_root" ]; then
      rel=$(basename "$remote")          # the root line names a single file
    else
      rel=${remote#"$matched_root"/}
    fi
    dest_dir="$HOME/.cache/wiki-sources/$wiki/$key"
    [ "$(dirname "$rel")" = . ] || dest_dir="$dest_dir/$(dirname "$rel")"
    mkdir -p "$dest_dir" || die "cannot create $dest_dir"
    # Recorded syntax: download [-f STRATEGY] [-d STRATEGY] path... localFolder.
    # Conflict strategies are always set, because a prompt would hang a
    # non-interactive call: -f remove replaces a stale copy in the cache
    # (local only), -d merge merges a folder into its cached copy.
    "$CLI" filesystem download --json -f remove -d merge "$remote" "$dest_dir" || exit $?
    printf 'pd-read: downloaded to %s/%s\n' "$dest_dir" "$(basename "$rel")"
    ;;
esac
