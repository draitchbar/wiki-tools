"""PreToolUse(Bash|PowerShell): block any git push. The user pushes themselves.

Python port of block-push.sh (speed plan, step 2b spike); same rules, same
messages. Run through py-launch.sh, which turns any exit other than 0 or 2
into a block.

Known false positive: a command mentioning both "git" and the word "push",
e.g. a commit message containing "push". Rephrase the message.
`git stash push` is let through, but only written exactly so: "git" (or
"git.exe") directly followed by "stash push". Anything between them, as in
`git -C stash push` or `git --git-dir=stash push`, could be a real push and
stays blocked.
"""

import os
import sys

# -I leaves this folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re  # noqa: E402

import hookjson  # noqa: E402

# re.ASCII: \b and \s as in grep -E/sed -E ([A-Za-z0-9_] words, POSIX space).
_STASH_PUSH = re.compile(r"\bgit(\.exe)?\s+stash\s+push\b", re.ASCII)
_PUSH = re.compile(r"\bgit\b.*\bpush\b", re.ASCII | re.DOTALL)


def block(msg):
    sys.stderr.buffer.write(("wiki guard: %s\n" % msg).encode("utf-8", errors="replace"))
    sys.stderr.flush()
    sys.exit(2)


def main():
    h = hookjson.parse(sys.stdin.buffer.read())
    if h is None:
        block("could not parse hook input; refusing (fail closed).")
    if h.tool not in ("Bash", "PowerShell"):
        sys.exit(0)
    if not h.command:
        block("%s call without a command; refusing (fail closed)." % h.tool)
    # Drop "stash push" from each `git stash push`, then look for any other push.
    cmd = _STASH_PUSH.sub("git stash", hookjson.norm(h.command))
    if _PUSH.search(cmd):
        block("git push is not allowed in wiki sessions. Commit locally; the user pushes.")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 - any failure blocks
        try:
            sys.stderr.write("wiki guard: block_push.py failed (%s); refusing (fail closed).\n" % type(e).__name__)
        finally:
            os._exit(2)
