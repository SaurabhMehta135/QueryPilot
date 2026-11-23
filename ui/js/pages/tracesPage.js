/**
 * ui/js/pages/tracesPage.js - Lightweight Traces List & Architecture SVG
 * Clean view of recent execution traces and pipeline architecture.
 * Strictly uses textContent & SVG createElementNS (zero innerHTML).
 */

import { fetchTraces } from '../api.js';

export function createTracesPage() {
  const container = document.createElement('div');
  container.className = 'page-container traces-page';

  // 1. Architecture SVG Section
  const archCard = document.createElement('div');
  archCard.className = 'card mb-4';

  const archHeader = document.createElement('div');
  archHeader.className = 'card-header';
  const archTitle = document.createElement('h3');
  archTitle.textContent = '📐 Multi-Agent Graph Architecture';
  archHeader.appendChild(archTitle);
  archCard.appendChild(archHeader);

  const archBody = document.createElement('div');
  archBody.className = 'card-body';

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 920 180");
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", "180");
  svg.style.borderRadius = "8px";
  svg.style.background = "var(--bg-surface-elevated)";

  const nodes = [
    { x: 25, y: 70, w: 150, h: 48, label: "Schema Agent", sub: "L1 pre-check & L2 intent", color: "#38bdf8" },
    { x: 205, y: 70, w: 150, h: 48, label: "SQL Writer", sub: "Structured Proposal", color: "#38bdf8" },
    { x: 385, y: 70, w: 150, h: 48, label: "Safety Validator", sub: "L3 SQL validator", color: "#f59e0b" },
    { x: 565, y: 70, w: 150, h: 48, label: "Executor", sub: "L4 read-only connection", color: "#10b981" },
    { x: 745, y: 70, w: 150, h: 48, label: "Explainer", sub: "untrusted-data wrapping", color: "#a855f7" },
  ];

  // Draw connecting arrows
  for (let i = 0; i < nodes.length - 1; i++) {
    const x1 = nodes[i].x + nodes[i].w;
    const y1 = nodes[i].y + 24;
    const x2 = nodes[i + 1].x;
    const y2 = nodes[i + 1].y + 24;

    const line = document.createElementNS(svgNS, "line");
    line.setAttribute("x1", String(x1));
    line.setAttribute("y1", String(y1));
    line.setAttribute("x2", String(x2 - 8));
    line.setAttribute("y2", String(y2));
    line.setAttribute("stroke", "var(--border-strong)");
    line.setAttribute("stroke-width", "2");
    svg.appendChild(line);

    const arrow = document.createElementNS(svgNS, "polygon");
    arrow.setAttribute("points", `${x2 - 8},${y2 - 5} ${x2},${y2} ${x2 - 8},${y2 + 5}`);
    arrow.setAttribute("fill", "var(--border-strong)");
    svg.appendChild(arrow);
  }

  // Draw nodes
  nodes.forEach((n) => {
    const rect = document.createElementNS(svgNS, "rect");
    rect.setAttribute("x", String(n.x));
    rect.setAttribute("y", String(n.y));
    rect.setAttribute("width", String(n.w));
    rect.setAttribute("height", String(n.h));
    rect.setAttribute("rx", "6");
    rect.setAttribute("fill", "var(--bg-surface)");
    rect.setAttribute("stroke", n.color);
    rect.setAttribute("stroke-width", "1.5");
    svg.appendChild(rect);

    const txt1 = document.createElementNS(svgNS, "text");
    txt1.setAttribute("x", String(n.x + n.w / 2));
    txt1.setAttribute("y", String(n.y + 20));
    txt1.setAttribute("text-anchor", "middle");
    txt1.setAttribute("fill", "var(--text-primary)");
    txt1.setAttribute("font-size", "11px");
    txt1.setAttribute("font-weight", "600");
    txt1.textContent = n.label;
    svg.appendChild(txt1);

    const txt2 = document.createElementNS(svgNS, "text");
    txt2.setAttribute("x", String(n.x + n.w / 2));
    txt2.setAttribute("y", String(n.y + 35));
    txt2.setAttribute("text-anchor", "middle");
    txt2.setAttribute("fill", "var(--text-muted)");
    txt2.setAttribute("font-size", "9px");
    txt2.textContent = n.sub;
    svg.appendChild(txt2);
  });

  archBody.appendChild(svg);
  archCard.appendChild(archBody);
  container.appendChild(archCard);

  // 2. Recent Traces Table
  const traceCard = document.createElement('div');
  traceCard.className = 'card';

  const traceHeader = document.createElement('div');
  traceHeader.className = 'card-header';
  const traceTitle = document.createElement('h3');
  traceTitle.textContent = '📊 Execution Traces & Telemetry';
  traceHeader.appendChild(traceTitle);
  traceCard.appendChild(traceHeader);

  const traceBody = document.createElement('div');
  traceBody.className = 'card-body';

  const table = document.createElement('table');
  table.className = 'data-table text-xs';

  const thead = document.createElement('thead');
  const hTr = document.createElement('tr');
  ['Run ID', 'Question', 'Status', 'Duration (ms)', 'Tokens', 'Guardrail Events'].forEach((col) => {
    const th = document.createElement('th');
    th.textContent = col;
    hTr.appendChild(th);
  });
  thead.appendChild(hTr);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  table.appendChild(tbody);
  traceBody.appendChild(table);
  traceCard.appendChild(traceBody);
  container.appendChild(traceCard);

  // Load traces asynchronously
  fetchTraces(20)
    .then((traces) => {
      while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
      if (!traces || traces.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 6;
        td.className = 'text-center text-muted';
        td.textContent = 'No execution traces logged yet. Run queries from Query Assistant.';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
      }

      traces.forEach((t) => {
        const tr = document.createElement('tr');

        const tdId = document.createElement('td');
        tdId.className = 'font-mono';
        tdId.textContent = (t.run_id || '').slice(0, 8);
        tr.appendChild(tdId);

        const tdQ = document.createElement('td');
        tdQ.textContent = t.natural_question || '(Empty)';
        tr.appendChild(tdQ);

        const tdStat = document.createElement('td');
        const badge = document.createElement('span');
        badge.className = `badge ${t.final_status === 'success' ? 'badge-success' : (t.final_status === 'blocked' ? 'badge-danger' : 'badge-warning')}`;
        badge.textContent = t.final_status || 'unknown';
        tdStat.appendChild(badge);
        tr.appendChild(tdStat);

        const tdDur = document.createElement('td');
        tdDur.textContent = typeof t.total_duration_ms === 'number' ? `${Math.round(t.total_duration_ms)} ms` : '-';
        tr.appendChild(tdDur);

        const tdTok = document.createElement('td');
        tdTok.textContent = typeof t.total_tokens === 'number' ? t.total_tokens.toLocaleString() : '-';
        tr.appendChild(tdTok);

        const tdGuard = document.createElement('td');
        const count = (t.guardrail_events || []).length;
        tdGuard.textContent = count > 0 ? `${count} events` : '0 (Passed)';
        tr.appendChild(tdGuard);

        tbody.appendChild(tr);
      });
    })
    .catch(() => {
      while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 6;
      td.className = 'text-center text-muted';
      td.textContent = 'Failed to load telemetry traces.';
      tr.appendChild(td);
      tbody.appendChild(tr);
    });

  return { element: container };
}
