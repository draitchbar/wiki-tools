# Speed plan: a faster guard and test suite

Status: **not started**, plan only (2026-11-04). Replaces the "Speed and Python" note in CLAUDE.md's Open plans.

## Problem
`bash tests/run-tests.sh` takes over 10 minutes on Windows (Git Bash). On Linux, measured 2026-11-04: **112 s for 577 checks**, and one `guard.sh` call (a pass fixture) takes **about 320 ms**. That is slow even on Linux, so the cost is in starting processes, not in the logic: `guard.sh` has about 65 command substitutions or pipes, `lib-source.sh` about 50, and each one forks. Under Git Bash a fork costs several times more, which fits the Windows number.

It isn't only the tests. `guard.sh` runs on every tool call in the wikis, so its speed is felt in every session.

## Decision so far (2026-11-01)
A Python requirement is acceptable. The "no Python" rule in CLAUDE.md stands until the port starts. Wrappers that mostly wait on `git`/`gh` stay bash either way.

Added here: try cutting process starts in bash (step 2a) before committing to the port (step 2b). The step 1 numbers decide.

## Step 1: Measure
Size: half a day.

1. `WIKI_TEST_TIMING=1 bash tests/run-tests.sh` prints a timestamp before each section and a total per section at the end. The sections are guard fixtures, `gbroken`/`gdiag`/`gwin`, proton-drive, codebase, lint, sources/contracts and the rest. Use `date +%s%N` (GNU date, which Git Bash ships).
2. Time single calls on both machines: a guard call that passes, one that blocks, and `sources.sh show`, each run 10 times in a loop.
3. Count the processes one guard call starts: `strace -f -c -e trace=execve` on Linux. On Windows the timing alone will do.
4. Record the numbers below under "Measurements". If the guard and contract parsing don't dominate on Windows, rethink before going on.

## Step 2a: Fewer process starts, in bash
Size: one or two sessions. Stays within the current rules, and the existing fixtures already cover it.

- `guard.sh`, `lib-source.sh`: replace `$(… | sed …)`, `echo | grep` and `cut`/`tr` pipes with parameter expansion, `case` and `[[ =~ ]]`. Read and parse each contract once per call, into variables, instead of once per lookup. Keep the fail-closed paths exactly as they are (the `gbroken`/`gdiag` cases must stay green).
- `run-tests.sh`: run the fixture loop (131 files) in parallel with `xargs -P` (Git Bash has it), with each worker writing its result to a file and the runner tallying them afterwards so the output order stays the same. Set up each throwaway wiki once per section, not once per check, wherever the checks don't change it.
- Commit message: say that the guard changed but its behaviour didn't (CLAUDE.md asks for that whenever a guard is touched).

**Gate:** if the Windows suite is under about 2–3 minutes and a guard call under about 100 ms there, stop: drop step 2b, or postpone it with a trigger.

## Step 2b: Port the guard to Python
Only if step 2a isn't enough.

1. **Launcher.** A small bash shim in `plugins/wiki/scripts/` finds an interpreter in the order `python3`, `python`, `py -3`. It skips the Windows Store alias by checking that `--version` actually runs and prints a 3.x version. With no interpreter found it fails closed (exit 2) with a message naming the fix. Fixtures: interpreter missing, Store alias only, `py` only (fakes on PATH, as `tests/sources/` does).
2. **Port.** `guard.py` for `guard.sh`, plus a `contract.py` module for the contract parsing in `lib-source.sh`. Standard library only. The bash versions stay during the transition.
3. **Dual run.** `run-tests.sh` runs every guard fixture and every `gbroken`/`gdiag`/`gwin` case against both versions and fails on any disagreement, counted as its own check. `hooks.json` switches to the Python guard only when both agree on Linux and on Windows.
4. **`/wiki:init`.** Check that an interpreter is there (via the launcher), with a fix-it message if not.
5. **Clean up.** Delete the bash guard and its dual-run code. Replace the "no Python" rule in CLAUDE.md with the new rule (which scripts are Python, the launcher, the minimum version). Update the README. The commit message says the guard was reimplemented.

Not ported: `codebase/*.sh`, proton-drive `read.sh` and the other wrappers that mostly wait on `git`/`gh`/a CLI. Proton's faster `new` (see `proton-drive-plan.md`) is decided at this point, from its step 1 timing.

## Step 3 (optional): Run guard fixtures in one process
After step 2b only. Most guard fixtures run inside one Python process that imports `guard.py`, so a case costs no new process. Keep a handful of end-to-end runs through the real hook entry point (`hooks.json` command, launcher, stdin JSON, exit code). Leave the source-wrapper tests alone: their cost is in `git` and the fakes.

## Measurements
| Date | Machine | Suite | One guard call | `sources.sh show` | Notes |
|---|---|---|---|---|---|
| 2026-11-04 | Linux | 112 s (577 checks) | ~320 ms | — | before any change |
| | Windows (Git Bash) | >10 min | — | — | from memory, to measure in step 1 |
