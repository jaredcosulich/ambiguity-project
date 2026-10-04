import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  decodeEntities,
  feedUrlFor,
  formatPostDate,
  getSubstackPosts,
  latestPosts,
  looksLikeRssFeed,
  parseSubstackFeed,
  type SubstackPost,
} from './substack';

const item = (fields: string) => `<item>${fields}</item>`;
const feed = (items: string) =>
  `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>The Ambiguity Project</title>${items}</channel></rss>`;

const post = (title: string, date: string): SubstackPost => ({ title, url: `https://x.substack.com/p/${title}`, date });

describe('parseSubstackFeed', () => {
  // A normal Substack item maps every field: title, link, date, summary, cover and category.
  it('normalizes a full item', () => {
    const xml = feed(
      item(
        '<title><![CDATA[Why we stopped]]></title><link>https://x.substack.com/p/why</link>' +
          '<pubDate>Sun, 28 Sep 2026 14:00:00 GMT</pubDate><description><![CDATA[A summary]]></description>' +
          '<enclosure url="https://cdn.example/cover.jpg" length="0" type="image/jpeg"/><category>Essays</category>',
      ),
    );
    expect(parseSubstackFeed(xml)).toEqual([
      {
        title: 'Why we stopped',
        url: 'https://x.substack.com/p/why',
        date: '2026-09-28T14:00:00.000Z',
        summary: 'A summary',
        image: 'https://cdn.example/cover.jpg',
        category: 'Essays',
      },
    ]);
  });

  // The real feed today: a channel with no items yields no posts.
  it('returns an empty list for an empty channel', () => {
    expect(parseSubstackFeed(feed(''))).toEqual([]);
  });

  // An item without an enclosure or category omits those keys rather than inventing placeholders.
  it('omits image and category when the item has none', () => {
    const xml = feed(item('<title>Plain</title><link>https://x/p/plain</link><pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate>'));
    const [only] = parseSubstackFeed(xml);
    expect(only).toEqual({ title: 'Plain', url: 'https://x/p/plain', date: '2026-09-01T10:00:00.000Z' });
  });

  // HTML entities decode both in plain text and inside CDATA, where the XML parser leaves them alone.
  it('decodes HTML entities in titles', () => {
    const xml = feed(
      item('<title>Rock &amp; roll</title><link>https://x/p/a</link><pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate>') +
        item('<title><![CDATA[Don&#8217;t &amp; won&rsquo;t]]></title><link>https://x/p/b</link><pubDate>Tue, 02 Sep 2026 10:00:00 GMT</pubDate>'),
    );
    expect(parseSubstackFeed(xml).map((p) => p.title)).toEqual(['Don’t & won’t', 'Rock & roll']);
  });

  // Posts come back newest first regardless of feed order.
  it('sorts posts newest first', () => {
    const xml = feed(
      item('<title>Old</title><link>https://x/p/old</link><pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate>') +
        item('<title>New</title><link>https://x/p/new</link><pubDate>Mon, 22 Sep 2026 10:00:00 GMT</pubDate>'),
    );
    expect(parseSubstackFeed(xml).map((p) => p.title)).toEqual(['New', 'Old']);
  });

  // Items missing a title, link or a parseable date are skipped instead of rendering a broken card.
  it('skips incomplete items', () => {
    const xml = feed(
      item('<link>https://x/p/no-title</link><pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate>') +
        item('<title>No date</title><link>https://x/p/no-date</link>') +
        item('<title>Bad date</title><link>https://x/p/bad</link><pubDate>someday</pubDate>'),
    );
    expect(parseSubstackFeed(xml)).toEqual([]);
  });

  // Malformed XML or a non-RSS document yields no posts and never throws.
  it('returns an empty list for malformed input', () => {
    expect(parseSubstackFeed('<rss><channel')).toEqual([]);
    expect(parseSubstackFeed('<html><body>Error</body></html>')).toEqual([]);
    expect(parseSubstackFeed('')).toEqual([]);
  });
});

describe('looksLikeRssFeed', () => {
  // A real feed, even an empty one, carries a channel element.
  it('accepts a document with a channel', () => {
    expect(looksLikeRssFeed(feed(''))).toBe(true);
  });

  // An error page or empty body must not be treated as a feed, so the sync keeps the old snapshot.
  it('rejects an error page or empty body', () => {
    expect(looksLikeRssFeed('<html><body>502 Bad Gateway</body></html>')).toBe(false);
    expect(looksLikeRssFeed('')).toBe(false);
  });

  // An element merely starting with "channel" is not a channel.
  it('does not match a channel-prefixed element name', () => {
    expect(looksLikeRssFeed('<channelGroup></channelGroup>')).toBe(false);
  });
});

describe('decodeEntities', () => {
  // Named, decimal and hex entities all decode.
  it('decodes named and numeric entities', () => {
    expect(decodeEntities('A &amp; B &lt;3 &#8217; &#x2014; &hellip;')).toBe('A & B <3 ’ — …');
  });

  // Unknown entities are left as written rather than dropped.
  it('leaves unknown entities untouched', () => {
    expect(decodeEntities('&bogus; stays')).toBe('&bogus; stays');
  });

  // Text without entities passes through unchanged.
  it('passes plain text through', () => {
    expect(decodeEntities('No entities here')).toBe('No entities here');
  });
});

describe('latestPosts', () => {
  const posts = [post('b', '2026-09-02T00:00:00Z'), post('d', '2026-09-04T00:00:00Z'), post('a', '2026-09-01T00:00:00Z'), post('c', '2026-09-03T00:00:00Z')];

  // The Blog section shows the newest three.
  it('returns the newest three by default', () => {
    expect(latestPosts(posts).map((p) => p.title)).toEqual(['d', 'c', 'b']);
  });

  // Fewer posts than the limit are all returned, newest first.
  it('returns all posts when under the limit', () => {
    expect(latestPosts(posts.slice(0, 2)).map((p) => p.title)).toEqual(['b', 'd'].reverse());
  });

  // No posts gives an empty list, and the input array is not mutated.
  it('handles empty input without mutating', () => {
    expect(latestPosts([])).toEqual([]);
    const copy = [...posts];
    latestPosts(posts, 1);
    expect(posts).toEqual(copy);
  });
});

describe('formatPostDate', () => {
  // Dates render as a short US date.
  it('formats an ISO date', () => {
    expect(formatPostDate('2026-09-28T14:00:00.000Z')).toBe('Sep 28, 2026');
  });

  // A post published late in the UTC day keeps its UTC calendar date on any build machine.
  it('formats in UTC', () => {
    expect(formatPostDate('2026-09-28T23:59:00.000Z')).toBe('Sep 28, 2026');
    expect(formatPostDate('2026-09-28T00:01:00.000Z')).toBe('Sep 28, 2026');
  });

  // An unparseable date renders nothing instead of "Invalid Date".
  it('returns an empty string for an invalid date', () => {
    expect(formatPostDate('not a date')).toBe('');
  });
});

describe('feedUrlFor', () => {
  // The feed lives at /feed under the Substack home URL.
  it('appends /feed', () => {
    expect(feedUrlFor('https://ambiguityproject.substack.com')).toBe('https://ambiguityproject.substack.com/feed');
  });

  // A trailing slash on the setting does not produce a double slash.
  it('strips trailing slashes', () => {
    expect(feedUrlFor('https://ambiguityproject.substack.com//')).toBe('https://ambiguityproject.substack.com/feed');
  });
});

describe('getSubstackPosts', () => {
  let dir: string;
  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'substack-'));
  });
  afterEach(() => {
    fs.rmSync(dir, { recursive: true, force: true });
  });

  // Posts are read from the synced snapshot under the data root.
  it('reads posts from the snapshot', () => {
    const posts = [post('a', '2026-09-01T00:00:00Z')];
    fs.writeFileSync(path.join(dir, 'substackPosts.json'), JSON.stringify({ posts }));
    expect(getSubstackPosts(dir)).toEqual(posts);
  });

  // No snapshot yet means no posts, not a broken build.
  it('returns an empty list when the file is missing', () => {
    expect(getSubstackPosts(dir)).toEqual([]);
  });

  // A corrupt snapshot or one without a posts array also means no posts.
  it('returns an empty list for unreadable or malformed snapshots', () => {
    fs.writeFileSync(path.join(dir, 'substackPosts.json'), '{ not json');
    expect(getSubstackPosts(dir)).toEqual([]);
    fs.writeFileSync(path.join(dir, 'substackPosts.json'), JSON.stringify({ posts: 'nope' }));
    expect(getSubstackPosts(dir)).toEqual([]);
  });
});
