// Resolve the content/data roots the site reads from.
//
// In a real production `astro build` (GitHub Pages deploy) the site reads its
// committed `src/content`/`src/data`. During a codeyam session the editor seeds
// a sandbox copy under `.codeyam/tmp/` and points the app at it via the
// `CODEYAM_CONTENT_ROOT` / `CODEYAM_DATA_ROOT` env vars, injected into the dev
// server the editor spawns. So scenario seeding never touches committed source.
//
// Resolution order (first match wins): env override → default.
//
// Two properties are load-bearing, and both exist because this boundary leaked
// in production:
//
//  1. The env var is the ONLY override. This module used to also read
//     `.codeyam/tmp/content-root` / `data-root` sidecar files. Those were
//     ambient — every process whose cwd was the project read them, including
//     the developer's own `npm run dev` — and nothing ever deleted them, so one
//     editor session redirected a checkout permanently and edits to committed
//     content silently did nothing. A dev server the editor did not launch now
//     resolves committed source, by design.
//  2. A production build refuses the override outright, whatever is in the
//     environment. The deploy's isolation must not rest on `.codeyam/tmp/`
//     happening to be gitignored and CI happening to build from a clean
//     checkout.
import * as path from 'path';

/**
 * Whether this module is executing inside a production build (`astro build`),
 * as opposed to `astro dev` or a test run. Astro/Vite statically replaces
 * `import.meta.env.PROD`; the optional chain keeps the check from throwing if
 * this module is ever loaded in a bare Node context with no Vite env.
 */
function isProductionBuild(): boolean {
  return import.meta.env?.PROD === true;
}

function resolveRoot(envVar: string, defaultRel: string, projectRoot: string): string {
  // A production build always resolves committed source. Checked before the
  // env read, so an override that leaked into the build environment cannot
  // redirect a deploy at scenario data.
  if (!isProductionBuild()) {
    const fromEnv = process.env[envVar];
    if (fromEnv && fromEnv.length > 0) return fromEnv;
  }

  return path.join(projectRoot, defaultRel);
}

/** Absolute content root: `CODEYAM_CONTENT_ROOT` → `src/content`. */
export function resolveContentRoot(projectRoot: string = process.cwd()): string {
  return resolveRoot('CODEYAM_CONTENT_ROOT', 'src/content', projectRoot);
}

/** Absolute data root: `CODEYAM_DATA_ROOT` → `src/data`. */
export function resolveDataRoot(projectRoot: string = process.cwd()): string {
  return resolveRoot('CODEYAM_DATA_ROOT', 'src/data', projectRoot);
}
