# Content Management Setup

The site is edited through **CodeYam CMS** (`@codeyam/cms`), served at
**`/admin`** on the live site and in local dev. It commits changes straight to
this repo (`jaredcosulich/ambiguity-project`, branch `main`, set in
`src/data/cms.json`), and the deploy workflow republishes the site.

## What editors can change

- **Site settings** (Settings screen): site title, description, footer text,
  and the Substack URL. Stored in `src/data/settings.json`. Site-specific
  settings are declared in the `settings` block of `src/data/collections.json`.
- **Navigation**: the header and footer menu in `src/data/nav.json`. The last
  item renders as the header's call-to-action button ("Support Us").
- **Pages**: the `pages` collection (`src/content/pages/*.md`), e.g. an About
  page.

## Signing in (no extra infrastructure)

`src/data/cms.json` uses `auth.token: true`: each editor signs in by pasting a
GitHub fine-grained personal access token. There is no auth server to run.

To create a token, an editor (with write access to the repo) goes to
**github.com** → their avatar → **Settings** → **Developer settings** →
**Personal access tokens** → **Fine-grained tokens** → **Generate new token**,
and sets:

- **Repository access**: Only select repositories →
  `jaredcosulich/ambiguity-project`
- **Permissions** → **Repository permissions** → **Contents**: Read and write

They paste the token into the `/admin` sign-in screen. It stays in their
browser; never commit it.

## Content schema

Collections are declared in `src/content/config.ts` using the package's
`collectionLoader`, `draftField` and `seoFields` (from `@codeyam/cms/content`),
so the CMS's Draft toggle and SEO fields reach the site. During a codeyam
session the loader reads a sandbox under `.codeyam/tmp/`, so scenario seeding
never touches committed content; a production build always reads
`src/content` and `src/data`.
