---
title: "Support Section With Substack Signup And Donations"
mode: ui
createdAt: "2026-09-30T23:53:39Z"
source: manual
dependsOn: ["astro-site-foundation-with-codeyam-cms-and-github-pages-deploy"]
---

## Summary

Build the navy Support Us section from `design/mockup/index.html` with working
actions. The "Get updates" form subscribes the visitor to the
`ambiguityproject.substack.com` newsletter, so blog readers and update
subscribers are a single list. The Donate panel's amount buttons ($25 / $50 /
$100 / Other) lead to a real donation page. In the mockup, the signup form
does nothing (`onsubmit="return false"`), the donate button points at `#`, and
the EIN is a placeholder `[XX-XXXXXXX]`. After this plan, all of the section's
copy, the donation amounts, the donation link, and the EIN are editable in
`/admin`.

## Key Decisions

- **Keep the custom signup form and hand off to Substack's subscribe page.**
  Submitting opens `<substackUrl>/subscribe?email=<entered email>` (the
  `substackUrl` setting from the foundation plan), where Substack pre-fills the
  address and handles confirmation and spam protection. Two alternatives were
  rejected. Substack's `<iframe src=".../embed">` widget can't be styled to
  match the navy panel. Posting to Substack's undocumented `/api/v1/free`
  endpoint is blocked by CORS and could break without notice. Validate the email
  client-side first (the input is already `type="email"`). The form should still
  work without JavaScript as a plain GET form to that URL.
- **The donation provider is a setting, not code.** No processor has been
  chosen yet. Declare these settings:
  - `donateUrl`: the donation page URL. It may contain an `{amount}`
    placeholder (e.g. Stripe Payment Links, Givebutter, Every.org, and Zeffy
    all accept an amount in the URL in some form).
  - `donationAmounts`: a textarea, one amount per line, defaulting to 25 / 50 /
    100.
  - `donationDefaultAmount`: defaults to 50.
  - `ein`
  The Donate button substitutes the selected amount into `{amount}` when
  present and otherwise links to `donateUrl` as-is. "Other" always links
  without an amount. With `donateUrl` blank, the Donate panel shows its copy
  and a "Donations open soon" note instead of a dead button. The
  "501(c)(3) · EIN …" line shows only when `ein` is set.
- **Port the mockup's amount picker as-is.** Keep its `aria-pressed` toggle
  state and its "Donate $50" label update, now built from `donationAmounts`.
  Put the URL-building and amount-parsing logic in a pure, unit-tested helper
  (`src/lib/donate.ts`), not inline script.
- **All section copy is editable.** Declare settings for `supportHeading` (the
  word "ambiguity" stays salmon via a `highlightWord` setting),
  `updatesHeading`/`updatesBody`, and `donateHeading`/`donateBody`, with the
  mockup's text as defaults.

## Implementation

### 1. Helpers

**New file**: `src/lib/donate.ts` parses `donationAmounts` (trims whitespace,
drops blanks and non-numbers, falls back to the defaults) and builds the donate
href for an amount. Add `src/lib/donate.test.ts`.
**New file**: `src/lib/subscribe.ts` builds the Substack subscribe URL from
`substackUrl` + email (encodes the email, tolerates a trailing slash or a
missing `https://`). Add `src/lib/subscribe.test.ts`.

### 2. Support section

**New file**: `src/components/SupportSection.astro` holds the mockup's navy
section with the salmon bracket label, the translucent "Get updates" panel, and
the white Donate panel. The two-column grid stacks below 860px. Mount it at
`#support` in `src/pages/index.astro`. Declare the settings in
`src/data/collections.json` and seed `src/data/settings.json` with the mockup's
copy.

## Scenarios to Demonstrate

- Default: the mockup's copy, $50 preselected, Donate button labelled "Donate $50"
- Custom amounts (10 / 35 / 250 / 1000) with a different default
- `donateUrl` blank: "Donations open soon", no dead button
- `donateUrl` with `{amount}` versus without it (the button href differs)
- EIN set versus blank (the fine print is shown or hidden)
- Mobile: panels stacked, amount buttons wrapping