/**
 * ui/js/api.js - QueryPilot REST & SSE Streaming Client
 * Safe, robust, no innerHTML usage anywhere.
 */

export class QueryPilotAPI {
  constructor() {
    this.currentAbortController = null;
  }

  /**
   * Get server health and active LLM provider/model metadata
   */
  async getHealth() {
    const res = await fetch("/health");
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Get database schema metadata
   */
  async getSchema() {
    const res = await fetch("/schema");
    if (!res.ok) throw new Error(`Schema check failed: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Get recent execution traces
   */
  async getTraces(limit = 20) {
    const res = await fetch(`/traces?limit=${limit}`);
    if (!res.ok) throw new Error(`Traces fetch failed: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Get a specific trace by run_id
   */
  async getTraceById(runId) {
    const res = await fetch(`/traces/${encodeURIComponent(runId)}`);
    if (!res.ok) throw new Error(`Trace fetch failed: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Submit natural language query and stream execution via Server-Sent Events
   */
  async streamAsk(question, { onEvent, onError, onComplete }) {
    this.abortCurrent();
    this.currentAbortController = new AbortController();

    try {
      const response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: this.currentAbortController.signal,
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Server returned ${response.status}: ${errText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop(); // keep remainder

        for (const block of lines) {
          if (!block.trim()) continue;
          const parsed = this._parseSSEBlock(block);
          if (parsed && onEvent) {
            onEvent(parsed.event, parsed.data);
          }
        }
      }

      if (buffer.trim()) {
        const parsed = this._parseSSEBlock(buffer);
        if (parsed && onEvent) onEvent(parsed.event, parsed.data);
      }

      if (onComplete) onComplete();
    } catch (err) {
      if (err.name === "AbortError") {
        if (onEvent) onEvent("client_aborted", { message: "Query cancelled by user." });
      } else {
        if (onError) onError(err);
      }
    } finally {
      this.currentAbortController = null;
    }
  }

  /**
   * Resume an interrupted LangGraph state (HITL Approval / Clarification)
   */
  async streamResume(threadId, responsePayload, { onEvent, onError, onComplete }) {
    this.abortCurrent();
    this.currentAbortController = new AbortController();

    try {
      const response = await fetch("/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: threadId,
          response: responsePayload,
        }),
        signal: this.currentAbortController.signal,
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Resume returned ${response.status}: ${errText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();

        for (const block of lines) {
          if (!block.trim()) continue;
          const parsed = this._parseSSEBlock(block);
          if (parsed && onEvent) onEvent(parsed.event, parsed.data);
        }
      }

      if (buffer.trim()) {
        const parsed = this._parseSSEBlock(buffer);
        if (parsed && onEvent) onEvent(parsed.event, parsed.data);
      }

      if (onComplete) onComplete();
    } catch (err) {
      if (err.name === "AbortError") {
        if (onEvent) onEvent("client_aborted", { message: "Resume cancelled by user." });
      } else {
        if (onError) onError(err);
      }
    } finally {
      this.currentAbortController = null;
    }
  }

  /**
   * Abort active streaming fetch
   */
  abortCurrent() {
    if (this.currentAbortController) {
      this.currentAbortController.abort();
      this.currentAbortController = null;
    }
  }

  _parseSSEBlock(block) {
    let eventName = "message";
    let dataStr = "";

    const lines = block.split("\n");
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataStr = line.slice(5).trim();
      }
    }

    if (!dataStr) return null;

    try {
      return { event: eventName, data: JSON.parse(dataStr) };
    } catch (e) {
      return { event: eventName, data: { raw: dataStr } };
    }
  }
}

export const api = new QueryPilotAPI();

export async function fetchHealth() {
  return await api.getHealth();
}

export async function fetchTraces(limit = 20) {
  return await api.getTraces(limit);
}

export async function fetchSchema() {
  return await api.getSchema();
}

export function streamAsk(question, callbacks) {
  return api.streamAsk(question, {
    onEvent: (event, data) => {
      if (event === "run_started" && callbacks.onRunStarted) callbacks.onRunStarted(data);
      else if (event === "node_started" && callbacks.onNodeStarted) callbacks.onNodeStarted(data);
      else if (event === "node_finished" && callbacks.onNodeFinished) callbacks.onNodeFinished(data);
      else if (event === "sql_generated" && callbacks.onSqlGenerated) callbacks.onSqlGenerated(data);
      else if (event === "validation_result" && callbacks.onValidationResult) callbacks.onValidationResult(data);
      else if (event === "execution_result" && callbacks.onExecutionResult) callbacks.onExecutionResult(data);
      else if (event === "explanation_chunk" && callbacks.onExplanationChunk) callbacks.onExplanationChunk(data);
      else if (event === "explanation_finished" && callbacks.onExplanationFinished) callbacks.onExplanationFinished(data);
      else if (event === "blocked" && callbacks.onBlocked) callbacks.onBlocked(data);
      else if (event === "needs_input" && callbacks.onNeedsInput) callbacks.onNeedsInput(data);
    },
    onError: callbacks.onError,
    onComplete: callbacks.onRunFinished
  });
}

export function streamResume(threadId, userInput, callbacks) {
  return api.streamResume(threadId, userInput, {
    onEvent: (event, data) => {
      if (event === "node_started" && callbacks.onNodeStarted) callbacks.onNodeStarted(data);
      else if (event === "node_finished" && callbacks.onNodeFinished) callbacks.onNodeFinished(data);
      else if (event === "sql_generated" && callbacks.onSqlGenerated) callbacks.onSqlGenerated(data);
      else if (event === "execution_result" && callbacks.onExecutionResult) callbacks.onExecutionResult(data);
      else if (event === "explanation_chunk" && callbacks.onExplanationChunk) callbacks.onExplanationChunk(data);
      else if (event === "explanation_finished" && callbacks.onExplanationFinished) callbacks.onExplanationFinished(data);
    },
    onError: callbacks.onError,
    onComplete: callbacks.onRunFinished
  });
}
