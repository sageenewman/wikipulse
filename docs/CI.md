# CI and the Pull Request Workflow

How a change gets from a branch into `main`: what runs on every pull request, how to read a failure, and how reviews are requested. The decisions behind it are in [ADR-0009](adr/0009-ci-and-automated-review.md); the review procedure itself is in [CODE_REVIEW.md](CODE_REVIEW.md).

## The pull request, step by step

1. **Branch and commit.** Branch names and commit messages follow [CONTRIBUTING.md](../CONTRIBUTING.md).
2. **Open the pull request.** The description answers four questions: why, what changed, how it was verified, what is not included ([ENGINEERING.md](ENGINEERING.md), section 7).
3. **CI runs by itself:** the checks, the lakehouse test, the Spark tests and, once, the automated review. The review appears as a comment that starts with `## Review of #<number>` and ends with the commit it reviewed.
4. **Answer the review.** Fix what needs fixing and push. Each push runs the checks again, but **not** the review.
5. **Post a "Changes after review" comment**, using the template in [CODE_REVIEW.md](CODE_REVIEW.md#changes-after-review-template). It must start with the heading `## Changes after review`.
6. **Optional: request another review** by adding the `review` label to the pull request (see below).
7. **The owner decides the merge,** after reading the description and the changes-after-review comment. Pull requests are squash-merged.

## Requesting another review

Pushes never start a review: each review uses the owner's Claude subscription. To ask for one:

- **Add the label `review`** to the pull request (in GitHub: *Labels* on the right, or `gh pr edit <number> --add-label review`).
- The workflow reviews the pull request as it is now. It also reads the earlier reviews and the changes-after-review comments, and starts the new review with an **Earlier findings** section: each earlier blocker and "should fix", marked fixed, not fixed or deferred.
- **The label is removed automatically** when the review is done, so you add it again for the next one. (GitHub sends no event for a label that is already on the pull request.)

Only comments that can be trusted are passed to the reviewer: reviews posted by the workflow (`github-actions`), and changes-after-review comments from people with write access. A comment from anyone else is ignored, whatever its heading.

## The CI jobs

All jobs are in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). They run on every push to a pull request and to `main`.

| Job | What it does | When it fails | Typical time |
|---|---|---|---|
| **Lint, types, tests** | `make lint`, `make typecheck`, `make test`. Each runs even if the one before failed | Code style, a type error, or a failing test | 20s |
| **Lakehouse end to end** | `make lakehouse` (object storage and catalog), then `make check-lakehouse`: a table is created through the catalog, its files are found in storage, and dropping it removes them | A broken image upgrade, catalog setting or setup script | 30s |
| **Spark tests** | Builds the Spark image and runs `tests/spark/` inside it (`make test-spark`), on the image's Python 3.10 | A failing Spark test, or code in `streaming/` that does not run on Python 3.10 | 1 min |
| **Code review** | The automated review (below). Once when the pull request opens or leaves draft, then only with the `review` label | The review could not be written (below) | 2–4 min |
| **Remove the review label** | Removes `review` after a requested review | Rarely; the label then stays and must be removed by hand | seconds |

### Reading a failure

- **The run's summary page** (the *Summary* of the workflow run) shows a table with each check passed or failed, and the output of every failing check under a fold.
- **On the pull request's "Files changed" tab**, lint and type errors are marked on the line they refer to.
- **The lakehouse job** prints the logs of the storage and catalog services when it fails.
- To reproduce locally, run the same `make` target in the codespace.

## The automated review

The reviewer is the agent defined in [`.claude/agents/code-reviewer.md`](../.claude/agents/code-reviewer.md), following [CODE_REVIEW.md](CODE_REVIEW.md).

**What it gets:** the diff, the pull request description, the output of the lint, type and test job (produced by CI, not by the author), and the earlier reviews.

**What it can do:** read and search files. It has no shell, cannot run code, and cannot write anything. The workflow, not the agent, posts its review as a comment. Anything that needs running to confirm goes under "Not verified" in the review.

**Things to know:**

- The agent's definition (`.claude/`) is always taken from `main`, so a pull request cannot change its own reviewer. The workflow file and `docs/CODE_REVIEW.md`, however, come from the pull request.
- Pull requests from forks get no automated review: GitHub does not give them the secret. They are reviewed by hand.
- The reviewer does not yet see the results of the lakehouse and Spark jobs (roadmap item).
- Its verdict is a recommendation. Its findings are checked before they are acted on: it cannot run anything, and it is sometimes wrong.

### When the review fails

The **Code review** job turns red and **no comment is posted**. Common causes:

- **The Claude subscription limit was reached.** Add the `review` label again later.
- **The token expired or was revoked.** Replace the secret (below).
- **The review has no `## Review of` heading.** It is posted anyway, with a warning line at the end: a later review will not see it.

For debugging, each review run keeps the agent's full session as the artifact `review-session` for 7 days (on the run's summary page).

## Setup and secrets

| Item | What it is | How to set it |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` (repository secret) | The Claude subscription token the review runs on | Run `claude setup-token` on your machine, then `gh secret set CLAUDE_CODE_OAUTH_TOKEN` and paste it. To replace it, do the same again |
| `review` label | Requests a review | Exists already. To recreate: `gh label create review --description "Run the automated code review again without a push"` |

There is deliberately no Anthropic API key: reviews use the subscription and are never billed per use. Keep "extra usage" turned off in the Claude account settings so that reaching the limit stops reviews instead of costing money.

## Changing the workflow

- Every third-party action is pinned to a full commit SHA, with the version in a comment (`uses: actions/checkout@<sha> # v7.0.1`). To update one, take the SHA of the new release tag (`gh api repos/<owner>/<repo>/git/ref/tags/<tag>`) and change both.
- A change to the workflow runs on its own pull request, so the pull request is the test of the change.
