# ADR-0009: CI and automated code review in GitHub Actions

- **Status:** Accepted
- **Date:** 2026-10-20

## Context
Lint, type checks and tests existed, but only as `make` targets. Nothing stopped a merge if nobody ran them ([ENGINEERING.md](../ENGINEERING.md), section 8).

Every pull request is meant to be reviewed by the read-only reviewer agent ([CODE_REVIEW.md](../CODE_REVIEW.md)). It was started by hand, and it was skipped at least once. It also took the check results from the author, so it could not report a "pass" on its own evidence.

Two constraints shape the answer: the repository is public, and the project's running costs must stay near zero ([ADR-0005](0005-cloud-cost-strategy.md)).

## Decision
One workflow, [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), with two jobs:

- **checks** runs `make lint`, `make typecheck` and `make test` on every push to a pull request and to `main`. Each check runs even if an earlier one failed. Results are shown as a table on the run's summary page, with the output of each failing check, and lint and type errors are marked on their lines in the pull request's changed files. The output is also saved for the reviewer.
- **review** runs after the checks. It gives the reviewer agent the diff, the pull request description, the CI output and the earlier reviews of the pull request. Claude writes the review to a file, and a plain workflow step posts it as a comment, with the reviewed commit and a link to the run. It uses [`anthropics/claude-code-action`](https://github.com/anthropics/claude-code-action).

The review runs when a pull request is opened, on every push to it, and when it leaves draft. A review after fixes starts with the earlier findings, each marked fixed or not fixed, and then reviews the pull request as it is now. A newer push cancels a review that is still running. The `review` label runs a review again without a push, for example after a review failed because the subscription limit was reached.

Authentication and permissions:

- **Claude:** a Claude subscription token (`CLAUDE_CODE_OAUTH_TOKEN`, created with `claude setup-token`). The workflow has no API key, so a review is never billed per use.
- **GitHub:** the workflow's own token, limited to reading the code and writing pull request comments. Comments appear as `github-actions[bot]`.
- **Pinning:** every third-party action is pinned to a full commit SHA, so a moved tag cannot change what runs.

## Alternatives considered
- **A cloud scheduled task in Claude Code with a GitHub trigger:** the fastest to set up, and nothing is added to the repository. But the setup lives in a personal account, with no version history and no review. It posts under the owner's GitHub name, so the review would look like the author approving their own work. The feature is also a research preview.
- **An Anthropic API key instead of the subscription token:** the standard choice for a team. It is billed per use, and nothing caps a bill except limits set separately in the API console. It becomes the right choice when several people open pull requests, or when reviews outgrow a personal subscription.
- **The Claude GitHub App instead of the workflow token:** comments would appear as `claude[bot]`, and the app refuses to run a workflow file that differs from the one on `main`. It needs the app installed on the repository with write access to contents, which this read-only reviewer does not need.
- **Review only when a pull request opens, and again on request with a label:** uses less of the subscription. But the fixes made after a review would not be reviewed unless someone remembers to ask, and the fixes are where new mistakes often come in. Reviewing every push is chosen while pull requests are few. It becomes the wrong choice if pushes are frequent enough to reach the subscription limit.
- **Claude posts the comment itself (`gh pr comment`):** one step fewer. A plain workflow step does it instead, so Claude needs no command-line tools at all, only reading and writing files.

## Consequences
- ✅ A pull request cannot look green without lint, types and tests passing on GitHub's machines.
- ✅ The review always runs, and it reports check results that the author did not produce.
- ✅ No per-use bill: GitHub Actions is free on standard runners for public repositories, and the review uses the subscription.
- ✅ The action takes the `.claude/` folder from the base branch, so a pull request cannot change its own reviewer.
- ⚠️ Every push uses the owner's subscription, including a push that only fixes a typo. When the limit is reached, the review posts that it failed, and is run again later with the label.
- ⚠️ A change to the reviewer agent takes effect only after it is merged, since the pull request is reviewed by the agent on the base branch.
- ⚠️ Pull requests from forks get no review: GitHub does not pass secrets to them. This is correct for a public repository. A contributor's PR would be reviewed by hand.
- ⚠️ The subscription token is tied to one person's account. If it expires or the subscription ends, reviews stop until it is replaced.
- ⚠️ Making the checks required for merging is a repository setting (branch protection), not part of this file.
