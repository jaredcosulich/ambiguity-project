import { describe, expect, it } from 'vitest';
import { pickFirstByOrder, sortByOrder } from './contentOrder';

const entry = (id: string, order?: number) => ({ id, data: { order } });

describe('sortByOrder', () => {
  // Entries come back lowest order first.
  it('sorts ascending by order', () => {
    const sorted = sortByOrder([entry('c', 3), entry('a', 1), entry('b', 2)]);
    expect(sorted.map((e) => e.id)).toEqual(['a', 'b', 'c']);
  });

  // An entry with no order goes after every ordered entry.
  it('puts entries without an order last', () => {
    const sorted = sortByOrder([entry('none'), entry('two', 2), entry('one', 1)]);
    expect(sorted.map((e) => e.id)).toEqual(['one', 'two', 'none']);
  });

  // Equal orders keep their incoming sequence so builds are deterministic.
  it('keeps the incoming order for ties', () => {
    const sorted = sortByOrder([entry('x', 1), entry('y', 1), entry('z')]);
    expect(sorted.map((e) => e.id)).toEqual(['x', 'y', 'z']);
  });

  // Sorting never mutates the caller's array.
  it('does not mutate its input', () => {
    const input = [entry('b', 2), entry('a', 1)];
    sortByOrder(input);
    expect(input.map((e) => e.id)).toEqual(['b', 'a']);
  });

  // Zero is a real order, not a missing one.
  it('treats order zero as first', () => {
    const sorted = sortByOrder([entry('one', 1), entry('zero', 0)]);
    expect(sorted.map((e) => e.id)).toEqual(['zero', 'one']);
  });
});

describe('pickFirstByOrder', () => {
  // The hero shows the lowest-ordered quote.
  it('returns the lowest-ordered entry', () => {
    expect(pickFirstByOrder([entry('keats', 2), entry('voltaire', 1)])?.id).toBe('voltaire');
  });

  // No quotes means no hero quote, not a crash.
  it('returns undefined for an empty list', () => {
    expect(pickFirstByOrder([])).toBeUndefined();
  });
});
