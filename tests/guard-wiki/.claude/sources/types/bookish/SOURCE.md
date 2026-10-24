---
type: bookish
title: Bookish (local test type)
access: script
platforms:
  - linux
parameters:
  - shelf (required): shelf name
state:
  - last_checked: date
cite_prefix: Bookish
read_tools:
  - Bash(bash .claude/sources/types/bookish/fetch.sh *)
bookkeeping_tools:
forbidden_tools:
  - Bash(bookish-cli *)
guard_words:
  - bookish-cli
scripts:
  - fetch.sh
---

# Source type: Bookish
