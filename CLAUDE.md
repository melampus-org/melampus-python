# CLAUDE.md

Ground rules for Claude Code (and other AI coding agents) working in this repo.
Merge with any task-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Always Work in a Dedicated Git Worktree

**Never switch branches in the main checkout. Never commit directly on `main`.**

This repo is worked on by multiple Claude Code sessions in parallel (and
alongside the human maintainer). Checking out a different branch in the shared
clone changes what every other session sees on disk mid-task — edits, running
processes, and file reads all silently start pointing at the wrong branch. A
dedicated worktree per task avoids that entirely.

Before starting any change:

```bash
git fetch origin main
git worktree add ../melampus-python-<short-task-slug> -b <type>/<short-task-slug> origin/main
cd ../melampus-python-<short-task-slug>
```

- `<type>` matches this repo's convention: `chore/`, `feat/`, `fix/`.
- Do all edits, commits, and testing inside that worktree directory.
- Push the branch and open a PR from there — `main` is protected by the
  `protect-main` ruleset (PR + review required), so a direct push is rejected
  anyway. The worktree rule is about not disturbing concurrent sessions, not
  about working around branch protection.
- Once the PR is pushed (or merged), remove the worktree:
  ```bash
  git worktree remove ../melampus-python-<short-task-slug>
  ```
- If asked to work on something in the main checkout directly, stop and ask —
  don't `git checkout`/`switch` there instead.

## 2. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 3. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 4. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 5. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 6. Releases

Version bumps go through `VERSION` + a matching `[X.Y.Z]` entry in
`CHANGELOG.md`, checked by the `version-guard` workflow on every PR. Merging
to `main` then tags and publishes the release automatically — never hand-run
`git tag`.

---

**These guidelines are working if:** no two sessions ever collide on the same
checkout, fewer unnecessary changes in diffs, fewer rewrites due to
overcomplication, and clarifying questions come before implementation rather
than after mistakes.
