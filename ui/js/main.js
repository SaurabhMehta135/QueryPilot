/**
 * QueryPilot UI Main Application Entrypoint
 * Bootstraps the application layout, theme handling, header stats,
 * and page navigation.
 * Strictly avoids innerHTML for XSS safety.
 */

import { fetchHealth, fetchTraces } from './api.js';
import { getState, setState, subscribe } from './state.js';
import { createAskPage } from './pages/askPage.js';
import { createAttacksPage } from './pages/attacksPage.js';
import { createEvalPage } from './pages/evalPage.js';
import { createTracesPage } from './pages/tracesPage.js';
import { createTraceDrawer } from './components/traceDrawer.js';
import { createThemeToggle } from './components/themeToggle.js';

async function initApp() {
  const root = document.getElementById('app-root');
  if (!root) return;

  // Initialize Theme from localStorage or OS preference
  const savedTheme = localStorage.getItem('querypilot_theme') || 
    (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  document.documentElement.setAttribute('data-theme', savedTheme);
  setState({ theme: savedTheme });

  // App Layout Shell
  const appContainer = document.createElement('div');
  appContainer.className = 'app-layout';

  // Left Sidebar
  const sidebar = document.createElement('aside');
  sidebar.className = 'app-sidebar';

  const brand = document.createElement('div');
  brand.className = 'sidebar-brand';

  const logoIcon = document.createElement('span');
  logoIcon.className = 'brand-icon';
  logoIcon.textContent = '⚡';

  const brandText = document.createElement('div');
  brandText.className = 'brand-text-wrap';

  const brandName = document.createElement('span');
  brandName.className = 'brand-name';
  brandName.textContent = 'QueryPilot';

  const brandBadge = document.createElement('span');
  brandBadge.className = 'badge badge-version';
  brandBadge.textContent = 'v2.0';

  brandText.appendChild(brandName);
  brandText.appendChild(brandBadge);
  brand.appendChild(logoIcon);
  brand.appendChild(brandText);
  sidebar.appendChild(brand);

  // Navigation Links
  const nav = document.createElement('nav');
  nav.className = 'sidebar-nav';

  const navItems = [
    { id: 'ask', label: '💬 Query Assistant', active: true },
    { id: 'traces', label: '📈 Observability Traces' },
    { id: 'attacks', label: '🛡️ Security Simulator' },
    { id: 'evals', label: '📊 Benchmark Evals' },
    { id: 'schema', label: '🗄️ Database Schema' }
  ];

  const navButtons = {};

  navItems.forEach((item) => {
    const btn = document.createElement('button');
    btn.className = `nav-item ${item.active ? 'active' : ''}`;
    btn.textContent = item.label;
    btn.onclick = () => switchPage(item.id);
    nav.appendChild(btn);
    navButtons[item.id] = btn;
  });

  sidebar.appendChild(nav);

  // Sidebar Footer: Theme switcher
  const sidebarFooter = document.createElement('div');
  sidebarFooter.className = 'sidebar-footer';

  const themeToggle = createThemeToggle();
  sidebarFooter.appendChild(themeToggle.element);
  sidebar.appendChild(sidebarFooter);

  // Main Content Area
  const mainWrapper = document.createElement('div');
  mainWrapper.className = 'app-main-wrapper';

  // Top Header Bar
  const header = document.createElement('header');
  header.className = 'app-header';

  const headerLeft = document.createElement('div');
  headerLeft.className = 'header-left';

  const pageHeading = document.createElement('h1');
  pageHeading.className = 'header-heading';
  pageHeading.textContent = 'Query Assistant';
  headerLeft.appendChild(pageHeading);

  const headerRight = document.createElement('div');
  headerRight.className = 'header-right';

  // Dynamic Provider / Model Badge
  const modelBadge = document.createElement('div');
  modelBadge.className = 'badge badge-model';
  modelBadge.textContent = 'Connecting to backend...';

  // Telemetry drawer trigger button
  const traceDrawerBtn = document.createElement('button');
  traceDrawerBtn.className = 'btn btn-secondary btn-sm';
  traceDrawerBtn.textContent = '📊 Telemetry';

  headerRight.appendChild(modelBadge);
  headerRight.appendChild(traceDrawerBtn);

  header.appendChild(headerLeft);
  header.appendChild(headerRight);
  mainWrapper.appendChild(header);

  // Page Viewport
  const pageViewport = document.createElement('main');
  pageViewport.className = 'app-viewport';
  mainWrapper.appendChild(pageViewport);

  // Trace Drawer Component
  const traceDrawer = createTraceDrawer();
  traceDrawerBtn.onclick = () => traceDrawer.toggle();

  appContainer.appendChild(sidebar);
  appContainer.appendChild(mainWrapper);
  appContainer.appendChild(traceDrawer.element);
  root.appendChild(appContainer);

  // Mount Ask Page, Attacks Page, Eval Page & Traces Page
  const askPage = createAskPage({
    onTraceOpen: () => traceDrawer.open(),
    onTraceUpdate: (traceData) => traceDrawer.updateTrace(traceData)
  });
  window._askPage = askPage;
  const attacksPage = createAttacksPage();
  window._attacksPage = attacksPage;
  const evalPage = createEvalPage();
  window._evalPage = evalPage;
  const tracesPage = createTracesPage();
  window._tracesPage = tracesPage;
  pageViewport.appendChild(askPage.element);

  // Placeholder pages for remaining nav tabs
  const placeholderPages = {
    traces: tracesPage,
    attacks: attacksPage,
    evals: evalPage,
    schema: createPlaceholderPage('🗄️ Database Schema & Catalog', 'Interactive table explorer with column types, sample values, and foreign key relationships.')
  };

  function createPlaceholderPage(titleText, descText) {
    const p = document.createElement('div');
    p.className = 'page-container placeholder-page';

    const h = document.createElement('h2');
    h.className = 'page-title';
    h.textContent = titleText;

    const desc = document.createElement('p');
    desc.className = 'text-muted';
    desc.textContent = descText;

    p.appendChild(h);
    p.appendChild(desc);
    return p;
  }

  function switchPage(pageId) {
    Object.keys(navButtons).forEach((id) => {
      navButtons[id].classList.toggle('active', id === pageId);
    });

    while (pageViewport.firstChild) {
      pageViewport.removeChild(pageViewport.firstChild);
    }

    if (pageId === 'ask') {
      pageHeading.textContent = 'Query Assistant';
      pageViewport.appendChild(askPage.element);
    } else if (pageId === 'traces') {
      pageHeading.textContent = 'Observability Traces & Architecture';
      pageViewport.appendChild(tracesPage.element);
    } else if (pageId === 'attacks') {
      pageHeading.textContent = 'Security Simulator';
      pageViewport.appendChild(attacksPage.element);
    } else if (pageId === 'evals') {
      pageHeading.textContent = 'Benchmark Evaluations';
      pageViewport.appendChild(evalPage.element);
    } else if (placeholderPages[pageId]) {
      pageHeading.textContent = placeholderPages[pageId].querySelector('h2').textContent;
      pageViewport.appendChild(placeholderPages[pageId]);
    }
  }

  // Load backend health and model metadata
  try {
    const health = await fetchHealth();
    if (health) {
      const provider = health.llm_provider || 'Local / Mock';
      const model = health.sql_writer_model || health.model || 'gemini-3.1-flash-lite';
      modelBadge.textContent = `⚡ ${provider} (${model})`;
      modelBadge.classList.add('badge-success');
    }
  } catch (e) {
    modelBadge.textContent = '⚡ Offline / Disconnected';
    modelBadge.classList.add('badge-error');
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
