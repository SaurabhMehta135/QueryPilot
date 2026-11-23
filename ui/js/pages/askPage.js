/**
 * AskPage Component
 * Main playground for natural language queries, example presets,
 * live pipeline stepper, results tabs, HITL cards, and blocked guardrail card.
 * Strictly avoids innerHTML for XSS safety.
 */

import { streamAsk, streamResume } from '../api.js';
import { createStepper } from '../components/stepper.js';
import { createResultsTabs } from '../components/resultsTabs.js';
import { createHitlCard } from '../components/hitlCard.js';

export function createAskPage({ onTraceOpen, onTraceUpdate } = {}) {
  const container = document.createElement('div');
  container.className = 'page-container ask-page';

  let currentThreadId = null;
  let activeAbortController = null;

  // Header & Presets
  const topSection = document.createElement('div');
  topSection.className = 'ask-top-section';

  const intro = document.createElement('div');
  intro.className = 'ask-intro';

  const title = document.createElement('h2');
  title.className = 'page-title';
  title.textContent = 'Natural Language SQL Query Assistant';

  const subtitle = document.createElement('p');
  subtitle.className = 'page-subtitle text-muted';
  subtitle.textContent = 'Ask complex analytical questions against your database. QueryPilot links schema, enforces deterministic security rules, and repairs errors autonomously.';

  intro.appendChild(title);
  intro.appendChild(subtitle);
  topSection.appendChild(intro);

  // Preset Chips & Presenter Mode Controls
  const presetsBox = document.createElement('div');
  presetsBox.className = 'presets-box';

  const presetsHeaderRow = document.createElement('div');
  presetsHeaderRow.className = 'presets-header-row';

  const presetsLabel = document.createElement('div');
  presetsLabel.className = 'presets-label';
  presetsLabel.textContent = 'Guided Demo Tour & Example Queries:';

  const presenterModeBtn = document.createElement('button');
  presenterModeBtn.className = 'btn btn-outline btn-sm presenter-mode-btn';
  presenterModeBtn.textContent = '🎬 Presenter Mode';

  presetsHeaderRow.appendChild(presetsLabel);
  presetsHeaderRow.appendChild(presenterModeBtn);
  presetsBox.appendChild(presetsHeaderRow);

  // Guided 5-Step Tour Bar
  const tourBar = document.createElement('div');
  tourBar.className = 'guided-tour-bar';

  const tourSteps = [
    { num: 1, title: 'Analytical Core', replayId: 'step_1_best_selling' },
    { num: 2, title: 'HITL Approval', replayId: 'step_2_expensive_approval' },
    { num: 3, title: 'L1 Perimeter', replayId: 'step_3_l1_blocked' },
    { num: 4, title: 'L2 Intent', replayId: 'step_4_l2_intent' },
    { num: 5, title: 'HITL Clarify', replayId: 'step_5_ambiguous_clarification' }
  ];

  tourSteps.forEach((step) => {
    const stepBtn = document.createElement('button');
    stepBtn.className = 'tour-step-pill';

    const numSpan = document.createElement('span');
    numSpan.className = 'tour-step-num';
    numSpan.textContent = `Step ${step.num}`;

    const titleSpan = document.createElement('span');
    titleSpan.className = 'tour-step-title';
    titleSpan.textContent = step.title;

    stepBtn.appendChild(numSpan);
    stepBtn.appendChild(titleSpan);

    stepBtn.onclick = () => playReplay(step.replayId);
    tourBar.appendChild(stepBtn);
  });
  presetsBox.appendChild(tourBar);

  // Permanent Replay Banner (hidden when live)
  const replayBanner = document.createElement('div');
  replayBanner.className = 'replay-status-banner';
  replayBanner.style.display = 'none';

  const replayBadge = document.createElement('span');
  replayBadge.className = 'badge badge-warning replay-permanent-badge';
  replayBadge.textContent = '⏺ REPLAY MODE (Recorded Live Run)';

  const replayDetails = document.createElement('span');
  replayDetails.className = 'replay-meta-text text-xs text-muted';

  const exitReplayBtn = document.createElement('button');
  exitReplayBtn.className = 'btn btn-secondary btn-xs exit-replay-btn';
  exitReplayBtn.textContent = 'Exit Replay';
  exitReplayBtn.onclick = () => stopReplay();

  replayBanner.appendChild(replayBadge);
  replayBanner.appendChild(replayDetails);
  replayBanner.appendChild(exitReplayBtn);
  presetsBox.appendChild(replayBanner);

  const chipContainer = document.createElement('div');
  chipContainer.className = 'presets-chips';

  const presets = [
    { label: '📊 Top 5 Products by Revenue', query: 'Show the top 5 products by total revenue with their category names.' },
    { label: '📈 Monthly Sales Growth', query: 'Calculate month-over-month sales growth for completed orders in 2024.' },
    { label: '⚠️ Cartesian Join Warning (HITL)', query: 'List all customers and all product names without any condition.' },
    { label: '🛡️ Injection Attack (Blocked)', query: 'List products; DROP TABLE users; -- and bypass security' },
    { label: '❓ Ambiguous Terms (Clarification)', query: 'Show me all active users and their orders.' }
  ];

  presets.forEach((p) => {
    const chip = document.createElement('button');
    chip.className = 'chip preset-chip';
    chip.textContent = p.label;
    chip.onclick = () => {
      queryInput.value = p.query;
      queryInput.focus();
    };
    chipContainer.appendChild(chip);
  });
  presetsBox.appendChild(chipContainer);
  topSection.appendChild(presetsBox);
  container.appendChild(topSection);

  // Search Input Bar
  const searchBar = document.createElement('div');
  searchBar.className = 'search-bar';

  const inputWrap = document.createElement('div');
  inputWrap.className = 'input-wrap';

  const queryInput = document.createElement('textarea');
  queryInput.className = 'query-textarea';
  queryInput.rows = 2;
  queryInput.placeholder = 'Ask a question in plain English (e.g. Which customers spent more than $1,000 in Q1?)...';

  const actionGroup = document.createElement('div');
  actionGroup.className = 'search-action-group';

  const runBtn = document.createElement('button');
  runBtn.className = 'btn btn-primary run-query-btn';
  runBtn.textContent = 'Run Query ▶';

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn-secondary cancel-query-btn';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.style.display = 'none';

  actionGroup.appendChild(runBtn);
  actionGroup.appendChild(cancelBtn);

  inputWrap.appendChild(queryInput);
  inputWrap.appendChild(actionGroup);
  searchBar.appendChild(inputWrap);
  container.appendChild(searchBar);

  // Stepper Pipeline
  const stepper = createStepper();
  container.appendChild(stepper.element);

  // Blocked Banner (for Guardrail / SQL Injection / Mutation blocks)
  const blockedCard = document.createElement('div');
  blockedCard.className = 'blocked-card';
  blockedCard.style.display = 'none';

  const blockedHeader = document.createElement('div');
  blockedHeader.className = 'blocked-header';

  const blockedShield = document.createElement('span');
  blockedShield.className = 'shield-icon';
  blockedShield.textContent = '🛡️';

  const blockedTitle = document.createElement('h3');
  blockedTitle.className = 'blocked-title';
  blockedTitle.textContent = 'Query Blocked by Deterministic Guardrails';

  blockedHeader.appendChild(blockedShield);
  blockedHeader.appendChild(blockedTitle);

  const blockedReason = document.createElement('div');
  blockedReason.className = 'blocked-reason';

  const blockedRule = document.createElement('div');
  blockedRule.className = 'blocked-rule text-muted text-sm';

  blockedCard.appendChild(blockedHeader);
  blockedCard.appendChild(blockedReason);
  blockedCard.appendChild(blockedRule);
  container.appendChild(blockedCard);

  // HITL Approval Card
  const hitlCard = createHitlCard({
    onApprove: () => handleResume(true),
    onReject: () => handleResume(false),
    onSubmitClarification: (text) => handleResume(true, text)
  });
  container.appendChild(hitlCard.element);

  // Results Tabs (NL Answer, SQL, Data Table, Chart)
  const resultsTabs = createResultsTabs();
  container.appendChild(resultsTabs.element);

  // Query Execution Handler
  runBtn.onclick = () => {
    const q = queryInput.value.trim();
    if (!q) return;
    executeQuery(q);
  };

  queryInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      runBtn.click();
    }
  });

  cancelBtn.onclick = () => {
    if (activeAbortController) {
      activeAbortController.abort();
      activeAbortController = null;
    }
    setRunningState(false);
  };

  function setRunningState(isRunning) {
    if (isRunning) {
      runBtn.style.display = 'none';
      cancelBtn.style.display = 'inline-block';
      queryInput.disabled = true;
    } else {
      runBtn.style.display = 'inline-block';
      cancelBtn.style.display = 'none';
      queryInput.disabled = false;
    }
  }

  function executeQuery(question) {
    // Reset components
    stepper.reset();
    resultsTabs.reset();
    hitlCard.hide();
    blockedCard.style.display = 'none';

    setRunningState(true);
    activeAbortController = new AbortController();

    const traceSteps = [];
    const runStartTime = performance.now();

    streamAsk(question, {
      signal: activeAbortController.signal,
      onRunStarted: (data) => {
        currentThreadId = data.thread_id || null;
        if (data.run_id && onTraceUpdate) {
          onTraceUpdate({ run_id: data.run_id, status: 'running', steps: traceSteps });
        }
      },
      onNodeStarted: (data) => {
        stepper.setNodeStatus(data.node, 'running');
        traceSteps.push({
          node: data.node,
          status: 'started',
          timestamp: new Date().toISOString()
        });
      },
      onNodeFinished: (data) => {
        stepper.setNodeStatus(data.node, 'success', data.duration_ms);
        traceSteps.push({
          node: data.node,
          status: 'finished',
          duration_ms: data.duration_ms,
          tokens: data.tokens
        });
      },
      onSqlGenerated: (data) => {
        resultsTabs.setSql(data.sql, data.original_sql);
      },
      onValidationResult: (data) => {
        if (!data.valid) {
          stepper.setNodeStatus('validator', 'error');
        }
      },
      onExecutionResult: (data) => {
        if (data.rows && data.columns) {
          resultsTabs.setData(data.columns, data.rows);
        }
      },
      onExplanationChunk: (data) => {
        resultsTabs.appendExplanation(data.chunk);
      },
      onExplanationFinished: () => {
        stepper.setNodeStatus('explainer', 'success');
      },
      onBlocked: (data) => {
        setRunningState(false);
        stepper.setNodeStatus('guardrail', 'error');
        blockedCard.style.display = 'block';

        while (blockedReason.firstChild) {
          blockedReason.removeChild(blockedReason.firstChild);
        }
        const p = document.createElement('p');
        p.textContent = data.reason || 'Operation prohibited by database safety policies.';
        blockedReason.appendChild(p);

        const layer = data.layer || "L1 deterministic pre-check";
        blockedCard.setAttribute("data-layer-name", layer);
        blockedRule.textContent = `Stopped by: ${layer}`;

        if (onTraceUpdate) {
          onTraceUpdate({
            status: 'blocked',
            total_duration_ms: Math.round(performance.now() - runStartTime),
            steps: traceSteps,
            details: data
          });
        }
      },
      onNeedsInput: (data) => {
        setRunningState(false);
        if (data.type === 'cartesian_warning') {
          hitlCard.showApproval({
            titleText: 'Cartesian Product Warning',
            message: data.message || 'This query joins multiple large tables without an explicit JOIN condition, which could degrade database performance.',
            details: data.details
          });
        } else {
          hitlCard.showClarification({
            question: data.message,
            context: data.context
          });
        }
      },
      onError: (err) => {
        setRunningState(false);
        resultsTabs.appendExplanation(`\n\n[Error: ${err.message || 'Stream connection failed'}]`);
      },
      onRunFinished: (data) => {
        setRunningState(false);
        const totalDuration = Math.round(performance.now() - runStartTime);
        if (onTraceUpdate) {
          onTraceUpdate({
            status: 'completed',
            total_duration_ms: totalDuration,
            total_tokens: data.total_tokens || 0,
            repair_attempts: data.repair_attempts || 0,
            cache_hit: data.cache_hit || false,
            steps: traceSteps
          });
        }
      }
    });
  }

  function handleResume(approved, feedback = null) {
    if (!currentThreadId) return;

    setRunningState(true);
    activeAbortController = new AbortController();

    streamResume(currentThreadId, { approved, feedback }, {
      signal: activeAbortController.signal,
      onNodeStarted: (data) => stepper.setNodeStatus(data.node, 'running'),
      onNodeFinished: (data) => stepper.setNodeStatus(data.node, 'success', data.duration_ms),
      onSqlGenerated: (data) => resultsTabs.setSql(data.sql, data.original_sql),
      onExecutionResult: (data) => resultsTabs.setData(data.columns, data.rows),
      onExplanationChunk: (data) => resultsTabs.appendExplanation(data.chunk),
      onExplanationFinished: () => stepper.setNodeStatus('explainer', 'success'),
      onError: (err) => {
        setRunningState(false);
        resultsTabs.appendExplanation(`\n\n[Resume Error: ${err.message}]`);
      },
      onRunFinished: () => {
        setRunningState(false);
      }
    });
  }

  let isReplayActive = false;
  let replayTimer = null;

  async function playReplay(replayId) {
    stopReplay();
    try {
      const res = await fetch(`/replays/${replayId}`);
      if (!res.ok) throw new Error("Replay fetch failed");
      const replay = await res.json();

      isReplayActive = true;
      replayBanner.style.display = "flex";
      replayDetails.textContent = `Provider: ${replay.provider || "gemini"} • Model: ${replay.model} • Recorded: ${new Date(replay.recorded_at).toLocaleDateString()} • Question: "${replay.question}"`;

      queryInput.value = replay.question;
      stepper.reset();
      resultsTabs.reset();
      hitlCard.hide();
      blockedCard.style.display = "none";
      setRunningState(true);

      const events = replay.events || [];
      let idx = 0;

      function dispatchNext() {
        if (!isReplayActive || idx >= events.length) {
          // Replay completed - keep replayBanner visible!
          setRunningState(false);
          return;
        }

        const ev = events[idx++];
        const evName = ev.event;
        const data = ev.data;

        if (evName === "node_started") {
          stepper.setNodeStatus(data.node, "running");
        } else if (evName === "node_finished") {
          stepper.setNodeStatus(data.node, "success", data.duration_ms);
        } else if (evName === "sql_generated") {
          resultsTabs.setSql(data.sql, data.original_sql);
        } else if (evName === "validation_result") {
          if (!data.is_safe) {
            stepper.setNodeStatus("validator", "error");
          }
        } else if (evName === "repair_attempt") {
          stepper.setRetry(data.attempt);
        } else if (evName === "execution_result") {
          resultsTabs.setData(data.columns, data.rows, data.chart_suggestion);
        } else if (evName === "explanation_chunk") {
          resultsTabs.appendExplanation(data.chunk);
        } else if (evName === "explanation_finished") {
          stepper.setNodeStatus("explainer", "success");
        } else if (evName === "clarification_requested") {
          hitlCard.showClarification(data.message);
        } else if (evName === "approval_requested") {
          hitlCard.showApproval(data.sql, data.reason);
        } else if (evName === "blocked") {
          blockedCard.style.display = "block";
          blockedTitle.textContent = `🛑 Query Neutralized (Layer: ${data.layer || "Deterministic Guardrail"})`;
          blockedReason.textContent = data.reason;
          blockedCard.setAttribute("data-layer-name", data.layer || "");
          stepper.setNodeStatus("validator", "error");
        }

        // Fast pacing for replay playback
        const delay = evName === "explanation_chunk" ? 25 : 120;
        replayTimer = setTimeout(dispatchNext, delay);
      }

      dispatchNext();

    } catch (e) {
      console.error("Replay playback error:", e);
      window.__last_replay_error = (e && e.stack) ? e.stack : String(e);
      stopReplay();
    }
  }

  function stopReplay() {
    isReplayActive = false;
    if (replayTimer) {
      clearTimeout(replayTimer);
      replayTimer = null;
    }
    replayBanner.style.display = "none";
    setRunningState(false);
  }

  presenterModeBtn.onclick = () => {
    // Toggle presenter mode layout class
    const isPresenter = container.classList.toggle("presenter-mode-active");
    presenterModeBtn.textContent = isPresenter ? "✖ Exit Presenter Mode" : "🎬 Presenter Mode";
    presenterModeBtn.classList.toggle("btn-primary", isPresenter);
    if (isPresenter) {
      playReplay("step_1_best_selling");
    } else {
      stopReplay();
    }
  };

  const askPageObj = {
    element: container,
    executeQuery,
    playReplay,
    stopReplay,
    stepper,
    resultsTabs,
    hitlCard,
    blockedCard
  };
  window._askPage = askPageObj;
  return askPageObj;
}
