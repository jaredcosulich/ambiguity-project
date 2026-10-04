// Substack posts for the home Blog section.
//
// Writing happens in Substack; the site never fetches the feed at render time.
// `scripts/sync-substack.mjs` fetches `<substackUrl>/feed`, normalizes it with
// `parseSubstackFeed`, and writes `substackPosts.json` under the data root.
// The Blog section reads only that file, so the site renders offline and every
// blog state (empty, one post, many, no cover image) is a seedable scenario.
import * as fs from 'fs';
import * as path from 'path';
import { XMLParser } from 'fast-xml-parser';
import { resolveDataRoot } from './contentRoot';

export interface SubstackPost {
  title: string;
  url: string;
  /** ISO 8601 publish date. */
  date: string;
  summary?: string;
  image?: string;
  category?: string;
}

export interface SubstackSnapshot {
  _note?: string;
  feedUrl?: string;
  syncedAt?: string;
  posts: SubstackPost[];
}

/**
 * Read the synced snapshot. A missing or unreadable file means "no posts yet"
 * rather than a broken build: the section then shows its subscribe card.
 * Read on every call so a re-sync or a re-seeded scenario shows immediately.
 */
export function getSubstackPosts(dataRoot: string = resolveDataRoot()): SubstackPost[] {
  try {
    const raw = fs.readFileSync(path.join(dataRoot, 'substackPosts.json'), 'utf-8');
    const snapshot = JSON.parse(raw) as Partial<SubstackSnapshot>;
    return Array.isArray(snapshot.posts) ? snapshot.posts : [];
  } catch {
    return [];
  }
}

/** The newest `limit` posts, newest first. */
export function latestPosts(posts: SubstackPost[], limit = 3): SubstackPost[] {
  return [...posts].sort((a, b) => Date.parse(b.date) - Date.parse(a.date)).slice(0, limit);
}

/** "Sep 28, 2026" — formatted in UTC so the build machine's timezone never shifts the day. */
export function formatPostDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

/** The feed URL for a Substack home URL: `https://x.substack.com/` → `https://x.substack.com/feed`. */
export function feedUrlFor(substackUrl: string): string {
  return `${substackUrl.replace(/\/+$/, '')}/feed`;
}

const NAMED_ENTITIES: Record<string, string> = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ',
  rsquo: '’', lsquo: '‘', rdquo: '”', ldquo: '“', mdash: '—', ndash: '–', hellip: '…',
};

// Substack wraps titles and descriptions in CDATA, where the XML parser leaves
// HTML entities (`&amp;`, `&#8217;`) undecoded, so decode them here.
export const decodeEntities = (s: string): string =>
  s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (match, code: string) => {
    if (code[0] === '#') {
      const n = code[1].toLowerCase() === 'x' ? parseInt(code.slice(2), 16) : parseInt(code.slice(1), 10);
      return Number.isFinite(n) ? String.fromCodePoint(n) : match;
    }
    return NAMED_ENTITIES[code.toLowerCase()] ?? match;
  });

const text = (v: unknown): string => {
  if (v == null) return '';
  const raw =
    typeof v === 'object' && '#text' in (v as Record<string, unknown>)
      ? String((v as Record<string, unknown>)['#text'])
      : String(v);
  return decodeEntities(raw).trim();
};

const asArray = <T>(v: T | T[] | undefined): T[] => (v == null ? [] : Array.isArray(v) ? v : [v]);

/**
 * Whether a fetched body is an RSS feed at all. A real feed always has a
 * `<channel>`, even with no posts; an error page or empty body does not, and
 * must not overwrite the last good snapshot.
 */
export function looksLikeRssFeed(body: string): boolean {
  return /<channel[\s>]/.test(body);
}

/**
 * Parse a Substack RSS feed into normalized posts, newest first.
 * Malformed XML or a feed with no channel yields `[]` — never throws.
 */
export function parseSubstackFeed(xml: string): SubstackPost[] {
  let doc: Record<string, any>;
  try {
    const parser = new XMLParser({
      ignoreAttributes: false,
      attributeNamePrefix: '@_',
      processEntities: true,
      htmlEntities: true,
    });
    doc = parser.parse(xml, true);
  } catch {
    return [];
  }

  const channel = doc?.rss?.channel;
  if (!channel) return [];

  const posts: SubstackPost[] = [];
  for (const item of asArray(channel.item)) {
    const title = text(item?.title);
    const url = text(item?.link);
    const parsedDate = Date.parse(text(item?.pubDate));
    if (!title || !url || Number.isNaN(parsedDate)) continue;

    const post: SubstackPost = { title, url, date: new Date(parsedDate).toISOString() };
    const summary = text(item?.description);
    if (summary) post.summary = summary;
    const enclosure = asArray(item?.enclosure).find((e: any) => e?.['@_url']);
    if (enclosure) post.image = String(enclosure['@_url']);
    const category = text(asArray(item?.category)[0]);
    if (category) post.category = category;
    posts.push(post);
  }

  return latestPosts(posts, posts.length);
}
