import { rm } from 'node:fs/promises';
import type { AstroIntegration } from 'astro';

// The `/isolated-components/*` pages exist only so codeyam can screenshot one
// component at a time in dev. They are committed (a fresh clone needs them) but
// must never reach the published site, so the build deletes their output and
// the sitemap skips them.
export const ISOLATION_DIR = 'isolated-components';

/** True when a URL or pathname points at an isolation page. */
export function isIsolationPath(urlOrPath: string): boolean {
  let pathname = urlOrPath;
  try {
    pathname = new URL(urlOrPath).pathname;
  } catch {
    // Already a bare pathname.
  }
  return pathname.split('/').includes(ISOLATION_DIR);
}

export function excludeIsolationPages(): AstroIntegration {
  return {
    name: 'exclude-isolation-pages',
    hooks: {
      'astro:build:done': async ({ dir, logger }) => {
        await rm(new URL(`${ISOLATION_DIR}/`, dir), { recursive: true, force: true });
        logger.info(`removed /${ISOLATION_DIR}/ from the build output`);
      },
    },
  };
}
