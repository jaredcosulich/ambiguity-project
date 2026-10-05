---
title: "Library of Reviewed Books with Book Pages"
mode: ui
createdAt: "2026-10-04T23:47:20Z"
source: manual
---

## Summary

Add a **Library** of the books The Ambiguity Project has reviewed. A new "Library" link in the top nav goes to `/library`, a grid of every reviewed book shown as a cover card (cover, title, author). Clicking a card opens that book's page at `/library/<slug>`, with a larger cover, the book's details, and the full "book report" (the markdown body of the entry). The home page gets a new Library section: the newest few covers in a row plus an "Explore the library →" link. Reviewed books are a **new, separate CMS collection** (`library`). The existing `books` collection keeps driving the Ambiguity Everywhere band and its pre-order button, unchanged.

## Key Decisions

- **Separate `library` collection, not the existing `books` one.** `books` means "our own book(s)" and carries pre-order fields (eyebrow, primary/secondary buttons). A reviewed book needs different fields (author, report body). The user confirmed this split.
- **Book report = markdown body** of each library entry, rendered with `render()` the same way `src/pages/[slug].astro` renders pages. The CMS edits it as rich text, so writing a report needs no code change.
- **Routes live under `/library/`.** `/library` is the index and `/library/[slug]` is a book. This keeps book slugs from colliding with `pages` slugs at the root `/[slug]` route. For example, `ambiguity-everywhere` already exists as a page.
- **Nav: insert "Library" after "Books"** in `src/data/nav.json` with `url: "/library"`. `toNavLinks` flags the *last* item as the CTA, so "Support Us" stays the button. A page link goes through `withBase()` the same way the anchors do.
- **Home section: a row of covers + link.** Show up to 4 books in `order`, each linking to its book page, plus "Explore the library →". When the library is empty, render nothing (no empty band), so the home page stays clean until the first review is published.
- **Reuse `BookCover`** for the cover art, including its salmon title-card fallback when an entry has no cover. A size option keeps the grid card cover at normal size and makes the book page's cover large. The book page and grid should show covers untilted, or at most slightly tilted. Decide the look against the scenarios.
- Drafts are filtered with `publishedEntries` everywhere, as with `pages`/`books`, so a draft report is not publicly reachable.

## Implementation

### 1. Library collection schema

**File**: `src/content/config.ts`

Add a `library` collection with `collectionLoader('library')`. Fields: `title` (required), `author` (string, optional), `cover` / `coverAlt` (optional), `summary` (optional, one or two sentences for the card and page header), `order` (optional), `...draftField`, `...seoFields`. Export it in `collections`.

### 2. CMS wiring

**File**: `src/data/collections.json`

Add a `library` collection entry (label "Library", singular "book") with the fields above (`cover` as `type: "image"`) and a body/report field if the CMS needs one declared. Add `"library": "/library/:slug"` to `paths` and `"library": { "field": "order" }` to `order`.

### 3. Library index page

**New file**: `src/pages/library/index.astro`

`BaseLayout` with a heading (e.g. "Library" bracket label + "Books we've read and reviewed"), and a responsive grid of `LibraryCard`s for every published entry sorted with `sortByOrder`. Empty state: a short "Our first book reports are on the way" message instead of an empty grid.

### 4. Book page

**New file**: `src/pages/library/[slug].astro`

`getStaticPaths` over published library entries. Layout: large cover beside the title, author and summary (stacked on mobile), then the rendered report body with the same prose styling `ContentPage` gives pages. Include a "← Back to the library" link. Pass title/summary to `BaseLayout` for SEO.

### 5. Components

**New file**: `src/components/LibraryCard.astro`: one cover card (cover via `BookCover`, title, author) linking to `withBase('/library/<id>')`, with `data-cms-entry={`library/${id}`}` so the CMS can edit it in place.

**New file**: `src/components/LibrarySection.astro`: the home band, `id="library"`, label "Library", heading, up to 4 `LibraryCard`s, "Explore the library →" link. Renders nothing for an empty list.

**File**: `src/components/BookCover.astro`: add an optional size/tilt prop for the large book-page cover and the untilted grid cover. The existing call in `BookFeature` keeps its current look.

### 6. Home page and nav

**File**: `src/pages/index.astro`: load `sortByOrder(publishedEntries(await getCollection('library')))` and render `<LibrarySection>` right after `<BooksSection>`.

**File**: `src/data/nav.json`: add `{ "label": "Library", "url": "/library" }` after "Books". Update the real-nav case in `src/lib/navLinks.test.ts` if it asserts the site's actual item list.

### 7. Content and seeds

**New file**: `src/content/library/` with at least one real entry once the user supplies a book and report. Until then, seed data drives the scenarios. Cover images go under `public/images/library/`.

**New file**: `.codeyam/seeds/library-*.json` seeds (several books with covers and reports, one book, empty, one book with no cover / long title). Isolation pages for `LibraryCard` and `LibrarySection` under `src/pages/isolated-components/`, following the existing ones.

## Reused existing code

- `BookCover` from `src/components/BookCover.astro`: cover art and missing-cover fallback
- `sortByOrder` from `src/lib/contentOrder.ts`: stable ordering
- `withBase` from `src/lib/base.ts`: every internal link and cover src
- `toNavLinks` from `src/lib/navLinks.ts`: nav rendering, last item stays the CTA
- `collectionLoader` via `src/lib/watchedCollectionLoader.ts`: sandbox-aware loader so seeds work
- `ContentPage` from `src/components/ContentPage.astro` and `src/pages/[slug].astro`: pattern for rendering a markdown body as a page
- `BlogSection` from `src/components/BlogSection.astro`: section-head + grid + "All posts →" layout to mirror for the home Library band
- `publishedEntries` from `@codeyam/cms/content`: draft filtering

## Scenarios to Demonstrate

- Library page with 6–8 reviewed books with real-looking covers (rich grid, desktop and mobile)
- Library page empty state (no reviews yet)
- Library page where one book has no cover (salmon title-card fallback) and one has a very long title
- Book page: full report with headings, quotes and lists, plus a large cover
- Book page: short report, no cover, no author
- Home page with the Library section (4 covers + explore link), and with only 1–2 books
- Home page with an empty library: the section is absent and the rest of the page is unchanged
- Header nav showing "Library" between Books and Blog, with Support Us still the button (desktop and mobile menu)