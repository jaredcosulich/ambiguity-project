// Ordering for CMS collections that carry an optional numeric `order`
// (books, tools, quotes). Entries without an order sort last, and ties keep
// their incoming order, so builds and screenshots stay stable.
export interface Orderable {
  data: { order?: number };
}

export function sortByOrder<T extends Orderable>(entries: readonly T[]): T[] {
  const rank = (e: T) => e.data.order ?? Number.POSITIVE_INFINITY;
  return entries
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => rank(a.entry) - rank(b.entry) || a.index - b.index)
    .map(({ entry }) => entry);
}

/** The lowest-ordered entry, or undefined for an empty collection. */
export function pickFirstByOrder<T extends Orderable>(entries: readonly T[]): T | undefined {
  return sortByOrder(entries)[0];
}
