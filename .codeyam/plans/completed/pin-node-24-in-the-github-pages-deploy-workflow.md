---
title: "Pin Node 24 in the GitHub Pages deploy workflow"
mode: backend
createdAt: "2026-10-04T16:05:28Z"
source: proposed-plan
---

## Summary

The lockfile-sync hook required an `.nvmrc`, which now says 24 (the local Node). The deploy workflow uses `withastro/action@v3` without `node-version`, so CI builds on the action's default Node. Pin it so CI and local installs agree.

## Key Decisions

- Set `with: node-version: 24` on the `withastro/action@v3` step, with a comment tying it to `.nvmrc`.

## Implementation

- `.github/workflows/deploy.yml`: replace the commented-out `with:` block under "Build Astro site".
- Push and confirm the run's "Build Astro site" step logs Node 24.