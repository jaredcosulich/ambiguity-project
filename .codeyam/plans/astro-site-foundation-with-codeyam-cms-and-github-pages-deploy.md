---
title: "Astro Site Foundation With CodeYam CMS And GitHub Pages Deploy"
mode: ui
createdAt: "2026-09-30T23:53:29Z"
source: manual
---

## Summary

Turn this repo from a single hand-written `index.html` mockup into a real Astro
static site, managed with `@codeyam/cms` and deployed to GitHub Pages. This plan
lays the foundation every later plan builds on. It covers the Astro scaffold, the
CMS at `/admin`, the design tokens and fonts from the mockup, and the shared site
shell (navy header with the bracket logo and mobile menu, plus the footer). It
also adds a GitHub Actions deploy to the current Pages subpath
(`https://jaredcosulich.github.io/ambiguity-project/`). When it's done, visitors
see the same header and footer as the mockup, and editors can sign in at
`/admin` and change the site title, nav, and footer without touching code. The
home page sections themselves (hero, book, blog, tools, learn more, support) are
built by the follow-up plans.

## Key Decisions

- **Start from codeyam's `astro-github-pages` template.** It already carries the
  static output, the content-collection seed adapter and sandbox that scenarios
  need, the isolated-components route, and a Pages deploy workflow. Scaffold it
  in the Prepare step with `codeyam-editor editor template astro-github-pages`.
- **Replace the template's Sveltia editor with `@codeyam/cms` (published on npm,
  currently 0.14.0).** Run `npm install @codeyam/cms` then
  `npx codeyam-cms integrate`, and delete the template's `public/admin/`
  (Sveltia `index.html` + `config.yml`) and its Sveltia `CMS_SETUP.md`
  guidance. This is the same migration harvardintech already made (its
  completed plan "Adopt CodeYam CMS And Retire Sveltia" is a good reference).
  Keep the template's Astro 5 / `@astrojs/react` 4 pairing; the CMS supports
  it, and `integrate` picks the matching React major.
- **Sign-in stays zero-infrastructure.** Keep `src/data/cms.json` on
  `auth.token: true` (each editor pastes a fine-grained GitHub token with
  Contents read/write on `jaredcosulich/ambiguity-project`). No
  `cms-auth-worker` and no Cloudflare account.
- **Drop the template's sample content.** Remove the template's `welcome` blog
  post, the `team`/`events` samples, and the `blog`/`team`/`events`
  collections. This site's blog comes from Substack (a later plan), and it has
  no team or events pages yet. Keep the `pages` collection, which the Learn More
  plan uses for an About page.
- **Env-driven `base`/`site`, so the domain switch is a config change.** Follow
  harvardintech's `astro.config.mjs`: `base` comes from `DEPLOY_BASE_PATH`
  (default `/`) and `site` from `PAGES_SITE`. The deploy workflow sets
  `DEPLOY_BASE_PATH=/ambiguity-project` and
  `PAGES_SITE=https://jaredcosulich.github.io` for now. Every internal link and
  asset URL goes through a `withBase()` helper, so it resolves under the subpath
  and later at the root of `ambiguityproject.org`. Moving to the custom domain
  later means: unset the base path, add `public/CNAME`, and set `siteUrl` in
  `cms.json`. Write that recipe into `DEPLOY_SETUP.md`. Nothing else should
  change.
- **Switch Pages to Actions in the same push that removes the root
  `index.html`.** Pages currently builds in legacy mode from `main` `/`
  (`build_type: legacy`), serving the mockup directly. Once the mockup leaves
  the root, a legacy build would serve nothing. At push time, run
  `gh api -X PUT repos/jaredcosulich/ambiguity-project/pages -f build_type=workflow`
  (or have the user flip Settings → Pages → Source to "GitHub Actions"). Then
  confirm the deploy workflow publishes.
- **Keep the mockup as the design reference, out of the web root.** Move
  `index.html` to `design/mockup/index.html` and keep a copy of
  `images/book-cover.png` beside it at `design/mockup/images/`, so the mockup
  still opens standalone. The follow-up plans port sections from that file.
  Ship `favicon.svg`, `apple-touch-icon.png`, and `images/book-cover.png` from
  `public/`. Delete the root `.nojekyll`; the template already ships
  `public/.nojekyll`.
- **Port the design faithfully.** Move the mockup's `:root` custom properties
  (navy, ivory, salmon, plum, ochre, sage, the tint colors, `--gutter`,
  `--section-y`, the serif/sans stacks) into `src/styles/tokens.css`. Move the
  shared rules (`.wrap`, `.btn`, `.more`, the bracket `.label`, `.eyebrow`,
  `.card`, `.sr-only`) into a global stylesheet. Section-specific CSS moves
  with its section's component in later plans. Load the Libre Caslon Text +
  Source Sans 3 Google Fonts in `BaseLayout`, as the mockup does.
- **Declare site-wide settings the later plans read.** Add a `settings` block to
  `src/data/collections.json`. The only field this plan needs is
  `substackUrl`; the other plans add their own settings.

## Implementation

### 1. Scaffold and install the CMS

Run `codeyam-editor editor template astro-github-pages`. Then install
`@codeyam/cms`, run `npx codeyam-cms integrate`, remove the Sveltia
`public/admin/` scaffold, and update `CMS_SETUP.md` to describe the
token sign-in path only. Point `src/data/cms.json` at
`{ "owner": "jaredcosulich", "repo": "ambiguity-project", "branch": "main" }`.
Move the content collections onto the package's `collectionLoader` /
`draftField` / `seoFields` (from `@codeyam/cms/content`), keeping only `pages`.

### 2. Relocate the mockup and static assets

**File**: `index.html`

Move it to `design/mockup/index.html` (with `design/mockup/images/book-cover.png`).
Move `favicon.svg`, `apple-touch-icon.png`, and `images/book-cover.png` into
`public/`. Delete the root `.nojekyll`.

### 3. Tokens, fonts, and the site shell

**New file**: `src/components/SiteHeader.astro` renders the navy header band with
the inline bracket-logo SVG and the nav links from `src/data/nav.json`. The
"Support Us" item is the white button. It also includes the mobile Menu/Close
toggle below 860px, ported from the mockup's inline script.
**New file**: `src/components/SiteFooter.astro` renders the navy-on-ivory logo,
the footer nav, and a copyright line built from `settings.json`'s footer text.
Replace the template's `src/data/settings.json` (title "The Ambiguity Project",
the mockup's meta description) and `src/data/nav.json` (Books, Blog,
Technology, Learn More, Support Us → `#books`, `#blog`, `#technology`,
`#learn`, `#support`). Fill `src/styles/tokens.css` from the mockup's `:root`.
Rebuild `src/layouts/BaseLayout.astro` around the header and footer, keeping
`SEO.astro`. `src/pages/index.astro` becomes a shell with empty section anchors
for the later plans to fill.

### 4. Base-path-aware config and deploy

Rewrite `astro.config.mjs` with env-driven `base`/`site`, `codeyamCms()`, and
harvardintech's dev-only `optimizeDeps.include` for `micromark` /
`micromark-extension-gfm` / `debug`. Add the `withBase()` helper and its unit
test. Set the two env vars in `.github/workflows/deploy.yml`. Update
`DEPLOY_SETUP.md` with the subpath → `ambiguityproject.org` switch recipe.

## Reused existing code

- The mockup markup and CSS in `index.html` are the visual source of truth.
- The harvardintech repo's Astro config (a sibling codeyam project, not in this
  repo) shows the env-driven base, the content sandbox wiring, and the
  optimizeDeps fix for CMS admin hydration.
- The @codeyam/cms package README (on npm, and in the codeyam-cms repo) covers
  "Install", "Declaring your own site settings", and "Content collections".

## Scenarios to Demonstrate

- Home page shell at Desktop: navy header with logo and nav, ivory body, footer
- Home page shell at Mobile: nav collapsed behind the Menu button, then opened
- Site settings with a long custom site title and footer text (the header and
  footer don't break)
- Nav with an extra item added through `nav.json` (it wraps or collapses cleanly)
- `/admin` dashboard renders with the `pages` collection and Site settings