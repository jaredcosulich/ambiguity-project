import { describe, expect, it } from 'vitest';
import { MAX_HOME_LIBRARY_BOOKS, homeLibraryBooks, libraryHref } from './library';

describe('homeLibraryBooks', () => {
  // Six reviewed books show only the first four in the home Library band.
  it('caps the list at four by default', () => {
    expect(homeLibraryBooks(['a', 'b', 'c', 'd', 'e', 'f'])).toEqual(['a', 'b', 'c', 'd']);
    expect(MAX_HOME_LIBRARY_BOOKS).toBe(4);
  });

  // Fewer books than the cap are all shown, in their incoming order.
  it('returns every book when under the cap', () => {
    expect(homeLibraryBooks(['b', 'a'])).toEqual(['b', 'a']);
  });

  // An empty library yields no books, which hides the home band.
  it('returns an empty list for an empty library', () => {
    expect(homeLibraryBooks([])).toEqual([]);
  });

  // A custom cap is respected and a negative one clamps to zero without throwing.
  it('honours a custom cap and clamps a negative one to zero', () => {
    expect(homeLibraryBooks(['a', 'b', 'c'], 2)).toEqual(['a', 'b']);
    expect(homeLibraryBooks(['a', 'b'], -3)).toEqual([]);
  });

  // The input list is never mutated.
  it('does not modify the list it is given', () => {
    const books = ['a', 'b', 'c', 'd', 'e'];
    homeLibraryBooks(books);
    expect(books).toEqual(['a', 'b', 'c', 'd', 'e']);
  });
});

describe('libraryHref', () => {
  // A book page lives at /library/<id> under the root base.
  it('builds the book page path at the domain root', () => {
    expect(libraryHref('range', '/')).toBe('/library/range');
  });

  // Under the GitHub Pages subpath the base is prefixed.
  it('prefixes the deploy base when the site lives under a subpath', () => {
    expect(libraryHref('the-black-swan', '/ambiguity-project/')).toBe('/ambiguity-project/library/the-black-swan');
  });

  // A base without a trailing slash still produces a single separator.
  it('handles a base without a trailing slash', () => {
    expect(libraryHref('range', '/ambiguity-project')).toBe('/ambiguity-project/library/range');
  });

  // No id points at the library index rather than a broken book path.
  it('falls back to the library index for an empty id', () => {
    expect(libraryHref('', '/')).toBe('/library');
  });
});
