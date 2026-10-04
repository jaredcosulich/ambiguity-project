// Shape the editable `nav.json` items into the links the header and footer
// render. Items without a URL (dropdown-only parents) are skipped, every href
// goes through `withBase()`, and the LAST link is flagged as the header's
// call-to-action button ("Support Us").
import { withBase } from './base';
import type { NavItem } from './site';

export interface NavLink {
  label: string;
  href: string;
  isCta: boolean;
}

export function toNavLinks(items: NavItem[], base?: string): NavLink[] {
  const linked = items.filter((item): item is NavItem & { url: string } => Boolean(item.url));
  return linked.map((item, i) => ({
    label: item.label,
    href: withBase(item.url, base),
    isCta: i === linked.length - 1,
  }));
}
