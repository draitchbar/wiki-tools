#!/usr/bin/env bash
# install-source-file.sh: the user installs one file into a wiki's
# protected .claude/sources/ tree, after checking it.
#
#   bash <plugin>/scripts/install-source-file.sh instances/<key>.md
#   bash <plugin>/scripts/install-source-file.sh types/<type>/<file>
#
# Run it in a terminal outside Claude, from inside the wiki. Paste the file's
# content, end with Ctrl-D. The script then:
#   1. checks the file in a scratch copy of .claude/sources/ (frontmatter,
#      key matches the file name, the type exists, required parameters,
#      roots of filesystem instances, the contract of a local type) and
#      re-checks every instance, so one file can't break another;
#   2. shows the diff against the current file and asks before writing;
#   3. prints the settings rules (.claude/settings.json) the source types
#      need that are still missing.
# It never touches git: commit the installed files yourself.
#
# Claude can't run it: the guard blocks every command that names the
# plugin folder except its listed scripts, and the script refuses to run
# inside a Claude Code session.
#
# Environment (for tests only): WIKI_INSTALL_ANSWER=y|n answers the prompt.

set -u

. "$(dirname "$0")/lib-source.sh"

die() { printf 'install-source-file: %s\n' "$1" >&2; exit 1; }

[ -z "${CLAUDECODE:-}" ] || die "run this in a terminal outside Claude; it writes protected files."
[ $# -eq 1 ] || die "usage: install-source-file.sh <instances/<key>.md | types/<type>/<file>>"

target=${1#./}
target=${target#.claude/sources/}
case "$target" in
  instances/*.md)
    key=${target#instances/}; key=${key%.md}
    printf '%s' "$key" | grep -Eq "$SRC_NAME_RE" || die "instance key '$key' must be kebab-case (a-z, 0-9, -)."
    kind=instance
    ;;
  types/*/*)
    rest=${target#types/}
    type=${rest%%/*}; name=${rest#*/}
    printf '%s' "$type" | grep -Eq "$SRC_NAME_RE" || die "type name '$type' must be kebab-case."
    printf '%s' "$name" | grep -Eq '^[A-Za-z0-9_][A-Za-z0-9_.-]*$' || die "file name '$name' must be a plain name in types/$type/ (no subfolders)."
    [ -f "$SRC_PLUGIN/sources/$type/SOURCE.md" ] && die "'$type' is a standard type; a local type can't use its name."
    kind=type
    ;;
  *)
    die "target must be instances/<key>.md or types/<type>/<file>, relative to .claude/sources/."
    ;;
esac

root=$(src_wiki_root) || die "not inside a git repo; run it from the wiki."
[ -f "$root/CLAUDE.md" ] || die "$root has no CLAUDE.md; run it from the wiki."
dest="$root/.claude/sources/$target"

scratch=$(mktemp -d) || die "cannot create a temp dir"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/wiki/.claude/sources"
[ -d "$root/.claude/sources" ] && cp -R "$root/.claude/sources/." "$scratch/wiki/.claude/sources/"

if [ -t 0 ]; then
  printf 'Paste the content of .claude/sources/%s, then press Ctrl-D on an empty line:\n' "$target" >&2
fi
new="$scratch/wiki/.claude/sources/$target"
mkdir -p "$(dirname "$new")"
tr -d '\r' > "$new"
[ -s "$new" ] || die "nothing pasted; nothing installed."
# A final newline, so the file ends cleanly whatever the paste did.
[ -z "$(tail -c 1 "$new")" ] || printf '\n' >> "$new"

# 1. Check, in the scratch copy.
errs="" warns=""
# A contract may list scripts not installed yet (contract first, then its
# scripts): that is a warning, everything else an error.
add_err() {
  local l
  while IFS= read -r l; do
    [ -n "$l" ] || continue
    case "$l" in
      *"is listed but missing"*) case "$warns" in *"$l"*) ;; *) warns="$warns
  - $l (install it next)" ;; esac ;;
      *) errs="$errs
  - $l" ;;
    esac
  done <<EOF
$1
EOF
}
if [ "$kind" = instance ]; then
  src_has_fm "$new" || add_err "no frontmatter: the file must start with a line '---' and close the block with another '---' (first line pasted: \"$(head -n 1 "$new" | cut -c1-60)\")"
else
  case "$name" in
    SOURCE.md)
      e=$(src_validate_contract "$new" 2>&1) || add_err "$(printf '%s' "$e" | sed "s#$scratch/wiki/##g")"
      ;;
    *)
      c="$scratch/wiki/.claude/sources/types/$type/SOURCE.md"
      [ -f "$c" ] || add_err "types/$type/SOURCE.md doesn't exist yet; install the contract first."
      case "$name" in
        *.sh) [ ! -f "$c" ] || src_list "$c" scripts | grep -qxF -- "$name" ||
                add_err "$name isn't listed under scripts: in types/$type/SOURCE.md, so the guard won't let Claude run it." ;;
      esac
      ;;
  esac
fi
# Every instance must still validate (the new file included).
for k in $(src_instances "$scratch/wiki"); do
  f="$scratch/wiki/.claude/sources/instances/$k.md"
  e=$(src_validate_instance "$scratch/wiki" "$k" 2>&1) || { add_err "$(printf '%s' "$e" | sed "s#$scratch/wiki/##g")"; continue; }
  c=$(src_contract "$scratch/wiki" "$(src_field "$f" type)")
  if [ "$(src_field "$c" access)" = filesystem ] && [ -z "$(src_values "$f" roots)" ]; then
    add_err ".claude/sources/instances/$k.md: a filesystem instance needs roots"
  fi
done
[ -z "$errs" ] || die "not installed; fix these and run it again:$errs"
[ -z "$warns" ] || printf "Note:%s\n" "$warns"

# 2. Diff and confirm.
if [ -f "$dest" ]; then
  if cmp -s "$dest" "$new"; then
    printf 'install-source-file: .claude/sources/%s is already exactly this; nothing to do.\n' "$target"
    exit 0
  fi
  printf '\nChanges to .claude/sources/%s:\n' "$target"
  diff -u "$dest" "$new" | sed -e "1s#.*#--- current#" -e "2s#.*#+++ pasted#"
else
  printf '\nNew file .claude/sources/%s:\n' "$target"
  sed 's/^/  /' "$new"
fi
printf '\nInstall it? [y/N] '
if [ -n "${WIKI_INSTALL_ANSWER:-}" ]; then
  answer=$WIKI_INSTALL_ANSWER; printf '%s\n' "$answer"
elif [ -r /dev/tty ]; then
  read -r answer < /dev/tty || answer=""
else
  answer=""
fi
case "$answer" in y|Y|yes|Yes) ;; *) printf 'Not installed.\n'; exit 1 ;; esac

mkdir -p "$(dirname "$dest")" || die "cannot create $(dirname "$dest")"
cp "$new" "$dest" || die "cannot write $dest"
printf 'Installed .claude/sources/%s.\n' "$target"

# 3. Settings rules the wiki's source types need that settings.json lacks.
settings="$root/.claude/settings.json"
missing() { # LIST-OF-RULES: those not quoted in settings.json
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    [ -f "$settings" ] && grep -qF -- "\"$r\"" "$settings" && continue
    printf '      "%s",\n' "$r"
  done
}
types=$(for k in $(src_instances "$root"); do src_field "$(src_instance_dir "$root")/$k.md" type; done | LC_ALL=C sort -u)
allow="" deny=""
for t in $types; do
  c=$(src_contract "$root" "$t" 2>/dev/null) || continue
  allow="$allow
$(printf '%s\n%s\n' "$(src_list "$c" read_tools)" "$(src_list "$c" bookkeeping_tools)" | missing)"
  deny="$deny
$(src_list "$c" forbidden_tools | missing)"
done
allow=$(printf "%s\n" "$allow" | grep -v "^$" | awk "!seen[\$0]++")
deny=$(printf "%s\n" "$deny" | grep -v "^$" | awk "!seen[\$0]++")
if [ -n "$allow$deny" ]; then
  printf '\n.claude/settings.json still lacks rules these sources need. Add them by hand:\n'
  [ -z "$allow" ] || printf '  under "permissions" -> "allow":\n%s\n' "$allow"
  [ -z "$deny" ] || printf '  under "permissions" -> "deny":\n%s\n' "$deny"
fi
printf '\nWhen all files are in, commit them yourself, e.g.\n  git add -- .claude/sources/%s && git commit -m "Add source files"\n' "$target"
