DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>STARFIRE OS</title>
<style>
  :root {
    --bg: #0a0e1a;
    --surface: #111827;
    --surface2: #1a2235;
    --border: #1e2d45;
    --accent: #3b82f6;
    --accent2: #6366f1;
    --green: #10b981;
    --red: #ef4444;
    --yellow: #f59e0b;
    --text: #e2e8f0;
    --muted: #64748b;
    --font: 'Inter', system-ui, sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: var(--font); min-height: 100vh; }

  /* Header */
  .header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  .logo { font-size: 20px; font-weight: 700; letter-spacing: 2px; background: linear-gradient(135deg, #3b82f6, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .status-dot { width: 8px; height: 8px; background: var(--green); border-radius: 50%; display: inline-block; margin-right: 6px; box-shadow: 0 0 6px var(--green); }
  .header-right { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--muted); }

  /* Layout */
  .container { max-width: 1400px; margin: 0 auto; padding: 24px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 900px) { .container { grid-template-columns: 1fr; } }
  .full-width { grid-column: 1 / -1; }

  /* Cards */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
  .card-header { padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); }
  .card-title { font-size: 13px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; color: var(--muted); }
  .card-body { padding: 20px; }

  /* Memory section */
  .memory-grid { display: grid; gap: 10px; }
  .memory-item { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; display: flex; align-items: flex-start; gap: 10px; transition: border-color 0.2s; }
  .memory-item:hover { border-color: var(--accent); }
  .memory-cat { font-size: 10px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; padding: 2px 7px; border-radius: 4px; flex-shrink: 0; margin-top: 2px; }
  .cat-fact { background: rgba(59,130,246,0.15); color: #60a5fa; }
  .cat-preference { background: rgba(99,102,241,0.15); color: #818cf8; }
  .cat-instruction { background: rgba(245,158,11,0.15); color: #fbbf24; }
  .cat-event { background: rgba(16,185,129,0.15); color: #34d399; }
  .memory-content { flex: 1; font-size: 14px; line-height: 1.5; }
  .memory-actions { display: flex; gap: 6px; flex-shrink: 0; }
  .btn-icon { background: none; border: none; cursor: pointer; color: var(--muted); padding: 4px; border-radius: 4px; font-size: 14px; transition: color 0.2s; }
  .btn-icon:hover { color: var(--text); }
  .btn-icon.delete:hover { color: var(--red); }

  /* Add memory form */
  .add-memory { margin-top: 14px; display: flex; gap: 8px; flex-wrap: wrap; }
  .input { background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 8px; padding: 8px 12px; font-size: 14px; outline: none; transition: border-color 0.2s; }
  .input:focus { border-color: var(--accent); }
  .input-main { flex: 1; min-width: 200px; }
  select.input { cursor: pointer; }
  .btn { padding: 8px 16px; border-radius: 8px; border: none; cursor: pointer; font-size: 13px; font-weight: 600; transition: opacity 0.2s; }
  .btn:hover { opacity: 0.85; }
  .btn-primary { background: var(--accent); color: white; }
  .btn-sm { padding: 5px 10px; font-size: 12px; }

  /* OSIRIS panel */
  .metric-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .metric { background: var(--surface2); border-radius: 8px; padding: 14px; text-align: center; }
  .metric-val { font-size: 22px; font-weight: 700; }
  .metric-label { font-size: 11px; color: var(--muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
  .green { color: var(--green); }
  .red { color: var(--red); }
  .muted { color: var(--muted); }

  /* Tables */
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); padding: 6px 8px; border-bottom: 1px solid var(--border); }
  td { padding: 8px; border-bottom: 1px solid rgba(30,45,69,0.5); }
  tr:last-child td { border-bottom: none; }

  /* Pill badges */
  .badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; }
  .badge-osiris { background: rgba(59,130,246,0.15); color: #60a5fa; }
  .badge-lumisnova { background: rgba(99,102,241,0.15); color: #818cf8; }
  .badge-queued { background: rgba(245,158,11,0.15); color: #fbbf24; }
  .badge-progress { background: rgba(59,130,246,0.15); color: #60a5fa; }
  .badge-sent { background: rgba(16,185,129,0.15); color: #34d399; }

  /* Progress bar */
  .progress-wrap { background: var(--surface2); border-radius: 4px; height: 6px; overflow: hidden; margin-top: 6px; }
  .progress-bar { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); border-radius: 4px; transition: width 0.5s; }

  /* Empty state */
  .empty { color: var(--muted); font-size: 13px; text-align: center; padding: 20px 0; }

  /* Toast */
  .toast { position: fixed; bottom: 24px; right: 24px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px 18px; font-size: 13px; opacity: 0; transform: translateY(10px); transition: all 0.3s; pointer-events: none; z-index: 999; }
  .toast.show { opacity: 1; transform: translateY(0); }

  /* Edit mode */
  .memory-edit-input { background: var(--surface2); border: 1px solid var(--accent); color: var(--text); border-radius: 6px; padding: 4px 8px; font-size: 14px; width: 100%; outline: none; }

  /* Loader */
  .loader { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="header">
  <div class="logo">⚡ STARFIRE OS</div>
  <div class="header-right">
    <span id="user-name" style="color:var(--text);font-weight:600"></span>
    <span><span class="status-dot"></span>Online</span>
    <span id="last-refresh" style="font-size:11px"></span>
  </div>
</div>

<div class="container">

  <!-- MEMORY MANAGER (full width) -->
  <div class="card full-width">
    <div class="card-header">
      <span class="card-title">🧠 Persistent Memory</span>
      <span id="mem-count" style="font-size:12px;color:var(--muted)"></span>
    </div>
    <div class="card-body">
      <div class="memory-grid" id="memory-list">
        <div class="empty"><span class="loader"></span></div>
      </div>
      <div class="add-memory">
        <input id="new-content" class="input input-main" placeholder="Add a memory — fact, preference, or standing instruction..." />
        <select id="new-cat" class="input">
          <option value="fact">🧠 Fact</option>
          <option value="preference">⚙️ Preference</option>
          <option value="instruction">📌 Instruction</option>
          <option value="event">📅 Event</option>
        </select>
        <select id="new-imp" class="input">
          <option value="8">High importance</option>
          <option value="5" selected>Normal</option>
          <option value="2">Low</option>
        </select>
        <button class="btn btn-primary" onclick="addMemory()">+ Add Memory</button>
      </div>
    </div>
  </div>

  <!-- OSIRIS / ALPACA -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">📊 OSIRIS — Alpaca Paper</span>
      <span id="osiris-updated" style="font-size:11px;color:var(--muted)"></span>
    </div>
    <div class="card-body" id="osiris-panel">
      <div class="empty"><span class="loader"></span></div>
    </div>
  </div>

  <!-- OPEN TICKETS -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">🎫 Open Tickets</span>
      <span id="ticket-count" style="font-size:12px;color:var(--muted)"></span>
    </div>
    <div class="card-body" id="tickets-panel">
      <div class="empty"><span class="loader"></span></div>
    </div>
  </div>

  <!-- TASKS -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">✅ Open Tasks</span>
    </div>
    <div class="card-body" id="tasks-panel">
      <div class="empty"><span class="loader"></span></div>
    </div>
  </div>

  <!-- GOALS -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">🎯 Goals</span>
    </div>
    <div class="card-body" id="goals-panel">
      <div class="empty"><span class="loader"></span></div>
    </div>
  </div>

</div>

<div class="toast" id="toast"></div>

<script>
const TOKEN = '__TOKEN__';
const API = '/dashboard/api';

// ── Helpers ────────────────────────────────────────────────────────────────
function toast(msg, err = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = err ? 'var(--red)' : 'var(--green)';
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2500);
}

function fmt(n) { return n >= 0 ? '+$' + n.toFixed(2) : '-$' + Math.abs(n).toFixed(2); }
function cls(n) { return n >= 0 ? 'green' : 'red'; }

function catBadge(cat) {
  return `<span class="memory-cat cat-${cat}">${cat}</span>`;
}

// ── Memory ──────────────────────────────────────────────────────────────────
let memories = [];

async function loadMemories() {
  const res = await fetch(`${API}/memories?token=${TOKEN}`);
  memories = await res.json();
  renderMemories();
}

function renderMemories() {
  const el = document.getElementById('memory-list');
  document.getElementById('mem-count').textContent = memories.length + ' stored';
  if (!memories.length) {
    el.innerHTML = '<div class="empty">No memories yet — add one below</div>';
    return;
  }
  el.innerHTML = memories.map(m => `
    <div class="memory-item" id="mem-${m.id}">
      ${catBadge(m.category)}
      <div class="memory-content" id="mem-content-${m.id}">${escHtml(m.content)}</div>
      <div class="memory-actions">
        <button class="btn-icon" title="Edit" onclick="editMemory(${m.id})">✏️</button>
        <button class="btn-icon delete" title="Delete" onclick="deleteMemory(${m.id})">🗑</button>
      </div>
    </div>
  `).join('');
}

function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

async function addMemory() {
  const content = document.getElementById('new-content').value.trim();
  if (!content) { toast('Enter a memory first', true); return; }
  const category = document.getElementById('new-cat').value;
  const importance = parseInt(document.getElementById('new-imp').value);
  const res = await fetch(`${API}/memories?token=${TOKEN}`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({content, category, importance})
  });
  if (res.ok) {
    document.getElementById('new-content').value = '';
    toast('Memory saved ✓');
    await loadMemories();
  } else { toast('Failed to save', true); }
}

function editMemory(id) {
  const mem = memories.find(m => m.id === id);
  if (!mem) return;
  const el = document.getElementById(`mem-content-${id}`);
  el.innerHTML = `<input class="memory-edit-input" id="edit-${id}" value="${escHtml(mem.content)}" />
    <div style="margin-top:6px;display:flex;gap:6px">
      <button class="btn btn-primary btn-sm" onclick="saveEdit(${id})">Save</button>
      <button class="btn btn-sm" style="background:var(--surface2)" onclick="renderMemories()">Cancel</button>
    </div>`;
  document.getElementById(`edit-${id}`).focus();
}

async function saveEdit(id) {
  const val = document.getElementById(`edit-${id}`).value.trim();
  if (!val) return;
  const res = await fetch(`${API}/memories/${id}?token=${TOKEN}`, {
    method: 'PUT', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({content: val})
  });
  if (res.ok) { toast('Updated ✓'); await loadMemories(); }
  else { toast('Update failed', true); }
}

async function deleteMemory(id) {
  if (!confirm('Delete this memory?')) return;
  const res = await fetch(`${API}/memories/${id}?token=${TOKEN}`, { method: 'DELETE' });
  if (res.ok) { toast('Memory deleted'); await loadMemories(); }
  else { toast('Delete failed', true); }
}

// ── Dashboard data ──────────────────────────────────────────────────────────
async function loadData() {
  const res = await fetch(`${API}/data?token=${TOKEN}`);
  const d = await res.json();

  document.getElementById('user-name').textContent = d.user?.name || '';
  document.getElementById('last-refresh').textContent = 'Updated ' + new Date().toLocaleTimeString();

  renderOsiris(d.alpaca, d.osiris_report);
  renderTickets(d.tickets);
  renderTasks(d.tasks);
  renderGoals(d.goals);
}

function renderOsiris(alpaca, report) {
  const el = document.getElementById('osiris-panel');
  if (!alpaca && !report) {
    el.innerHTML = '<div class="empty">No data yet — OSIRIS needs to report a trade</div>';
    return;
  }
  const data = alpaca || {};
  const pnl = data.pnl_today ?? (report?.pnl_today ?? null);
  const equity = data.equity ?? null;
  const bp = data.buying_power ?? null;

  let html = '<div class="metric-row">';
  if (pnl !== null) html += `<div class="metric"><div class="metric-val ${cls(pnl)}">${fmt(pnl)}</div><div class="metric-label">P/L Today</div></div>`;
  if (equity !== null) html += `<div class="metric"><div class="metric-val">$${equity.toLocaleString('en-US',{minimumFractionDigits:0})}</div><div class="metric-label">Equity</div></div>`;
  if (bp !== null) html += `<div class="metric"><div class="metric-val muted">$${Math.round(bp).toLocaleString()}</div><div class="metric-label">Buying Power</div></div>`;
  html += '</div>';

  if (data.positions?.length) {
    html += '<table><tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>Unr. P/L</th></tr>';
    data.positions.forEach(p => {
      html += `<tr><td><b>${p.symbol}</b></td><td>${p.qty}</td><td>$${p.avg_entry.toFixed(2)}</td><td class="${cls(p.unrealized_pl)}">${fmt(p.unrealized_pl)}</td></tr>`;
    });
    html += '</table>';
  }

  if (data.fills?.length) {
    html += '<div style="margin-top:14px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Recent Fills</div>';
    html += '<table><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Date</th></tr>';
    data.fills.slice(0,8).forEach(f => {
      const sideCol = f.side === 'buy' ? 'green' : 'red';
      html += `<tr><td><b>${f.symbol}</b></td><td class="${sideCol}">${f.side.toUpperCase()}</td><td>${f.qty}</td><td>$${f.price.toFixed(2)}</td><td style="color:var(--muted)">${f.filled_at?.slice(0,10)||''}</td></tr>`;
    });
    html += '</table>';
  }

  el.innerHTML = html || '<div class="empty">No positions</div>';
}

function renderTickets(tickets) {
  const el = document.getElementById('tickets-panel');
  document.getElementById('ticket-count').textContent = tickets.length + ' open';
  if (!tickets.length) { el.innerHTML = '<div class="empty">All clear — no open tickets</div>'; return; }
  let html = '<table><tr><th>#</th><th>Title</th><th>Bot</th><th>Status</th></tr>';
  tickets.forEach(t => {
    const botBadge = `<span class="badge badge-${t.assigned_to.toLowerCase()}">${t.assigned_to}</span>`;
    const statusBadge = `<span class="badge badge-${t.status.toLowerCase().replace('_','')}">${t.status}</span>`;
    html += `<tr><td style="color:var(--muted)">${t.id}</td><td>${t.title}</td><td>${botBadge}</td><td>${statusBadge}</td></tr>`;
  });
  html += '</table>';
  el.innerHTML = html;
}

function renderTasks(tasks) {
  const el = document.getElementById('tasks-panel');
  if (!tasks.length) { el.innerHTML = '<div class="empty">No pending tasks</div>'; return; }
  let html = '<table><tr><th>Task</th><th>Priority</th><th>Due</th></tr>';
  tasks.forEach(t => {
    const p = t.priority >= 8 ? `<span style="color:var(--red)">${t.priority}</span>` : `<span style="color:var(--muted)">${t.priority}</span>`;
    html += `<tr><td>${t.title}</td><td>${p}</td><td style="color:var(--muted)">${t.due ? t.due.slice(0,10) : '—'}</td></tr>`;
  });
  html += '</table>';
  el.innerHTML = html;
}

function renderGoals(goals) {
  const el = document.getElementById('goals-panel');
  if (!goals.length) { el.innerHTML = '<div class="empty">No active goals</div>'; return; }
  let html = '';
  goals.forEach(g => {
    const pct = g.target > 0 ? Math.min(100, Math.round((g.current / g.target) * 100)) : 0;
    html += `<div style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;font-size:14px"><span>${g.title}</span><span style="color:var(--muted)">${g.current}/${g.target} ${g.unit||''}</span></div>
      <div class="progress-wrap"><div class="progress-bar" style="width:${pct}%"></div></div>
    </div>`;
  });
  el.innerHTML = html;
}

// ── Init ────────────────────────────────────────────────────────────────────
document.getElementById('new-content').addEventListener('keydown', e => { if (e.key === 'Enter') addMemory(); });

(async () => {
  await Promise.all([loadMemories(), loadData()]);
})();

// Auto-refresh every 60s
setInterval(() => { loadData(); }, 60000);
</script>
</body>
</html>
"""
