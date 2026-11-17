# Disposable Linux environment for the Copilot compatibility spike
# (docs/plans/copilot-wiki-support.md, step 1). Both clients pinned to the
# versions under test; the home folder lives in a named volume so the
# one-time logins survive rebuilds. Never copy a personal profile in.
FROM node:22-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip git shellcheck ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip3 install --no-cache-dir --break-system-packages pytest pytest-xdist ruff

ARG COPILOT_VERSION=1.0.112
ARG CLAUDE_VERSION=2.1.326
RUN npm install -g "@github/copilot@${COPILOT_VERSION}" "@anthropic-ai/claude-code@${CLAUDE_VERSION}" \
 && npm cache clean --force

RUN useradd -m -s /bin/bash spike
USER spike
ENV LANG=C.UTF-8
