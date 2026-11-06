# Speed plan: a faster guard and test suite

Status: **step 2b spike done, verdict go** (2026-11-05), merged into `main` 2026-11-05. Linux: block-push 59 → 24 ms per call. Windows: 1.5 s → 126 ms per call, suite green (646 checks), and a real udbygning session at 129 ms p90 with the push blocked. Rest of 2b in progress on `speed-spike`: `contract.py` built 2026-11-05 (item 1), next `guard.py`. Step 1 done (Linux 2026-11-04, Windows 2026-11-05). Step 2a only if still needed after 2b; bash trimming of the guard dropped 2026-11-05. Replaces the "Speed and Python" note in CLAUDE.md's Open plans.

## Problem
`bash tests/run-tests.sh` takes about 40 minutes on Windows (Git Bash), measured 2026-11-05. On Linux, measured 2026-11-04: **112 s for 577 checks**, and one `guard.sh` call (a pass fixture) takes **about 320 ms**. That is slow even on Linux, so the cost is in starting processes, not in the logic: `guard.sh` has about 65 command substitutions or pipes, `lib-source.sh` about 50, and each one forks. Under Git Bash a fork costs several times more, which fits the Windows number.

It isn't only the tests. `guard.sh` runs on every tool call in the wikis, so its speed is felt in every session.

## Decision so far (2026-11-01)
A Python requirement is acceptable. The "no Python" rule in CLAUDE.md stands until the port starts. Wrappers that mostly wait on `git`/`gh` stay bash either way.

Added 2026-11-04: try cutting process starts in bash before committing to the port, with the step 1 numbers deciding. Decided 2026-11-05 from those numbers: the guard goes to Python (step 2b), and the bash work is limited to the test runner (step 2a).

## Step 1: Measure
Size: half a day.

1. `WIKI_TEST_TIMING=1 bash tests/run-tests.sh` prints a timestamp before each section and a total per section at the end. The sections are guard fixtures, `gbroken`/`gdiag`/`gwin`, proton-drive, codebase, lint, sources/contracts and the rest. It uses bash 5's `EPOCHREALTIME`, which starts no process, and falls back to `date +%s%N`. Done 2026-11-04.
2. Time single calls on both machines: a guard call that passes, one that blocks, and `sources.sh show`, each run 10 times in a loop.
3. Count the processes one guard call starts: `strace -f -c -e trace=execve` on Linux. On Windows the timing alone will do.
4. Record the numbers below under "Measurements". If the guard and contract parsing don't dominate on Windows, rethink before going on.

## Step 2a: A faster test runner
Size: one session. Stays within the current rules. Only if still needed after step 2b (decided 2026-11-05).

- `run-tests.sh`: run the fixture loop (131 files) in parallel with `xargs -P` (Git Bash has it). Each worker writes its result to a file, and the runner tallies them afterwards so the output order stays the same. Set up each throwaway wiki once per section, not once per check, wherever the checks don't change it.
- Tests only: no change to `guard.sh`, `lib-source.sh` or any wrapper.
- Measure again with `WIKI_TEST_TIMING=1` on both machines and add a row to Measurements.

Not doing (decided 2026-11-05): trimming `guard.sh` and `lib-source.sh` in bash. On Windows a process start costs 26–47 ms, so a guard under the 100 ms gate could start at most two or three programs. Every lookup would have to be pure bash: parsing contracts with no `sed`, `awk` or `$(…)`. That rewrite would be fragile and still slower than Python's ~105 ms (Measurements, "Python start"). The guard goes straight to step 2b.

## Step 2b: Port the guard to Python
This fixes the per-call cost: about 8 s per tool call on Windows today, about 150 ms expected after the port (47 ms of bash, which Claude Code starts for every hook anyway, plus about 105 ms of Python). Starting this step lifts the "no Python" rule in CLAUDE.md for the guard, block-push and the contract parsing they share (decided 2026-11-01). CLAUDE.md's rule is updated when the spike starts, not at the end.

Plan reviewed 2026-11-05 by a review agent; its findings are folded in below.

### Rules for every Python hook
These keep a Python hook from failing open:
- **Exit codes.** The launcher runs Python as a child, not with `exec`, and maps any exit code other than 0 or 2 to a message plus `exit 2`. Python exits 1 on a SyntaxError, an ImportError or a fatal error before the script's own `try` can act. Bash exits 126/127 when it can't run the program. Neither may let the call through, whatever `"onFailure": "block"` covers. Under MSYS, `exec` of a native program saves almost nothing anyway, because the bash side waits for the child either way.
- **Inside the script,** everything sits in a `try`, and any exception exits 2. Use `sys.exit`, never `exit()` (`-S` removes it).
- **Encoding.** Run as `"$py" -I -S -X utf8 …`. Under `-I`, `PYTHONUTF8` and `PYTHONIOENCODING` are ignored, and on Windows piped stdin would be decoded as cp1252, garbling a path such as `Bøger` so it no longer matches a root. `-X utf8` still applies under `-I`. Messages go to stderr as UTF-8.
- **Imports.** `-I` drops the script's folder from `sys.path`, so a script that imports a sibling module adds its own folder first: `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`. The plugin folder is protected, so this is safe.
- **JSON, carried over from `lib-hookjson.sh`,** each with a fixture:
  - a missing or empty `tool_name`, or a top-level value that isn't an object, blocks (`block-malformed`);
  - a `command`, `file_path`, `content`, `new_string`, `path`, `pattern` or `glob` that isn't a string blocks; it never becomes `str(value)` and never crashes as an allow;
  - `\n` and `\r` in a value become `;`, and `\t` becomes a space;
  - `description` is never read;
  - regexes that look across a command use `re.DOTALL`.
- **Intended differences from bash,** each with a fixture that only the Python version blocks:
  - `\uXXXX` escapes are decoded;
  - every MultiEdit `new_string` is checked (bash's greedy `sed` takes only the last one);
  - non-ASCII is lowercased.

### Launcher
`plugins/wiki/scripts/py-launch.sh`, sourced by the hook command (`. "${CLAUDE_PLUGIN_ROOT}/scripts/py-launch.sh" block_push`), so it starts no bash of its own. It:
- finds its own folder from `${BASH_SOURCE[0]%/*}`, since `$0` is `bash` when sourced;
- reads the cached interpreter path with `read -r` (a builtin) and uses it only if it is absolute, executable and its file name starts with `python`;
- otherwise takes the slow path. It runs each candidate (`python`, `python3`, `py -3`, in that order: on Windows `python3` is usually the Store alias, about 300 ms to fail) once with `-c 'import sys; print(sys.version_info >= (3, 9)); print(sys.executable)'` and caches the first good `sys.executable`. This one call checks the version, rejects the Store alias (it doesn't run) without a `WindowsApps` path rule, and turns `py -3` into a real path, which also saves `py`'s ~25 ms per call. The cache is written to a temp file plus `mv` (two hooks may probe at once), with a trailing newline;
- with no interpreter found, prints a message naming the fix and exits 2.

**Cache location:** `${CLAUDE_PLUGIN_DATA}/python` only. A cache that points at a program exiting 0 (for example `/bin/true`) would allow every call, so the cache must be protected. Claude Code (2.1.318) passes `CLAUDE_PLUGIN_DATA` to hooks as `~/.claude/plugins/data/<plugin>-<marketplace>/`, which the guards' existing `.claude/plugins/` entry already protects (checked 2026-11-05). When it is unset (older Claude Code, a manual run), the launcher probes on every call and caches nothing. That is slow but safe, and it needs no new protected path.

### Spike: block-push in Python (first)
We already know Python's start time. The spike tests what we don't know, on the smallest real hook: the hook plumbing on Windows, the real per-call cost inside a Claude session, and what Windows Python receives. `block-push.sh` is 21 lines plus `lib-hookjson.sh`, runs on every Bash call like the guard, and has 19 fixtures. Everything the spike builds stays.

Work happens on branch `speed-spike`. It stays off `main` until the go decision. Commit messages say that a guard changed, as CLAUDE.md asks.

1. **The launcher** as above, and **`block_push.py`**, following the rules above. Standard library only, imports limited to `json`, `os`, `re` and `sys`. Messages stay word for word the same.
2. **Dual run** in `run-tests.sh`. Every block-push fixture runs against both versions. Exit code and message must agree, except for the listed intended differences. The tests set the cache folder to a test folder and never touch the user's real cache.
3. **Launcher fixtures,** with fake interpreters on PATH:
   - a fresh cache;
   - a stale cache (interpreter deleted);
   - a cached interpreter that exists but is broken;
   - a cache with no trailing newline;
   - a cache holding a relative path, or a path to a program not named `python*`;
   - a Store-alias stub only, `py` only, and Python 3.8 only;
   - none at all;
   - a fake interpreter that exits 1, exits 127, or prints a traceback (each must give 2);
   - empty stdin;
   - a non-ASCII path.
4. **End to end:** run the exact `command` string from `hooks.json` through `bash -c`, with `CLAUDE_PLUGIN_ROOT` set to a path containing a space. Today's tests call `bash "$scripts/$1.sh"` directly and never test the hook command itself.
5. **Measure** on both machines and add the results to Measurements:
   - one call, loop of 10: `block-push.sh` against the launcher plus `block_push.py`, with a warm cache;
   - the block-push section of the suite, both versions;
   - the full dual run on Windows (the user's run).
6. **Real session, on Windows.** On `speed-spike`, `hooks.json` runs the Python block-push **alongside** `block-push.sh`, not instead of it, so bash stays the safety net. While `WIKI_HOOK_TIMING=1` is set (start `claude` with it), the launcher appends a line to `${CLAUDE_PLUGIN_DATA}/hook-timing.log`: the script, the time Python ran in ms, its exit code, the interpreter and the plugin folder it ran from. The plugin folder shows which copy of the plugin is loaded: the clone, or an installed copy that a `git checkout` doesn't change.

**Go** if all of these hold:
- about 20 real Bash calls run with no launcher error;
- a deliberate `git push` is blocked by the Python hook, and its message reaches Claude intact (block-push's messages are ASCII; non-ASCII messages, which name paths, are checked in the guard's dual run on Windows);
- the cache ends up in the expected, protected folder;
- the Python hook alone costs at most 200 ms at p90 on Windows, from the log.

Then merge the spike and do the rest of 2b. **Rethink** if the plumbing costs much more, for example because sourcing doesn't work there and a second bash starts. Then try calling the interpreter directly from `hooks.json` before porting the guard.

### The rest of 2b, after the spike
1. **`contract.py`**: the parts of `lib-source.sh` the guard uses (`has_fm`, `field`, `list`, `values`, `contract` with its shadowing error, `instances`, `expand`, `is_abs`, `has_dots`). Until `sources.sh`, `wiki-check`, `lint` and `install` move to it (see "Later"), a parity check keeps the two parsers in step: `contract.py field|list|has-fm FILE KEY` runs against every `SOURCE.md` and instance file in the plugin and the test wikis, and must match the bash functions byte for byte. **Built 2026-11-05:** the parity check runs `contract.py parity FILE KEY...` (has-fm, then the values of every frontmatter key and one absent key) against 26 contract and instance files and 11 edge-case files (no closing fence, BOM, CRLF, bare CR, non-UTF-8 bytes, duplicate keys, odd list items), plus `contract`, `instances`, `expand`, `is_abs` and `has_dots` checks; 105 checks. Files are read with `surrogateescape` rather than `errors="replace"`, so output stays byte-identical even for invalid UTF-8. `~` expands from `HOME`, else `USERPROFILE`, with backslashes turned to slashes; the `/c/` forms stay with `guard.py` (item 3). The tests run `contract.py` directly with the cached interpreter, and set `MSYS2_ARG_CONV_EXCL` and `MSYS2_ENV_CONV_EXCL=HOME` for the pure string functions, so Git Bash doesn't rewrite their arguments.
2. **`guard.py`**, a port of `guard.sh` with the same order of checks and the same messages. Carried over exactly:
   - the Read/Grep/Glob fast path;
   - the first-broken-file rule and the diagnostic exceptions;
   - `PLUGIN_FORMS`, `root_forms`, `abs_path`, `script_path`, `allowed_script`, `main_ops` and `contains_any`.
   Files are read as UTF-8 with `errors="replace"`, CRs stripped. `subprocess` is imported only for the `git rev-parse` fallback.
3. **Windows paths.** Native Python can't open `/c/Users`, so any `/c/...` path is converted to `c:/...` before the filesystem is touched. `~` expands from `HOME`, else `USERPROFILE`. Git Bash also rewrites POSIX-looking environment variables when it starts a native program: in a real session Python gets `HOME` as `C:\Users\…`, and the fixtures' `HOME=/home/u` arrives as `C:/Program Files/Git/home/u`. Either normalise every form in Python, or set `MSYS2_ENV_CONV_EXCL` in the tests so both versions see the same value. Decide when the dual run first runs on Windows.
4. **Fold block-push into `guard.py`** (recommended), so a Bash call starts one interpreter, not two, unless the spike shows a second start is cheap enough to keep them apart. The push check runs **first**, before the Read/Grep/Glob, `allowed_script` and `diagnostic_ok` exits, and independent of `BROKEN`. Today `bash <plugin>/scripts/sources.sh show git-push` passes the guard and is blocked only by block-push. All 19 block-push fixtures keep running against `guard.py`.
5. **Dual run** for every guard fixture, every `gbroken`/`gdiag`/`gwin` case and the tilde/backslash cases: exit codes and messages agree, except the listed differences. Green on Linux, then on Windows (the user's run), with timings added to Measurements.
6. **`/wiki:init`** checks that the launcher finds an interpreter and fills the cache, with a fix-it message if not.
7. **Switch `hooks.json`** to the launcher for the guard. The commit message says the guard was reimplemented.
8. **Clean up after about a week of use in both wikis:** delete `guard.sh`, `block-push.sh`, `lib-hookjson.sh` and the dual run. Finish the CLAUDE.md rule (which scripts are Python, the launcher, the minimum version), and update the README.

Size: about 250 lines in `guard.py`, 120 in `contract.py`, 60 in the launcher and 150 in the tests. Two or three sessions after the spike, plus the Windows runs.

Defaults taken 2026-11-05, open to change: Python 3.9 or later; the dual run compares messages as well as exit codes; a week between switching and deleting.

Not ported: `codebase/*.sh`, proton-drive `read.sh` and the other wrappers that mostly wait on `git`/`gh`/a CLI. Proton's faster `new` (see `proton-drive-plan.md`) is decided at this point, from its step 1 timing.

Later, after the port: `wiki-check` (13.5 s per check on Windows) and `sources.sh` (about 3 s per `show`) don't run on every tool call, so they wait. The aim is to move them, with `lint` and `install`, onto `contract.py`, then delete the bash parser in `lib-source.sh` and the parity check with it. Trimming them in bash is the fallback.

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
- The gate (under 100 ms per guard call) is out of reach for any bash version that still starts programs: at 26–47 ms per start, it allows two or three. Step 2a should still cut the suite a lot. But reaching the gate for the guard means either pure-bash parsing with no `sed`/`awk`/`$(…)` at all, or step 2b. Python's start time, below, was measured to compare the two.

### Python start, Windows (Git Bash), 2026-11-05
Same machine, 10 runs each.

| Interpreter | `-c pass` | `-I -S -c pass` | `-c 'import json,re,os,sys,subprocess'` |
|---|---|---|---|
| `python3` (`WindowsApps`) | Store alias: prints "Python was not found" and doesn't run | | |
| `python` 3.13.5 (`AppData\Local\Programs\Python\Python313`) | 64 ms | 51 ms | 105 ms |
| `py -3` (3.13.5) | 91 ms | 73 ms | 129 ms |
| `bash -c true`, for comparison | 45 ms | | |

Findings:
- A Python guard would take about 100 ms per call, where the bash one takes 7.8 s, so step 2b alone reaches the gate. Step 2a can still cut the suite time, but for the per-call guard cost step 2b is the likely route.
- The Store alias is real here: `python3` is first on PATH and is the stub. `py` works but costs about 25 ms more than `python`.
- The launcher could cost more than the guard. A bash shim (45 ms) that checks `--version` (another ~60 ms) before running the guard (~105 ms) comes to about 210 ms per call. See step 2b's launcher item.

### Spike, Linux, 2026-11-05
Same machine as the Linux numbers above. Each call goes through `bash -c "<hooks.json command>"`, as Claude Code runs it, averaged over 20 runs.

| block-push call | `git push` (blocks) | `git commit` (passes) | Programs run | Forks |
|---|---|---|---|---|
| `bash block-push.sh` (today) | 59 ms | 58 ms | 37 | 88 |
| `. py-launch.sh block_push`, warm cache | 24 ms | 23 ms | 1 (Python) | 1 |
| same, no `CLAUDE_PLUGIN_DATA` (probes every call) | 32 ms | 33 ms | — | — |

For comparison: `bash -c true` 1 ms, `python3 -I -S -X utf8 -c pass` 13 ms (Python 3.14.4).

Suite: 646 checks, 0 failed. The block-push fixtures (28, 9 of them new) run against both versions, and the 29 `py-launch` checks take 1.2 s.

Found by the dual run: `\u0067it push` (a JSON escape for `git push`) gets past `block-push.sh` because `lib-hookjson.sh` leaves `\uXXXX` undecoded. `block_push.py` blocks it. The guard has the same gap for its words and paths until `guard.py` replaces it. Listed in `tests/fixtures/py-stricter.txt`.

### Spike, Windows, 2026-11-05: single calls
Same machine as the Windows numbers above. Each call goes through `bash -c "<hooks.json command>"`, as Claude Code runs it, 20 runs each. Every call gave the expected exit code.

| block-push call | `git push` (blocks) | `git commit` (passes) |
|---|---|---|
| `bash block-push.sh` (today) | 1544 ms (p90 1700) | 1499 ms (p90 1676) |
| `. py-launch.sh block_push`, warm cache | 173 ms (p90 189) | 167 ms (p90 197) |
| same, no `CLAUDE_PLUGIN_DATA` (probes every call) | 506 ms | 489 ms |

For comparison: `bash -c true` 62 ms, `python -I -S -X utf8 -c pass` 69 ms (Python 3.13.5). The cache filled with `C:/Users/mikke/AppData/Local/Programs/Python/Python313/python.exe`, not the Store alias, and the block message arrived intact with exit 2.

The first run above was noisy. Two more rounds, taking the hook apart:

| Part | Round 1 | Round 2 |
|---|---|---|
| `bash -c true` | 45 ms | 42 ms |
| `python -I -S -X utf8 -c pass` | 53 ms | 48 ms |
| `python -I -S -X utf8 -c 'import json,re,os,sys'` | 82 ms | 80 ms |
| `python … block_push.py` directly | 92 ms | 81 ms |
| the hook command, warm cache | 127 ms | 126 ms |

Findings:
- Sourcing works: bash plus `block_push.py` adds up to the whole hook command, so the launcher costs almost nothing and starts no second bash. No need for the "Rethink" branch.
- The Python hook costs about 126 ms per call, steady, close to the ~150 ms expected. That is about 12× less than `block-push.sh`, which alone adds 1.5 s to every Bash call today, on top of the guard's 7.8 s.
- About 30 ms of the Python time is imports (`json`, `re`). A possible saving later, not needed for the gate.
- Without the cache a call cost about 500 ms, because the probe tried the `python3` Store alias first. The probe now tries `python` first (commit after the spike), which should bring an uncached call to about 200 ms (estimate, not measured). `/wiki:init` still fills the cache (2b item 6).
- How to time: the loop in the spike commit message, with the hook command inside `bash -c` (Claude Code's outer bash costs ~45 ms on Windows, against ~1 ms on Linux), one untimed call first to fill the cache, and 20 runs.

### Spike, Windows, 2026-11-05: suite
Same machine, plugged in with sleep turned off. `WIKI_TEST_TIMING=1 bash tests/run-tests.sh` on `speed-spike`.
Suite: **2430 s (40 min 30 s)**, 646 checks, 0 failed.

| Section | Time | Checks | Before the spike |
|---|---|---|---|
| guard-fixtures (includes the block-push dual run) | 862.1 s | 173 | 834.0 s / 133 |
| py-launch | 23.5 s | 29 | new |
| guard-broken | 178.8 s | 25 | 174.9 s |
| codebase | 401.4 s | 93 | 399.5 s |
| wiki-check | 305.7 s | 23 | 310.3 s |
| sources | 278.1 s | 78 | 282.5 s |
| install | 148.8 s | 56 | 148.7 s |
| proton-drive | 73.1 s | 38 | 72.9 s |
| lint | 61.3 s | 31 | 58.2 s |
| lib-source | 53.0 s | 51 | 55.4 s |
| ms-teams | 32.6 s | 26 | 32.9 s |
| sync-status | 9.5 s | 10 | 8.5 s |
| ocr, plugin-schema, setup | 2.5 s | 13 | 1.9 s |

Findings:
- The block-push dual run agrees on Windows: Python and bash give the same exit code and message for every fixture, except those in `tests/fixtures/py-stricter.txt`. The non-ASCII fixtures pass, so `-X utf8` works with native Windows Python fed from Git Bash.
- All 29 launcher checks pass under Git Bash (fake interpreters, Store-alias stub, `py` only, broken caches, a space in the plugin path), at about 0.8 s each.
- The spike adds about 50 s to the suite. The other sections are within a few percent of the run before it, so the two runs are comparable.

### Spike, Windows, 2026-11-05: real session
Run in udbygning, not ai-wiki: ai-wiki isn't cloned on the laptop. udbygning enables `wiki@wiki-tools` from the directory marketplace at `c:\src\wiki-tools`, with no installed copy, so the session ran the clone on `speed-spike`. Every log line names `c:/src/wiki-tools/plugins/wiki/scripts` and the cached `Python313/python.exe`.

Started from PowerShell as `$env:WIKI_HOOK_TIMING=1; claude`. A first attempt wrote the cache but no log: `WIKI_HOOK_TIMING=1 claude` is Git Bash syntax, and the variable never reached the hooks.

Each run: 20 everyday Bash calls (`git status`, `ls`, `echo` and so on), then `git push` and `git -C . push`. The times are Python's run time inside the launcher, from `hook-timing.log`.

| Run | Calls | min | median | p90 | max |
|---|---|---|---|---|---|
| Parallel: two messages of 10 Bash calls each | 20 + 2 pushes | 107 ms | ~880 ms | 1169 ms | 1189 ms |
| One Bash call per message | 20 + 2 pushes | 102 ms | 109 ms | **129 ms** | 134 ms |

Findings:
- No launcher errors in either run: every pass exited 0, and both push forms exited 2.
- Both pushes were blocked by the Python hook, and the message reached Claude intact: "wiki guard: git push is not allowed in wiki sessions. Commit locally; the user pushes." udbygning's `settings.json` denies `Bash(git push *)`, but the hook ran anyway, so Claude Code runs PreToolUse hooks before the deny rule.
- The cache landed in `~/.claude/plugins/data/wiki-wiki-tools/python`, the protected folder, holding the real `python.exe` with a trailing newline.
- Parallel calls are slow because of contention, not the hook. Each Bash call starts `guard.sh` (~8 s, ~680 process starts), `block-push.sh` and the Python hook together. With ten calls arriving 0.5 s apart on a 4-core laptop, the Python processes wait for CPU: each batch climbs from ~110 ms to ~1.2 s, and the log is roughly sorted by duration. The two pushes, which came as a pair, took 148 and 118 ms. The bash guards cause this, and the port removes them. Check the parallel case again once `guard.py` replaces `guard.sh`.
- One call at a time, the Python hook takes about 110 ms even while sharing the CPU with that call's `guard.sh` and `block-push.sh`. That matches the 126 ms single-call figure, which includes bash's start.

**Verdict: go.** All four criteria hold: no launcher error, the push blocked with its message intact, the cache in the protected folder, and a p90 of 129 ms one call at a time (limit 200 ms). Next: merge `speed-spike` into `main`, then the rest of 2b, starting with `contract.py`.
