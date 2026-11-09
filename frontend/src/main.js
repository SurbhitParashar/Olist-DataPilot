import { Chart } from 'chart.js/auto';
import './style.css';

const app = document.querySelector('#app');
let currentPayload = null;
let chart;
const pinKey = 'olist-dashboard-v1';
const pinCharts = [];
const readPins = () => JSON.parse(localStorage.getItem(pinKey) || '[]');
const writePins = (pins) => localStorage.setItem(pinKey, JSON.stringify(pins));

async function request(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Request failed. Please try again.');
  return payload;
}
const post = (url, payload) => request(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
const showError = (error) => { $('status').textContent = error.message; };

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
      <p class="muted">Pins are saved in this browser. Select a pin to view its chart.</p>
      <div id="pins"></div>
    </section>
  </main>
`;

const $ = (id) => document.getElementById(id);

async function ask(query) {
  if (query.length < 3) throw new Error('Enter a question with at least 3 characters.');
  $('ask').disabled = true;
  try {
  $('status').textContent = 'Running agent…';
  $('result').classList.add('hidden');
  const payload = await post('/api/ask', {query});
  currentPayload = payload;
  renderResult(payload);
  $('status').textContent = `Done via ${payload.agent_mode} agent.`;
  } finally {
    $('ask').disabled = false;
  }
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
  chart = null;
  document.querySelector('.chart-wrap').innerHTML = '<canvas id="chart"></canvas>';
  $('pin').disabled = p.chart_type === 'none';
  if (p.chart_type !== 'none') {
    chart = new Chart($('chart'), p.chart_config);
  } else {
    $('chart').replaceWith(Object.assign(document.createElement('div'), {className:'no-chart', textContent:'No chart for this query.'}));
  }
}

async function loadPins() {
  pinCharts.splice(0).forEach(c => c.destroy());
  const pins = readPins();
  $('pins').innerHTML = pins.length ? pins.map(pinCard).join('') : '<p class="muted">Nothing pinned yet.</p>';
  pins.forEach(p => {
    if (p.chart_payload.chart_type !== 'none') {
      pinCharts.push(new Chart($(`pin-${p.id}`), structuredClone(p.chart_payload.chart_config)));
    }
  });
}

function pinCard(p) {
  return `<article class="pin-card"><div class="pin-head"><div><strong>${escapeHtml(p.query)}</strong><div class="muted">Updated ${escapeHtml(p.updated_at)}</div><p>${escapeHtml(p.chart_payload.insight)}</p></div><div><button data-view="${p.id}">View</button><button data-refresh="${p.id}">Refresh</button><button data-delete="${p.id}">Remove</button></div></div><div class="chart-wrap"><canvas id="pin-${p.id}"></canvas></div></article>`;
}

function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }

$('ask').onclick = () => ask($('query').value.trim()).catch(e => $('status').textContent = e.message);
document.querySelectorAll('[data-q]').forEach(b => b.onclick = () => { $('query').value = b.dataset.q; ask(b.dataset.q).catch(e => $('status').textContent = e.message); });
$('pin').onclick = async () => {
  try {
  if (!currentPayload) return;
  const pins = readPins();
  pins.unshift({id: crypto.randomUUID(), query: currentPayload.query, chart_payload: currentPayload, updated_at: new Date().toLocaleString()});
  writePins(pins);
  await loadPins();
  $('status').textContent = 'Chart pinned to this browser.';
  } catch (error) { showError(error); }
};
async function refreshPin(id) {
  const old = readPins().find(p => p.id === id);
  if (!old) return;
  const result = await post('/api/refresh', {query: old.query, chart_payload: old.chart_payload});
  if (result.payload.chart_type === 'none') throw new Error('Refresh returned no chart. Your previous pin has been kept.');
  writePins(readPins().map(p => p.id === id ? {...p, chart_payload: result.payload, updated_at: new Date().toLocaleString()} : p));
  $('status').textContent = result.changed ? 'Significant change detected in refreshed chart.' : 'Chart refreshed. No significant change detected.';
}
$('refresh-all').onclick = async () => {
  $('refresh-all').disabled = true;
  try {
    for (const pin of readPins()) await refreshPin(pin.id);
  } catch (error) { showError(error); }
  finally { await loadPins(); $('refresh-all').disabled = false; }
};
$('pins').onclick = async (e) => {
  try {
  const r = e.target.dataset.refresh;
  const d = e.target.dataset.delete;
  const v = e.target.dataset.view;
  if (r) await refreshPin(r);
  if (d) writePins(readPins().filter(p => p.id !== d));
  if (v) { currentPayload = readPins().find(p => p.id === v).chart_payload; renderResult(currentPayload); }
  if (r || d) await loadPins();
  } catch (error) { showError(error); }
};
loadPins().catch(showError);
