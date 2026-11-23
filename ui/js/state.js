/**
 * ui/js/state.js - Reactive client state management
 */

export class AppState {
  constructor() {
    this.theme = this._initTheme();
    this.activePage = "ask";
    this.isPresenterMode = false;
    this.isReplay = false;
    
    // Server status
    this.health = null;
    this.activeModel = "loading...";
    
    // Current Run State
    this.currentRun = {
      runId: null,
      threadId: null,
      question: "",
      status: "idle", // idle, running, needs_input, blocked, failed, success
      nodes: {
        schema_node: { status: "idle", duration_ms: null, tokens: null, meta: null },
        writer_node: { status: "idle", duration_ms: null, tokens: null, meta: null, retryCount: 0 },
        validator_node: { status: "idle", duration_ms: null, tokens: null, meta: null, isExpensive: false },
        executor_node: { status: "idle", duration_ms: null, tokens: null, rowCount: 0 },
        explainer_node: { status: "idle", duration_ms: null, tokens: null },
      },
      sql: null,
      rewrittenSql: null,
      validation: null,
      executionResult: null,
      explanation: null,
      streamedText: "",
      blockedReason: null,
      blockedLayer: null,
      interrupt: null,
      traceSteps: [],
      estimatedCostUsd: 0,
      totalLatencyMs: 0,
      guardrailEvents: [],
    };

    this.listeners = new Set();
  }

  _initTheme() {
    try {
      const saved = localStorage.getItem("querypilot_theme");
      if (saved === "light" || saved === "dark") return saved;
    } catch (e) {
      // ignore localStorage errors in privacy mode
    }
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  setTheme(theme) {
    this.theme = theme;
    try {
      localStorage.setItem("querypilot_theme", theme);
    } catch (e) {}
    document.documentElement.setAttribute("data-theme", theme);
    this.notify();
  }

  toggleTheme() {
    this.setTheme(this.theme === "dark" ? "light" : "dark");
  }

  setActivePage(page) {
    this.activePage = page;
    this.notify();
  }

  resetRun(question) {
    this.currentRun = {
      runId: null,
      threadId: null,
      question: question || "",
      status: "running",
      nodes: {
        schema_node: { status: "idle", duration_ms: null, tokens: null, meta: null },
        writer_node: { status: "idle", duration_ms: null, tokens: null, meta: null, retryCount: 0 },
        validator_node: { status: "idle", duration_ms: null, tokens: null, meta: null, isExpensive: false },
        executor_node: { status: "idle", duration_ms: null, tokens: null, rowCount: 0 },
        explainer_node: { status: "idle", duration_ms: null, tokens: null },
      },
      sql: null,
      rewrittenSql: null,
      validation: null,
      executionResult: null,
      explanation: null,
      streamedText: "",
      blockedReason: null,
      blockedLayer: null,
      interrupt: null,
      traceSteps: [],
      estimatedCostUsd: 0,
      totalLatencyMs: 0,
      guardrailEvents: [],
    };
    this.notify();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify() {
    for (const l of this.listeners) l(this);
  }
}

export const state = new AppState();

export function getState() {
  return state;
}

export function setState(partial) {
  Object.assign(state, partial);
  state.notify();
}

export function subscribe(listener) {
  return state.subscribe(listener);
}
