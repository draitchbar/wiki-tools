#!/usr/bin/env bash
# git.sh: read-only access to a codebase source (a git clone) for the wiki.
#
#   bash <plugin>/sources/codebase/git.sh <key> status
#   bash <plugin>/sources/codebase/git.sh <key> resolve  <rev>
#   bash <plugin>/sources/codebase/git.sh <key> fetch
#   bash <plugin>/sources/codebase/git.sh <key> grep     <rev> "<regex>" ["<pathspec>" ...]
#   bash <plugin>/sources/codebase/git.sh <key> igrep    <rev> "<regex>" ["<pathspec>" ...]
#   (grep and igrep also take -e "<regex>" -e "<regex>" ... for <regex>:
#   a line matches if any does; at most 20. Up to 10 pathspecs; no other
#   flags: igrep is the case-insensitive grep)
#   bash <plugin>/sources/codebase/git.sh <key> show     <rev> "<path>" [Lx-Ly]
#   bash <plugin>/sources/codebase/git.sh <key> ls       <rev> ["<path>"]
#   bash <plugin>/sources/codebase/git.sh <key> log      <rev> ["<path>" [Lx-Ly]]
#   bash <plugin>/sources/codebase/git.sh <key> blame    <rev> "<path>" Lx-Ly
#   bash <plugin>/sources/codebase/git.sh <key> branches ["<text>"]
#   bash <plugin>/sources/codebase/git.sh <key> contains <rev>
#   bash <plugin>/sources/codebase/git.sh <key> drift    <rev> "<path>" Lx-Ly
#   bash <plugin>/sources/codebase/git.sh <key> verify   <rev> "<path>" Lx-Ly
#   bash <plugin>/sources/codebase/git.sh <key> verify-all <file> [--all]
#   bash <plugin>/sources/codebase/git.sh <key> drift-all  <file> [--all]
#
# verify-all and drift-all run verify or drift on every citation
# `<path>#L<x>-L<y> @<sha>` in <file>: @<path below the cache folder> (a run's
# answer.md) or a path relative to the wiki (a page). At most 300 citations.
# They print only results other than ok/unchanged (all with --all) and a
# tally; drift-all also prints when the ref was last fetched.
#
# A grep <regex> of the form @<file> names a pattern file below the
# instance's cache folder ~/.cache/wiki-sources/<wiki>/<key>/ (e.g.
# @runs/<run>/p1.txt): one ERE per line, a line matches if any pattern does.
# It carries regexes the guard refuses on a command line (| $ ` ; & < >).
# For a regex that starts with @, pass it with -e (-e @Override).
#
# fetch never prompts for credentials. With gh_user set and an https GitHub
# remote, it authenticates with that gh account's token (passed through the
# environment, never on a command line). One fetch runs at a time: while it
# runs, <cache>/fetch-running holds its PID and start time; at the end it
# records its completion in <cache>/last-fetch, or a failure in
# <cache>/fetch-failed. status reports all three, a marker whose process is
# gone (or older than FETCH_MAX_AGE) as stale, and a fetch by anything else
# (FETCH_HEAD newer than last-fetch) as outside git.sh.
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

# Builtins wherever bash can do the work: every process start costs ~25 ms
# in Git Bash.
here_dir=${0%/*}
[ "$here_dir" != "$0" ] || here_dir=.
. "$here_dir/../../scripts/lib-source.sh"

die() { printf 'codebase: %s\n' "$1" >&2; exit 1; }

OPS="status resolve fetch grep igrep show ls log blame branches contains drift verify drift-all verify-all"
GREP_CAP=200
LINE_CAP=300
SHOW_DEFAULT=400
SHOW_MAX=600
LIST_CAP=500
LOG_CAP=50
FETCH_MAX_AGE=7200   # seconds; a fetch-running marker older than this is stale

usage="usage: git.sh <key> <${OPS// /|}> [args]; see the comment at the top of git.sh"
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
  resolve|contains)  nargs 1 1 ;;
  verify-all|drift-all)
    nargs 1 2
    [ $# -eq 1 ] || [ "$2" = --all ] || die "'$op' takes <file> [--all], got '$2'." ;;
  grep|igrep)
    for a in "$@"; do
      case "$a" in -i|--ignore-case) die "'$op' takes no -i; use igrep for a case-insensitive search." ;; esac
    done
    if [ "${2-}" = -e ]; then nargs 3 99; else nargs 2 12; fi ;;
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

# 2. The instance and its clone. One Python call reads and validates the
# instance (src_instance_fields); the checks keep their order.
root_wiki=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
[[ $key =~ $SRC_NAME_RE ]] || die "invalid instance key '$key'"
inst="$(src_instance_dir "$root_wiki")/$key.md"
[ -f "$inst" ] || die "no instance '$key' ($inst) in this wiki."
info=$(src_instance_fields "$root_wiki" "$key" type 'roots[]' ref gh_user 2>/dev/null) || die "instance file $inst doesn't validate; run /wiki:init to check it."
{ IFS= read -r i_valid; IFS= read -r i_type; IFS= read -r i_nroots; IFS= read -r i_root
  IFS= read -r i_ref; IFS= read -r i_ghuser; } <<<"$info"
[ "$i_type" = codebase ] || die "instance '$key' is not a codebase instance."
[ "$i_valid" = 1 ] || die "instance file $inst doesn't validate; run /wiki:init to check it."
[ "$i_nroots" = 1 ] || die "a codebase instance names exactly one root (the clone or a folder in it)."
root=$(src_expand "$i_root")
[ -d "$root" ] || die "root '$root' of '$key' is not a folder on this machine."
command -v git >/dev/null 2>&1 || die "git not found on PATH."

# git with nothing from the environment that runs programs or pages.
unset GIT_EXTERNAL_DIFF GIT_PAGER PAGER GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
g() { GIT_OPTIONAL_LOCKS=0 git -C "$top" --no-pager -c core.quotepath=off "$@"; }

top=$(git -C "$root" rev-parse --show-toplevel --show-prefix 2>/dev/null) || die "root '$root' is not inside a git work tree."
prefix=""                                                      # "" or "sub/dir/"
[[ $top != *$'\n'* ]] || { prefix=${top#*$'\n'}; top=${top%%$'\n'*}; }
pre=${prefix%/}                                                # "" or "sub/dir"

# The instance's ref: its `ref` parameter, else the remote's default branch.
iref=$i_ref
if [ -z "$iref" ]; then
  iref=$(g symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null) || iref=""
  if [ -z "$iref" ]; then
    for r in origin/main origin/master; do
      g rev-parse --verify --quiet "$r^{commit}" >/dev/null && { iref=$r; break; }
    done
  fi
  [ -n "$iref" ] || die "can't tell the default branch; set 'ref' in $inst (e.g. origin/main)."
fi
# remote_of: set remote to the ref's remote if the clone has it, else
# origin (status and fetch only: the others don't need it).
remote_of() {
  local r
  remote=${iref%%/*}
  while IFS= read -r r; do [ "$r" = "$remote" ] && return 0; done <<<"$(g remote)"
  remote=origin
}
cache="$HOME/.cache/wiki-sources/${root_wiki##*/}/$key"
cshow="~/.cache/wiki-sources/${root_wiki##*/}/$key"   # in messages: no user name

# 3. Argument checks.
# rev REV: the full commit SHA of a checked revision.
rev() {
  r=$1
  [ "$r" = ref ] && r=$iref
  [[ $r =~ ^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$ ]] || die "'$1' is not a SHA or a plain ref name."
  case "/$r/" in */../*|*/./*|*..*) die "'$1' is not a plain ref name." ;; esac
  g rev-parse --verify --quiet "$r^{commit}" 2>/dev/null || die "'$1' is not a commit in this clone (fetch first?)."
}
# path PATH [glob]: a path relative to the repository top, inside the root.
path_ok() {
  p=$1
  case "$p" in ''|-*|:*|/*|~*|*\\*) die "'$p' must be a path relative to the repository's top folder (no leading -, :, / or ~, no backslashes)." ;; esac
  [[ $p =~ ^[A-Za-z]: ]] && die "'$p' must be relative to the repository's top folder."
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
  [[ $1 =~ ^L?([0-9]{1,7})(-L?([0-9]{1,7}))?$ ]] || die "'$1' is not a line range Lx-Ly."
  x=${BASH_REMATCH[1]} y=${BASH_REMATCH[3]}
  y=${y:-$x}
  x=$((10#$x)) y=$((10#$y))
  [ "$x" -ge 1 ] && [ "$y" -ge "$x" ] || die "'$1': the range must start at 1 or later and not end before it starts."
  printf '%s %s' "$x" "$y"
}
blob_of() { g rev-parse --verify --quiet "$1:$2" 2>/dev/null; }
is_blob() { [ "$(g cat-file -t "$1:$2" 2>/dev/null)" = blob ]; }
lines_of() { g cat-file blob "$1:$2" | awk 'END { print NR }'; }
s12() { printf '%s' "${1:0:12}"; }
here() { [ -n "$pre" ] && printf '%s' "$pre" || printf '.'; }

# fetch_state: whether a fetch by this wrapper is running, from its marker
# <cache>/fetch-running ("<pid> <epoch> <YYYY-MM-DD HH:MM>", removed when
# the fetch ends). Sets fr_pid and fr_when. Returns 0 when one runs (its
# process is alive and the marker is younger than FETCH_MAX_AGE, which
# guards against a reused PID), 1 when there is no marker, 2 when the marker
# is stale (the process was killed before it could remove it).
fetch_state() {
  fr_pid= fr_when=
  local epoch=
  [ -f "$cache/fetch-running" ] || return 1
  read -r fr_pid epoch fr_when < "$cache/fetch-running" || true
  case "$fr_pid$epoch" in ''|*[!0-9]*) return 2 ;; esac
  [ $(($(printf '%(%s)T' -1) - epoch)) -lt "$FETCH_MAX_AGE" ] && kill -0 "$fr_pid" 2>/dev/null && return 0
  return 2
}

# firstline FILE: its first line (head -n 1).
firstline() { local l=; IFS= read -r l < "$1"; printf '%s\n' "$l"; }

# fetch_note: when the remote refs were last fetched (status, drift-all).
# FETCH_HEAD only says when something fetched: the user's own git fetch
# touches it too, so it never stands for a fetch by this wrapper.
fetch_note() {
  fh=$(g rev-parse --git-path FETCH_HEAD)
  case "$fh" in /*|[A-Za-z]:*) ;; *) fh="$top/$fh" ;; esac
  stamp="$cache/last-fetch"
  fetch_state; st=$?
  if [ -f "$stamp" ]; then
    printf 'last fetch: completed %s\n' "$(firstline "$stamp")"
  elif [ -f "$fh" ]; then
    printf 'last fetch: none by git.sh\n'
  else
    printf 'last fetch: never\n'
  fi
  if [ "$st" -eq 1 ] && [ -f "$fh" ] && { [ ! -f "$stamp" ] || [ "$fh" -nt "$stamp" ]; }; then
    printf 'remote refs: fetched %s outside git.sh (e.g. by the user); the ref above is as of then\n' "$(date -r "$fh" '+%Y-%m-%d %H:%M')"
  fi
  case "$st" in
    0) printf 'fetch: running since %s (pid %s); wait for it, then run status again\n' "$fr_when" "$fr_pid" ;;
    2) printf 'fetch: one started %s did not complete (its process is gone, or it is over %s hours old); safe to fetch again\n' "${fr_when:-?}" "$((FETCH_MAX_AGE / 3600))" ;;
  esac
  if [ -f "$cache/fetch-failed" ] && { [ ! -f "$stamp" ] || [ "$cache/fetch-failed" -nt "$stamp" ]; }; then
    printf 'fetch: the last attempt failed: %s\n' "$(firstline "$cache/fetch-failed")"
  fi
}

# check_one REV PATH Lx-Ly: verify or drift ($op) of one citation. Exits
# (1 for broken); verify-all and drift-all run it in a subshell per citation.
check_one() {
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
  exit 0
}

# 4. Run.
case "$op" in
  status)
    remote_of
    head_sha=$(g rev-parse --verify --quiet HEAD 2>/dev/null || echo none)
    branch=$(g symbolic-ref --quiet --short HEAD 2>/dev/null || echo "(detached)")
    dirty=0
    while IFS= read -r l; do [ -z "$l" ] || dirty=$((dirty + 1)); done <<<"$(g status --porcelain -- "$(here)" 2>/dev/null)"
    url=$(g remote get-url "$remote" 2>/dev/null || echo none)
    gh_repo=
    if [[ $url =~ ^(https://|ssh://git@|git@)github\.com[:/]([^/]+)/([^/]+)$ ]]; then
      gh_repo=${BASH_REMATCH[2]}/${BASH_REMATCH[3]}; gh_repo=${gh_repo%.git}
    fi
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
    fetch_note
    ;;
  resolve)
    sha=$(rev "$1") || exit 1
    printf '%s %s (%s, %s)\n' "$1" "$sha" "$(s12 "$sha")" "$(g log -1 --format=%cs "$sha")"
    ;;
  fetch)
    # Never prompt (a prompt hangs a Claude Bash call).
    export GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never GIT_ASKPASS= SSH_ASKPASS=
    remote_of
    url=$(g config --get "remote.$remote.url" 2>/dev/null || echo "")   # as configured, before insteadOf
    user=$i_ghuser
    via="the user's git credentials"
    case "$url" in
      https://github.com/*)
        if [ -n "$user" ] && [[ $user =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,38}$ ]] && command -v gh >/dev/null 2>&1 &&
           CODEBASE_GH_TOKEN=$(GH_PROMPT_DISABLED=1 gh auth token -u "$user" 2>/dev/null) && [ -n "$CODEBASE_GH_TOKEN" ]; then
          export CODEBASE_GH_TOKEN
          via="gh account $user"
          # An empty helper first drops the configured ones (e.g. a broken
          # Credential Manager); the token stays in the environment.
          set -- -c credential.helper= -c 'credential.helper=!f() { test "$1" = get && printf "username=x-access-token\npassword=%s\n" "$CODEBASE_GH_TOKEN"; }; f'
        fi ;;
    esac
    # One fetch at a time: a marker with this process's PID, created only if
    # absent (noclobber), removed on exit. A stale one is replaced.
    mkdir -p "$cache" || die "can't create the cache folder $cshow."
    fetch_state; st=$?
    [ "$st" -ne 0 ] || die "a fetch is already running (started $fr_when, pid $fr_pid). Wait for it: run status until 'last fetch: completed' shows a new time."
    [ "$st" -ne 2 ] || rm -f "$cache/fetch-running"
    printf -v t0 '%(%Y-%m-%d %H:%M)T' -1
    (set -C; printf '%s %(%s)T %s\n' "$$" -1 "$t0" > "$cache/fetch-running") 2>/dev/null ||
      die "another fetch started just now; wait for it: run status until 'last fetch: completed' shows a new time."
    trap 'rm -f "$cache/fetch-running"' EXIT
    trap 'exit 1' INT TERM HUP
    failed() { printf '%s: %s\n' "$t0" "$1" > "$cache/fetch-failed"; die "$1"; }
    g "$@" fetch --prune --no-tags --no-recurse-submodules --quiet "$remote" ||
      failed "fetch from '$remote' failed (using $via; started $t0). git never prompts here: with an https GitHub remote, set gh_user in the instance, or fix the git credentials."
    sha=$(g rev-parse --verify --quiet "$iref^{commit}") || failed "fetched, but '$iref' is not found."
    printf '%(%Y-%m-%d %H:%M)T, %s @ %s\n' -1 "$iref" "${sha:0:12}" > "$cache/last-fetch"
    rm -f "$cache/fetch-failed"
    printf 'fetched %s (using %s, started %s); %s @ %s (%s)\n' "$remote" "$via" "$t0" "$iref" "$(s12 "$sha")" "$(g log -1 --format=%cs "$sha")"
    ;;
  grep|igrep)
    sha=$(rev "$1") || exit 1
    shift
    pats=() shown=
    if [ "$1" = -e ]; then   # -e A -e B ... [<pathspec>]: or-ed
      while [ $# -ge 1 ] && [ "$1" = -e ]; do
        [ $# -ge 2 ] || die "-e needs a regex after it."
        pats+=("$2"); shift 2
      done
    else
      re=$1; shift
      case "$re" in
        @*)
          pf=${re#@}
          [[ $pf =~ ^[A-Za-z0-9_][A-Za-z0-9._/-]*$ ]] || die "'$re': a pattern file is @<path below $cshow/> (letters, digits, . _ - /); for a regex starting with @, use -e."
          src_has_dots "$pf" && die "'.' and '..' are not allowed in a pattern file path."
          [ -f "$cache/$pf" ] || die "pattern file '$cshow/$pf' not found (a leading @ names a pattern file; for a regex starting with @, use -e)."
          while IFS= read -r line || [ -n "$line" ]; do
            line=${line%$'\r'}
            [ -n "$line" ] || continue
            [ "${#line}" -le 500 ] || die "pattern file line $((${#pats[@]} + 1)) is longer than 500 characters."
            [ "${#pats[@]}" -lt 20 ] || die "a pattern file holds at most 20 patterns."
            pats+=("$line")
          done < "$cache/$pf"
          [ "${#pats[@]}" -ge 1 ] || die "pattern file '$cshow/$pf' has no patterns."
          shown="${#pats[@]} patterns from $pf: " ;;
        *) pats=("$re") ;;
      esac
    fi
    [ "${#pats[@]}" -le 20 ] || die "at most 20 -e patterns."
    for re in "${pats[@]}"; do
      [ -n "$re" ] && [ "${#re}" -le 500 ] || die "the regex must be 1 to 500 characters."
    done
    # Pathspecs: up to 10, searched together; none means the root.
    [ $# -le 10 ] || die "at most 10 pathspecs."
    specs=()
    for a in "$@"; do
      case "$a" in -*) die "'$a': '$op' takes no flags but -e, and -e goes before the pathspecs." ;; esac
      sp=$(path_ok "$a" glob) || exit 1; specs+=("$sp")
    done
    [ "${#specs[@]}" -ge 1 ] || specs=("$(here)")
    spec="${specs[*]}"
    flags="-n -I --no-color -E"
    [ "$op" = igrep ] && flags="$flags -i"
    set --
    for re in "${pats[@]}"; do
      set -- "$@" -e "$re"
      r=${re//$'\r'/}; [ -z "$r" ] || shown+=$r'|'   # shown without CRs
    done
    shown=${shown%|}
    printf '@%s grep %s in %s\n' "$(s12 "$sha")" "$shown" "$spec"
    # shellcheck disable=SC2086
    g grep $flags "$@" "$sha" -- "${specs[@]}" 2>/dev/null |
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
    if [ "$(g rev-parse --is-shallow-repository 2>/dev/null)" = true ]; then printf '(shallow clone: history stops at the shallow boundary)\n'; fi
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
    fre='^[A-Za-z0-9_][A-Za-z0-9._/ -]*$'
    [[ $pf =~ $fre ]] || die "'$f': give @<path below $cshow/> or a path relative to the wiki."
    src_has_dots "$pf" && die "'.' and '..' are not allowed in the file path."
    [ -f "$base/$pf" ] || die "'$base/$pf' not found."
    one=${op%-all}
    cites=$(tr -d '\r' < "$base/$pf" | grep -oE '[A-Za-z0-9_][A-Za-z0-9_./-]*#L[0-9]{1,7}(-L[0-9]{1,7})? @[0-9a-f]{7,40}' | awk '!s[$0]++')
    [ -n "$cites" ] || { printf 'no citations found in %s\n' "$pf"; exit 0; }
    n=0
    while IFS= read -r c; do [ -z "$c" ] || n=$((n + 1)); done <<<"$cites"
    [ "$n" -le 300 ] || die "$n citations in $pf; at most 300 per call."
    all=${2:-}
    bad=0 kinds=""
    while IFS= read -r c; do
      p=${c%%#*} r=${c%% @*} s=${c##*@}
      r=${r#*#}
      res=$(op=$one; check_one "$s" "$p" "$r" 2>&1) || bad=$((bad + 1))
      res=${res%%$'\n'*}; res=${res#codebase: }
      kind=${res%%[ :]*}
      kinds="$kinds$kind
"
      # Only what needs attention, unless --all.
      case "$kind" in ok|unchanged) [ -n "$all" ] || continue ;; esac
      printf '%s -> %s\n' "$c" "$res"
    done <<EOF
$cites
EOF
    printf '%s citations: %s\n' "$n" "$(printf '%s' "$kinds" | grep . | LC_ALL=C sort | uniq -c | awk '{ printf "%s%s %s", (NR > 1 ? ", " : ""), $1, $2 }')"
    if [ "$one" = drift ]; then
      printf 'compared with %s as of the last fetch; fetch first (an agent) if that is old.\n' "$iref"
      fetch_note
    fi
    [ "$bad" -eq 0 ] || exit 1
    ;;
  drift|verify)
    check_one "$@"
    ;;
esac
