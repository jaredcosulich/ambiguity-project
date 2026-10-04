# GitHub Pages Deploy Setup

The site builds with Astro and deploys to GitHub Pages through
`.github/workflows/deploy.yml` on every push to `main`.

## Where it deploys today

`https://jaredcosulich.github.io/ambiguity-project/` (the project-site subpath).

`astro.config.mjs` reads two environment variables, and the deploy workflow
sets both:

| Variable | Today | Feeds |
| --- | --- | --- |
| `DEPLOY_BASE_PATH` | `/ambiguity-project` | Astro `base` (defaults to `/` locally) |
| `PAGES_SITE` | `https://jaredcosulich.github.io` | Astro `site` (canonical URLs, sitemap) |

Every internal link and asset URL goes through `withBase()` in
`src/lib/base.ts`, so it resolves under whichever base is active. Never
hard-code a leading `/ambiguity-project/` in markup.

## One-time: switch Pages to GitHub Actions

Pages used to serve the hand-written mockup straight from `main` (legacy
"Deploy from a branch" mode). The Astro build needs Actions mode instead.
Either:

- **On github.com**: the `jaredcosulich/ambiguity-project` repo → **Settings** →
  **Pages** → under **Build and deployment**, set **Source** to
  **GitHub Actions**; or
- **From a terminal with the `gh` CLI signed in**:
  ```bash
  gh api -X PUT repos/jaredcosulich/ambiguity-project/pages -f build_type=workflow
  ```

Then push to `main` (or run the workflow from the repo's **Actions** tab →
**Deploy to GitHub Pages** → **Run workflow**) and confirm it publishes.

## Later: move to ambiguityproject.org

Nothing in the code changes. Four config edits:

1. In `.github/workflows/deploy.yml`, delete the `DEPLOY_BASE_PATH` line (the
   base falls back to `/`) and set `PAGES_SITE: https://ambiguityproject.org`.
2. Add `public/CNAME` containing the bare domain on one line:
   `ambiguityproject.org`
3. In `src/data/cms.json`, add `"siteUrl": "https://ambiguityproject.org/"` so
   the CMS's "View live site" link and publish watch point at the new domain.
4. At the domain's DNS provider, add GitHub Pages' records:
   - `A` records for the apex: `185.199.108.153`, `185.199.109.153`,
     `185.199.110.153`, `185.199.111.153`
   - a `CNAME` for `www` pointing to `jaredcosulich.github.io`

   Then in the repo's **Settings** → **Pages**, enter the domain under
   **Custom domain** and tick **Enforce HTTPS** once the certificate is issued.
