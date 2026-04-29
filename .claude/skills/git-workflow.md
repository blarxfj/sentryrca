# Skill: Git workflow, branching, and CI/CD discipline

## Before starting any task
1. `git fetch && git switch main && git pull --ff-only`.
2. Branch: `git switch -c <type>/<short-kebab-name>`. Types: `feat`, `fix`,
   `chore`, `docs`, `eval`, `refactor`, `ci`, `test`.
3. If hooks aren't installed yet: `make hooks` (runs
   `pre-commit install && pre-commit install --hook-type pre-push`).

## While working
- Commit early and often. Each commit is one logical change.
- Conventional Commits: `<type>(<scope>): <subject>`.
  Subject is imperative, lowercase, ≤72 chars, no period. Example:
  `feat(retrieval): add reciprocal rank fusion`.
- Body explains *why*. Reference ADR by filename if relevant:
  `Refs: docs/ADR/0007-hybrid-retrieval.md`.
- Never commit secrets, `.env` files, or generated artifacts.
  `.gitignore` should already cover these — if you find yourself adding
  `git add -f`, stop.

## Before pushing
- Pre-commit hooks already ran on `git commit`. Pre-push runs the full
  unit + integration suite. Both must pass.
- `--no-verify` is forbidden. If a hook is genuinely broken, fix the hook
  in a separate `chore(ci):` branch, don't bypass it.
- Rebase on `main` before pushing if your branch is behind:
  `git fetch && git rebase origin/main`. Resolve conflicts locally, never
  in the GitHub UI.

## Opening a PR
- Title = the eventual squash-merge commit message. Use Conventional
  Commits format.
- Fill in `.github/pull_request_template.md`. Don't skip checkboxes — they
  exist because we've been burned by skipping them.
- Required PR template sections:
  - **What changed and why** (2–4 sentences)
  - **ADR link** if a non-trivial design choice was made
  - **Test plan** — what you ran locally, what CI will run
  - **Eval impact** — required for PRs touching `agents/`, `retrieval/`,
    `schema/`, or prompts. Paste the before/after metrics from
    `make eval-fast` (or full `make eval` for big changes).
  - **Observability impact** — did you add new spans, change tags, or
    alter the audit-table schema? If yes, link the Langfuse trace.
  - **Rollback plan** — one sentence. "Revert the squash commit" is a
    valid answer for most PRs; deploy migrations are not.
- Self-review the diff in the GitHub UI before requesting review. You'll
  catch 30% of your own bugs this way.

## CI gates a PR must pass
1. `lint` — `ruff` + `mypy --strict`.
2. `test` — pytest with coverage floors (80% for `schema/`, `retrieval/`,
   `eval/`; 60% elsewhere).
3. `build` — docker compose build + `/health` smoke test.
4. `eval-gate` — fast 10-incident subset. Hard fails: top-1 accuracy drop
   >3% vs `eval/baselines/main.json`, citation faithfulness <95%, p95
   latency >15s.
5. `security` — `pip-audit`, `gitleaks`, Trivy on the image.

If `eval-gate` fails because the agent legitimately got better/different,
update the baseline in the same PR and explain in the PR body. Never
update the baseline to mask a regression.

## Merging
- Squash-merge only. PR title becomes the commit on `main`.
- Delete the branch after merge (GitHub setting: enable
  "automatically delete head branches").
- If the merged commit breaks `main` (rare, but happens with flaky
  tests or eval drift), revert immediately with
  `git revert <sha>`, then fix forward in a new branch. `main` is always
  green.

## Releases and deploys
- `main` auto-deploys to staging on every merge (`deploy-staging.yml`).
- Production deploys are tag-triggered. Cut a release with:
  `git tag -a vX.Y.Z -m "Release X.Y.Z" && git push --tags`.
- `release.yml` runs the full 70-incident eval on the tag, builds and
  pushes the image, and waits at a manual approval gate before promoting.
- Tag the release notes against ADRs and PRs merged since the previous tag.
- SemVer: `v0.x.y` until the public demo is live; bump minor for new
  features, patch for fixes. Breaking schema changes bump minor in v0.x
  and major after v1.0.

## When something goes wrong
- Broken `main`: revert first, debug second.
- Flaky test: open a `fix(test):` PR within 24h. Don't `@pytest.skip` it
  without a tracking issue.
- Hook failure on commit: read the output, fix the actual issue. If the
  hook is wrong, fix the hook in a `chore(ci):` PR.
- Eval regression: don't rebaseline silently. Investigate, document the
  cause in the PR body, then either fix or rebaseline with explanation.
