---
title: "Seeds reset site data files they don't mention"
mode: backend
createdAt: "2026-10-04T19:03:54Z"
source: proposed-plan
---

## Summary

The seed loader (`.codeyam/seed-adapter.ts`) rewrites a site data file such as `substackPosts.json` only when a seed names it. A seed that does not mention a file keeps whatever the previous seed wrote, so preview states change depending on load order. This surfaced while building the Blog section: older home-page states showed demo posts until every seed in `.codeyam/seeds/` was edited to set `substackPosts` explicitly. The next data file (for example the Support Us section's) will hit the same trap.

## Key Decisions

- Before writing a seed's data files, reset every data file in the sandbox data root to its committed copy from `src/data/`, then apply the seed on top. Seeds stay small and only state what differs.
- Content collections already behave this way (their directories are cleared); this brings data files in line.
- Keep the explicit `substackPosts` entries already added to seeds; they become harmless.

## Implementation

- `.codeyam/seed-adapter.ts`: in the singleton-writing path (`writeSingleton` and its caller), first copy each `src/data/*.json` into the data root, then write the seeded singletons.
- Add a test seeding a payload without `substackPosts` after one with posts, and assert the sandbox file matches committed `src/data/substackPosts.json`.
- Recapture the home-page scenarios and confirm none change.