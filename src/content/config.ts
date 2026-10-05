import { defineCollection } from 'astro:content';
import { z } from 'astro/zod';
import { seoFields, draftField } from '@codeyam/cms/content';
import { watchedCollectionLoader as collectionLoader } from '../lib/watchedCollectionLoader';

// A typed content collection is the data layer for a static Astro site:
// markdown files validated against this schema at build time. codeyam's
// `content-collection` seed adapter writes and clears these files per scenario,
// so the schema below is also the contract the seed data must satisfy.
//
// `collectionLoader` (from @codeyam/cms) resolves the content root the same way
// the CMS does: committed `src/content` in production, the `.codeyam/tmp`
// sandbox during a codeyam session, so seeding never mutates committed source.
// It is wrapped (src/lib/watchedCollectionLoader.ts) so a collection that starts
// empty still picks up its first entry under `astro dev`.

// Free-form site pages (About, etc.). `order` sorts them in a nav or index;
// the markdown body is the page content.
const pages = defineCollection({
  loader: collectionLoader('pages'),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
    order: z.number().optional(),
    ...draftField,
    ...seoFields,
  }),
});

// Books featured in the home page Books section, first by `order`.
const books = defineCollection({
  loader: collectionLoader('books'),
  schema: z.object({
    title: z.string(),
    subtitle: z.string().optional(),
    eyebrow: z.string().optional(),
    cover: z.string().optional(),
    coverAlt: z.string().optional(),
    blurb: z.string().optional(),
    primaryLabel: z.string().optional(),
    primaryUrl: z.string().optional(),
    secondaryLabel: z.string().optional(),
    secondaryUrl: z.string().optional(),
    order: z.number().optional(),
    ...draftField,
  }),
});

// Tools listed in the home page Technology section (the first three by `order`).
const tools = defineCollection({
  loader: collectionLoader('tools'),
  schema: z.object({
    name: z.string(),
    description: z.string().optional(),
    url: z.string().optional(),
    order: z.number().optional(),
    ...draftField,
  }),
});

// Hero quotes; the hero shows the first by `order` so builds stay stable.
const quotes = defineCollection({
  loader: collectionLoader('quotes'),
  schema: z.object({
    text: z.string(),
    attribution: z.string().optional(),
    order: z.number().optional(),
  }),
});

// Books we have read and reviewed, listed in the Library (/library) by
// `order`. The markdown body is the book report shown on /library/<slug>.
const library = defineCollection({
  loader: collectionLoader('library'),
  schema: z.object({
    title: z.string(),
    author: z.string().optional(),
    cover: z.string().optional(),
    coverAlt: z.string().optional(),
    summary: z.string().optional(),
    order: z.number().optional(),
    ...draftField,
    ...seoFields,
  }),
});

export const collections = { pages, books, tools, quotes, library };
