/* Optional local evidence assistant. Created by ChatGPT (OpenAI). */
(function (root) {
  'use strict';
  const ENDPOINT = 'http://127.0.0.1:8768';
  let accessToken = ''; // Page memory only; never localStorage, URLs or analytics.
  let connected = false;

  function passages(company, period, question) {
    const context = `${company.name}; CIK ${company.cik}; ${period.form}; period ${period.label} ended ${period.end}; filed ${period.filed}.`;
    const stop = new Set(['the', 'what', 'was', 'were', 'are', 'and', 'for', 'from', 'does', 'this', 'that', 'about']);
    const terms = [...new Set(question.toLowerCase().match(/[a-z]{3,}/g) || [])].filter((term) => !stop.has(term));
    const nodes = [...(period.nodes || []), ...((period.cash || {}).nodes || [])];
    const candidates = [];
    const add = (kind, text, url) => {
      const full = `${context}\n${kind}\n${text}`;
      // Whole passages only. Oversized evidence remains available through the filing link.
      if (full.length > 2400 || candidates.some((p) => p.text === full)) return;
      candidates.push({ text: full, url, score: terms.reduce((n, term) => n + (text.toLowerCase().includes(term) ? 1 : 0), 0) });
    };
    const head = period.headline || {};
    const facts = [['revenue', 'revenue'], ['oi', 'operating income'], ['ni', 'net income'], ['ocf', 'operating cash flow']]
      .filter(([key]) => Number.isFinite(head[key])).map(([key, label]) => `${label}: ${head[key]} USD.`);
    if (facts.length) add('Website summary fields; monetary values are USD in unscaled units. Derived values may differ from reported line items.',
      facts.join('\n'), period.doc_url);
    for (const node of nodes) {
      if (Number.isFinite(node.v)) add('Website chart value; monetary value is USD in unscaled units.',
        `${node.name}: ${node.v}. Source description: ${node.source || 'Website-derived chart value; verify the filing.'}`, period.doc_url);
      for (const note of node.notes || []) if (typeof note.text === 'string')
        add('Website filing excerpt; not independently verified as a complete footnote.',
          `${note.heading || node.name}\n${note.text}`, period.doc_url);
    }
    let remaining = 3600;
    return candidates.sort((a, b) => b.score - a.score).filter((p) => {
      if (p.text.length > remaining) return false;
      remaining -= p.text.length; return true;
    }).slice(0, 3).map((p, i) => ({ ...p, id: `S${i + 1}` }));
  }

  async function call(path, body) {
    const response = await fetch(ENDPOINT + path, {
      method: body ? 'POST' : 'GET', mode: 'cors', credentials: 'omit', cache: 'no-store',
      headers: { Authorization: 'Bearer ' + accessToken, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(body ? 120000 : 10000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Local service returned ${response.status}`);
    return result;
  }

  function mount(container, company, period) {
    if (typeof document === 'undefined') return;
    const panel = document.createElement('details');
    panel.className = 'section local-model';
    panel.innerHTML = `<summary>Ask local Qwen3-8B <span class="muted">Experimental</span></summary>
      <p>Uses the model running on this computer. The site does not host an 8B model. Answers are drafts: verify the linked evidence.</p>
      <div class="local-connect"><label>Local access token <input type="password" autocomplete="off" spellcheck="false" aria-label="Local access token"></label>
      <button class="btn" type="button" data-connect>Connect</button><button class="btn" type="button" data-disconnect>Disconnect</button></div>
      <p class="muted">Start the Windows companion on port 8768, then paste its local token. Allow local network access if your browser asks. The token stays in page memory. <a href="https://github.com/eurikamonica/filing-flows/tree/beta/windows-qwen3-8b-20261016/local-inference" target="_blank" rel="noopener">Companion setup</a></p>
      <form><label>Question about this period <textarea required maxlength="1000" rows="2" placeholder="What does the supplied evidence say about revenue?"></textarea></label>
      <button class="btn" type="submit">Ask using this period</button></form>
      <p role="status" aria-live="polite"></p><div class="local-answer"></div>
      <details class="local-evidence"><summary>Evidence sent to your computer</summary><div></div></details>`;
    container.appendChild(panel);
    const status = panel.querySelector('[role=status]');
    const token = panel.querySelector('input');
    const output = panel.querySelector('.local-answer');
    const evidenceView = panel.querySelector('.local-evidence div');
    panel.querySelector('[data-connect]').onclick = async () => {
      accessToken = token.value.trim(); token.value = '';
      connected = false;
      if (!accessToken) { status.textContent = 'Paste the token from the local companion first.'; return; }
      status.textContent = 'Connecting to this computer...';
      try {
        const health = await call('/health');
        if (health.model !== 'Qwen/Qwen3-8B') throw new Error('Unexpected local model');
        connected = true;
        status.textContent = `Connected to Qwen3-8B (${health.status}).`;
      } catch (error) {
        accessToken = '';
        status.textContent = `Could not connect. Check the companion, token and browser local network permission. ${error.message}`;
      }
    };
    panel.querySelector('[data-disconnect]').onclick = () => {
      accessToken = ''; connected = false; token.value = ''; status.textContent = 'Disconnected.';
    };
    panel.querySelector('form').onsubmit = async (event) => {
      event.preventDefault();
      if (!connected) { status.textContent = 'Connect to the local companion first.'; return; }
      const button = event.currentTarget.querySelector('button');
      const question = panel.querySelector('textarea').value.trim();
      const evidence = passages(company, period, question);
      output.replaceChildren(); evidenceView.replaceChildren();
      for (const item of evidence) {
        const paragraph = document.createElement('p');
        paragraph.textContent = `[${item.id}] ${item.text}`;
        evidenceView.appendChild(paragraph);
      }
      if (!evidence.length) { status.textContent = 'No complete evidence passage fits the local context budget.'; return; }
      button.disabled = true; status.textContent = 'Reading evidence locally...';
      try {
        const result = await call('/ask', { question, evidence: evidence.map(({ id, text }) => ({ id, text })) });
        if (!panel.isConnected) return;
        const paragraph = document.createElement('p');
        paragraph.textContent = result.insufficient_evidence ? 'The selected evidence does not support an answer.' : result.answer;
        output.appendChild(paragraph);
        for (const quotation of result.quotations || []) {
          const block = document.createElement('blockquote');
          block.textContent = `[${quotation.source_id}] ${quotation.quote}`;
          output.appendChild(block);
        }
        for (const id of result.source_ids || []) {
          const item = evidence.find((p) => p.id === id);
          try {
            const url = new URL(item.url);
            if (url.protocol !== 'https:' || url.hostname !== 'www.sec.gov') continue;
            const link = document.createElement('a');
            link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = `[${id}] Verify filing `;
            output.appendChild(link);
          } catch (_) { /* Missing filing URLs are never replaced by model-generated URLs. */ }
        }
        status.textContent = `Draft completed in ${result.timing.seconds.toFixed(1)}s. JSON and literal quotes checked; claim support and numerical accuracy require review.`;
      } catch (error) {
        if (panel.isConnected) status.textContent = `No accepted answer. ${error.message}`;
      } finally { button.disabled = false; }
    };
  }

  root.LocalFilingModel = { mount, passages };
  if (typeof module !== 'undefined') module.exports = { passages };
})(typeof globalThis !== 'undefined' ? globalThis : this);
