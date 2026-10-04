// Prefix an internal link or asset path with the site's deploy base.
//
// The site deploys under a GitHub Pages subpath today
// (`/ambiguity-project/`) and at the domain root later. Astro exposes the
// active base as `import.meta.env.BASE_URL`; routing every internal href and
// asset src through this helper keeps them resolving under either.
//
// - `/about` and `about` → `<base>about`
// - `#books` → `<base>#books` (a section anchor on the home page, so it works
//   from any page, not only the home page)
// - `/` → `<base>`
// - external URLs (`https:`, `mailto:`, `tel:`, protocol-relative `//`) are
//   returned unchanged.
const EXTERNAL = /^(?:[a-z][a-z\d+.-]*:|\/\/)/i;

export function withBase(href: string, base: string = import.meta.env.BASE_URL ?? '/'): string {
  if (EXTERNAL.test(href)) return href;
  const root = base.endsWith('/') ? base : `${base}/`;
  if (href === '' || href === '/') return root;
  return root + href.replace(/^\/+/, '');
}
