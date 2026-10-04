// Mobile nav toggle, ported from the mockup's inline script. Below 860px the
// header nav is hidden until the Menu button adds `.open`; the button's label
// and `aria-expanded` track the state, and following any nav link closes it.

export function menuLabel(open: boolean): string {
  return open ? 'Close' : 'Menu';
}

export function setMenuOpen(button: HTMLElement, nav: HTMLElement, open: boolean): void {
  nav.classList.toggle('open', open);
  button.setAttribute('aria-expanded', open ? 'true' : 'false');
  button.textContent = menuLabel(open);
}

export function bindMobileMenu(button: HTMLElement, nav: HTMLElement): void {
  button.addEventListener('click', () => setMenuOpen(button, nav, !nav.classList.contains('open')));
  nav.querySelectorAll('a').forEach((link) =>
    link.addEventListener('click', () => setMenuOpen(button, nav, false)),
  );
}
