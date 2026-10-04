# The Ambiguity Project website

The site for [The Ambiguity Project](https://jaredcosulich.github.io/ambiguity-project/),
a 501(c)(3) non-profit helping people better recognize, live with, and navigate
ambiguity. It is a static [Astro](https://astro.build) site, edited through
CodeYam CMS at `/admin` and published to GitHub Pages.

## Develop

```bash
npm install
npm run dev        # http://127.0.0.1:4321 (CMS at /admin)
npm run build      # type-check + static build into dist/
npm run test       # unit tests (vitest + jsdom)
```

## Layout

```
design/mockup/       # the original hand-written mockup — the visual source of truth
public/              # favicon, apple-touch-icon, images (served as-is)
src/
  components/        # SiteHeader, SiteFooter and their parts, one component per file
  content/config.ts  # content collections (currently `pages`)
  data/              # editable JSON: settings.json, nav.json, cms.json, collections.json
  layouts/           # BaseLayout: <head>, fonts, header, footer
  lib/               # site data loading, withBase(), nav links, mobile menu
  pages/             # routes; the home page is a shell the section plans fill in
  styles/            # tokens.css (design tokens) and global.css (shared rules)
```

## Editable site data

Site-wide text and links are content, not markup. `src/data/settings.json`
(title, description, footer text, Substack URL) and `src/data/nav.json` (the
header and footer menu; the last item is the header's button) are loaded by
`src/lib/site.ts`. Changing them is a commit the CMS makes, never a source
change. See `CMS_SETUP.md`.

## Deploy

Every push to `main` builds and publishes through
`.github/workflows/deploy.yml`. Internal links go through `withBase()` so the
site works under the `/ambiguity-project/` subpath today and at the root of a
custom domain later. See `DEPLOY_SETUP.md`.
