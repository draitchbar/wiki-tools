#!/usr/bin/env bash
# gh.sh: read-only GitHub context (PRs, issues) for a codebase source.
#
#   bash <plugin>/sources/codebase/gh.sh <key> pr-of        <sha>
#   bash <plugin>/sources/codebase/gh.sh <key> pr           <number>
#   bash <plugin>/sources/codebase/gh.sh <key> pr-diff      <number>
#   bash <plugin>/sources/codebase/gh.sh <key> pr-search    "<query>"
#   bash <plugin>/sources/codebase/gh.sh <key> issue        <number>
#   bash <plugin>/sources/codebase/gh.sh <key> issue-search "<query>"
#
# Rules:
# - <key> is a codebase instance with gh_user; the repository is the
#   GitHub remote of its clone.
# - Only these GET operations reach gh. The account is picked per call
#   (GH_TOKEN from `gh auth token -u <gh_user>`); the active account is
#   never switched.
# - No version pin: any gh works as long as its help output still shows the
#   syntax this wrapper relies on (check_syntax). Recorded from gh 2.103.2
#   (2026-10-23) on 2026-10-31.
# - gh never prompts here (GH_PROMPT_DISABLED); output is capped.
#
# Run it from inside a wiki (any directory of its git repo).

set -u

. "$(dirname "$0")/../../scripts/lib-source.sh"

CLI=gh
OPS="pr-of pr pr-diff pr-search issue issue-search"
CAP=400
DIFF_CAP=1500

die() { printf 'codebase-gh: %s\n' "$1" >&2; exit 1; }

[ $# -eq 3 ] || die "usage: gh.sh <key> <$(printf '%s' "$OPS" | tr ' ' '|')> <arg>"
key=$1 op=$2 arg=$3

# 1. Operation allowlist and argument shape, before anything touches gh.
case " $OPS " in *" $op "*) ;; *) die "operation '$op' is not allowed; read-only ops are: $OPS" ;; esac
case "$arg" in *"
"*) die "the argument may not contain a newline." ;; esac
case "$op" in
  pr-of) printf '%s' "$arg" | grep -Eq '^[0-9a-f]{7,40}$' || die "pr-of takes a commit SHA (7 to 40 hex)." ;;
  pr|pr-diff|issue) printf '%s' "$arg" | grep -Eq '^[0-9]{1,7}$' || die "$op takes a number." ;;
  pr-search|issue-search)
    [ -n "$arg" ] && [ "${#arg}" -le 200 ] || die "the query must be 1 to 200 characters." ;;
esac

# 2. The instance, its repository and its gh account.
wroot=$(src_wiki_root) || die "not inside a git repo; run from a wiki."
printf '%s' "$key" | grep -Eq "$SRC_NAME_RE" || die "invalid instance key '$key'"
inst="$(src_instance_dir "$wroot")/$key.md"
[ -f "$inst" ] || die "no instance '$key' ($inst) in this wiki."
[ "$(src_field "$inst" type)" = codebase ] || die "instance '$key' is not a codebase instance."
src_validate_instance "$wroot" "$key" 2>/dev/null || die "instance file $inst doesn't validate; run /wiki:init to check it."
user=$(src_field "$inst" gh_user)
[ -n "$user" ] || die "instance '$key' has no gh_user, so PR and issue context is off. Add gh_user to $inst to turn it on."
printf '%s' "$user" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_-]{0,38}$' || die "gh_user '$user' is not a GitHub login."
root=$(src_expand "$(src_values "$inst" roots | head -n 1)")
url=$(git -C "$root" remote get-url origin 2>/dev/null) || die "the root of '$key' has no 'origin' remote."
repo=$(printf '%s' "$url" | sed -En 's#^(https://|ssh://git@|git@)github\.com[:/]([^/]+)/([^/]+)$#\2/\3#p' | sed 's/\.git$//')
printf '%s' "$repo" | grep -Eq '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' || die "origin ($url) is not a GitHub repository."
if [ "$op" = pr-of ]; then
  sha=$(git -C "$root" rev-parse --verify --quiet "$arg^{commit}" 2>/dev/null) || die "'$arg' is not a commit in this clone."
fi

# 3. gh present and still speaking the syntax this wrapper was written for.
command -v "$CLI" >/dev/null 2>&1 || die "'$CLI' not found on PATH."
check_syntax() { # TEXT EXPECTED...
  text=$1; shift
  for want in "$@"; do
    case "$text" in
      *"$want"*) ;;
      *) die "gh syntax changed (missing '$want'). Re-record the help output and review gh.sh before using it." ;;
    esac
  done
}
check_syntax "$("$CLI" auth token --help 2>&1)" "gh auth token [flags]" "-u, --user string"
case "$op" in
  pr-of) check_syntax "$("$CLI" api --help 2>&1)" "gh api <endpoint> [flags]" "-X, --method string" "-q, --jq string" ;;
  pr) check_syntax "$("$CLI" pr view --help 2>&1)" "gh pr view [<number> | <url> | <branch>] [flags]" "--json" ;;
  pr-diff) check_syntax "$("$CLI" pr diff --help 2>&1)" "gh pr diff [<number> | <url> | <branch>] [flags]" "--color" ;;
  pr-search) check_syntax "$("$CLI" pr list --help 2>&1)" "gh pr list [flags]" "--search" "--state" ;;
  issue) check_syntax "$("$CLI" issue view --help 2>&1)" "gh issue view {<number> | <url>} [flags]" "--json" ;;
  issue-search) check_syntax "$("$CLI" issue list --help 2>&1)" "gh issue list [flags]" "--search" "--state" ;;
esac

export GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 GH_PAGER=cat NO_COLOR=1
unset GH_HOST GH_REPO GITHUB_TOKEN
GH_TOKEN=$("$CLI" auth token -u "$user" 2>/dev/null) || die "gh has no token for account '$user' (gh auth status lists the accounts; the user logs in with gh auth login)."
[ -n "$GH_TOKEN" ] || die "gh returned an empty token for '$user'."
export GH_TOKEN

# 4. Run. Nothing from the caller reaches gh except the checked values.
cap() { head -n "$1"; }
case "$op" in
  pr-of)
    "$CLI" api -X GET "repos/$repo/commits/$sha/pulls" \
      --jq '.[] | "#\(.number) \(.title) (\(.state); merged \(.merged_at // "no"); \(.html_url))"' | cap 50
    ;;
  pr)
    "$CLI" pr view "$arg" -R "$repo" --json number,title,author,state,mergedAt,url,body,files,reviews,comments \
      --jq '"#\(.number) \(.title)\n\(.state); merged \(.mergedAt // "no"); by \(.author.login); \(.url)\n\n\(.body[0:4000])\n\nFiles:\n\([.files[].path] | join("\n"))\n\nReviews:\n\([.reviews[] | "- \(.author.login) \(.state): \(.body[0:500])"] | join("\n"))\n\nComments:\n\([.comments[] | "- \(.author.login): \(.body[0:500])"] | join("\n"))"' | cap "$CAP"
    ;;
  pr-diff)
    "$CLI" pr diff "$arg" -R "$repo" --color never | awk -v cap="$DIFF_CAP" '{ n++; if (n <= cap) print } END { if (n > cap) print "(" n - cap " more diff lines not shown)" }'
    ;;
  pr-search)
    "$CLI" pr list -R "$repo" --state all --search "$arg" --limit 30 --json number,title,state,mergedAt,url \
      --jq '.[] | "#\(.number) \(.title) (\(.state); merged \(.mergedAt // "no"); \(.url))"'
    ;;
  issue)
    "$CLI" issue view "$arg" -R "$repo" --json number,title,state,author,url,body,comments \
      --jq '"#\(.number) \(.title)\n\(.state); by \(.author.login); \(.url)\n\n\(.body[0:4000])\n\nComments:\n\([.comments[] | "- \(.author.login): \(.body[0:500])"] | join("\n"))"' | cap "$CAP"
    ;;
  issue-search)
    "$CLI" issue list -R "$repo" --state all --search "$arg" --limit 30 --json number,title,state,url \
      --jq '.[] | "#\(.number) \(.title) (\(.state); \(.url))"'
    ;;
esac
