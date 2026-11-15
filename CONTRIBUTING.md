# Contributing

wiki-tools is shared for people to install and use. Issues and pull requests are open to invited collaborators only; anyone may read, fork and use the code under the MIT license (`LICENSE`).

## For collaborators

- **Workflow:** a branch pushed to this repo (not a fork: fork PRs get no secrets, so the checks fail), a pull request, squash merge. The rules for changing the code are in `CLAUDE.md` and `docs/development.md`: tests for every script or hook change, lint, LF line endings.
- **No personal data, anywhere public.** Not in files, commits, branch names, tags, PR titles and descriptions, issues or comments: no real names, emails, addresses or places, hostnames or user folders, employer details or third parties. Test data uses made-up names and reserved domains (`example.com`, `.invalid`). A push to a public repo can't be taken back, even by deleting the branch.
- **Before your first push,** switch on the check in your clone: `git config core.hooksPath .githooks`. Never push with `--no-verify`.
- **Your GitHub email settings:** turn on "Keep my email addresses private", and commit as your noreply address (`git config user.email <id>+<user>@users.noreply.github.com`). The squash commit on `main` uses your GitHub email, and the check accepts only noreply addresses.
- **Trust:** the checks run your branch's own copy of the workflows and the check, with the repo's secrets. Changes to `.github/workflows/` or `scripts/pii*` are reviewed by the owner before merging.
