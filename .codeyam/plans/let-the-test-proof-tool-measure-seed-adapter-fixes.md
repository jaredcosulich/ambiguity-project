---
title: "Let the test-proof tool measure seed-adapter fixes"
mode: backend
createdAt: "2026-10-05T10:28:32Z"
source: proposed-plan
---

## Summary

The editor's test-proof tool could not measure the new seed-adapter tests. The adapter lives at `.codeyam/seed-adapter.ts`, and the `tests` runner in `.codeyam/editor.json` scopes the fix's files in a way that skips `.codeyam/`. So prove-red reported `selected-nothing`, and the red-if-reverted proof had to be hand-attested (the fix was neutered with Edit and the tests re-run). Separately, `vitest.config.ts` only includes `src/**/*.test.{ts,tsx}`, so the adapter's tests have to live in `src/lib/seedAdapter.test.ts`, away from the code they cover.

## Key Decisions

- Make the runner own `.codeyam/seed-adapter.ts` as a source file, so prove-red can neuter or revert it and measure the result. Do not widen ownership to the rest of `.codeyam/`.
- Keep the tests where they are unless widening vitest's `include` is cheap. Moving them is optional.

## Implementation

**File**: `.codeyam/editor.json`
- Find out why `testRunners[tests]` does not select `.codeyam/seed-adapter.ts` even though `sourceFilePatterns` is `**/*.{ts,tsx,js,jsx}` (it is probably a dot-directory or exclude rule), then add an explicit pattern for it.

**Verify**: run `prove-red --test "leaves files untouched when the seed is unchanged" --neuter-file .codeyam/seed-adapter.ts --neuter-find "if (existing !== contents) fs.writeFileSync" --neuter-replace "if (existing !== null || true) fs.writeFileSync"` and confirm it reports a measured fault-pinning verdict instead of `selected-nothing`.