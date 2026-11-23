/**
 * ThemeToggle Component
 * Toggles between 'dark' and 'light' theme on document.documentElement.
 * Persists user choice in localStorage.
 * Strictly avoids innerHTML for XSS safety.
 */

import { getState, setState } from '../state.js';

export function createThemeToggle() {
  const btn = document.createElement('button');
  btn.className = 'btn-theme-toggle';
  btn.setAttribute('aria-label', 'Toggle Dark or Light theme');

  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  updateButtonText(current);

  btn.onclick = () => {
    const curTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const nextTheme = curTheme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
  };

  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem('querypilot_theme', theme);
    } catch (e) {
      // storage quota or disabled
    }
    setState({ theme });
    updateButtonText(theme);
  }

  function updateButtonText(theme) {
    btn.textContent = theme === 'dark' ? '☀️ Light Mode' : '🌙 Dark Mode';
  }

  return {
    element: btn,
    setTheme
  };
}
