// Helpers for the Library of reviewed books (the `library` collection): the
// link to a book's report page, and the few books the home Library band shows.
import { withBase } from './base';

export const MAX_HOME_LIBRARY_BOOKS = 4;

/** The first `max` books (already in `order`) for the home Library band. */
export function homeLibraryBooks<T>(books: readonly T[], max: number = MAX_HOME_LIBRARY_BOOKS): T[] {
  return books.slice(0, Math.max(0, max));
}

/** A book's report page, `/library/<id>`, under the deploy base. */
export function libraryHref(id: string, base?: string): string {
  return withBase(id ? `/library/${id}` : '/library', base);
}
