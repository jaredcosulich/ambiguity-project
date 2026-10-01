---
title: "Home Page Sections Editable In The CMS"
mode: ui
createdAt: "2026-09-30T23:53:39Z"
source: manual
dependsOn: ["astro-site-foundation-with-codeyam-cms-and-github-pages-deploy"]
---

## Summary

Build the home page's content sections from the mockup
(`design/mockup/index.html`, moved there by the foundation plan): the hero, the
Books section, the Technology/tools section, and Learn More. All of their copy
is editable in `/admin` rather than hard-coded. An editor can change the
mission's rotating words, swap the hero quote, add a second book, add or
reorder tools, and edit the About page, all without a code change. The Blog and
Support Us sections are handled by their own plans.

## Key Decisions

- **Model repeating things as collections and one-off strings as settings.**
  CMS settings can't hold `list` or `image` fields, so:
  - `books` collection (new): `title`, `subtitle`, `eyebrow`
    ("New book · Pre-order now"), `cover` (image), `coverAlt`, `blurb`
    (textarea), `primaryLabel` / `primaryUrl` ("Pre-order the book"),
    `secondaryLabel` / `secondaryUrl` ("About the book →"), `order`, `draft`.
    The home page shows the first non-draft book by `order`. If more than one
    is published, they stack in the same section layout.
  - `tools` collection (new): `name`, `description`, `url`, `order`, `draft`.
    The home page shows the first three. The mockup's placeholder rows
    ("[Tool name]") become real empty-state handling: with zero tools, the
    Technology section is hidden rather than showing placeholders.
  - `quotes` collection (new): `text`, `attribution`, `order`. The hero shows
    one quote. With several, it picks one per build (deterministically by
    `order`, first one) so screenshots stay stable.
  - Settings (declared in `src/data/collections.json` → `settings`):
    `heroEyebrow` ("A 501(c)(3) Non-Profit"), `missionPrefix` ("Helping"),
    `missionWords` (textarea, one word per line: people, students, businesses,
    governments, organizations, schools), `missionSuffix` ("better recognize,
    live with, and navigate ambiguity."), and each section's heading and
    "All tools →" link (`toolsHeading`, `toolsAllUrl`, `learnHeading`,
    `learnButtonLabel`).
- **The Learn More button and "About the book" link go to real pages.** Seed a
  `pages/about.md` entry ("About The Ambiguity Project") rendered at `/about`,
  and give "About the book" a `pages/ambiguity-everywhere.md` page. Both are
  editable `pages` entries, so the links never point at `#`. Register their
  locations in the `collections.json` `paths` map.
- **Keep the typewriter accessible and stable.** Port the mockup's rotating-word
  script as-is: sized to the longest word, respects
  `prefers-reduced-motion`, and keeps a screen-reader-only full list. Build the
  word list from `missionWords` and the width measure from the longest word
  (not a hard-coded "organizations"). Add a unit test for the pure word-list
  parsing (trims whitespace, drops blank lines, falls back to "people" when
  empty).
- **Add CMS staged-preview markers** (`data-cms-entry` / `data-cms-field`) to
  the book and tool renderers, so "Preview changes" in `/admin` patches the
  real page exactly instead of matching by shape.

## Implementation

### 1. Content schema and registry

Add the `books`, `tools`, and `quotes` collections to the content config (using
the CMS `collectionLoader`). Declare them, plus the new settings and `paths`,
in `src/data/collections.json`. Seed the content from the mockup: the "Ambiguity
Everywhere" book with its blurb and cover, the Voltaire quote, and the About and
book pages. Leave tools empty until real ones exist. For scenarios, the seed
data carries three sample tools.

### 2. Section components

**New files**: `src/components/Hero.astro` (eyebrow, h1, typewriter mission,
quote aside), `src/components/BooksSection.astro`,
`src/components/ToolsSection.astro`, `src/components/LearnMore.astro`. Each
one carries its CSS from the mockup (hero grid, rotated book cover with hover,
sage tool cards, periwinkle Learn More band) and its responsive breakpoints
(960 / 1024 / 860 / 640px).

### 3. Pages

Compose the sections in `src/pages/index.astro` in the mockup's order, leaving
the Blog and Support anchors to their plans. Add a `pages` route (e.g.
`src/pages/[slug].astro`) for About and the book page, using the shared
header and footer.

## Scenarios to Demonstrate

- Full home page, desktop and mobile, with the mockup's real content
- Hero with a very long quote and a long rotating word (layout holds; the word
  slot is sized correctly)
- Books: one book; two books; a book with no secondary link; missing cover
- Tools: zero tools (section hidden); one tool; five tools (only three shown,
  "All tools →" present); a long description
- Learn More pointing at the About page; the About page rendered
- Reduced-motion: rotating word swaps without typing animation