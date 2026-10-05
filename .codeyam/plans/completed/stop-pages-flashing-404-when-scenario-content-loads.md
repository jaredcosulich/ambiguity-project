---
title: "Stop pages flashing 404 when scenario content loads"
mode: backend
createdAt: "2026-10-05T00:26:24Z"
source: proposed-plan
---

## Summary

Loading a scenario's sample content briefly breaks pages in the dev server. The seed adapter (`.codeyam/seed-adapter.ts`) deletes every markdown file in a collection folder and then rewrites them all, even when the content is unchanged. Astro's content watcher sees the deletions first, so for up to a second after a scenario loads, pages built from that collection (e.g. `/library/<slug>`) return 404. This session hit it repeatedly: the batch error check reported two book pages as broken, a direct capture returned HTTP 404, and registration had to wait and retry.

## Key Decisions

- Write first, prune after: write each entry's file, skip writing when the bytes already match, then delete only files whose slug is no longer in the seed. Unchanged scenarios then produce no file events at all, and changed ones never pass through an empty folder.
- Keep the adapter's wire shape and singleton handling unchanged.

## Implementation

**File**: `.codeyam/seed-adapter.ts`
- Replace `clearCollectionDir` + write loop in `writeSeed` with: compute the target `{fileName: contents}` map via `entryToFile`; for each, write only if the existing file differs; then remove `.md`/`.mdx` files not in the map.
- Add unit tests beside the adapter (or in its existing test file) for: unchanged seed writes nothing, a removed entry is deleted, a changed entry is rewritten, and an empty seed empties the folder.

**Verify**: switch between the Library scenarios in the preview and run the impacted error check; the book page scenarios should pass in one batch without a 404.