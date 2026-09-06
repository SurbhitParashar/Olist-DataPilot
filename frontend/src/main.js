import { Chart } from 'chart.js/auto';
import './style.css';

const app = document.querySelector('#app');
let currentPayload = null;
let chart;

app.innerHTML = `
  <header>
    <div><h1>Olist Sales Analytics</h1><p>Ask a plain-English question. The backend plans, queries, visualizes, and explains it.</p></div>
    <span class="pill">MCP + OpenRouter</span>
  </header>
  <main>
    <section class="search">
      <textarea id="query" rows="2" placeholder="Try: Show monthly revenue trend for 2017"></textarea>
      <button id="ask">Analyze</button>
      <div class="examples">
        <button data-q="Show monthly revenue trend for 2017">1. Monthly revenue trend</button>
        <button data-q="Which product categories generate the most revenue?">2. Top categories</button>
        <button data-q="Top 10 sellers by revenue in São Paulo">3. Top São Paulo sellers</button>
        <button data-q="Show review score distribution for electronics">4. Electronics reviews</button>
        <button data-q="Do sellers with faster delivery get better reviews?">5. Delivery vs reviews</button>
      </div>
    </section>

    <section id="status" class="status">Ready.</section>
    <section id="result" class="result hidden">
      <div class="result-head"><div><h2 id="title"></h2><p id="insight"></p></div><button id="pin">Pin to dashboard</button></div>
      <p id="justification" class="muted"></p>
      <div id="assumptions"></div><div id="warnings"></div>
      <div class="chart-wrap"><canvas id="chart"></canvas></div>
      <details><summary>Tool trace</summary><pre id="trace"></pre></details>
    </section>

    <section class="dashboard">
      <div class="dashboard-head"><h2>Pinned dashboard</h2><button id="refresh-all">Refresh all</button></div>
      <div id="pins"></div>
    </section>
  </main>
`;

const $ = (id) => document.getElementById(id);

async function ask(query) {
  $('status').textContent = 'Running agent…';
  $('result').classList.add('hidden');
  const res = await fetch('/api/ask', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({query}) });
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.detail || 'Request failed');
  currentPayload = payload;
  renderResult(payload);
  $('status').textContent = `Done via ${payload.agent_mode} agent.`;
}

function renderResult(p) {
  $('result').classList.remove('hidden');
  $('title').textContent = p.query;
  $('insight').textContent = p.insight || 'No insight was generated.';
  $('justification').textContent = `${p.chart_type}: ${p.chart_justification}`;
  $('assumptions').innerHTML = p.assumptions.map(x => `<div class="note">Assumption: ${escapeHtml(x)}</div>`).join('');
  $('warnings').innerHTML = p.warnings.map(x => `<div class="warning">${escapeHtml(x)}</div>`).join('');
  $('trace').textContent = JSON.stringify(p.tool_trace, null, 2);
  if (chart) chart.destroy();
  if (p.chart_type !== 'none') {
    chart = new Chart($('chart'), p.chart_config);
  } else {
    $('chart').replaceWith(Object.assign(document.createElement('div'), {className:'no-chart', textContent:'No chart for this query.'}));
  }
}

async function loadPins() {
  const pins = await (await fetch('/api/pins')).json();
  $('pins').innerHTML = pins.length ? pins.map(pinCard).join('') : '<p class="muted">Nothing pinned yet.</p>';
}

function pinCard(p) {
  return `<article class="pin-card"><div><strong>${escapeHtml(p.query)}</strong><div class="muted">Updated ${escapeHtml(p.updated_at)}</div></div><div><button data-refresh="${p.id}">Refresh</button><button data-delete="${p.id}">Remove</button></div></article>`;
}

function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }

$('ask').onclick = () => ask($('query').value.trim()).catch(e => $('status').textContent = e.message);
document.querySelectorAll('[data-q]').forEach(b => b.onclick = () => { $('query').value = b.dataset.q; ask(b.dataset.q).catch(e => $('status').textContent = e.message); });
$('pin').onclick = async () => {
  if (!currentPayload) return;
  await fetch('/api/pins', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({query: currentPayload.query, chart_payload: currentPayload}) });
  loadPins();
};
$('refresh-all').onclick = async () => {
  const pins = await (await fetch('/api/pins')).json();
  await Promise.all(pins.map(p => fetch(`/api/pins/${p.id}/refresh`, {method:'POST'})));
  loadPins();
};
$('pins').onclick = async (e) => {
  const r = e.target.dataset.refresh;
  const d = e.target.dataset.delete;
  if (r) await fetch(`/api/pins/${r}/refresh`, {method:'POST'});
  if (d) await fetch(`/api/pins/${d}`, {method:'DELETE'});
  loadPins();
};
loadPins();
