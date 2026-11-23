/**
 * ui/js/components/resultsTabs.js - Tabbed Results Viewer
 * Renders Answer, SQL (with validator diff marker), Sortable Data Table (CSV download), and Chart.js.
 * Pure DOM, zero innerHTML.
 */

export class ResultsTabsComponent {
  constructor(container) {
    this.container = container;
    this.activeTab = "answer";
    this.chartInstance = null;
    this.tableSort = { col: null, asc: true };
    this.lastRows = [];
    this.lastCols = [];
    this._renderShell();
  }

  _renderShell() {
    this.container.textContent = "";

    const wrapper = document.createElement("div");
    wrapper.className = "results-card";

    // Tab Header Bar
    const tabsBar = document.createElement("div");
    tabsBar.className = "results-tabs-bar";

    const tabsList = document.createElement("ul");
    tabsList.className = "tabs-list";

    const tabDefs = [
      { id: "answer", label: "💬 Natural Language Answer" },
      { id: "sql", label: "⚡ Generated SQL" },
      { id: "data", label: "📊 Execution Data" },
      { id: "chart", label: "📈 Visualization" },
    ];

    this.tabButtons = {};
    for (const def of tabDefs) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.className = `tab-btn ${def.id === this.activeTab ? "active" : ""}`;
      btn.textContent = def.label;
      btn.addEventListener("click", () => this.switchTab(def.id));
      li.appendChild(btn);
      tabsList.appendChild(li);
      this.tabButtons[def.id] = btn;
    }
    tabsBar.appendChild(tabsList);
    wrapper.appendChild(tabsBar);

    // Tab 1: Answer Content
    const answerTab = document.createElement("div");
    answerTab.className = "tab-content active";
    answerTab.id = "tab-content-answer";

    const streamLabel = document.createElement("div");
    streamLabel.className = "stream-label";
    streamLabel.textContent = "streamed from a validated response";
    answerTab.appendChild(streamLabel);

    const streamBox = document.createElement("div");
    streamBox.className = "answer-stream-box";
    streamBox.textContent = "Run a natural language question above to view generated insights.";
    answerTab.appendChild(streamBox);

    const keyPointsUl = document.createElement("ul");
    keyPointsUl.className = "key-points-list";
    answerTab.appendChild(keyPointsUl);

    wrapper.appendChild(answerTab);

    // Tab 2: SQL Content
    const sqlTab = document.createElement("div");
    sqlTab.className = "tab-content";
    sqlTab.id = "tab-content-sql";

    const diffBadge = document.createElement("div");
    diffBadge.className = "sql-diff-badge";
    diffBadge.style.display = "none";
    diffBadge.textContent = "⚙️ Rewritten by SQLglot AST Validator (LIMIT added / sanitized)";
    sqlTab.appendChild(diffBadge);

    const sqlWrapper = document.createElement("div");
    sqlWrapper.className = "sql-wrapper";

    const actions = document.createElement("div");
    actions.className = "sql-actions";

    const copyBtn = document.createElement("button");
    copyBtn.className = "btn btn-secondary";
    copyBtn.style.padding = "4px 8px";
    copyBtn.style.fontSize = "11px";
    copyBtn.textContent = "Copy SQL";
    copyBtn.addEventListener("click", () => {
      const code = sqlCode.textContent;
      if (code) {
        navigator.clipboard.writeText(code).then(() => {
          copyBtn.textContent = "Copied!";
          setTimeout(() => { copyBtn.textContent = "Copy SQL"; }, 2000);
        });
      }
    });
    actions.appendChild(copyBtn);
    sqlWrapper.appendChild(actions);

    const sqlCode = document.createElement("code");
    sqlCode.className = "sql-code";
    sqlCode.textContent = "-- SQL query will appear here upon generation";
    sqlWrapper.appendChild(sqlCode);
    sqlTab.appendChild(sqlWrapper);
    wrapper.appendChild(sqlTab);

    // Tab 3: Data Table Content
    const dataTab = document.createElement("div");
    dataTab.className = "tab-content";
    dataTab.id = "tab-content-data";

    const metaBar = document.createElement("div");
    metaBar.className = "table-meta-bar";

    const rowCountSpan = document.createElement("span");
    rowCountSpan.textContent = "0 rows returned";
    metaBar.appendChild(rowCountSpan);

    const csvBtn = document.createElement("button");
    csvBtn.className = "btn btn-secondary";
    csvBtn.style.padding = "4px 8px";
    csvBtn.style.fontSize = "11px";
    csvBtn.textContent = "Download CSV";
    csvBtn.addEventListener("click", () => this._downloadCSV());
    metaBar.appendChild(csvBtn);
    dataTab.appendChild(metaBar);

    const tableContainer = document.createElement("div");
    tableContainer.className = "data-table-container";

    const table = document.createElement("table");
    table.className = "data-table";
    tableContainer.appendChild(table);
    dataTab.appendChild(tableContainer);
    wrapper.appendChild(dataTab);

    // Tab 4: Chart Content
    const chartTab = document.createElement("div");
    chartTab.className = "tab-content";
    chartTab.id = "tab-content-chart";

    const chartWrap = document.createElement("div");
    chartWrap.className = "chart-container";

    const canvas = document.createElement("canvas");
    canvas.id = "querypilot-chart-canvas";
    chartWrap.appendChild(canvas);
    chartTab.appendChild(chartWrap);
    wrapper.appendChild(chartTab);

    this.container.appendChild(wrapper);

    this.dom = {
      wrapper,
      streamBox,
      streamLabel,
      keyPointsUl,
      sqlCode,
      diffBadge,
      rowCountSpan,
      table,
      canvas,
      tabs: {
        answer: answerTab,
        sql: sqlTab,
        data: dataTab,
        chart: chartTab,
      },
    };
  }

  switchTab(tabId) {
    this.activeTab = tabId;
    for (const [id, btn] of Object.entries(this.tabButtons)) {
      btn.className = `tab-btn ${id === tabId ? "active" : ""}`;
    }
    for (const [id, el] of Object.entries(this.dom.tabs)) {
      el.className = `tab-content ${id === tabId ? "active" : ""}`;
    }
    if (tabId === "chart") {
      if (this.chartInstance) {
        this.chartInstance.resize();
      } else if (this.lastCols.length > 0 && this.lastRows.length > 0) {
        this._renderChart(null, this.lastCols, this.lastRows);
      }
    }
  }

  reset() {
    this.dom.streamBox.textContent = "Run a natural language question above to view generated insights.";
    while (this.dom.keyPointsUl.firstChild) {
      this.dom.keyPointsUl.removeChild(this.dom.keyPointsUl.firstChild);
    }
    this.dom.sqlCode.textContent = "-- SQL query will appear here upon generation";
    this.dom.diffBadge.style.display = "none";
    this.dom.rowCountSpan.textContent = "0 rows returned";
    while (this.dom.table.firstChild) {
      this.dom.table.removeChild(this.dom.table.firstChild);
    }
    if (this.chartInstance) {
      this.chartInstance.destroy();
      this.chartInstance = null;
    }
    this.lastRows = [];
    this.lastCols = [];
    this.switchTab("answer");
  }

  setSql(sql, originalSql) {
    if (this.dom.sqlCode) {
      this.dom.sqlCode.textContent = sql || "";
    }
    if (this.dom.diffBadge) {
      this.dom.diffBadge.style.display = (originalSql && originalSql !== sql) ? "inline-flex" : "none";
    }
  }

  setData(cols, rows, chartSuggestion = null) {
    this.lastCols = cols || [];
    this.lastRows = rows || [];
    if (this.dom.rowCountSpan) {
      this.dom.rowCountSpan.textContent = `${this.lastRows.length} rows returned`;
    }
    this._renderTable(this.lastCols, this.lastRows);
    const suggestion = chartSuggestion || { chart_type: "bar", x_column: cols[0], y_column: cols.length > 1 ? cols[1] : cols[0] };
    this._renderChart(suggestion, this.lastCols, this.lastRows);
  }

  appendExplanationChunk(chunk) {
    if (this.dom.streamBox) {
      this.dom.streamBox.textContent += chunk;
    }
  }

  finishExplanation(exp) {
    if (!exp) return;
    if (exp.summary && this.dom.streamBox) {
      this.dom.streamBox.textContent = exp.summary;
    }
    if (this.dom.keyPointsUl && Array.isArray(exp.key_points)) {
      this.dom.keyPointsUl.textContent = "";
      for (const pt of exp.key_points) {
        const li = document.createElement("li");
        li.textContent = pt;
        this.dom.keyPointsUl.appendChild(li);
      }
    }
    if (exp.chart_suggestion) {
      this._renderChart(exp.chart_suggestion, this.lastCols, this.lastRows);
    }
  }

  update(runState) {
    // 1. Answer Streaming
    if (runState.streamedText) {
      this.dom.streamBox.textContent = runState.streamedText;
    } else if (runState.explanation && runState.explanation.summary) {
      this.dom.streamBox.textContent = runState.explanation.summary;
    }

    // Key points
    this.dom.keyPointsUl.textContent = "";
    if (runState.explanation && Array.isArray(runState.explanation.key_points)) {
      for (const pt of runState.explanation.key_points) {
        const li = document.createElement("li");
        li.textContent = pt;
        this.dom.keyPointsUl.appendChild(li);
      }
    }

    // 2. SQL Display & Diff marker
    if (runState.sql) {
      this.dom.sqlCode.textContent = runState.sql;
    }
    if (runState.validation && runState.validation.rewritten_sql && runState.validation.rewritten_sql !== runState.sql) {
      this.dom.diffBadge.style.display = "inline-flex";
    } else {
      this.dom.diffBadge.style.display = "none";
    }

    // 3. Execution Data Table
    if (runState.executionResult && Array.isArray(runState.executionResult.rows)) {
      this.lastRows = runState.executionResult.rows;
      this.lastCols = runState.executionResult.columns || (this.lastRows.length > 0 ? Object.keys(this.lastRows[0]) : []);
      this.dom.rowCountSpan.textContent = `${this.lastRows.length} rows returned ${runState.executionResult.truncated ? "(Truncated at row limit)" : ""}`;
      this._renderTable(this.lastCols, this.lastRows);
      this._renderChart(runState.explanation?.chart_suggestion, this.lastCols, this.lastRows);
    }
  }

  _renderTable(cols, rows) {
    const table = this.dom.table;
    table.textContent = "";

    if (!cols || cols.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.textContent = "No data returned";
      tr.appendChild(td);
      table.appendChild(tr);
      return;
    }

    const thead = document.createElement("thead");
    const headerTr = document.createElement("tr");
    for (const col of cols) {
      const th = document.createElement("th");
      th.textContent = col;
      th.addEventListener("click", () => this._sortTable(col));
      headerTr.appendChild(th);
    }
    thead.appendChild(headerTr);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const row of rows) {
      const tr = document.createElement("tr");
      for (const col of cols) {
        const td = document.createElement("td");
        const val = Array.isArray(row) ? row[cols.indexOf(col)] : row[col];
        td.textContent = val !== null && val !== undefined ? String(val) : "NULL";
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
  }

  _sortTable(col) {
    if (this.tableSort.col === col) {
      this.tableSort.asc = !this.tableSort.asc;
    } else {
      this.tableSort.col = col;
      this.tableSort.asc = true;
    }

    const sorted = [...this.lastRows].sort((a, b) => {
      const va = a[col];
      const vb = b[col];
      if (va === vb) return 0;
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      return this.tableSort.asc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });

    this._renderTable(this.lastCols, sorted);
  }

  _downloadCSV() {
    if (!this.lastRows || this.lastRows.length === 0) return;
    const header = this.lastCols.join(",");
    const rows = this.lastRows.map(r => this.lastCols.map(c => `"${String(r[c] || "").replace(/"/g, '""')}"`).join(","));
    const csvContent = "data:text/csv;charset=utf-8," + [header, ...rows].join("\n");
    const link = document.createElement("a");
    link.setAttribute("href", encodeURI(csvContent));
    link.setAttribute("download", "querypilot_results.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  _renderChart(suggestion, cols, rows) {
    if (!window.Chart || !rows || rows.length === 0 || !cols || cols.length === 0) return;

    if (this.chartInstance) {
      this.chartInstance.destroy();
      this.chartInstance = null;
    }

    const xCol = suggestion?.x_column || cols[0];
    const yCol = suggestion?.y_column || cols.find(c => {
      const v = Array.isArray(rows[0]) ? rows[0][cols.indexOf(c)] : rows[0][c];
      return typeof v === "number";
    }) || (cols.length > 1 ? cols[1] : cols[0]);

    const xIdx = cols.indexOf(xCol);
    const yIdx = cols.indexOf(yCol);

    const labels = rows.map(r => String(Array.isArray(r) ? r[xIdx] : (r[xCol] !== undefined ? r[xCol] : "")));
    const values = rows.map(r => Number(Array.isArray(r) ? r[yIdx] : r[yCol]) || 0);

    const canvas = this.dom.canvas;
    if (!canvas) return;
    canvas.width = canvas.parentElement?.clientWidth || 700;
    canvas.height = 320;
    const ctx = canvas.getContext("2d");

    this.chartInstance = new window.Chart(ctx, {
      type: suggestion?.chart_type === "line" ? "line" : "bar",
      data: {
        labels: labels,
        datasets: [{
          label: yCol,
          data: values,
          backgroundColor: "rgba(56, 189, 248, 0.4)",
          borderColor: "#38bdf8",
          borderWidth: 2,
          borderRadius: 4,
        }]
      },
      options: {
        animation: false,
        responsive: false,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: "#94a3b8" } },
        },
        scales: {
          x: { ticks: { color: "#64748b" }, grid: { color: "rgba(255,255,255,0.05)" } },
          y: { ticks: { color: "#64748b" }, grid: { color: "rgba(255,255,255,0.05)" } },
        }
      }
    });
  }
}

export function createResultsTabs() {
  const container = document.createElement("div");
  container.className = "results-tabs-wrapper";
  const component = new ResultsTabsComponent(container);

  return {
    element: container,
    component,
    switchTab: (id) => component.switchTab(id),
    appendExplanation: (chunk) => component.appendExplanationChunk(chunk),
    finishExplanation: (exp) => component.finishExplanation(exp),
    setSql: (sql, originalSql) => component.setSql(sql, originalSql),
    setData: (cols, rows) => component.setData(cols, rows),
    reset: () => component.reset()
  };
}
