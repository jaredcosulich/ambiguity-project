import { describe, expect, it, vi } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { pathToFileURL } from 'url';
import { excludeIsolationPages, isIsolationPath } from './isolationPages';

describe('isIsolationPath', () => {
  // A bare isolation route is recognised whatever the trailing slash.
  it('matches a bare isolation pathname', () => {
    expect(isIsolationPath('/isolated-components/SiteHeader')).toBe(true);
    expect(isIsolationPath('/isolated-components/SiteHeader/')).toBe(true);
  });

  // The sitemap filter receives absolute URLs, including ones under a Pages base path.
  it('matches an absolute URL under a base path', () => {
    expect(
      isIsolationPath('https://jaredcosulich.github.io/ambiguity-project/isolated-components/MainNav/'),
    ).toBe(true);
  });

  // Real site pages must stay in the sitemap.
  it('does not match ordinary pages', () => {
    expect(isIsolationPath('https://ambiguityproject.org/')).toBe(false);
    expect(isIsolationPath('/about/')).toBe(false);
  });

  // Only a whole path segment counts, so a page whose slug merely contains the word is kept.
  it('does not match a segment that only contains the directory name', () => {
    expect(isIsolationPath('/blog/isolated-components-explained/')).toBe(false);
  });

  // An empty string is not an isolation page.
  it('returns false for an empty string', () => {
    expect(isIsolationPath('')).toBe(false);
  });
});

describe('excludeIsolationPages', () => {
  // The build hook deletes the isolation output and leaves every other page in place.
  it('removes the isolated-components folder from the build output', async () => {
    const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'codeyam-isolation-'));
    fs.mkdirSync(path.join(dist, 'isolated-components', 'SiteHeader'), { recursive: true });
    fs.writeFileSync(path.join(dist, 'isolated-components', 'SiteHeader', 'index.html'), '<html></html>');
    fs.writeFileSync(path.join(dist, 'index.html'), '<html></html>');

    const hook = excludeIsolationPages().hooks['astro:build:done'] as (opts: unknown) => Promise<void>;
    await hook({ dir: pathToFileURL(`${dist}/`), logger: { info: vi.fn() } });

    expect(fs.existsSync(path.join(dist, 'isolated-components'))).toBe(false);
    expect(fs.existsSync(path.join(dist, 'index.html'))).toBe(true);
  });

  // A build with no isolation pages (or a second run) must not fail.
  it('is a no-op when the folder is absent', async () => {
    const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'codeyam-isolation-'));
    const hook = excludeIsolationPages().hooks['astro:build:done'] as (opts: unknown) => Promise<void>;
    await expect(hook({ dir: pathToFileURL(`${dist}/`), logger: { info: vi.fn() } })).resolves.toBeUndefined();
  });
});
