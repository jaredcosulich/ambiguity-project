---
title: "Commit the isolation pages so component scenarios survive a fresh clone"
mode: ui
createdAt: "2026-10-04T16:05:26Z"
source: proposed-plan
---

## Summary

`codeyam-editor editor isolate` added `/src/pages/isolated-components/` to `.gitignore`. On this Astro stack those pages are hand-written (real props, navy backgrounds for the white-on-navy parts, slotted content for SectionAnchor), not regenerated from the glossary, so a fresh clone has none of them and every component scenario 404s on capture. Keep the pages in the repo without shipping them in the production build.

## Key Decisions

- Commit `src/pages/isolated-components/*.astro` and remove the ignore rule.
- Keep them out of `dist/`: guard each page (or a shared layout) so `astro build` emits nothing for `/isolated-components/*` — e.g. `getStaticPaths` returning no paths in production, or filtering the routes in an Astro integration hook.
- Confirm with `astro build` that `dist/isolated-components` does not exist, and with `probe-isolation-routes` that dev still serves all of them.

## Implementation

- `.gitignore`: drop `/src/pages/isolated-components/`.
- `src/pages/isolated-components/*.astro` (BracketLogo, FooterNav, LogoLink, MainNav, MenuToggle, NotFound, SectionAnchor, SiteFooter, SiteHeader): add the production guard.
- Re-run `recapture-stale` and verify the scenarios still capture.