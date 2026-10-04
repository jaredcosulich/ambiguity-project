// Site-wide data loaded from editable JSON singletons under `src/data/`.
//
// `settings.json` and `nav.json` are content, not code: the CMS edits them as
// Sveltia "file" collections, and every layout reads them through this module.
// Changing the contact email, a social link, or a menu item is therefore a
// data edit (a commit the CMS makes), never a source change. codeyam's
// `content-collection` seed adapter rewrites these same files per scenario, so
// a scenario can render "site with 3 socials and a chapters dropdown" vs a
// minimal nav without touching markup.
//
// The singletons are read at build/render time with `fs` (rather than a static
// `import ... from '../data/settings.json'`) so the data root can be
// redirected: in production it resolves to `src/data`, but during a codeyam
// session it points at the `.codeyam/tmp` sandbox so seeding never mutates
// committed source. A static import is bundled from a fixed path and cannot be
// redirected. This runs in Node at build/render time, so `fs` is available for
// both the dev server and the production GitHub Pages build.
import * as fs from 'fs';
import * as path from 'path';
import { resolveDataRoot } from './contentRoot';

// Read on every call, not once at module load: the dev server keeps modules
// cached across requests, so a module-level read would keep serving the first
// values after the CMS or a codeyam scenario rewrites the file.
const readSingleton = <T>(name: string): T =>
  JSON.parse(fs.readFileSync(path.join(resolveDataRoot(), `${name}.json`), 'utf-8')) as T;

export interface SocialLink {
  label: string;
  url: string;
  icon?: string;
}

export interface SiteSettings {
  siteTitle: string;
  description: string;
  contactEmail: string;
  footerText: string;
  socials: SocialLink[];
  substackUrl?: string;
  // Home page copy (declared in collections.json `settings`).
  heroEyebrow?: string;
  missionPrefix?: string;
  missionWords?: string;
  missionSuffix?: string;
  toolsHeading?: string;
  toolsAllUrl?: string;
  learnHeading?: string;
  learnButtonLabel?: string;
  learnButtonUrl?: string;
}

export interface NavItem {
  label: string;
  url?: string;
  children?: NavItem[];
}

export interface SiteNav {
  items: NavItem[];
}

export const getSettings = (): SiteSettings => readSingleton<SiteSettings>('settings');
export const getNav = (): SiteNav => readSingleton<SiteNav>('nav');
