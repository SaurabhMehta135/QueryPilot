/**
 * ui/js/components/stepper.js - Pipeline Stepper Component
 * Renders the 5-node pipeline with live states, tokens, retry loops, and guardrail shields.
 * Pure DOM, zero innerHTML.
 */

export class StepperComponent {
  constructor(container) {
    this.container = container;
    this.nodesDef = [
      { id: "schema_node", label: "Schema Agent", icon: "1" },
      { id: "writer_node", label: "SQL Writer", icon: "2" },
      { id: "validator_node", label: "Safety Validator", icon: "3" },
      { id: "executor_node", label: "Executor (MCP)", icon: "4" },
      { id: "explainer_node", label: "Explainer Agent", icon: "5" },
    ];
    this.elements = {};
    this._renderShell();
  }

  _renderShell() {
    this.container.textContent = "";

    const wrapper = document.createElement("div");
    wrapper.className = "pipeline-stepper";

    const header = document.createElement("div");
    header.className = "stepper-header";

    const title = document.createElement("span");
    title.className = "stepper-title";
    title.textContent = "Multi-Agent Execution Pipeline";
    header.appendChild(title);

    const liveBadge = document.createElement("span");
    liveBadge.className = "status-badge";
    liveBadge.id = "pipeline-status-badge";
    liveBadge.textContent = "IDLE";
    header.appendChild(liveBadge);

    wrapper.appendChild(header);

    const track = document.createElement("div");
    track.className = "stepper-track";

    const line = document.createElement("div");
    line.className = "stepper-line";
    track.appendChild(line);

    for (const node of this.nodesDef) {
      const nodeEl = document.createElement("div");
      nodeEl.className = "step-node idle";
      nodeEl.setAttribute("data-node-id", node.id);

      // Guardrail Shield
      const shield = document.createElement("span");
      shield.className = "guardrail-shield-badge";
      shield.style.display = "none";
      shield.textContent = "🛡️";
      nodeEl.appendChild(shield);

      // Retry Loop Badge for writer
      if (node.id === "writer_node") {
        const retryBadge = document.createElement("span");
        retryBadge.className = "retry-loop-badge";
        retryBadge.textContent = "↻ Retry 1/3";
        retryBadge.style.display = "none";
        nodeEl.appendChild(retryBadge);
        this.elements.retryBadge = retryBadge;
      }

      const iconWrap = document.createElement("div");
      iconWrap.className = "node-icon-wrapper";
      iconWrap.textContent = node.icon;
      nodeEl.appendChild(iconWrap);

      const label = document.createElement("div");
      label.className = "node-label";
      label.textContent = node.label;
      nodeEl.appendChild(label);

      const meta = document.createElement("div");
      meta.className = "node-meta";
      meta.textContent = "-";
      nodeEl.appendChild(meta);

      track.appendChild(nodeEl);

      this.elements[node.id] = {
        root: nodeEl,
        icon: iconWrap,
        meta: meta,
        shield: shield,
      };
    }

    const loopBack = document.createElement("div");
    loopBack.className = "retry-loop-back";
    loopBack.textContent = "↺ repair loop active";
    loopBack.style.display = "none";
    track.appendChild(loopBack);
    this.elements.loopBack = loopBack;

    wrapper.appendChild(track);
    this.container.appendChild(wrapper);
  }

  setRetry(count) {
    if (this.elements.retryBadge) {
      if (count > 0) {
        this.elements.retryBadge.textContent = `↻ Retry ${count}/3`;
        this.elements.retryBadge.classList.add("active");
        this.elements.retryBadge.style.display = "inline-flex";
        if (this.elements.loopBack) this.elements.loopBack.style.display = "flex";
      } else {
        this.elements.retryBadge.classList.remove("active");
        this.elements.retryBadge.style.display = "none";
        if (this.elements.loopBack) this.elements.loopBack.style.display = "none";
      }
    }
  }

  reset() {
    this.setRetry(0);
    for (const def of this.nodesDef) {
      const el = this.elements[def.id];
      if (el) {
        el.root.className = "step-node idle";
        el.meta.textContent = "-";
        el.shield.style.display = "none";
      }
    }
  }

  update(runState) {
    const statusBadge = document.getElementById("pipeline-status-badge");
    if (statusBadge) {
      statusBadge.textContent = (runState.status || "IDLE").toUpperCase();
      statusBadge.className = `status-badge ${runState.status}`;
    }

    for (const def of this.nodesDef) {
      const nodeData = runState.nodes[def.id] || { status: "idle" };
      const el = this.elements[def.id];
      if (!el) continue;

      // Update state classes
      el.root.className = `step-node ${nodeData.status}`;

      // Update meta text safely
      const parts = [];
      if (nodeData.duration_ms !== null && nodeData.duration_ms !== undefined) {
        parts.push(`${Math.round(nodeData.duration_ms)}ms`);
      }
      if (nodeData.tokens) {
        parts.push(`${nodeData.tokens} tok`);
      }
      if (nodeData.rowCount !== undefined && def.id === "executor_node" && nodeData.status === "done") {
        parts.push(`${nodeData.rowCount} rows`);
      }
      el.meta.textContent = parts.length > 0 ? parts.join(" • ") : "-";

      // Shield badge
      if (def.id === "schema_node" && runState.guardrailEvents.some(e => e.includes("L1") || e.includes("intent"))) {
        el.shield.style.display = "flex";
      } else if (def.id === "validator_node" && runState.validation) {
        el.shield.style.display = "flex";
      } else {
        el.shield.style.display = "none";
      }
    }

    // Writer retry loop badge
    if (this.elements.retryBadge) {
      const retryCount = runState.nodes.writer_node?.retryCount || 0;
      if (retryCount > 0) {
        this.elements.retryBadge.textContent = `↻ Retry ${retryCount}/2`;
        this.elements.retryBadge.classList.add("active");
      } else {
        this.elements.retryBadge.classList.remove("active");
      }
    }
  }
}

export function createStepper() {
  const container = document.createElement("div");
  container.className = "stepper-container-wrapper";
  const component = new StepperComponent(container);

  return {
    element: container,
    component,
    setNodeStatus: (nodeId, status, duration = null) => {
      // Map standard node IDs to component format if needed
      const mappedId = nodeId.endsWith("_node") ? nodeId : `${nodeId}_node`;
      const currentRunState = {
        status: status === "running" ? "running" : "idle",
        nodes: {
          [mappedId]: {
            status: status === "running" ? "running" : (status === "success" ? "done" : "error"),
            duration_ms: duration
          }
        },
        guardrailEvents: []
      };
      component.update(currentRunState);
    },
    setRetry: (count) => component.setRetry(count),
    reset: () => component.reset()
  };
}
