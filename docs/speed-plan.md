# Speed plan: a faster guard and test suite

Status: **step 1 done**: Linux measured 2026-11-04, Windows 2026-11-05. Next: step 2a. Replaces the "Speed and Python" note in CLAUDE.md's Open plans.

## Problem
`bash tests/run-tests.sh` takes over 10 minutes on Windows (Git Bash). On Linux, measured 2026-11-04: **112 s for 577 checks**, and one `guard.sh` call (a pass fixture) takes **about 320 ms**. That is slow even on Linux, so the cost is in starting processes, not in the logic: `guard.sh` has about 65 command substitutions or pipes, `lib-source.sh` about 50, and each one forks. Under Git Bash a fork costs several times more, which fits the Windows number.

It isn't only the tests. `guard.sh` runs on every tool call in the wikis, so its speed is felt in every session.

## Decision so far (2026-11-01)
A Python requirement is acceptable. The "no Python" rule in CLAUDE.md stands until the port starts. Wrappers that mostly wait on `git`/`gh` stay bash either way.

Added here: try cutting process starts in bash (step 2a) before committing to the port (step 2b). The step 1 numbers decide.

## Step 1: Measure
Size: half a day.

1. `WIKI_TEST_TIMING=1 bash tests/run-tests.sh` prints a timestamp before each section and a total per section at the end. The sections are guard fixtures, `gbroken`/`gdiag`/`gwin`, proton-drive, codebase, lint, sources/contracts and the rest. It uses bash 5's `EPOCHREALTIME`, which starts no process, and falls back to `date +%s%N`. Done 2026-11-04.
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
How: `WIKI_TEST_TIMING=1 bash tests/run-tests.sh` gives the section times. Single calls are averaged over 10 runs on a copy of `tests/guard-wiki` committed into a git repo (`sources.sh` refuses to run outside one). Process counts come from `strace -f -e trace=execve,clone,clone3`.

### Linux, 2026-11-04 (before any change)
Suite: 107 s, 577 checks (112 s in an earlier run without timing).

| Section | Time | Checks | Per check |
|---|---|---|---|
| guard-fixtures | 35.3 s | 133 | 265 ms |
| guard-broken | 7.4 s | 25 | 296 ms |
| codebase | 18.3 s | 93 | 197 ms |
| wiki-check | 14.8 s | 23 | 643 ms |
| sources | 12.6 s | 78 | 162 ms |
| install | 7.3 s | 56 | 130 ms |
| lint | 3.6 s | 31 | 115 ms |
| proton-drive | 3.5 s | 38 | 93 ms |
| lib-source | 2.6 s | 51 | 51 ms |
| ms-teams | 1.6 s | 26 | 62 ms |
| sync-status | 0.6 s | 10 | 55 ms |
| ocr, plugin-schema, setup | 0.1 s | 13 | — |

| Single call | Time | Programs run | Forks |
|---|---|---|---|
| `guard.sh`, pass (`pass-bash-similar-word`) | 325 ms | 206 | 478 |
| `guard.sh`, block (`block-bash-cat-claude-sources`) | 322 ms | 206 | 478 |
| `sources.sh show books` | 134 ms | 113 | — |
| `sources.sh show gmail` / `code` | 149 / 174 ms | — | — |

A guard call runs `sed` 78 times, `awk` 57, `tr` 31, `head` 26 and `grep` 8. The remaining forks are `$(…)` subshells that run no program. Pass and block cost the same, because the guard parses every instance and contract before it looks at the command.

Findings:
- The guard sections are 40% of the Linux suite (43 of 107 s), and each guard call is about 680 process starts. If a start costs a few ms under Git Bash, that alone would account for several minutes of the Windows run, as step 1 expected. This still needs confirming on Windows.
- `wiki-check` is the most expensive per check (643 ms) and `codebase` is second in total. Look at both in step 2a: wiki-check may call `sources.sh`/`lint.sh` per check, and codebase is mostly `git`, which stays.
- `sources.sh show` runs 113 programs, nearly all `sed`/`awk`/`grep`/`head` in `lib-source.sh`'s parsing. The guard repeats that same parsing for each instance.

### Windows (Git Bash), 2026-11-05 (before any change)
Machine: Windows 11 laptop, i5-10210U, on AC power with sleep turned off, Defender real-time protection on. Git Bash 5.2.37, Git 2.49.0.
Suite: **2380 s (39 min 40 s)**, 577 checks, 0 failed.

A first run on 2026-11-04 is not counted: the laptop went into Modern Standby overnight, which pauses desktop processes and inflated the wall-clock section times. To time on a laptop, plug it in and run `powercfg /change standby-timeout-ac 0` from PowerShell. Git Bash rewrites `/change` into a path, so there it needs `MSYS_NO_PATHCONV=1`.

| Section | Time | Checks | Per check | × Linux |
|---|---|---|---|---|
| guard-fixtures | 834.0 s | 133 | 6.27 s | 24 |
| guard-broken | 174.9 s | 25 | 7.00 s | 24 |
| codebase | 399.5 s | 93 | 4.30 s | 22 |
| wiki-check | 310.3 s | 23 | 13.5 s | 21 |
| sources | 282.5 s | 78 | 3.62 s | 22 |
| install | 148.7 s | 56 | 2.66 s | 20 |
| proton-drive | 72.9 s | 38 | 1.92 s | 21 |
| lint | 58.2 s | 31 | 1.88 s | 16 |
| lib-source | 55.4 s | 51 | 1.09 s | 21 |
| ms-teams | 32.9 s | 26 | 1.26 s | 21 |
| sync-status | 8.5 s | 10 | 0.85 s | 14 |
| ocr, plugin-schema, setup | 1.9 s | 13 | — | — |

| Single call | Time | × Linux |
|---|---|---|
| `bash -c true` (baseline) | 47 ms | |
| `sed -n 1p /dev/null` (baseline) | 26 ms | |
| `guard.sh`, pass (`pass-bash-similar-word`) | 7.87 s | 24 |
| `guard.sh`, block (`block-bash-cat-claude-sources`) | 7.66 s | 24 |
| `sources.sh show books` | 2.85 s | 21 |
| `sources.sh show gmail` / `code` | 3.07 / 3.83 s | 21 / 22 |

Findings:
- Process starts explain it. Every section is about 21× slower than on Linux, whatever it does, and a guard call's ~680 starts (206 programs at ~26 ms, plus ~270 subshell forks) add up to its 7.8 s. No single script is slow. Forking is slow, everywhere.
- The guard sections are 42% of the suite (1009 of 2380 s), as on Linux, so step 1's premise holds and step 2a goes ahead. `codebase`, `wiki-check` and `sources` are the next 41%.
- **A guard call costs about 8 s on Windows, and it runs on every tool call in a wiki session.** This matters more than the test suite.
- The gate (under 100 ms per guard call) is out of reach for any bash version that still starts programs: at 26–47 ms per start, it allows two or three. Step 2a should still cut the suite a lot. But reaching the gate for the guard means either pure-bash parsing with no `sed`/`awk`/`$(…)` at all, or step 2b. Before step 2a, time a Python start under Git Bash (`python -c pass`) on this machine, so the two can be compared.
