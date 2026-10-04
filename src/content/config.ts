import { defineCollection } from 'astro:content';
import { z } from 'astro/zod';
import { seoFields, draftField, collectionLoader } from '@codeyam/cms/content';

// A typed content collection is the data layer for a static Astro site:
// markdown files validated against this schema at build time. codeyam's
// `content-collection` seed adapter writes and clears these files per scenario,
// so the schema below is also the contract the seed data must satisfy.
//
// `collectionLoader` (from @codeyam/cms) resolves the content root the same way
// the CMS does: committed `src/content` in production, the `.codeyam/tmp`
// sandbox during a codeyam session, so seeding never mutates committed source.

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

export const collections = { pages };
