# Speed plan: a faster guard and test suite

Status: **step 2b spike done, verdict go** (2026-11-05), merged into `main` 2026-11-05. Linux: block-push 59 → 24 ms per call. Windows: 1.5 s → 126 ms per call, suite green (646 checks), and a real udbygning session at 129 ms p90 with the push blocked. Rest of 2b in progress on `speed-spike`: `contract.py` (item 1) and `guard.py` with block-push folded in (items 2–5) built 2026-11-06, green on Linux (a Bash call 394 → 29 ms). On Windows 2026-11-06 a Bash call drops from ~7 s to ~140 ms; the suite's 54 failures (two test-harness bugs) fixed 2026-11-07, 952 checks green. The `/wiki:init` Python check (item 6) built 2026-11-07. Switched 2026-11-07 (item 7): `hooks.json` runs only `guard.py`; next a real session in each wiki on `speed-spike`, then merge to main. Step 1 done (Linux 2026-11-04, Windows 2026-11-05). Step 2a only if still needed after 2b; bash trimming of the guard dropped 2026-11-05. Replaces the "Speed and Python" note in CLAUDE.md's Open plans.

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
   Files are read through `contract.py` (UTF-8 with `surrogateescape`, one CR stripped per line end). `subprocess` is imported only for the `git rev-parse` fallback.
3. **Windows paths.** Native Python can't open `/c/Users`, so any `/c/...` path is converted to `c:/...` before the filesystem is touched. `~` expands from `HOME`, else `USERPROFILE`. Git Bash also rewrites POSIX-looking environment variables when it starts a native program: in a real session Python gets `HOME` as `C:\Users\…`, and the fixtures' `HOME=/home/u` arrives as `C:/Program Files/Git/home/u`. Either normalise every form in Python, or set `MSYS2_ENV_CONV_EXCL` in the tests so both versions see the same value. Decide when the dual run first runs on Windows. **Decided 2026-11-06, to confirm on Windows:** both. `guard.py` matches every path in both spellings, as `guard.sh` does (`drive_form`/`slash_form`), and turns a `/c/...` path into `c:/...` before opening it (`native`); the tests set `MSYS2_ENV_CONV_EXCL=HOME` for the Python runs, so `HOME=/home/u` reaches both versions unchanged. In messages, Python's spelling of `$tmp` and the plugin folder is mapped back to Git Bash's before comparing (`pymap`). **Windows, 2026-11-06: half confirmed.** The matching works, and the `*-native-home` cases pass. But Git Bash converts `HOME` for a native program even when `MSYS2_ENV_CONV_EXCL` names it, so `HOME=/home/u` reaches Python as `C:\Program Files\Git\home\u`, and the three `~` fixtures fail (Measurements, "guard.py, Windows"). **Fixed and confirmed 2026-11-07:** Python works out the home as `contract._home()` does, `HOME`, else `USERPROFILE` (`guard.py` used `HOME` only). The tests hand Python the test home as `USERPROFILE`, with `HOME` removed by `env -u` (`pyhome`): Git Bash leaves `USERPROFILE` alone when `MSYS2_ENV_CONV_EXCL` names it. The `*-native-home` cases still pass `HOME` in the `C:\Users\…` form a real session uses, so both branches are tested. Checked by hand with the real home (`C:\Users\mikke`): `~/…`, `/c/Users/…`, `C:/Users/…` and `C:\Users\…` forms of a `~` root block in both guards with identical messages. A home or root under another Git Bash mount (`/home`, `/tmp`, `/usr`) would still not match on Windows; a real session doesn't have one.
4. **Fold block-push into `guard.py`** (recommended), so a Bash call starts one interpreter, not two, unless the spike shows a second start is cheap enough to keep them apart. The push check runs **first**, before the Read/Grep/Glob, `allowed_script` and `diagnostic_ok` exits, and independent of `BROKEN`. Today `bash <plugin>/scripts/sources.sh show git-push` passes the guard and is blocked only by block-push. All 28 block-push fixtures keep running against `guard.py`. **Done 2026-11-06:** the push check runs in `main()` before any other; `block_push.py` stays until the switch, as the twin of `block-push.sh`.
5. **Dual run** for every guard fixture, every `gbroken`/`gdiag`/`gwin` case and the tilde/backslash cases: exit codes and messages agree, except the listed differences. Green on Linux, then on Windows (the user's run), with timings added to Measurements. **Linux done 2026-11-06:** see Measurements, "guard.py, Linux".
6. **`/wiki:init`** checks that the launcher finds an interpreter and fills the cache, with a fix-it message if not. **Done 2026-11-06, without filling the cache:** `wiki-check.sh` (Check mode) runs the launcher with `py_version.py` and no `CLAUDE_PLUGIN_DATA`, so it probes and writes nothing: PASS with the version and path, or FAIL with the launcher's message and the fix; an INFO line says whether the hooks have cached an interpreter. Filling the cache from a wiki session isn't possible or needed: `CLAUDE_PLUGIN_DATA` isn't in the Bash tool's environment (Claude Code docs, plugins reference), any command naming the data folder is blocked by the guard's `.claude/plugins/` rule, and the first guard call caches the interpreter itself (about 200 ms once, measured 2026-11-06). The init skill also stops on a "no Python 3.9 or later found" refusal, and the README lists Python as a prerequisite.
7. **Switch `hooks.json`** to the launcher for the guard. The commit message says the guard was reimplemented. **Done 2026-11-07 on `speed-spike`:** one PreToolUse entry, matcher `Bash|PowerShell|Write|Edit|MultiEdit|Read|Grep|Glob` (the tools the three bash entries covered), command `. "${CLAUDE_PLUGIN_ROOT}/scripts/py-launch.sh" guard`, `onFailure: block`. No bash guard runs any more, so a Bash call starts one interpreter. The tests read that command from `hooks.json` for the whole dual run, and check the matcher, that the launcher appears once and that no bash guard is left. Before merging to main, a real session in each wiki on this branch, started with `WIKI_HOOK_TIMING=1`: ordinary Read, Grep, Glob, Write, Edit and MultiEdit calls pass (`hookjson.py` is stricter than `lib-hookjson.sh` and refuses input it can't parse), a `git push` and a protected path are blocked with intact messages, `agent_only` roots stay closed to the main session, and the parallel case (Measurements, "Real session") is timed again. **Linux done 2026-11-07** (Measurements, "guard.py, Linux, 2026-11-07: real session"): it found that dash ignores the `.` arguments, so the command now runs the launcher with bash where `sh` isn't bash; 25 ms median per call, nothing wrongly refused. Still to do: one Windows session, and `agent_only` in ai-wiki.
8. **Clean up after about a week of use in both wikis:** delete `guard.sh`, `block-push.sh`, `lib-hookjson.sh`, `block_push.py` and the dual run (the launcher checks that run `block_push` move to `guard`). Finish the CLAUDE.md rule (which scripts are Python, the launcher, the minimum version), and update the README.

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
- Without the cache a call cost about 500 ms, because the probe tried the `python3` Store alias first. The probe now tries `python` first (`4c6cdd9`). Measured 2026-11-06 with the same loop on `main` at `e0afb91`: an uncached call costs **200 ms** (p90 212), against 134 ms warm. The probe now costs about 65 ms, where it cost about 330 ms before. This run's machine was quieter (`bash -c true` 42 ms, `python -c pass` 50 ms, `block-push.sh` 1.3 s), so compare within a run rather than across runs. `/wiki:init` doesn't fill the cache; the first guard call does (2b item 6).
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

### guard.py, Linux, 2026-11-06
Dual run: `guard.py` is compared with what Claude Code gets from the bash hooks: `block-push.sh`'s block, else `guard.sh`'s result (`gdual` in `run-tests.sh`; `block-push.sh` runs only when the input mentions "push", since otherwise it blocks only where `guard.sh` blocks with the same message). It covers all 113 guard and 28 block-push fixtures, the `gbroken`, `gdiag` and `gwin` cases, the tilde and backslash forms, and the review cases below (`gcase`): 185 checks. 172 give identical exit code and message; the other 13 are the deliberate differences (the four block-push cases in `py-stricter.txt` and the review cases marked stricter, message or locale). Suite: 952 checks, 0 failed. The bash hooks run with `LC_COLLATE=C` in the tests, so their globs sort as Python's do.

Checking the checks: 13 deliberate bugs in `guard.py`, each run through the suite. Nine failed checks at once. Three got through and showed gaps that `guard.sh`'s own tests had too; each now has a test:
- a wrapper nested one folder deeper (`sources/<type>/sub/read.sh`): new fixture `block-source-script-nested`;
- `..` at a drive root (`C:\..\Users\...` stays `C:/Users`): `gwin`-style check `codebase-read-windows-dotdot`;
- two broken source files (the message names the first): `gbroken first-of-two`.
The fourth can't be reached: `main_session_op` takes the longer of `"..."` and a bare word as the script, as `sed -E` does, but a script call with text right after the closing quote is never an allowed script, so the choice never shows.

Per call (20 runs each, the guard-wiki copy, warm cache):

| Fixture | `guard.sh` | `block-push.sh` | `guard.py` (both, via the launcher) |
|---|---|---|---|
| pass-ordinary-bash | 335 ms | 59 ms | 29 ms |
| pass-edit-wiki-page | 312 ms | | 27 ms |
| pass-read-wiki-page | 140 ms | | 27 ms |
| pass-standard-source-script | 324 ms | 57 ms | 27 ms |

A Bash call drops from about 394 ms (both bash hooks) to 29 ms. Windows: see "guard.py, Windows".

### guard.py review, 2026-11-06
A review agent compared `guard.py` with `guard.sh` and `block-push.sh` line by line and ran about 40 crafted inputs through both. It found no realistic input where Python allows what bash blocks. The edge cases it found, and what was done (each has a `gcase` in `run-tests.sh`):
- **Unicode whitespace in contract values** (e.g. `roots: /home/u/Scans<U+2003>`): in a UTF-8 locale sed strips it, so bash blocked and Python allowed. Now `contract.py` strips Unicode whitespace around values and before list items, and `guard.py`'s `agent_only`/`type` greps take it too (`unicode-space-root`, `unicode-space-agent-only`). Bash's result depends on the locale, so only Python is checked ("locale").
- **Unicode whitespace in commands** (`bash<U+2003><plugin>/scripts/lint.sh`): Python keeps ASCII whitespace and blocks; bash in a UTF-8 locale allows. Deliberately stricter (`unicode-space-command`).
- **Case folding**: Python lowercased Unicode, bash only ASCII. Now ASCII only in both (`hookjson.lower`), so messages keep Æ/Ø/Å as written (`non-ascii-root`, `kelvin-sign`).
- **Instance file names with spaces**: bash splits them into words. Python now treats any instance name that isn't a kebab-case key as a broken source file, stricter than both (`instance-key-space`, `instance-key-copy`).
- **Wiki path with a space**: bash splits the agent_only instance paths and lets a main-session Read through; Python blocks (`wiki-path-space-read`). A bash bug, not fixed in bash.
- **A source folder that can't be listed** (mode 000): both read it as empty and allowed everything. Python now treats it as broken for Bash and Write/Edit (`unreadable-instances`, skipped where the folder stays readable: root, Windows). Read/Grep/Glob still pass, as for a broken file.
- **Quotes or a backslash in a main-session wrapper call** (`git.sh code" "status grep`): bash read the operation as `status`, while the script gets `grep`. Python now requires the key and the operation to be plain words (`main-op-quoted`, `main-op-backslash`).
- **JSON null**: Python blocked a call with a null field (e.g. Grep's `path`). Now null counts as absent, as in bash (`null-path`, `null-agent-id`).
- **Glob order**: bash sorts by the locale's collation, Python by bytes; with two broken files this can name a different one (same decision). The tests run bash with `LC_COLLATE=C` (`first-of-two-types`); in a real session the message may name the other file.
- **Windows HOME**: a real session hands Python `HOME` as `C:\Users\u`. Two dual-run cases now give Python that form while bash gets `/c/Users/u` (`*-native-home`). `pymap` also maps backslash spellings of the temp and plugin folders.
- Not changed: JSON `\b` and `\f` escapes (bash keeps them as text, Python decodes them; no realistic needle is affected), and `main_session_op`'s longest-match rule (unreachable, see above).
- Test and doc fixes: a duplicate `pyrun`/`pystr`, "19 block-push fixtures" (28), and the `errors="replace"` line in item 2.

### guard.py, Windows, 2026-11-06
Same laptop as the Windows numbers above, plugged in with sleep turned off. `WIKI_TEST_TIMING=1 bash tests/run-tests.sh` on `speed-spike` at `9263834`.
Suite: **2738 s (45 min 38 s)**, 950 checks, **54 failed**, 1 skipped (`unreadable-instances`: the folder stays readable on Windows).

| Section | Time | Checks | Spike run (2026-11-05) |
|---|---|---|---|
| guard-fixtures (with the guard.py and block-push dual run) | 907.7 s | 315 | 862.1 s / 173 |
| guard-broken (gbroken, gdiag, gwin, gcase, dual run) | 289.0 s | 78 | 178.8 s / 25 |
| contract-parity (with the contract-py path checks) | 67.8 s | 105 | new |
| py-launch | 23.9 s | 33 | 23.5 s / 29 |
| codebase | 429.3 s | 93 | 401.4 s |
| sources | 312.7 s | 78 | 278.1 s |
| wiki-check | 315.5 s | 23 | 305.7 s |
| install | 154.5 s | 56 | 148.8 s |
| proton-drive | 74.5 s | 38 | 73.1 s |
| lib-source | 56.4 s | 51 | 53.0 s |
| lint | 56.2 s | 31 | 61.3 s |
| ms-teams | 39.2 s | 26 | 32.6 s |
| sync-status | 8.6 s | 10 | 9.5 s |
| ocr, plugin-schema, setup | 2.9 s | 13 | 2.5 s |

The 54 failures are two bugs in how the tests start Python under Git Bash. Neither is a case a real session meets:
- **51 × `contract-py/expand|is_abs|has_dots-N`.** `pystr` sets `MSYS2_ARG_CONV_EXCL='*'`, which also leaves the script's own path unconverted: Python is handed `/c/src/wiki-tools/plugins/wiki/scripts/contract.py`, reads it as `C:\c\src\...`, and exits 2 before any function runs. Fix: pass the script path in Windows form, or exclude only the test arguments.
- **3 × `guard_py` tilde fixtures** (`block-bash-expanded-tilde-root`, `block-codebase-grep-tilde`, `block-edit-into-tilde-root`): `guard.py` allows where bash blocks. Git Bash always converts `HOME` for a native program and ignores `MSYS2_ENV_CONV_EXCL` for it: with `HOME=/home/u`, Python gets `C:\Program Files\Git\home\u` whether `MSYS2_ENV_CONV_EXCL` is `HOME`, `*` or unset (Git for Windows' MSYS runtime 3.5.7; the exclusion does work for other variables, e.g. `FOO=/home/u`). So `~/Pictures/Receipts` no longer matches `/home/u/Pictures/Receipts` in the command. Item 3's test approach doesn't hold for `HOME`; see the note there.

Passing on Windows: the rest of the dual run (exit code and message, including the `*-native-home` cases that use a real session's `HOME` form), `contract-parity` byte for byte, `py-launch`, and every bash section.

Per call: 20 runs for `guard.py` and `block-push.sh`, 5 for `guard.sh`. Each call goes through `bash -c` on a guard-wiki copy committed into its own git repo, with a warm cache and `HOME=/home/u`.

| Fixture | `guard.sh` | `block-push.sh` | `guard.py` (both, via the launcher) |
|---|---|---|---|
| pass-ordinary-bash | 6796 ms | 1188 ms | 139 ms (p90 144) |
| pass-edit-wiki-page | 7262 ms | | 193 ms (p90 204) |
| pass-read-wiki-page | 3927 ms | | 163 ms (p90 173) |
| pass-standard-source-script | 8151 ms | 1245 ms | 142 ms (p90 150) |

Findings:
- A Bash call drops from about 7 s (`guard.sh`, with `block-push.sh` beside it) to about 140 ms; Write/Edit, the slowest, from about 7.3 s to 193 ms.
- `pass-standard-source-script` exited 2 in this loop for **both** `guard.sh` and `guard.py`, so the loop's setup differs from the suite's for that fixture; both agree, and it passes in the suite. Only its times count here.
- Next: fix the two test bugs, rerun the suite on Windows, then `/wiki:init` (item 6) and the switch (item 7).

Rerun 2026-11-07, after the fixes (item 3): **2889 s (48 min 9 s), 952 checks, 0 failed**, 1 skipped (`unreadable-instances`). The 51 `contract-py` path checks now get their script path in Python's spelling (`pyscripts`); the three `~` fixtures, run through `USERPROFILE`, match bash; two new checks cover `HOME` winning over `USERPROFILE` and the fallback. Section times are within 10% of the run above (guard-fixtures 974.1 s, guard-broken 301.9 s, contract-parity 78.6 s / 107 checks); the laptop runs a little slower from day to day.

### guard.py, Linux, 2026-11-07: real session
Run in carleasing (gmail and proton-drive instances, no `codebase`), which loads the plugin from the clone on `speed-spike`, started with `WIKI_HOOK_TIMING=1`. A wiki-tools session sent it a checklist over a cross-session message.

**Found first: the switched hook refused every call.** Claude Code runs hook commands with `sh`, which on Ubuntu is dash, despite `"shell": "bash"`. Dash's `.` ignores arguments, so `py-launch.sh` saw an empty script name: "bad script name ''", fail closed. On Windows `sh` is Git Bash, which is why the spike's real session worked. `main` has had the same bug since the spike merge (2026-11-05): its `. py-launch.sh block_push` hook refuses every Bash call in a Linux wiki that loads the clone. The tests missed it because they ran the command with `bash -c`. Fixed: the command sources the launcher only when `$BASH_VERSION` is set, and otherwise runs it with `exec bash` (about 2 ms on Linux). The tests now run the `hooks.json` command under `sh`, `bash` and `dash`. The session needed a restart to pick up the new command.

After the restart, 28 guard calls:

| | n | min | median | p90 | max |
|---|---|---|---|---|---|
| `guard.py` per call (Python's run, from the log) | 28 | 23 ms | 25 ms | 27 ms | 32 ms |

- Passed (rc=0), as expected: Read, Write and Edit; Bash `grep`/`find`; `sources.sh list` and `show proton`; `sync-status.sh`, `lint.sh`, `wiki-check.sh`; `rm` of the scratch file. Read of the plugin's `hooks.json` passes too: Read is closed only for `agent_only` roots.
- Refused (rc=2) by the guard, with intact messages: `git push --dry-run` (the push message, before the settings' `Bash(git push *)` deny rule), `cat .claude/sources/instances/proton.md`, `cat <plugin>/hooks/hooks.json`, `proton-drive --help`.
- Ten parallel `echo` calls: 24–32 ms each. No climb, against ~110 ms → ~1.2 s on Windows with the bash guards beside the Python hook.
- `wiki-check.sh`: "PASS the guard hooks find Python 3.14.4 /usr/bin/python3" and "INFO the guard hooks have cached `/usr/bin/python3`". Its two FAILs are carleasing's own setup (the old schema import by path in CLAUDE.md; the wrapper rule `Bash(bash */sources/proton-drive/read.sh *)` missing from its settings), not the guard.
- Not covered: that session had no Grep, Glob or MultiEdit tool, so those tools' input went untested (the fixtures and dual run cover them); `agent_only` needs ai-wiki (Windows); Windows still has to run the new command once.
