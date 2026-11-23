# Disposable Linux environment for the Copilot compatibility spike
# (docs/plans/copilot-wiki-support.md, step 1). Both clients pinned to the
# versions under test; the home folder lives in a named volume so the
# one-time logins survive rebuilds. Never copy a personal profile in.
#
# The repo's own tests and lint are not run here: the image has no uv, no
# pytest, ruff, mypy or shellcheck, and stays outside uv.lock. If you need
# them in the container anyway, install the tools yourself and run
# WIKI_TOOLS_DEV_VENV=off bash tests/run-tests.sh (and scripts/dev-lint.sh):
# they then use the tools found on PATH, outside uv.lock, with whatever
# versions you installed (scripts/dev-env.sh).
FROM node:22-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ARG COPILOT_VERSION=1.0.112
ARG CLAUDE_VERSION=2.1.326
RUN npm install -g "@github/copilot@${COPILOT_VERSION}" "@anthropic-ai/claude-code@${CLAUDE_VERSION}" \
 && npm cache clean --force

RUN useradd -m -s /bin/bash spike
USER spike
ENV LANG=C.UTF-8
