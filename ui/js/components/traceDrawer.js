/**
 * TraceDrawer Component
 * Collapsible side panel showing complete run execution metrics,
 * step latencies, token consumption, guardrail events, and raw JSON payload.
 * Strictly avoids innerHTML for XSS safety.
 */

export function createTraceDrawer() {
  const drawer = document.createElement('aside');
  drawer.className = 'trace-drawer';
  drawer.setAttribute('aria-label', 'Execution Trace Drawer');

  const header = document.createElement('div');
  header.className = 'trace-drawer-header';

  const titleWrap = document.createElement('div');
  titleWrap.className = 'trace-drawer-title-wrap';

  const title = document.createElement('h3');
  title.className = 'trace-drawer-title';
  title.textContent = 'Execution Trace & Telemetry';

  const statusBadge = document.createElement('span');
  statusBadge.className = 'badge badge-idle';
  statusBadge.textContent = 'IDLE';

  titleWrap.appendChild(title);
  titleWrap.appendChild(statusBadge);

  const closeBtn = document.createElement('button');
  closeBtn.className = 'btn-icon close-drawer-btn';
  closeBtn.textContent = '✕';
  closeBtn.title = 'Close drawer';
  closeBtn.onclick = () => close();

  header.appendChild(titleWrap);
  header.appendChild(closeBtn);

  const body = document.createElement('div');
  body.className = 'trace-drawer-body';

  // Stats Grid
  const statsGrid = document.createElement('div');
  statsGrid.className = 'trace-stats-grid';

  const durationStat = createStatBox('Total Latency', '0.0s');
  const tokensStat = createStatBox('Total Tokens', '0');
  const retriesStat = createStatBox('Repairs', '0');
  const cacheStat = createStatBox('Cache Status', 'N/A');

  statsGrid.appendChild(durationStat.el);
  statsGrid.appendChild(tokensStat.el);
  statsGrid.appendChild(retriesStat.el);
  statsGrid.appendChild(cacheStat.el);
  body.appendChild(statsGrid);

  // Timeline section
  const timelineTitle = document.createElement('h4');
  timelineTitle.className = 'trace-section-title';
  timelineTitle.textContent = 'Pipeline Event Timeline';
  body.appendChild(timelineTitle);

  const timelineList = document.createElement('div');
  timelineList.className = 'trace-timeline-list';
  body.appendChild(timelineList);

  // Raw JSON accordion
  const rawDetails = document.createElement('details');
  rawDetails.className = 'trace-raw-details';

  const summary = document.createElement('summary');
  summary.textContent = 'View Raw Trace JSON';
  rawDetails.appendChild(summary);

  const rawPre = document.createElement('pre');
  rawPre.className = 'trace-raw-pre';
  rawPre.textContent = 'No trace data yet.';
  rawDetails.appendChild(rawPre);
  body.appendChild(rawDetails);

  drawer.appendChild(header);
  drawer.appendChild(body);

  function createStatBox(label, initialVal) {
    const el = document.createElement('div');
    el.className = 'stat-box';

    const lbl = document.createElement('div');
    lbl.className = 'stat-label';
    lbl.textContent = label;

    const val = document.createElement('div');
    val.className = 'stat-value';
    val.textContent = initialVal;

    el.appendChild(lbl);
    el.appendChild(val);
    return { el, val };
  }

  function open() {
    drawer.classList.add('open');
  }

  function close() {
    drawer.classList.remove('open');
  }

  function toggle() {
    drawer.classList.toggle('open');
  }

  function updateTrace(traceData) {
    if (!traceData) return;

    if (traceData.status) {
      statusBadge.textContent = traceData.status.toUpperCase();
      statusBadge.className = `badge badge-${traceData.status}`;
    }

    if (traceData.total_duration_ms != null) {
      durationStat.val.textContent = `${(traceData.total_duration_ms / 1000).toFixed(2)}s`;
    } else if (traceData.latency != null) {
      durationStat.val.textContent = `${traceData.latency}ms`;
    }

    if (traceData.total_tokens != null) {
      tokensStat.val.textContent = traceData.total_tokens.toLocaleString();
    } else if (traceData.tokens != null) {
      tokensStat.val.textContent = traceData.tokens.toLocaleString();
    }

    if (traceData.repair_attempts != null) {
      retriesStat.val.textContent = traceData.repair_attempts.toString();
    } else if (traceData.retries != null) {
      retriesStat.val.textContent = traceData.retries.toString();
    }

    if (traceData.cache_hit != null) {
      cacheStat.val.textContent = traceData.cache_hit ? 'HIT (0s)' : 'MISS';
    }

    // Timeline updates
    while (timelineList.firstChild) {
      timelineList.removeChild(timelineList.firstChild);
    }

    const steps = traceData.steps || traceData.nodes || [];
    if (steps.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'text-muted text-sm';
      empty.textContent = 'No event steps logged in this trace.';
      timelineList.appendChild(empty);
    } else {
      steps.forEach((step, idx) => {
        const item = document.createElement('div');
        item.className = 'timeline-item';

        const dot = document.createElement('span');
        dot.className = `timeline-dot ${step.error ? 'dot-error' : 'dot-success'}`;

        const content = document.createElement('div');
        content.className = 'timeline-content';

        const stepHeader = document.createElement('div');
        stepHeader.className = 'timeline-header';

        const stepName = document.createElement('strong');
        stepName.textContent = step.name || step.node || `Step ${idx + 1}`;

        const stepTime = document.createElement('span');
        stepTime.className = 'text-muted text-xs';
        stepTime.textContent = step.duration_ms ? `${step.duration_ms}ms` : '';

        stepHeader.appendChild(stepName);
        stepHeader.appendChild(stepTime);

        content.appendChild(stepHeader);

        if (step.description || step.details) {
          const detail = document.createElement('div');
          detail.className = 'timeline-detail text-sm';
          detail.textContent = step.description || (typeof step.details === 'string' ? step.details : JSON.stringify(step.details));
          content.appendChild(detail);
        }

        item.appendChild(dot);
        item.appendChild(content);
        timelineList.appendChild(item);
      });
    }

    rawPre.textContent = JSON.stringify(traceData, null, 2);
  }

  return {
    element: drawer,
    open,
    close,
    toggle,
    updateTrace
  };
}
