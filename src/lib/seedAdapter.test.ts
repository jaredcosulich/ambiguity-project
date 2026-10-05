import { describe, expect, it } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { syncCollectionDir, writeSeed } from '../../.codeyam/seed-adapter';

/** A throwaway `{content, data}` root pair for one seed run. */
function tempRoots(): { contentRoot: string; dataRoot: string } {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'codeyam-seedadapter-'));
  return { contentRoot: path.join(root, 'content'), dataRoot: path.join(root, 'data') };
}

/** Every file in `dir`, sorted, so assertions do not depend on readdir order. */
function listDir(dir: string): string[] {
  return fs.readdirSync(dir).sort();
}

/** Push a file's mtime into the past so a later rewrite is detectable. */
function ageFile(filePath: string): number {
  const past = new Date(Date.now() - 60_000);
  fs.utimesSync(filePath, past, past);
  return fs.statSync(filePath).mtimeMs;
}

describe('writeSeed collection sync', () => {
  // Re-seeding identical content must not touch any file: a rewrite is a file
  // event Astro's watcher reacts to, and that churn is what flashed pages 404.
  it('leaves files untouched when the seed is unchanged', () => {
    const { contentRoot, dataRoot } = tempRoots();
    const seed = { books: [{ slug: 'a', title: 'A' }, { slug: 'b', title: 'B' }] };
    writeSeed(contentRoot, seed, dataRoot);
    const fileA = path.join(contentRoot, 'books', 'a.md');
    const before = ageFile(fileA);

    writeSeed(contentRoot, seed, dataRoot);

    expect(fs.statSync(fileA).mtimeMs).toBe(before);
    expect(listDir(path.join(contentRoot, 'books'))).toEqual(['a.md', 'b.md']);
  });

  // An entry dropped from the seed must disappear from disk so a scenario
  // fully replaces the prior one, while surviving entries stay in place.
  it('deletes only the entries no longer in the seed', () => {
    const { contentRoot, dataRoot } = tempRoots();
    writeSeed(contentRoot, { books: [{ slug: 'a', title: 'A' }, { slug: 'b', title: 'B' }] }, dataRoot);
    const fileA = path.join(contentRoot, 'books', 'a.md');
    const before = ageFile(fileA);

    writeSeed(contentRoot, { books: [{ slug: 'a', title: 'A' }] }, dataRoot);

    expect(listDir(path.join(contentRoot, 'books'))).toEqual(['a.md']);
    expect(fs.statSync(fileA).mtimeMs).toBe(before);
  });

  // A changed entry must be rewritten with its new contents.
  it('rewrites an entry whose contents changed', () => {
    const { contentRoot, dataRoot } = tempRoots();
    writeSeed(contentRoot, { books: [{ slug: 'a', title: 'Old' }] }, dataRoot);

    writeSeed(contentRoot, { books: [{ slug: 'a', title: 'New' }] }, dataRoot);

    const contents = fs.readFileSync(path.join(contentRoot, 'books', 'a.md'), 'utf-8');
    expect(contents).toContain('title: New');
    expect(contents).not.toContain('title: Old');
  });

  // An empty collection in the seed must leave an empty folder, not stale files.
  it('empties the folder for an empty collection', () => {
    const { contentRoot, dataRoot } = tempRoots();
    writeSeed(contentRoot, { books: [{ slug: 'a', title: 'A' }] }, dataRoot);

    const counts = writeSeed(contentRoot, { books: [] }, dataRoot);

    expect(counts).toEqual({ books: 0 });
    expect(listDir(path.join(contentRoot, 'books'))).toEqual([]);
  });

  // A collection folder that does not exist yet is created on first seed.
  it('creates a missing collection folder', () => {
    const { contentRoot, dataRoot } = tempRoots();

    writeSeed(contentRoot, { books: [{ slug: 'a', title: 'A' }] }, dataRoot);

    expect(listDir(path.join(contentRoot, 'books'))).toEqual(['a.md']);
  });
});

describe('syncCollectionDir', () => {
  // Only markdown is managed: other files in the folder (images, notes) survive.
  it('prunes stale markdown but keeps non-markdown files', () => {
    const { contentRoot } = tempRoots();
    const dir = path.join(contentRoot, 'books');
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'stale.md'), 'x');
    fs.writeFileSync(path.join(dir, 'stale.mdx'), 'x');
    fs.writeFileSync(path.join(dir, 'cover.png'), 'x');

    syncCollectionDir(dir, new Map([['fresh.md', 'hello\n']]));

    expect(listDir(dir)).toEqual(['cover.png', 'fresh.md']);
    expect(fs.readFileSync(path.join(dir, 'fresh.md'), 'utf-8')).toBe('hello\n');
  });

  // Files are written before stale ones are pruned, so a kept slug is never
  // absent from the folder at any point during the sync.
  it('never removes a file that stays in the target set', () => {
    const { contentRoot } = tempRoots();
    const dir = path.join(contentRoot, 'books');
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'keep.md'), 'old\n');
    const keepIno = fs.statSync(path.join(dir, 'keep.md')).ino;

    syncCollectionDir(dir, new Map([['keep.md', 'new\n']]));

    expect(fs.statSync(path.join(dir, 'keep.md')).ino).toBe(keepIno);
    expect(fs.readFileSync(path.join(dir, 'keep.md'), 'utf-8')).toBe('new\n');
  });
});
