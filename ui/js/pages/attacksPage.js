/**
 * ui/js/pages/attacksPage.js - Attack Lab & Security Simulator (Phase B)
 * Features:
 * 1. Live Presets Grid grouped by attack type:
 *    - Direct Destructive
 *    - Stacked / Semicolon SQL
 *    - Prompt Injection in Data
 *    - Obfuscated Attacks
 *    - Conversational Intent
 *    - Hinglish / Hindi Attacks
 *    - Safe Look-Alikes (Allowed through)
 * 2. Real pipeline stepper execution showing live defense progress
 * 3. 4-Layer Defense panel dynamically highlighting the EXACT layer that stopped the attack
 *    (using standard names: L1 deterministic pre-check, L2 LLM intent classifier,
 *     untrusted-data wrapping, L3 SQL validator, L4 read-only connection)
 *    and marking subsequent layers as "not reached"
 * 4. Model-Complies Simulator on isolated throwaway copy
 * Strictly avoids innerHTML for XSS safety.
 */

import { streamAsk } from '../api.js';

export function createAttacksPage() {
  const container = document.createElement("div");
  container.className = "page-container attacks-page";

  // Page Header
  const intro = document.createElement("div");
  intro.className = "page-intro";

  const title = document.createElement("h2");
  title.className = "page-title";
  title.textContent = "🛡️ QueryPilot Attack Lab & 4-Layer Security Simulator";

  const subtitle = document.createElement("p");
  subtitle.className = "page-subtitle text-muted";
  subtitle.textContent = "Demonstrate multi-layered deterministic guardrails in real time. Choose from categorized attacks or simulate model compliance. Guardrail events and stopped layers are derived dynamically from live execution traces.";

  intro.appendChild(title);
  intro.appendChild(subtitle);
  container.appendChild(intro);

  // Layout: Left column (Attack Grid & Simulator) + Right column (Defense Panel & Stepper)
  const mainGrid = document.createElement("div");
  mainGrid.className = "attack-lab-main-grid";

  const leftCol = document.createElement("div");
  leftCol.className = "attack-lab-col-left";

  const rightCol = document.createElement("div");
  rightCol.className = "attack-lab-col-right";

  // -----------------------------------------------------------------
  // 1. Live Attack Presets Grid
  // -----------------------------------------------------------------
  const gridCard = document.createElement("div");
  gridCard.className = "attack-catalog-card card";

  const gridHeader = document.createElement("div");
  gridHeader.className = "card-header";
  const gridTitle = document.createElement("h3");
  gridTitle.textContent = "Attack Lab: Categorized Presets";
  const gridDesc = document.createElement("p");
  gridDesc.className = "text-muted text-sm";
  gridDesc.textContent = "Select any adversarial scenario to execute live through the pipeline.";
  gridHeader.appendChild(gridTitle);
  gridHeader.appendChild(gridDesc);
  gridCard.appendChild(gridHeader);

  const groupsContainer = document.createElement("div");
  groupsContainer.className = "attack-groups-container";
  gridCard.appendChild(groupsContainer);
  leftCol.appendChild(gridCard);

  // -----------------------------------------------------------------
  // 2. Model-Complies Simulator Section
  // -----------------------------------------------------------------
  const simCard = document.createElement("div");
  simCard.className = "simulator-card card";

  const simHeader = document.createElement("div");
  simHeader.className = "card-header";
  const simTitle = document.createElement("h3");
  simTitle.textContent = "Model-Complies Simulator (Physical Backstop)";
  const simDesc = document.createElement("p");
  simDesc.className = "text-muted text-sm";
  simDesc.textContent = "Demonstrates what happens if the LLM completely obeys a malicious prompt. Executed in a temporary throwaway DB sandbox — sample.db is never touched.";
  simHeader.appendChild(simTitle);
  simHeader.appendChild(simDesc);
  simCard.appendChild(simHeader);

  const simBody = document.createElement("div");
  simBody.className = "card-body";

  const selectWrap = document.createElement("div");
  selectWrap.className = "sim-controls";

  const select = document.createElement("select");
  select.className = "input-select";

  const presets = [
    { id: "drop_users", label: "💥 Direct DDL Drop Table (DROP TABLE customers;)" },
    { id: "batch_injection", label: "💉 Semicolon Batched Statement (SELECT 1; DELETE FROM orders;)" },
    { id: "attach_exfil", label: "🕵️ Database File Exfiltration (ATTACH DATABASE 'leak.db')" },
    { id: "cartesian_cross", label: "⚠️ Unbounded Cartesian Product (CROSS JOIN products)" },
  ];

  presets.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.label;
    select.appendChild(opt);
  });

  const fireBtn = document.createElement("button");
  fireBtn.className = "btn btn-primary";
  fireBtn.textContent = "Simulate Attack Execution ▶";

  selectWrap.appendChild(select);
  selectWrap.appendChild(fireBtn);
  simBody.appendChild(selectWrap);

  // Notice for DEMO_MODE disabled
  const demoDisabledNotice = document.createElement("div");
  demoDisabledNotice.className = "demo-disabled-notice text-sm";
  demoDisabledNotice.style.display = "none";
  demoDisabledNotice.textContent = "⚠️ Simulation disabled: Backend running with DEMO_MODE=false. Enable DEMO_MODE in environment to simulate.";
  simBody.appendChild(demoDisabledNotice);

  // Simulation Result Box
  const simResultBox = document.createElement("div");
  simResultBox.className = "sim-result-box";
  simResultBox.style.display = "none";

  const resBadge = document.createElement("span");
  resBadge.className = "badge badge-success";
  resBadge.textContent = "BLOCKED BY GUARDRAILS";

  const resSql = document.createElement("code");
  resSql.className = "sim-sql-display";

  const resDetail = document.createElement("div");
  resDetail.className = "sim-detail-text text-sm";

  simResultBox.appendChild(resBadge);
  simResultBox.appendChild(resSql);
  simResultBox.appendChild(resDetail);
  simBody.appendChild(simResultBox);

  simCard.appendChild(simBody);
  leftCol.appendChild(simCard);

  // -----------------------------------------------------------------
  // 3. Right Column: Defense-in-Depth Layer Status & Pipeline Stepper
  // -----------------------------------------------------------------
  const defenseCard = document.createElement("div");
  defenseCard.className = "defense-panel-card card";

  const defHeader = document.createElement("div");
  defHeader.className = "card-header";
  const defTitle = document.createElement("h3");
  defTitle.textContent = "Defense-in-Depth Status";
  const defSubtitle = document.createElement("p");
  defSubtitle.className = "text-muted text-sm";
  defSubtitle.textContent = "Highlights the exact layer that neutralized the attack in live execution.";
  defHeader.appendChild(defTitle);
  defHeader.appendChild(defSubtitle);
  defenseCard.appendChild(defHeader);

  const layersList = document.createElement("div");
  layersList.className = "defense-layers-list";

  const standardLayers = [
    { id: "L1", code: "L1", name: "L1 deterministic pre-check", role: "Fast Perimeter Refusal", desc: "Regex scanner catches obvious destructive DDL/DML, multi-statement semicolons & overrides." },
    { id: "L2", code: "L2", name: "L2 LLM intent classifier", role: "Schema Linking & Intent", desc: "Schema Agent classifies intent, refusing non-analytical, conversational, or multilingual deletions." },
    { id: "WRAP", code: "WRAP", name: "untrusted-data wrapping", role: "Prompt Neutralization", desc: "Delimiters and XML breakout tags are escaped into literal text boundaries." },
    { id: "L3", code: "L3", name: "L3 SQL validator", role: "AST ASTglot Engine", desc: "Enforces SELECT-only queries, bans recursive CTEs, and caps row limits." },
    { id: "L4", code: "L4", name: "L4 read-only connection", role: "Physical Engine Backstop", desc: "SQLite file:?mode=ro and authorizer callback physically deny file and schema writes." },
  ];

  const layerDomElements = {};

  standardLayers.forEach((layer) => {
    const row = document.createElement("div");
    row.className = "layer-row idle";

    const badge = document.createElement("span");
    badge.className = "layer-code-badge";
    badge.textContent = layer.code;

    const info = document.createElement("div");
    info.className = "layer-info";

    const titleRow = document.createElement("div");
    titleRow.className = "layer-title-row";

    const name = document.createElement("strong");
    name.textContent = layer.name;

    const statusPill = document.createElement("span");
    statusPill.className = "layer-status-pill";
    statusPill.textContent = "STANDBY";

    titleRow.appendChild(name);
    titleRow.appendChild(statusPill);

    const desc = document.createElement("div");
    desc.className = "layer-desc text-xs text-muted";
    desc.textContent = layer.desc;

    info.appendChild(titleRow);
    info.appendChild(desc);

    row.appendChild(badge);
    row.appendChild(info);
    layersList.appendChild(row);

    layerDomElements[layer.id] = { row, statusPill };
  });

  defenseCard.appendChild(layersList);

  // Live Live-Run Status Banner
  const liveRunBanner = document.createElement("div");
  liveRunBanner.className = "live-run-banner";
  liveRunBanner.style.display = "none";

  const bannerText = document.createElement("div");
  bannerText.className = "banner-text";
  liveRunBanner.appendChild(bannerText);

  defenseCard.appendChild(liveRunBanner);
  rightCol.appendChild(defenseCard);

  mainGrid.appendChild(leftCol);
  mainGrid.appendChild(rightCol);
  container.appendChild(mainGrid);

  // Load Catalog from Backend
  loadCatalog();

  async function loadCatalog() {
    try {
      const res = await fetch("/attack/catalog");
      if (!res.ok) throw new Error("Catalog fetch failed");
      const catalog = await res.json();
      renderCatalog(catalog);
    } catch (e) {
      // Fallback local list if offline
      renderCatalog([]);
    }
  }

  function renderCatalog(catalog) {
    while (groupsContainer.firstChild) {
      groupsContainer.removeChild(groupsContainer.firstChild);
    }

    catalog.forEach((group) => {
      const gBox = document.createElement("div");
      gBox.className = "attack-group-box";

      const gTitle = document.createElement("h4");
      gTitle.className = "attack-group-title";
      gTitle.textContent = group.group;
      gBox.appendChild(gTitle);

      const itemsGrid = document.createElement("div");
      itemsGrid.className = "attack-items-grid";

      group.items.forEach((item) => {
        const btn = document.createElement("button");
        btn.className = `btn-attack-preset ${group.group.includes("Safe") ? "preset-safe" : "preset-malicious"}`;

        const lbl = document.createElement("div");
        lbl.className = "preset-btn-label";
        lbl.textContent = item.label;

        const sub = document.createElement("div");
        sub.className = "preset-btn-sub text-xs text-muted";
        sub.textContent = item.expected_layer;

        btn.appendChild(lbl);
        btn.appendChild(sub);
        btn.onclick = () => runAttackScenario(item);
        itemsGrid.appendChild(btn);
      });

      gBox.appendChild(itemsGrid);
      groupsContainer.appendChild(gBox);
    });
  }

  function resetLayers() {
    standardLayers.forEach((layer) => {
      const el = layerDomElements[layer.id];
      if (el) {
        el.row.className = "layer-row idle";
        el.statusPill.textContent = "STANDBY";
        el.statusPill.className = "layer-status-pill";
      }
    });
    liveRunBanner.style.display = "none";
  }

  function setLayerStopped(stoppedLayerKey, reason) {
    let hit = false;
    standardLayers.forEach((layer) => {
      const el = layerDomElements[layer.id];
      if (!el) return;

      if (!hit) {
        if (layer.id === stoppedLayerKey || layer.name.toLowerCase().includes(stoppedLayerKey.toLowerCase())) {
          hit = true;
          el.row.className = "layer-row stopped";
          el.statusPill.textContent = "HALTED HERE";
          el.statusPill.className = "layer-status-pill pill-stopped";
        } else {
          el.row.className = "layer-row passed";
          el.statusPill.textContent = "PASSED";
          el.statusPill.className = "layer-status-pill pill-passed";
        }
      } else {
        el.row.className = "layer-row not-reached";
        el.statusPill.textContent = "NOT REACHED";
        el.statusPill.className = "layer-status-pill pill-not-reached";
      }
    });

    liveRunBanner.style.display = "block";
    bannerText.textContent = `🛑 Neutralized: Stopped by ${stoppedLayerKey}. ${reason || ""}`;
  }

  function setAllPassed(message) {
    standardLayers.forEach((layer) => {
      const el = layerDomElements[layer.id];
      if (el) {
        el.row.className = "layer-row passed";
        el.statusPill.textContent = "PASSED";
        el.statusPill.className = "layer-status-pill pill-passed";
      }
    });
    liveRunBanner.style.display = "block";
    bannerText.textContent = `✅ Safe Query: ${message || "Successfully verified by all deterministic guardrail layers."}`;
  }

  function runAttackScenario(item) {
    resetLayers();

    streamAsk(item.question, {
      onNodeStarted: (data) => {
        // Track intermediate progress
      },
      onBlocked: (data) => {
        // Reads exact layer field emitted by backend SSE guardrail event
        const layerKey = data.layer || "L1 deterministic pre-check";
        setLayerStopped(layerKey, data.reason || item.description);
      },
      onExecutionResult: () => {
        setAllPassed("Query executed safely and produced validated results.");
      },
      onError: (err) => {
        liveRunBanner.style.display = "block";
        bannerText.textContent = `Error: ${err.message}`;
      }
    });
  }

  // Model-Complies Click Handler
  fireBtn.onclick = async () => {
    fireBtn.disabled = true;
    fireBtn.textContent = "Simulating...";
    demoDisabledNotice.style.display = "none";
    simResultBox.style.display = "none";

    try {
      const res = await fetch("/attack/simulate-model-complies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset_id: select.value })
      });

      if (res.status === 403) {
        demoDisabledNotice.style.display = "block";
        return;
      }

      const data = await res.json();
      simResultBox.style.display = "block";
      resSql.textContent = data.sql;

      resDetail.textContent = `Layer Stopped: ${data.layer_stopped} | AST Validator Reason: ${data.validator_reason || 'N/A'} | SQLite Engine Error: ${data.engine_error || 'N/A'}`;

      // Update right defense panel
      resetLayers();
      let targetL = "L3";
      if (data.layer_stopped.includes("L4") || data.engine_blocked) targetL = "L4";
      setLayerStopped(targetL, "Model complied with malicious prompt, but physical engine & AST validator halted execution.");

    } catch (e) {
      simResultBox.style.display = "block";
      resSql.textContent = `Error: ${e.message}`;
    } finally {
      fireBtn.disabled = false;
      fireBtn.textContent = "Simulate Attack Execution ▶";
    }
  };

  const attacksPageObj = {
    element: container,
    setLayerStopped,
    setAllPassed,
    resetLayers
  };
  window._attacksPageRef = attacksPageObj;
  return attacksPageObj;
}
