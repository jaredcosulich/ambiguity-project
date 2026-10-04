import { EventEmitter } from 'events';
import * as path from 'path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const innerLoad = vi.fn();
vi.mock('@codeyam/cms/content', () => ({
  collectionLoader: () => ({ name: 'glob-loader', load: innerLoad }),
}));
vi.mock('./contentRoot', () => ({ resolveContentRoot: () => '/content' }));

const { watchedCollectionLoader } = await import('./watchedCollectionLoader');

// A minimal loader context: a store reporting `keys`, and an optional watcher.
function context(keys: string[], watcher?: EventEmitter & { add: ReturnType<typeof vi.fn> }) {
  return { store: { keys: () => keys }, watcher } as never;
}

function fakeWatcher() {
  return Object.assign(new EventEmitter(), { add: vi.fn() });
}

const toolsDir = path.join('/content', 'tools');

describe('watchedCollectionLoader', () => {
  beforeEach(() => innerLoad.mockReset());

  // The wrapper always delegates the actual load to the CMS glob loader.
  it('runs the inner loader once on load', async () => {
    await watchedCollectionLoader('tools').load(context(['a']));
    expect(innerLoad).toHaveBeenCalledTimes(1);
  });

  // A production build has no watcher, so nothing extra is registered.
  it('does nothing extra without a watcher', async () => {
    await watchedCollectionLoader('tools').load(context([]));
    expect(innerLoad).toHaveBeenCalledTimes(1);
  });

  // A collection that already has entries is watched by the glob loader itself.
  it('does not watch a collection that already has entries', async () => {
    const watcher = fakeWatcher();
    await watchedCollectionLoader('tools').load(context(['a'], watcher));
    expect(watcher.add).not.toHaveBeenCalled();
  });

  // An empty collection reloads when its first markdown file appears.
  it('reloads an empty collection when its first entry is added', async () => {
    const watcher = fakeWatcher();
    await watchedCollectionLoader('tools').load(context([], watcher));
    expect(watcher.add).toHaveBeenCalledWith(toolsDir);
    watcher.emit('add', path.join(toolsDir, 'first.md'));
    await Promise.resolve();
    expect(innerLoad).toHaveBeenCalledTimes(2);
  });

  // Only the first add reloads; the glob loader's own watcher handles the rest.
  it('reloads only once', async () => {
    const watcher = fakeWatcher();
    await watchedCollectionLoader('tools').load(context([], watcher));
    watcher.emit('add', path.join(toolsDir, 'one.md'));
    watcher.emit('add', path.join(toolsDir, 'two.md'));
    await Promise.resolve();
    expect(innerLoad).toHaveBeenCalledTimes(2);
  });

  // Files in other collections or non-markdown files are ignored.
  it('ignores other folders and non-markdown files', async () => {
    const watcher = fakeWatcher();
    await watchedCollectionLoader('tools').load(context([], watcher));
    watcher.emit('add', path.join('/content', 'books', 'x.md'));
    watcher.emit('add', path.join(toolsDir, '.gitkeep'));
    watcher.emit('add', path.join('/content', 'tools-old', 'y.md'));
    await Promise.resolve();
    expect(innerLoad).toHaveBeenCalledTimes(1);
  });
});
