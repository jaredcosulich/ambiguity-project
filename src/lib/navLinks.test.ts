import { describe, expect, it } from 'vitest';
import { toNavLinks } from './navLinks';

const BASE = '/ambiguity-project/';

describe('toNavLinks', () => {
  // The site's real nav: five section anchors, the last one the CTA button.
  it('maps every item and flags only the last as the call-to-action', () => {
    const links = toNavLinks(
      [
        { label: 'Books', url: '#books' },
        { label: 'Blog', url: '#blog' },
        { label: 'Support Us', url: '#support' },
      ],
      BASE,
    );
    expect(links).toEqual([
      { label: 'Books', href: '/ambiguity-project/#books', isCta: false },
      { label: 'Blog', href: '/ambiguity-project/#blog', isCta: false },
      { label: 'Support Us', href: '/ambiguity-project/#support', isCta: true },
    ]);
  });

  // An empty nav renders no links rather than throwing.
  it('returns an empty list for an empty nav', () => {
    expect(toNavLinks([], BASE)).toEqual([]);
  });

  // A single item is both the only link and the CTA.
  it('treats a single item as the call-to-action', () => {
    expect(toNavLinks([{ label: 'Donate', url: '#support' }], BASE)).toEqual([
      { label: 'Donate', href: '/ambiguity-project/#support', isCta: true },
    ]);
  });

  // Dropdown-only parents have no URL and are skipped; the CTA is the last linked item.
  it('skips items without a url when choosing the call-to-action', () => {
    const links = toNavLinks(
      [
        { label: 'Books', url: '#books' },
        { label: 'Support Us', url: '#support' },
        { label: 'Chapters', children: [{ label: 'Boston', url: '/boston' }] },
      ],
      BASE,
    );
    expect(links.map((l) => l.label)).toEqual(['Books', 'Support Us']);
    expect(links[1].isCta).toBe(true);
  });

  // External links pass through unchanged so a nav item can point off-site.
  it('keeps external urls untouched', () => {
    const [link] = toNavLinks([{ label: 'Substack', url: 'https://example.substack.com' }], BASE);
    expect(link.href).toBe('https://example.substack.com');
  });
});
