import { beforeEach, describe, expect, it } from 'vitest';
import { bindMobileMenu, menuLabel, setMenuOpen } from './mobileMenu';

function renderHeader() {
  document.body.innerHTML = `
    <button class="menu-btn" aria-expanded="false">Menu</button>
    <nav id="main-nav"><a href="#books">Books</a><a class="btn" href="#support">Support Us</a></nav>`;
  return {
    button: document.querySelector<HTMLButtonElement>('.menu-btn')!,
    nav: document.getElementById('main-nav')!,
  };
}

describe('menuLabel', () => {
  // The toggle offers the action that clicking it would take.
  it('reads Close when open and Menu when closed', () => {
    expect(menuLabel(true)).toBe('Close');
    expect(menuLabel(false)).toBe('Menu');
  });
});

describe('setMenuOpen', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  // Opening sets the class the CSS shows the nav on, plus the a11y state.
  it('opens the nav and updates the button', () => {
    const { button, nav } = renderHeader();
    setMenuOpen(button, nav, true);
    expect(nav.classList.contains('open')).toBe(true);
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(button.textContent).toBe('Close');
  });

  // Closing reverses every change opening made.
  it('closes the nav and restores the button', () => {
    const { button, nav } = renderHeader();
    setMenuOpen(button, nav, true);
    setMenuOpen(button, nav, false);
    expect(nav.classList.contains('open')).toBe(false);
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(button.textContent).toBe('Menu');
  });
});

describe('bindMobileMenu', () => {
  // Each click on the toggle flips the menu between open and closed.
  it('toggles the menu on each button click', () => {
    const { button, nav } = renderHeader();
    bindMobileMenu(button, nav);
    button.click();
    expect(nav.classList.contains('open')).toBe(true);
    button.click();
    expect(nav.classList.contains('open')).toBe(false);
  });

  // Choosing a section closes the menu so the page content is visible again.
  it('closes the open menu when a nav link is followed', () => {
    const { button, nav } = renderHeader();
    bindMobileMenu(button, nav);
    button.click();
    nav.querySelector<HTMLAnchorElement>('a.btn')!.click();
    expect(nav.classList.contains('open')).toBe(false);
    expect(button.textContent).toBe('Menu');
  });

  // Following a link while closed leaves the menu closed.
  it('keeps the menu closed when a link is followed while closed', () => {
    const { button, nav } = renderHeader();
    bindMobileMenu(button, nav);
    nav.querySelector('a')!.click();
    expect(nav.classList.contains('open')).toBe(false);
    expect(button.getAttribute('aria-expanded')).toBe('false');
  });
});
