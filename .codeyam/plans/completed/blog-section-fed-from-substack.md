---
title: "Blog Section Fed From Substack"
mode: ui
createdAt: "2026-09-30T23:53:39Z"
source: manual
dependsOn: ["astro-site-foundation-with-codeyam-cms-and-github-pages-deploy"]
---

## Summary

Fill the home page's Blog section (the three ochre "[Post title]" cards in
`design/mockup/index.html`) with the latest posts from the
`ambiguityproject.substack.com` Substack. Writing happens in Substack, and
visitors see the three most recent posts as cards: cover image, date, title,
"Read post →". Each card links to the post on Substack, and "All posts →"
goes to the Substack home. New posts appear on the site automatically within a
day, with no one touching the repo.

## Key Decisions

- **Fetch the RSS feed at build time, not in the browser.** The feed is
  `https://ambiguityproject.substack.com/feed` (checked 2026-09-30: returns 200
  `application/xml`, channel title "The Ambiguity Project", **zero items so
  far**). Browser fetching would hit CORS and render the cards with a flash
  after load. A build-time fetch keeps the site fully static and crawlable.
- **The sync writes a data file, and the section reads only that file.** A small
  Node script (`scripts/sync-substack.mjs`) fetches the feed and writes
  normalized posts (`title`, `url`, `date`, `summary`, `image`, `category?`) to
  `src/data/substackPosts.json`. The section component never touches the
  network. This keeps the site renderable offline and in codeyam scenarios:
  the content-collection seed adapter seeds `substackPosts.json` directly, so
  every blog state (empty, one post, many, missing image) is a scenario, with
  no HTTP mocking.
- **Commit a snapshot; CI refreshes it before building.** The committed file is
  what local dev and scenarios see. The deploy workflow runs the sync right
  before `astro build`, so production always has the current feed. It does not
  commit the result back. If the fetch fails in CI (Substack down), the build
  keeps the committed snapshot and logs a warning instead of failing the deploy.
- **A scheduled rebuild picks up new posts.** Add a daily `schedule:` cron (plus
  the existing `workflow_dispatch`) to `.github/workflows/deploy.yml`. Substack
  has no webhooks, and a daily delay is fine for a blog. Mention the manual
  "Run workflow" button in `DEPLOY_SETUP.md` for publishing immediately.
- **The feed URL comes from the `substackUrl` setting** (declared by the
  foundation plan). The sync reads it from `src/data/settings.json` and
  appends `/feed`. "All posts →" and the empty state's call-to-action use the
  same setting.
- **The feed is not CMS-editable.** `substackPosts.json` is generated, so it is
  not declared in `collections.json`, and the file carries a "generated — do not
  edit" note. Editors change posts in Substack.
- **Parse RSS with a small tested pure function.** `parseSubstackFeed(xml)`
  lives in `src/lib/substack.ts`, using a real XML parser dependency (e.g.
  `fast-xml-parser`) rather than regexes. Unit tests use feed fixtures: a
  normal feed, an empty channel (today's real state), an item with no
  enclosure image, HTML entities in titles, and malformed XML (returns `[]`
  and reports the error, never throws past the script). The cover image comes
  from `<enclosure>`. The category pill shows only when the item carries a
  `<category>`, and is otherwise omitted rather than showing "[Category]".
- **The empty state is the launch state.** With no posts yet, the section keeps
  its heading and shows one ochre card: "Our first posts are on the way —
  subscribe on Substack", linking to `substackUrl`. It does not show three
  placeholder cards.

## Implementation

### 1. Feed parsing and sync

**New file**: `src/lib/substack.ts`, the pure parser and normalizer, plus
`src/lib/substack.test.ts`.
**New file**: `scripts/sync-substack.mjs` fetches the feed, parses it,
writes `src/data/substackPosts.json`, and keeps the snapshot on failure. Add an
`npm run sync:substack` script.

### 2. Blog section

**New file**: `src/components/BlogSection.astro` holds the mockup's blog markup
and CSS: the ochre bracket label, a 3→2→1 column grid at 1024/640px (the
mockup hides the third card at tablet width), the card hover lift, and date
formatting. It also handles the empty state. Mount it at `#blog` in
`src/pages/index.astro`. Cards open Substack in the same tab.

### 3. Deploy pipeline

Add the sync step before the build and the daily cron to
`.github/workflows/deploy.yml`. Document both in `DEPLOY_SETUP.md`.

## Scenarios to Demonstrate

- No posts yet (the real launch state): heading plus the subscribe empty card
- One post; two posts; three posts; ten posts (only the latest three shown)
- A post with no cover image (the ochre placeholder panel with the site name)
- A very long post title and summary
- Mobile layout (single column) and tablet layout (two columns)