---
title: "Keep the isolate command from re-ignoring the committed preview pages"
mode: backend
createdAt: "2026-10-05T10:28:32Z"
source: proposed-plan
---

## Summary

`codeyam-editor editor isolate` is what originally added `/src/pages/isolated-components/` to `.gitignore`, and the Prepare step tells sessions to run `isolate --all` whenever an isolation route 404s. On this Astro stack the isolation pages are hand-written and now committed, so a future `isolate` run could re-add the ignore rule or overwrite a hand-tuned page (navy backgrounds, slotted content) without anyone noticing.

## Key Decisions

- Find out exactly what `isolate` writes on this stack (`.gitignore` block, page files) before changing anything.
- Prevent the regression: either a check that fails when `.gitignore` ignores `src/pages/isolated-components/`, or a project setting that tells `isolate` the pages are committed and hand-owned.

## Implementation

- Run `isolate` for one existing component on a scratch branch and diff `.gitignore` and `src/pages/isolated-components/`.
- Add a guard: a unit test next to `src/lib/isolationPages.test.ts` asserting `git check-ignore src/pages/isolated-components/SiteHeader.astro` reports not-ignored, or the equivalent stack setting.
- Keep `src/lib/isolationPages.ts` (the build-time exclusion) unchanged.