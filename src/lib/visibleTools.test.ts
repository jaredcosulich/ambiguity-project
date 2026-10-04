import { describe, expect, it } from 'vitest';
import { MAX_HOME_TOOLS, visibleTools } from './visibleTools';

describe('visibleTools', () => {
  // Five published tools show only the first three on the home page.
  it('caps the list at three by default', () => {
    expect(visibleTools(['a', 'b', 'c', 'd', 'e'])).toEqual(['a', 'b', 'c']);
    expect(MAX_HOME_TOOLS).toBe(3);
  });

  // Fewer than the cap are all shown.
  it('returns every tool when under the cap', () => {
    expect(visibleTools(['a'])).toEqual(['a']);
  });

  // Zero tools hides the section, so the result is empty.
  it('returns an empty list for no tools', () => {
    expect(visibleTools([])).toEqual([]);
  });

  // A custom or nonsensical cap is respected without throwing.
  it('honours a custom cap and clamps a negative one to zero', () => {
    expect(visibleTools(['a', 'b', 'c'], 2)).toEqual(['a', 'b']);
    expect(visibleTools(['a', 'b'], -1)).toEqual([]);
  });
});
