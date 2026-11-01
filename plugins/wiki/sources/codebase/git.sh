#!/usr/bin/env bash
# git.sh: read-only access to a codebase source (a git clone) for the wiki.
#
#   bash <plugin>/sources/codebase/git.sh <key> status
#   bash <plugin>/sources/codebase/git.sh <key> resolve  <rev>
#   bash <plugin>/sources/codebase/git.sh <key> fetch
#   bash <plugin>/sources/codebase/git.sh <key> grep     <rev> "<regex>" ["<pathspec>"]
#   bash <plugin>/sources/codebase/git.sh <key> igrep    <rev> "<regex>" ["<pathspec>"]
#   bash <plugin>/sources/codebase/git.sh <key> show     <rev> "<path>" [Lx-Ly]
#   bash <plugin>/sources/codebase/git.sh <key> ls       <rev> ["<path>"]
#   bash <plugin>/sources/codebase/git.sh <key> log      <rev> ["<path>" [Lx-Ly]]
#   bash <plugin>/sources/codebase/git.sh <key> blame    <rev> "<path>" Lx-Ly
#   bash <plugin>/sources/codebase/git.sh <key> branches ["<text>"]
#   bash <plugin>/sources/codebase/git.sh <key> contains <rev>
#   bash <plugin>/sources/codebase/git.sh <key> drift    <rev> "<path>" Lx-Ly
#   bash <plugin>/sources/codebase/git.sh <key> verify   <rev> "<path>" Lx-Ly
#   bash <plugin>/sources/codebase/git.sh <key> verify-all <file>
#   bash <plugin>/sources/codebase/git.sh <key> drift-all  <file>
#
# verify-all and drift-all run verify or drift on every citation
# `<path>#L<x>-L<y> @<sha>` in <file>: @<path below the cache folder> (a run's
# answer.md) or a path relative to the wiki (a page). At most 300 citations.
#
# A grep <regex> of the form @<file> names a pattern file below the
# instance's cache folder ~/.cache/wiki-sources/<wiki>/<key>/ (e.g.
# @runs/<run>/p1.txt): one ERE per line, a line matches if any pattern does.
# It carries regexes the guard refuses on a command line (| $ ` ; & < >).
#
# fetch never prompts for credentials. With gh_user set and an https GitHub
# remote, it authenticates with that gh account's token (passed through the
# environment, never on a command line). It records its completion in
# <cache>/last-fetch, which status reads.
#
# <rev> is a commit SHA (7 to 40 hex) or a ref name (origin/main, a tag),
# or "ref" for the instance's ref. Paths are relative to the repository's top
# folder and must lie in the instance's root (which may be a sub-folder).
# Every line that points at code is printed as a citation part:
# `<path>#L<n> @<sha12>`.
#
# Rules:
# - <key> is a codebase instance of this wiki; it names exactly one root,
#   inside a git work tree. Nothing from the caller reaches git except
#   checked values; git runs without pager, external diff or textconv.
# - The only write is `fetch` (remote-tracking refs and objects in .git).
#   No checkout, reset, worktree, clone or anything else that changes the
#   clone or its files.
# - Listings are capped.
#
# Run it from inside a wiki (any directory of its git repo).

set -u

. "$(dirname "$0")/../../scripts/lib-source.sh"

die() { printf 'codebase: %s\n' "$1" >&2; exit 1; }

OPS="status resolve fetch grep igrep show ls log blame branches contains drift verify drift-all verify-all"
GREP_CAP=200
LINE_CAP=300
SHOW_DEFAULT=400
SHOW_MAX=600
LIST_CAP=500
LOG_CAP=50

usage="usage: git.sh <key> <$(printf '%s' "$OPS" | tr ' ' '|')> [args]; see the comment at the top of git.sh"
[ $# -ge 2 ] || die "$usage"
key=$1 op=$2
shift 2

# 1. Operation allowlist and argument counts, before anything touches git.
nargs() { # MIN MAX

  [ "$ARGC" -ge "$1" ] && [ "$ARGC" -le "$2" ] || die "'$op' takes $1 to $2 arguments, got $ARGC. $usage"
}
ARGC=$#
case "$op" in
  status|fetch)      nargs 0 0 ;;
  resolve|contains|verify-all|drift-all) nargs 1 1 ;;
  grep|igrep)        nargs 2 3 ;;
  show)              nargs 2 3 ;;
  ls)                nargs 1 2 ;;
  log)               nargs 1 3 ;;
  branches)          nargs 0 1 ;;
  blame|drift|verify) nargs 3 3 ;;
  *) die "operation '$op' is not allowed; read-only ops are: $OPS" ;;
esac
for a in "$@"; do
  case "$a" in *"
"*) die "arguments may not contain a newline." ;; esac
done

# 2. The instance and its clone.
root_wiki=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
printf '%s' "$key" | grep -Eq "$SRC_NAME_RE" || die "invalid instance key '$key'"
inst="$(src_instance_dir "$root_wiki")/$key.md"
[ -f "$inst" ] || die "no instance '$key' ($inst) in this wiki."
[ "$(src_field "$inst" type)" = codebase ] || die "instance '$key' is not a codebase instance."
src_validate_instance "$root_wiki" "$key" 2>/dev/null || die "instance file $inst doesn't validate; run /wiki:init to check it."
[ "$(src_values "$inst" roots | grep -c .)" -eq 1 ] || die "a codebase instance names exactly one root (the clone or a folder in it)."
root=$(src_expand "$(src_values "$inst" roots)")
[ -d "$root" ] || die "root '$root' of '$key' is not a folder on this machine."
command -v git >/dev/null 2>&1 || die "git not found on PATH."

# git with nothing from the environment that runs programs or pages.
unset GIT_EXTERNAL_DIFF GIT_PAGER PAGER GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
g() { GIT_OPTIONAL_LOCKS=0 git -C "$top" --no-pager -c core.quotepath=off "$@"; }

top=$(git -C "$root" rev-parse --show-toplevel 2>/dev/null) || die "root '$root' is not inside a git work tree."
prefix=$(git -C "$root" rev-parse --show-prefix 2>/dev/null)   # "" or "sub/dir/"
pre=${prefix%/}                                                # "" or "sub/dir"

# The instance's ref: its `ref` parameter, else the remote's default branch.
iref=$(src_field "$inst" ref)
if [ -z "$iref" ]; then
  iref=$(g symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null) || iref=""
  if [ -z "$iref" ]; then
    for r in origin/main origin/master; do
      g rev-parse --verify --quiet "$r^{commit}" >/dev/null && { iref=$r; break; }
    done
  fi
  [ -n "$iref" ] || die "can't tell the default branch; set 'ref' in $inst (e.g. origin/main)."
fi
remote=${iref%%/*}
g remote | grep -qxF -- "$remote" || remote=origin
cache="$HOME/.cache/wiki-sources/$(basename "$root_wiki")/$key"

# 3. Argument checks.
# rev REV: the full commit SHA of a checked revision.
rev() {
  r=$1
  [ "$r" = ref ] && r=$iref
  printf '%s' "$r" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$' || die "'$1' is not a SHA or a plain ref name."
  case "/$r/" in */../*|*/./*|*..*) die "'$1' is not a plain ref name." ;; esac
  g rev-parse --verify --quiet "$r^{commit}" 2>/dev/null || die "'$1' is not a commit in this clone (fetch first?)."
}
# path PATH [glob]: a path relative to the repository top, inside the root.
path_ok() {
  p=$1
  case "$p" in ''|-*|:*|/*|~*|*\\*) die "'$p' must be a path relative to the repository's top folder (no leading -, :, / or ~, no backslashes)." ;; esac
  printf '%s' "$p" | grep -Eq '^[A-Za-z]:' && die "'$p' must be relative to the repository's top folder."
  src_has_dots "$p" && die "'.' and '..' are not allowed in paths."
  p=${p%/}
  if [ "${2:-}" != glob ]; then
    case "$p" in *[*?[]*) die "'$p': wildcards are only allowed in a grep pathspec." ;; esac
  fi
  if [ -n "$pre" ]; then
    case "$p" in "$pre"|"$pre"/*) ;; *) die "'$p' is outside the root of '$key' ($pre/)." ;; esac
  fi
  printf '%s' "$p"
}
# range Lx-Ly: "x y".
range() {
  printf '%s' "$1" | grep -Eq '^L?[0-9]{1,7}(-L?[0-9]{1,7})?$' || die "'$1' is not a line range Lx-Ly."
  x=$(printf '%s' "$1" | sed -E 's/^L?([0-9]+).*/\1/')
  y=$(printf '%s' "$1" | sed -En 's/^L?[0-9]+-L?([0-9]+)$/\1/p')
  y=${y:-$x}
  x=$((10#$x)) y=$((10#$y))
  [ "$x" -ge 1 ] && [ "$y" -ge "$x" ] || die "'$1': the range must start at 1 or later and not end before it starts."
  printf '%s %s' "$x" "$y"
}
blob_of() { g rev-parse --verify --quiet "$1:$2" 2>/dev/null; }
is_blob() { [ "$(g cat-file -t "$1:$2" 2>/dev/null)" = blob ]; }
lines_of() { g cat-file blob "$1:$2" | awk 'END { print NR }'; }
s12() { printf '%s' "$1" | cut -c1-12; }
here() { [ -n "$pre" ] && printf '%s' "$pre" || printf '.'; }

# 4. Run.
case "$op" in
  status)
    head_sha=$(g rev-parse --verify --quiet HEAD 2>/dev/null || echo none)
    branch=$(g symbolic-ref --quiet --short HEAD 2>/dev/null || echo "(detached)")
    dirty=$(g status --porcelain -- "$(here)" 2>/dev/null | grep -c .)
    url=$(g remote get-url "$remote" 2>/dev/null || echo none)
    gh_repo=$(printf '%s' "$url" | sed -En 's#^(https://|ssh://git@|git@)github\.com[:/]([^/]+)/([^/]+)$#\2/\3#p' | sed 's/\.git$//')
    printf 'instance: %s\n' "$key"
    printf 'root: %s (folder %s of %s)\n' "$root" "$(here)" "$top"
    printf 'remote: %s %s%s\n' "$remote" "$url" "${gh_repo:+ (GitHub $gh_repo)}"
    printf 'checkout: %s @ %s, %s\n' "$branch" "$(s12 "$head_sha")" "$([ "$dirty" -eq 0 ] && echo clean || echo "$dirty uncommitted changes in the root")"
    if rsha=$(g rev-parse --verify --quiet "$iref^{commit}" 2>/dev/null); then
      printf 'ref: %s @ %s (%s)\n' "$iref" "$(s12 "$rsha")" "$(g log -1 --format=%cs "$rsha")"
      if [ "$head_sha" != none ]; then
        ab=$(g rev-list --left-right --count "HEAD...$rsha" 2>/dev/null || echo "? ?")
        printf 'checkout vs ref: %s ahead, %s behind\n' "${ab%%[[:space:]]*}" "${ab##*[[:space:]]}"
      fi
    else
      printf 'ref: %s not found (fetch first?)\n' "$iref"
    fi
    if [ "$(g rev-parse --is-shallow-repository 2>/dev/null)" = true ]; then
      sf=$(g rev-parse --git-path shallow)
      case "$sf" in /*|[A-Za-z]:*) ;; *) sf="$top/$sf" ;; esac
      since=$(while IFS= read -r s; do g log -1 --format=%cs "$s" 2>/dev/null; done < "$sf" | LC_ALL=C sort | head -n 1)
      printf 'shallow: yes, history from %s (older log and blame unavailable)\n' "${since:-?}"
    else
      printf 'shallow: no\n'
    fi
    fh=$(g rev-parse --git-path FETCH_HEAD)
    case "$fh" in /*|[A-Za-z]:*) ;; *) fh="$top/$fh" ;; esac
    stamp="$cache/last-fetch"
    if [ -f "$stamp" ]; then
      printf 'last fetch: completed %s\n' "$(head -n 1 "$stamp")"
      if [ -f "$fh" ] && [ "$fh" -nt "$stamp" ]; then
        printf 'fetch: one started %s and has not completed (still running, or it failed)\n' "$(date -r "$fh" '+%Y-%m-%d %H:%M')"
      fi
    elif [ -f "$fh" ]; then
      printf 'last fetch: started %s (completion not recorded)\n' "$(date -r "$fh" '+%Y-%m-%d %H:%M')"
    else
      printf 'last fetch: never\n'
    fi
    ;;
  resolve)
    sha=$(rev "$1") || exit 1
    printf '%s %s (%s, %s)\n' "$1" "$sha" "$(s12 "$sha")" "$(g log -1 --format=%cs "$sha")"
    ;;
  fetch)
    # Never prompt (a prompt hangs a Claude Bash call).
    export GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never GIT_ASKPASS= SSH_ASKPASS=
    url=$(g config --get "remote.$remote.url" 2>/dev/null || echo "")   # as configured, before insteadOf
    user=$(src_field "$inst" gh_user)
    via="the user's git credentials"
    case "$url" in
      https://github.com/*)
        if [ -n "$user" ] && printf '%s' "$user" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_-]{0,38}$' && command -v gh >/dev/null 2>&1 &&
           CODEBASE_GH_TOKEN=$(GH_PROMPT_DISABLED=1 gh auth token -u "$user" 2>/dev/null) && [ -n "$CODEBASE_GH_TOKEN" ]; then
          export CODEBASE_GH_TOKEN
          via="gh account $user"
          # An empty helper first drops the configured ones (e.g. a broken
          # Credential Manager); the token stays in the environment.
          set -- -c credential.helper= -c 'credential.helper=!f() { test "$1" = get && printf "username=x-access-token\npassword=%s\n" "$CODEBASE_GH_TOKEN"; }; f'
        fi ;;
    esac
    t0=$(date '+%Y-%m-%d %H:%M')
    g "$@" fetch --prune --no-tags --no-recurse-submodules --quiet "$remote" ||
      die "fetch from '$remote' failed (using $via; started $t0). git never prompts here: with an https GitHub remote, set gh_user in the instance, or fix the git credentials."
    sha=$(g rev-parse --verify --quiet "$iref^{commit}") || die "fetched, but '$iref' is not found."
    mkdir -p "$cache" && printf '%s, %s @ %s\n' "$(date '+%Y-%m-%d %H:%M')" "$iref" "$(s12 "$sha")" > "$cache/last-fetch"
    printf 'fetched %s (using %s, started %s); %s @ %s (%s)\n' "$remote" "$via" "$t0" "$iref" "$(s12 "$sha")" "$(g log -1 --format=%cs "$sha")"
    ;;
  grep|igrep)
    sha=$(rev "$1") || exit 1
    re=$2
    [ -n "$re" ] && [ "${#re}" -le 500 ] || die "the regex must be 1 to 500 characters."
    if [ $# -eq 3 ]; then spec=$(path_ok "$3" glob) || exit 1; else spec=$(here); fi
    flags="-n -I --no-color -E"
    [ "$op" = igrep ] && flags="$flags -i"
    case "$re" in
      @*)
        pf=${re#@}
        printf '%s' "$pf" | grep -Eq '^[A-Za-z0-9_][A-Za-z0-9._/-]*$' || die "'$re': a pattern file is @<path below $cache/> (letters, digits, . _ - /)."
        src_has_dots "$pf" && die "'.' and '..' are not allowed in a pattern file path."
        [ -f "$cache/$pf" ] || die "pattern file '$cache/$pf' not found."
        set --
        n=0
        while IFS= read -r line || [ -n "$line" ]; do
          line=${line%$'\r'}
          [ -n "$line" ] || continue
          [ "${#line}" -le 500 ] || die "pattern file line $((n + 1)) is longer than 500 characters."
          n=$((n + 1))
          [ "$n" -le 20 ] || die "a pattern file holds at most 20 patterns."
          set -- "$@" -e "$line"
        done < "$cache/$pf"
        [ "$n" -ge 1 ] || die "pattern file '$cache/$pf' has no patterns."
        shown="$n patterns from $pf: $(tr -d '\r' < "$cache/$pf" | grep . | paste -sd'|' -)" ;;
      *) set -- -e "$re"; shown=$re ;;
    esac
    printf '@%s grep %s in %s\n' "$(s12 "$sha")" "$shown" "$spec"
    # shellcheck disable=SC2086
    g grep $flags "$@" "$sha" -- "$spec" 2>/dev/null |
      awk -v cap="$GREP_CAP" -v lcap="$LINE_CAP" '
        { rest = substr($0, index($0, ":") + 1)   # drop "<sha>:"
          i = index(rest, ":"); p = substr(rest, 1, i - 1); rest = substr(rest, i + 1)
          j = index(rest, ":"); ln = substr(rest, 1, j - 1); text = substr(rest, j + 1)
          n++
          if (n <= cap) { if (length(text) > lcap) text = substr(text, 1, lcap) " …"; print p "#L" ln ": " text } }
        END { if (n == 0) print "no matches"; else if (n > cap) print "(" n - cap " more matches not shown; narrow the regex or the path)" }'
    ;;
  show)
    sha=$(rev "$1") || exit 1
    p=$(path_ok "$2") || exit 1
    is_blob "$sha" "$p" || die "'$p' is not a file at $(s12 "$sha") (a folder? use ls)."
    total=$(lines_of "$sha" "$p")
    if [ $# -eq 3 ]; then r=$(range "$3") || exit 1; x=${r% *} y=${r#* }; else x=1 y=$SHOW_DEFAULT; fi
    [ $((y - x + 1)) -le "$SHOW_MAX" ] || die "at most $SHOW_MAX lines per call."
    [ "$y" -le "$total" ] || y=$total
    [ "$x" -le "$total" ] || die "'$p' has only $total lines."
    printf '%s#L%s-L%s @%s (%s lines in the file)\n' "$p" "$x" "$y" "$(s12 "$sha")" "$total"
    g cat-file blob "$sha:$p" | awk -v x="$x" -v y="$y" -v lcap="$LINE_CAP" '
      NR >= x && NR <= y { t = $0; if (length(t) > lcap) t = substr(t, 1, lcap) " …"; printf "%6d  %s\n", NR, t }
      NR > y { exit }'
    [ "$y" -ge "$total" ] || printf '(more: show %s %s L%s-L%s)\n' "$1" "$p" "$((y + 1))" "$((y + SHOW_DEFAULT < total ? y + SHOW_DEFAULT : total))"
    ;;
  ls)
    sha=$(rev "$1") || exit 1
    if [ $# -eq 2 ]; then p=$(path_ok "$2") || exit 1; else p=$(here); fi
    printf '@%s ls %s\n' "$(s12 "$sha")" "$p"
    if [ "$p" = . ]; then t=tree; else t=$(g cat-file -t "$sha:$p" 2>/dev/null) || die "'$p' does not exist at $(s12 "$sha")."; fi
    if [ "$t" = tree ]; then spec="$p/"; [ "$p" = . ] && spec=""; else spec=$p; fi
    g ls-tree -l "$sha" -- ${spec:+"$spec"} |
      awk -v cap="$LIST_CAP" '{ n++; if (n <= cap) { split($0, a, "\t"); split(a[1], m, " "); print (m[2] == "tree" ? "d" : "f") " " m[4] " " a[2] } }
        END { if (n > cap) print "(" n - cap " more entries not shown)" }'
    ;;
  log)
    sha=$(rev "$1") || exit 1
    fmt='%h %cs %an: %s'
    if [ $# -eq 3 ]; then
      p=$(path_ok "$2") || exit 1; r=$(range "$3") || exit 1; set -- $r
      is_blob "$sha" "$p" || die "'$p' is not a file at $(s12 "$sha")."
      printf '@%s log of %s#L%s-L%s\n' "$(s12 "$sha")" "$p" "$1" "$2"
      g log --no-color -s -n "$LOG_CAP" --format="$fmt" -L "$1,$2:$p" "$sha" 2>/dev/null | grep -v '^$'
    elif [ $# -eq 2 ]; then
      p=$(path_ok "$2") || exit 1
      printf '@%s log of %s\n' "$(s12 "$sha")" "$p"
      g log --no-color -n "$LOG_CAP" --format="$fmt" "$sha" -- "$p"
    else
      printf '@%s log of %s\n' "$(s12 "$sha")" "$(here)"
      g log --no-color -n "$LOG_CAP" --format="$fmt" "$sha" -- "$(here)"
    fi
    [ "$(g rev-parse --is-shallow-repository 2>/dev/null)" = true ] && printf '(shallow clone: history stops at the shallow boundary)\n'
    ;;
  blame)
    sha=$(rev "$1") || exit 1; p=$(path_ok "$2") || exit 1; r=$(range "$3") || exit 1; set -- $r
    [ $(($2 - $1 + 1)) -le "$SHOW_MAX" ] || die "at most $SHOW_MAX lines per call."
    is_blob "$sha" "$p" || die "'$p' is not a file at $(s12 "$sha")."
    printf '@%s blame %s#L%s-L%s\n' "$(s12 "$sha")" "$p" "$1" "$2"
    g blame --no-progress --date=short -L "$1,$2" "$sha" -- "$p" | cut -c1-"$LINE_CAP"
    ;;
  branches)
    if [ $# -eq 1 ]; then
      printf '%s' "$1" | grep -Eq '^[A-Za-z0-9._/-]{1,100}$' || die "the filter is a plain text (letters, digits, . _ / -)."
      f=$1
    else
      f=""
    fi
    # refs/remotes/<remote>/HEAD is an alias, not a branch.
    g branch -r --no-color --format='%(refname) %(objectname:short=12) %(committerdate:short)' |
      grep -v '^refs/remotes/[^ ]*/HEAD ' | sed 's#^refs/remotes/##' | grep -F -- "$f" | head -n "$LIST_CAP"
    ;;
  contains)
    sha=$(rev "$1") || exit 1
    b=$(g branch -r --no-color --contains "$sha" --format='%(refname)' | grep -v '/HEAD$' | sed 's#^refs/remotes/##' | head -n 50)
    if [ -n "$b" ]; then printf '%s\n' "$b"; else printf 'unpushed: %s is on no remote branch\n' "$(s12 "$sha")"; fi
    ;;
  verify-all|drift-all)
    # Every citation <path>#L<x>[-L<y>] @<sha> in a file, checked one by one.
    f=$1
    case "$f" in
      @*) pf=${f#@}; base=$cache ;;
      *) pf=$f; base=$root_wiki ;;
    esac
    printf '%s' "$pf" | grep -Eq '^[A-Za-z0-9_][A-Za-z0-9._/ -]*$' || die "'$f': give @<path below $cache/> or a path relative to the wiki."
    src_has_dots "$pf" && die "'.' and '..' are not allowed in the file path."
    [ -f "$base/$pf" ] || die "'$base/$pf' not found."
    one=${op%-all}
    cites=$(tr -d '\r' < "$base/$pf" | grep -oE '[A-Za-z0-9_][A-Za-z0-9_./-]*#L[0-9]{1,7}(-L[0-9]{1,7})? @[0-9a-f]{7,40}' | awk '!s[$0]++')
    [ -n "$cites" ] || { printf 'no citations found in %s\n' "$pf"; exit 0; }
    n=$(printf '%s\n' "$cites" | grep -c .)
    [ "$n" -le 300 ] || die "$n citations in $pf; at most 300 per call."
    bad=0 kinds=""
    while IFS= read -r c; do
      p=${c%%#*} r=${c%% @*} s=${c##*@}
      r=${r#*#}
      res=$(bash "$0" "$key" "$one" "$s" "$p" "$r" 2>&1) || bad=$((bad + 1))
      res=$(printf '%s' "$res" | head -n 1 | sed 's/^codebase: //')
      printf '%s -> %s\n' "$c" "$res"
      kinds="$kinds${res%%[ :]*}
"
    done <<EOF
$cites
EOF
    printf '%s citations: %s\n' "$n" "$(printf '%s' "$kinds" | grep . | LC_ALL=C sort | uniq -c | awk '{ printf "%s%s %s", (NR > 1 ? ", " : ""), $1, $2 }')"
    [ "$bad" -eq 0 ] || exit 1
    ;;
  drift|verify)
    sha=$(rev "$1") || exit 1; p=$(path_ok "$2") || exit 1; r=$(range "$3") || exit 1; x=${r% *} y=${r#* }
    old=$(blob_of "$sha" "$p") && is_blob "$sha" "$p" || { printf 'broken: %s does not exist at %s\n' "$p" "$(s12 "$sha")"; exit 1; }
    total=$(lines_of "$sha" "$p")
    [ "$y" -le "$total" ] || { printf 'broken: %s has %s lines at %s, the citation ends at L%s\n' "$p" "$total" "$(s12 "$sha")" "$y"; exit 1; }
    if [ "$op" = verify ]; then
      printf 'ok: %s#L%s-L%s @%s\n' "$p" "$x" "$y" "$(s12 "$sha")"
      exit 0
    fi
    rsha=$(rev ref) || exit 1
    at="($iref @$(s12 "$rsha"))"
    new=$(blob_of "$rsha" "$p") || new=""
    if [ "$new" = "$old" ]; then
      printf 'unchanged %s\n' "$at"
    elif [ -z "$new" ]; then
      to=$(g diff --no-ext-diff --no-textconv -M --name-status "$sha" "$rsha" -- "$(here)" |
        awk -F'\t' -v p="$p" '$1 ~ /^R/ && $2 == p { print $3; exit }')
      if [ -n "$to" ]; then printf 'renamed %s %s\n' "$to" "$at"; else printf 'deleted %s\n' "$at"; fi
    else
      g diff --no-ext-diff --no-textconv -U0 "$sha" "$rsha" -- "$p" | grep '^@@' |
        awk -v x="$x" -v y="$y" -v at="$at" '
          { split($2, o, ","); split($3, n, ",")
            a = substr(o[1], 2) + 0; b = (o[2] == "") ? 1 : o[2] + 0
            c = substr(n[1], 2) + 0; d = (n[2] == "") ? 1 : n[2] + 0
            if (b == 0) { if (a >= x && a < y) hit = 1; else if (a < x) shift += d }
            else if (a <= y && a + b - 1 >= x) hit = 1
            else if (a + b - 1 < x) shift += d - b }
          END { if (hit) print "changed-overlap " at
                else if (shift != 0) print "moved L" x + shift "-L" y + shift " " at
                else print "changed-elsewhere " at }'
    fi
    ;;
esac
