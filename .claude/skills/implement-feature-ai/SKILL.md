---
name: implement-feature-ai
description: Build a feature of this repo from a goal and hand back one pull request for approval. Argument, the goal, a description or words naming a docs/roadmap.md item (`"gws reader"`). Grills the user until nothing is open, writes a spec, then either a design pull request for the owner to merge first or a plan, builds the plan's tasks in parallel subagents on task branches, each reviewed, merges them into one pull request, and follows it until CI is green and the review is answered. Resumable, run it again with the same goal. Never merges. Only for a wiki-tools session, and only when the user runs /implement-feature-ai.
argument-hint: "<goal or roadmap item>"
disable-model-invocation: true
---

# Implement feature: $ARGUMENTS

Run only when the user typed `/implement-feature-ai`; if you loaded this skill yourself, stop and ask whether to start it.

You coordinate: grill the user on the goal, get it designed or planned, get each task built and reviewed by subagents, and follow the one pull request until it is ready for the user to merge. The decisions are the user's; facts you look up. You never merge.

Repo rules: `AGENTS.md` and `CONTRIBUTING.md`. They win over this skill where they differ. The parts this skill shares with `/fix-issues-ai` are in `docs/agent-pr-flow.md`; read it now (untrusted input, models, the brief, the pull request text, following a pull request).

`<agent>` is `claude` or `copilot`; `<slug>` is two to four words naming the goal, no personal data. Reuse the slug a goal already has (its roadmap item, `docs/plans/<slug>.md`, its pull requests or branches) before making one up. Branches: design `<agent>/design-<slug>`, integration `<agent>/<slug>`, tasks `<agent>/<slug>-<task>` (not `<agent>/<slug>/<task>`: git can't hold both refs).

## 0. Which goal, and where it stands
- No argument: ask for the goal. Start nothing the user didn't name.
- Words that may name a `docs/roadmap.md` item: match them against the items; none or several, list the candidates and ask. Read the item and any `docs/plans/<slug>.md` it links: that is the starting draft.
- Set up as in `docs/agent-pr-flow.md`, "Set up".
- Look for an earlier run of this goal (`gh pr list --state all --search <words>`, `git branch -a --list '<agent>/*<slug>*'`, `git worktree list`), and take the first that applies:
  1. an open goal pull request: carry on following it (step 6);
  2. an integration branch `<agent>/<slug>`, local or pushed, with no pull request (a run stopped in step 4 or 5): continue it, don't recreate it;
  3. an open design pull request: fold in the owner's review comments, push, follow it (step 2), stop again;
  4. a design plan merged on `main`: go to step 4, with that plan.
- Then remove local task branches and worktrees already merged into `<agent>/<slug>`; one with commits merged nowhere, ask.
- The scratchpad is per session: on a re-run, rebuild the spec file (step 1) and the plan from what the run left (the plan doc, the pull request description, the integration branch's commits), and grill briefly on only what is missing or changed.

## 1. Grill
Self-contained; don't start `/grilling`.
- Walk the design tree, a round at a time. Number each question and give your recommended answer, worded so "yes" accepts it. A fact the repo or a subagent can answer, look up; never ask it. Decisions are the user's. With a roadmap item or plan, grill only on what is open.
- Done when nothing is open and the user confirms. In that confirmation, say whether a **design session** is needed and why; the user can overrule. Signs: a new ADR or a change to one; a new mechanism, contract key, skill, source type or dependency; a choice of tech stack (language, tool, library, service) or design paradigm; a migration for existing wikis; a change to the guard, or across several scripts with a shared interface; design choices with real trade-offs left.
- Write the **spec file** in the scratchpad (Claude Code names one; otherwise a new folder under the system temp directory, never in the repo): intent, decisions, acceptance criteria ("done when"). Every subagent reads this file, not your paraphrase.

## 2. Design session (only when needed)
- A research subagent (`opus`) researches and drafts the design from the spec file, online best practice included, with sources cited; no personal or project data in a search query.
- A reviewer on the strongest model (`fable`; Copilot CLI, rubber duck as in step 4) reviews it with fresh context; fold the findings in.
- The **design pull request**, branch `<agent>/design-<slug>` from `origin/main`, its text as in `docs/agent-pr-flow.md`, "The pull request text" (it becomes the commit on `main`): `docs/plans/<slug>.md` with the plan contents (step 3) plus the design with alternatives weighed, the research with its sources, and the review's findings and how each was resolved; and the `docs/roadmap.md` item, linking to it. No ADR text: that comes with the last task.
- Follow it (`docs/agent-pr-flow.md`, "Following a pull request") until ready, then **stop**: "design pull request ready for your review; run `/implement-feature-ai <slug>` again once it is merged", naming the slug. The owner merges it; the next run goes on from step 0.

## 3. Plan (no design session)
A planner subagent (`opus`) writes the plan into the scratchpad, never the repo; a reviewer subagent with fresh context reviews it, and the planner folds the findings in. The plan, on both paths:
- **Tasks** that can be built alone, each with its dependencies, the files it owns, its "done when", its tests (automated, or live where only a real wiki will do), its docs updates, and its model (`docs/agent-pr-flow.md`, "Models"). Tasks that share a file are sequenced, never parallel.
- **Automate first:** every check that can be is a test (fixtures, fakes, e2e in `tests/`); only what needs a real wiki stays a live step.
- **Migration** per task: "none", or the steps for existing wikis (they go in the pull request description only, no upgrade doc).
- **Demo:** the user's steps, end to end, once the goal is built (TL;DR).

Show a TL;DR table (task, depends on, files owned, model) and carry on without waiting. If live steps remain, ask the user now to open the wiki sessions they need, so those are ready when the pull request is.

## 4. Implement
- Create `<agent>/<slug>` from `origin/main` (after a merged design, that has the plan), unless it exists (step 0): then continue it. It is the only branch pushed locally and the only pull request.
- After a merged design, if the plan has live steps, ask the user now to open the wiki sessions they need (as in step 3).
- One implementer subagent per task, on its own branch `<agent>/<slug>-<task>`, from the integration branch or, for a dependent task, from its upstream task's branch (or the integration branch once the upstream is merged in). Don't wait for approval between tasks.
  - **Claude Code:** each in its own worktree (`isolation: worktree`), in the background, on the plan's model. Independent tasks in parallel: start around 3; at most 4 at a time locally, 10 in a cloud session; the rest queue (parallel runs cost many times the tokens).
  - **Copilot CLI:** subagents (`task`) share one working tree: run implementers one after another, each on its branch.
- The brief: `docs/agent-pr-flow.md`, "The brief", written out, and: the spec file's path; the plan's path and the task's part; the files it owns; the base branch and commit to branch from (a worktree starts from the default branch otherwise); its "done when". Output: commits on its task branch, and the report. Say whether it pushes: locally an implementer never pushes (the brief's push rules apply only to a push the skill asks for); in a cloud session it may push its task branch.
- **Per-task review**, before merging: a reviewer subagent with fresh context, read-only, given the spec file, the task's part of the plan, the task branch, the diff to read (`git diff <base>..<agent>/<slug>-<task>`) and the worktree or checkout it is in. It reports correctness bugs and spec gaps with evidence, not style, and flags any edit to an existing test or fixture and any hard-coded or special-cased behaviour. Its model at least as strong as the implementer's, preferably stronger (`haiku` → `sonnet` or `opus`; `sonnet` → `opus`; `opus` → `fable`). **Copilot CLI:** rubber duck (`/rubber-duck`), which picks a different model family itself; you may invoke it only when "Proactive invocation" is on in `/subagents`, (`subagents.agents["rubber-duck"].autoInvoke`), otherwise ask the user to run `/rubber-duck <prompt>` with your prompt.
- Real findings go back to the implementer. A task that fails review or CI twice has failed its attempt (`docs/agent-pr-flow.md`, "Following a pull request": a retry on the next stronger model; on `fable`, stop and ask).
- Merge each reviewed task branch into `<agent>/<slug>` (`git merge`, no squash: the task commits stay). Delete a task branch pushed in a cloud session on GitHub once merged.

## 5. Integration
- The last task, or you here once every task is merged: remove the roadmap item, delete `docs/plans/<slug>.md` if one was committed, add the ADR text if the design called for one (`AGENTS.md`, "Plans").
- Then: `bash tests/run-tests.sh`, `bash tests/run-tests.sh --e2e` and `bash scripts/dev-lint.sh` on the integration branch; again after any later fix.
- One fresh-context review of the whole integration diff against the spec file, on the strongest model (`fable`; Copilot CLI: rubber duck), for clashes between tasks. Findings to a task's implementer, or a new task.

## 6. The pull request
Push `<agent>/<slug>` and open the pull request, base `main`. The description, TL;DR, in this order, as in `docs/agent-pr-flow.md`, "The pull request text" (it becomes the commit on `main`):
1. The goal; the roadmap item or design pull request it comes from.
2. Tasks: a table of task and what changed. No model names (the brief's commit rule holds for the description too); you give the models in the hand-over.
3. Demo.
4. Live test plan, if any; the user's steps marked as theirs.
5. Migration steps, or "none".
6. Decisions made along the way, and how to overrule each.
7. What wasn't checked.
8. The owner-review flag, if `.github/workflows/` or `scripts/pii*` changed.
Plus the evidence: the test commands and their results.

Follow it (`docs/agent-pr-flow.md`, "Following a pull request"), fixing through the task's implementer or yourself on the integration branch, and update the description after every fix.

**Live tests:** send the steps to the wiki sessions the user opened. In Claude Code you may send them to an open local session yourself (SendMessage); in Copilot CLI give the user the steps to paste. A skill the model can't start (`disable-model-invocation`: init, add-source, ingest, clarify, lint, audit, commit-themes) is the user's step. Failures the user reports are fixed on the same branch.

## 7. Hand over
When the pull request is ready or blocked, stop following it and tell the user: the slug; "ready", "ready, live test pending", or what blocks it; a table of task, implementer model, reviewer model; what to look at before merging (decisions made along the way, behaviour that changes); what wasn't checked. Delete the local task branches and worktrees. Merging is the user's: don't merge, approve, or delete the integration branch.
