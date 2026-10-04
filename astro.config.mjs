// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import codeyamCms from '@codeyam/cms';

// Astro static-site config for free GitHub Pages hosting.
//
// `output: 'static'` pre-renders every route to plain HTML at build time, so
// the whole `dist/` folder drops onto GitHub Pages as-is.
//
// `base` and `site` come from the environment so moving between the Pages
// subpath (jaredcosulich.github.io/ambiguity-project/) and a custom domain
// (ambiguityproject.org) is a config change, not a code change. The deploy
// workflow sets both; locally they default to the root. Every internal link
// and asset URL goes through `withBase()` (src/lib/base.ts) so it resolves
// under whichever base is active. See DEPLOY_SETUP.md for the switch recipe.
const base = process.env.DEPLOY_BASE_PATH || '/';
const site = process.env.PAGES_SITE || undefined;

export default defineConfig({
  output: 'static',
  site,
  base,
  integrations: [react(), sitemap(), codeyamCms()],
  vite: {
    // Dev only: pre-bundle the CMS admin's markdown deps so /admin hydrates
    // without Vite discovering them mid-request and forcing a reload.
    optimizeDeps: {
      include: ['micromark', 'micromark-extension-gfm', 'debug'],
    },
    server: {
      // Dev only — KEEP THIS LINE. CodeYam never serves the preview from the
      // origin this dev server binds: it serves it from the editor host, or
      // from a dedicated preview host. Astro's dev server is Vite, whose host
      // check refuses requests carrying an unknown Host header, so without
      // this the preview renders as a dead shell. Set CODEYAM_PREVIEW_HOSTS
      // (comma-separated) in the `env` block of `.codeyam/editor.json` to
      // narrow it to a known preview domain. `server.*` is not read by
      // `astro build`.
      allowedHosts: process.env.CODEYAM_PREVIEW_HOSTS
        ? process.env.CODEYAM_PREVIEW_HOSTS.split(',')
            .map((host) => host.trim())
            .filter(Boolean)
        : true,
    },
  },
});
