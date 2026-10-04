import { describe, expect, it } from 'vitest';
import { withBase } from './base';

describe('withBase', () => {
  // A root-absolute internal path lands under the Pages subpath.
  it('prefixes a root-absolute path with the base', () => {
    expect(withBase('/favicon.svg', '/ambiguity-project/')).toBe('/ambiguity-project/favicon.svg');
  });

  // A bare relative path is treated the same as a root-absolute one.
  it('prefixes a relative path with the base', () => {
    expect(withBase('images/book-cover.png', '/ambiguity-project/')).toBe(
      '/ambiguity-project/images/book-cover.png',
    );
  });

  // The home link resolves to the base itself, with its trailing slash.
  it('maps the root path to the base', () => {
    expect(withBase('/', '/ambiguity-project/')).toBe('/ambiguity-project/');
    expect(withBase('', '/ambiguity-project/')).toBe('/ambiguity-project/');
  });

  // Nav section anchors point at the home page so they work from any page.
  it('anchors a hash link to the home page under the base', () => {
    expect(withBase('#books', '/ambiguity-project/')).toBe('/ambiguity-project/#books');
  });

  // Astro may report the base without a trailing slash; links still join cleanly.
  it('tolerates a base without a trailing slash', () => {
    expect(withBase('/about', '/ambiguity-project')).toBe('/ambiguity-project/about');
  });

  // On a custom domain the base is the root, so paths come back unchanged.
  it('leaves paths root-relative when the base is the domain root', () => {
    expect(withBase('/about', '/')).toBe('/about');
    expect(withBase('#support', '/')).toBe('/#support');
  });

  // External links must never be rewritten under the site base.
  it('returns external and protocol-relative URLs unchanged', () => {
    expect(withBase('https://substack.com', '/ambiguity-project/')).toBe('https://substack.com');
    expect(withBase('mailto:hello@example.org', '/ambiguity-project/')).toBe('mailto:hello@example.org');
    expect(withBase('//cdn.example.com/x.js', '/ambiguity-project/')).toBe('//cdn.example.com/x.js');
  });
});
