// A `collectionLoader` that keeps watching a collection whose folder starts
// out empty.
//
// Astro's `glob` loader returns before registering its file watcher when the
// base directory has no matching files. A collection that ships empty (the
// `tools` collection, until real tools exist) therefore never notices its
// first entry under `astro dev`: not one added in /admin, and not one a codeyam
// scenario seeds. This wrapper watches the folder itself and re-runs the load
// once a first file appears; from then on the glob loader's own watcher takes
// over. Production builds have no watcher, so this is a no-op there.
import * as path from 'path';
import type { Loader, LoaderContext } from 'astro/loaders';
import { collectionLoader } from '@codeyam/cms/content';
import { resolveContentRoot } from './contentRoot';

export function watchedCollectionLoader(collection: string): Loader {
  const inner = collectionLoader(collection);
  return {
    name: `${inner.name}-watched`,
    load: async (ctx: LoaderContext) => {
      await inner.load(ctx);
      const { watcher, store } = ctx;
      if (!watcher || store.keys().length > 0) return;

      const dir = path.join(resolveContentRoot(), collection);
      let reloaded = false;
      watcher.add(dir);
      watcher.on('add', async (added: string) => {
        if (reloaded || !/\.mdx?$/.test(added) || !added.startsWith(dir + path.sep)) return;
        reloaded = true;
        await inner.load(ctx);
      });
    },
  };
}
