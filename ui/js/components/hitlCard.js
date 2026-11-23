/**
 * HitlCard Component
 * Displays human-in-the-loop approvals (e.g. Cartesian join detection)
 * or Schema clarification prompts.
 * Strictly avoids innerHTML for XSS safety.
 */

export function createHitlCard({ onApprove, onReject, onSubmitClarification } = {}) {
  const container = document.createElement('div');
  container.className = 'hitl-container';
  container.style.display = 'none';

  const card = document.createElement('div');
  card.className = 'hitl-card';

  const header = document.createElement('div');
  header.className = 'hitl-header';

  const badge = document.createElement('span');
  badge.className = 'hitl-badge';
  badge.textContent = 'Action Required';

  const title = document.createElement('h3');
  title.className = 'hitl-title';
  title.textContent = 'Human Approval Required';

  header.appendChild(badge);
  header.appendChild(title);

  const messageBox = document.createElement('div');
  messageBox.className = 'hitl-message';

  const actions = document.createElement('div');
  actions.className = 'hitl-actions';

  card.appendChild(header);
  card.appendChild(messageBox);
  card.appendChild(actions);
  container.appendChild(card);

  /**
   * Show HITL approval dialog (Cartesian join, risky query, etc.)
   */
  function showApproval({ titleText, message, details, onConfirm, onCancel }) {
    container.style.display = 'block';
    title.textContent = titleText || 'Approval Required';
    badge.textContent = 'Safety Gate';
    badge.className = 'hitl-badge badge-warning';

    // Clear messageBox
    while (messageBox.firstChild) {
      messageBox.removeChild(messageBox.firstChild);
    }

    const p = document.createElement('p');
    p.textContent = message;
    messageBox.appendChild(p);

    if (details) {
      const pre = document.createElement('pre');
      pre.className = 'hitl-details-pre';
      pre.textContent = typeof details === 'string' ? details : JSON.stringify(details, null, 2);
      messageBox.appendChild(pre);
    }

    // Clear actions
    while (actions.firstChild) {
      actions.removeChild(actions.firstChild);
    }

    const btnApprove = document.createElement('button');
    btnApprove.className = 'btn btn-primary';
    btnApprove.textContent = 'Approve & Continue';
    btnApprove.onclick = () => {
      container.style.display = 'none';
      if (onConfirm) onConfirm();
      if (onApprove) onApprove();
    };

    const btnReject = document.createElement('button');
    btnReject.className = 'btn btn-secondary';
    btnReject.textContent = 'Reject Query';
    btnReject.onclick = () => {
      container.style.display = 'none';
      if (onCancel) onCancel();
      if (onReject) onReject();
    };

    actions.appendChild(btnApprove);
    actions.appendChild(btnReject);
  }

  /**
   * Show Clarification dialog for ambiguous questions
   */
  function showClarification({ question, context, onSubmit }) {
    container.style.display = 'block';
    title.textContent = 'Clarification Needed';
    badge.textContent = 'Schema Agent';
    badge.className = 'hitl-badge badge-info';

    while (messageBox.firstChild) {
      messageBox.removeChild(messageBox.firstChild);
    }

    const p = document.createElement('p');
    p.textContent = question || 'Please clarify your question so QueryPilot can select the appropriate tables and filters:';
    messageBox.appendChild(p);

    if (context) {
      const sub = document.createElement('p');
      sub.className = 'hitl-context-text text-muted';
      sub.textContent = context;
      messageBox.appendChild(sub);
    }

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'input-field hitl-input';
    input.placeholder = 'e.g. Include canceled orders or completed only?';
    messageBox.appendChild(input);

    while (actions.firstChild) {
      actions.removeChild(actions.firstChild);
    }

    const btnSend = document.createElement('button');
    btnSend.className = 'btn btn-primary';
    btnSend.textContent = 'Submit Clarification';
    btnSend.onclick = () => {
      const val = input.value.trim();
      if (!val) return;
      container.style.display = 'none';
      if (onSubmit) onSubmit(val);
      if (onSubmitClarification) onSubmitClarification(val);
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        btnSend.click();
      }
    });

    actions.appendChild(btnSend);
  }

  function hide() {
    container.style.display = 'none';
  }

  return {
    element: container,
    showApproval,
    showClarification,
    hide
  };
}
