---
name: simplify
description: Review changed code for reuse, quality, and efficiency, then fix any issues found
when_to_use: After making changes to code
user_invocable: true
allowed_tools:
  - Read
  - Bash
  - Edit
  - Grep
---

# Simplify: Code Review and Cleanup

Review all changed files for reuse, quality, and efficiency. Fix any issues found.

## Phase 1: Identify Changes

Run `git diff` (or `git diff HEAD` if there are staged changes) to see what changed.

## Phase 2: Code Review

For each change:

1. **Reuse Review**: Search for existing utilities that could replace newly written code
2. **Quality Review**: Look for hacky patterns:
   - Redundant state or cached values
   - Parameter sprawl
   - Copy-paste with slight variation
   - Leaky abstractions
   - Stringly-typed code
3. **Efficiency Review**:
   - Unnecessary work or redundant computations
   - Missed concurrency
   - Unnecessary existence checks (TOCTOU anti-pattern)

## Phase 3: Fix Issues

Fix each issue directly. If a finding is a false positive, note it and move on.

When done, briefly summarize what was fixed.
