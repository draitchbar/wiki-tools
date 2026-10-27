---
type: std
title: Standard test type
access: script
platforms:
  - linux
  - windows
parameters:
  - roots (required): absolute paths
  - note (optional): free text
state:
  - last_checked: date of the newest ingest
  - cursor: opaque token
cite_prefix: Std
read_tools:
  - Bash(bash */sources/std/read.sh *)
bookkeeping_tools:
forbidden_tools:
  - Bash(std-cli *)
guard_words:
  - std-cli
scripts:
  - read.sh
---

# Source type: Standard test type
