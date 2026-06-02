DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>STARFIRE OS</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root {
  --bg: #0f172a;
  --card: rgba(255,255,255,.08);
  --border: rgba(255,255,255,.15);
  --primary: #38bdf8;
  --success: #22c55e;
  --warning: #f59e0b;
  --danger: #ef4444;
  --purple: #8b5cf6;
  --text: #f8fafc;
  --muted: #94a3b8;
  --surface: rgba(255,255,255,.04);
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: 'Inter', sans-serif;
  background: linear-gradient(135deg, #020617, #0f172a, #1e293b);
  color: var(--text);
  min-height: 100vh;
}
.dashboard { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }

/* ── Sidebar ── */
.sidebar {
  background: rgba(0,0,0,.3);
  backdrop-filter: blur(20px);
  border-right: 1px solid var(--border);
  padding: 28px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: sticky;
  top: 0;
  height: 100vh;
}
.logo {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 32px;
  padding: 0 8px;
  background: linear-gradient(135deg, #38bdf8, #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: 1px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  cursor: pointer;
  color: var(--muted);
  font-size: 14px;
  font-weight: 500;
  transition: all .2s;
  text-decoration: none;
  border: none;
  background: none;
  width: 100%;
  text-align: left;
}
.nav-item:hover { background: rgba(56,189,248,.1); color: var(--text); }
.nav-item.active { background: rgba(56,189,248,.15); color: var(--primary); }
.nav-icon { font-size: 16px; width: 20px; text-align: center; }
.sidebar-footer { margin-top: auto; padding-top: 20px; border-top: 1px solid var(--border); }
.last-refresh { font-size: 11px; color: var(--muted); text-align: center; margin-top: 8px; }

/* ── Main ── */
.main { padding: 28px; overflow-y: auto; }
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 28px;
}
.section-title { font-size: 24px; font-weight: 700; }
.user-chip {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 40px;
  padding: 8px 16px;
  backdrop-filter: blur(10px);
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #38bdf8, #8b5cf6);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
}
.user-name { font-size: 14px; font-weight: 600; }
.user-sub { font-size: 11px; color: var(--muted); }

/* ── Cards ── */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  backdrop-filter: blur(18px);
  border-radius: 18px;
  padding: 22px;
}
.card-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--muted);
  margin-bottom: 4px;
}

/* ── Metric cards ── */
.metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 22px; }
.metric-val { font-size: 28px; font-weight: 700; margin-top: 6px; }
.metric-sub { font-size: 12px; margin-top: 4px; }
.green { color: var(--success); }
.red { color: var(--danger); }
.orange { color: var(--warning); }
.blue { color: var(--primary); }
.purple { color: var(--purple); }

/* ── Two-column layout ── */
.two-col { display: grid; grid-template-columns: 2fr 1fr; gap: 18px; margin-bottom: 22px; }
.two-col-equal { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 22px; }
.chart-wrap { height: 300px; position: relative; }

/* ── AI insights ── */
.insights-list { display: flex; flex-direction: column; gap: 12px; margin-top: 4px; }
.insight {
  padding: 13px 15px;
  border-radius: 12px;
  background: rgba(56,189,248,.07);
  border-left: 3px solid var(--primary);
  font-size: 13px;
  line-height: 1.5;
}
.insight.warn { background: rgba(245,158,11,.07); border-left-color: var(--warning); }
.insight.good { background: rgba(34,197,94,.07); border-left-color: var(--success); }

/* ── Score ── */
.score-circle {
  text-align: center;
  padding: 24px 0 16px;
}
.score-num { font-size: 64px; font-weight: 700; color: var(--primary); line-height: 1; }
.score-label { font-size: 12px; color: var(--muted); margin-top: 6px; }

/* ── Goals ── */
.goal-item { margin-bottom: 18px; }
.goal-row { display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 6px; }
.goal-name { font-weight: 500; }
.goal-pct { color: var(--muted); }
.progress { height: 8px; background: rgba(255,255,255,.08); border-radius: 20px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--success), var(--primary)); border-radius: 20px; transition: width .5s; }
.progress-fill.warn { background: linear-gradient(90deg, var(--warning), #fb923c); }

/* ── Tables ── */
.table-wrap { overflow-x: auto; margin-top: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: var(--muted);
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
td { padding: 11px 10px; border-bottom: 1px solid rgba(255,255,255,.05); }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(255,255,255,.03); }

/* ── Badges ── */
.badge {
  display: inline-block;
  padding: 3px 9px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
}
.badge-green { background: rgba(34,197,94,.15); color: #4ade80; }
.badge-blue { background: rgba(56,189,248,.15); color: #7dd3fc; }
.badge-orange { background: rgba(245,158,11,.15); color: #fbbf24; }
.badge-purple { background: rgba(139,92,246,.15); color: #a78bfa; }
.badge-red { background: rgba(239,68,68,.15); color: #f87171; }

/* ── Account cards ── */
.account-card {
  background: rgba(255,255,255,.04);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px;
  margin-bottom: 14px;
}
.account-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.account-name { font-size: 15px; font-weight: 600; }
.account-meta { font-size: 12px; color: var(--muted); margin-top: 2px; }
.account-total { font-size: 22px; font-weight: 700; color: var(--success); }

.balance-row { display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 10px; }
.bal-item { flex: 1; min-width: 90px; }
.bal-label { font-size: 10px; text-transform: uppercase; letter-spacing: .5px; color: var(--muted); }
.bal-val { font-size: 15px; font-weight: 600; margin-top: 2px; }
.section-label { font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: var(--muted); margin: 12px 0 8px; }

/* ── Broker tiles ── */
.broker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 10px; margin-bottom: 18px; }
.broker-tile {
  background: rgba(255,255,255,.04);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 10px;
  text-align: center;
  cursor: pointer;
  transition: all .2s;
}
.broker-tile:hover { border-color: var(--primary); background: rgba(56,189,248,.07); }
.broker-icon { font-size: 22px; }
.broker-name { font-size: 12px; font-weight: 600; margin-top: 6px; }
.broker-hint { font-size: 10px; color: var(--muted); margin-top: 2px; }

/* ── Memory ── */
.memory-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: rgba(255,255,255,.04);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 11px 13px;
  margin-bottom: 8px;
  transition: border-color .2s;
}
.memory-item:hover { border-color: rgba(56,189,248,.4); }
.mem-cat {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .5px;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: 4px;
  flex-shrink: 0;
  margin-top: 2px;
}
.cat-fact { background: rgba(56,189,248,.15); color: #7dd3fc; }
.cat-preference { background: rgba(139,92,246,.15); color: #a78bfa; }
.cat-instruction { background: rgba(245,158,11,.15); color: #fbbf24; }
.cat-event { background: rgba(34,197,94,.15); color: #4ade80; }
.mem-text { flex: 1; font-size: 14px; line-height: 1.5; }
.mem-actions { display: flex; gap: 4px; flex-shrink: 0; }
.btn-icon { background: none; border: none; cursor: pointer; color: var(--muted); padding: 4px 6px; border-radius: 6px; font-size: 13px; transition: color .2s; }
.btn-icon:hover { color: var(--text); }
.btn-icon.del:hover { color: var(--danger); }
.mem-edit { background: rgba(255,255,255,.06); border: 1px solid var(--primary); color: var(--text); border-radius: 6px; padding: 4px 8px; font-size: 13px; width: 100%; outline: none; font-family: inherit; }

/* ── Add memory form ── */
.add-form { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.input {
  background: rgba(255,255,255,.06);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 10px;
  padding: 9px 13px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  transition: border-color .2s;
}
.input:focus { border-color: var(--primary); }
.input-grow { flex: 1; min-width: 200px; }
.btn {
  padding: 9px 16px;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: opacity .2s;
  font-family: inherit;
}
.btn:hover { opacity: .85; }
.btn:disabled { opacity: .45; cursor: default; }
.btn-primary { background: var(--primary); color: #0f172a; }
.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
.btn-sm { padding: 6px 12px; font-size: 12px; }

/* ── Sections ── */
.section { display: none; }
.section.active { display: block; }

/* ── Empty & loader ── */
.empty { color: var(--muted); font-size: 13px; text-align: center; padding: 24px 0; }
.loader { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.15); border-top-color: var(--primary); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Toast ── */
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: rgba(15,23,42,.95);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 18px;
  font-size: 13px;
  opacity: 0;
  transform: translateY(8px);
  transition: all .3s;
  pointer-events: none;
  z-index: 999;
  backdrop-filter: blur(20px);
}
.toast.show { opacity: 1; transform: none; }

/* ── Responsive ── */
@media (max-width: 1100px) { .metrics-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 900px) {
  .dashboard { grid-template-columns: 1fr; }
  .sidebar { display: none; }
  .two-col, .two-col-equal { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<div class="dashboard">

  <!-- ── SIDEBAR ── -->
  <aside class="sidebar">
    <div class="logo">⚡ STARFIRE</div>

    <button class="nav-item active" onclick="nav('dashboard')">
      <span class="nav-icon">📊</span> Dashboard
    </button>
    <button class="nav-item" onclick="nav('finances')">
      <span class="nav-icon">🏦</span> Finances
    </button>
    <button class="nav-item" onclick="nav('goals')">
      <span class="nav-icon">🎯</span> Goals
    </button>
    <button class="nav-item" onclick="nav('tasks')">
      <span class="nav-icon">✅</span> Tasks
    </button>
    <button class="nav-item" onclick="nav('memory')">
      <span class="nav-icon">🧠</span> Memory
    </button>

    <div class="sidebar-footer">
      <div id="conn-status" style="font-size:12px;color:var(--muted);text-align:center"></div>
      <div class="last-refresh" id="refresh-time"></div>
    </div>
  </aside>

  <!-- ── MAIN ── -->
  <main class="main">

    <!-- Topbar -->
    <div class="topbar">
      <div class="section-title" id="page-title">Dashboard</div>
      <div class="user-chip">
        <div>
          <div class="user-name" id="user-name">—</div>
          <div class="user-sub">AI Assisted</div>
        </div>
        <div class="avatar" id="user-avatar">?</div>
      </div>
    </div>

    <!-- ════════════════════════════════════ DASHBOARD ══ -->
    <div class="section active" id="sec-dashboard">

      <!-- Metrics -->
      <div class="metrics-grid">
        <div class="card">
          <div class="card-title">Net Worth</div>
          <div class="metric-val" id="m-networth"><span class="loader"></span></div>
          <div class="metric-sub muted" id="m-networth-sub">from connected accounts</div>
        </div>
        <div class="card">
          <div class="card-title">Monthly Expenses</div>
          <div class="metric-val" id="m-expenses"><span class="loader"></span></div>
          <div class="metric-sub" id="m-expenses-sub"></div>
        </div>
        <div class="card">
          <div class="card-title">Goals Progress</div>
          <div class="metric-val blue" id="m-goals"><span class="loader"></span></div>
          <div class="metric-sub muted">average completion</div>
        </div>
        <div class="card">
          <div class="card-title">Open Tasks</div>
          <div class="metric-val" id="m-tasks"><span class="loader"></span></div>
          <div class="metric-sub muted" id="m-tickets-sub"></div>
        </div>
      </div>

      <!-- Chart + Insights -->
      <div class="two-col">
        <div class="card">
          <div class="card-title" id="chart-label">Financial Performance</div>
          <div class="chart-wrap" style="margin-top:14px">
            <canvas id="mainChart"></canvas>
          </div>
        </div>
        <div class="card">
          <div class="card-title">AI Insights</div>
          <div class="insights-list" id="insights-list">
            <div class="empty"><span class="loader"></span></div>
          </div>
        </div>
      </div>

      <!-- Goals quick view + Livelihood Score -->
      <div class="two-col-equal">
        <div class="card">
          <div class="card-title">Life & Financial Goals</div>
          <div id="dash-goals">
            <div class="empty"><span class="loader"></span></div>
          </div>
        </div>
        <div class="card">
          <div class="card-title">Livelihood Score</div>
          <div class="score-circle">
            <div class="score-num" id="livelihood-score">—</div>
            <div class="score-label">AI Wellness & Sustainability Index</div>
          </div>
        </div>
      </div>

      <!-- Recent Tickets -->
      <div class="card">
        <div class="card-title">Active Bot Tickets</div>
        <div class="table-wrap" id="dash-tickets">
          <div class="empty"><span class="loader"></span></div>
        </div>
      </div>

    </div>

    <!-- ════════════════════════════════════ FINANCES ══ -->
    <div class="section" id="sec-finances">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div style="font-size:16px;font-weight:600">Connected Accounts</div>
        <button class="btn btn-primary btn-sm" onclick="connectBroker()" id="btn-connect-fin">+ Connect Account</button>
      </div>
      <div id="finances-panel">
        <div class="empty"><span class="loader"></span></div>
      </div>
    </div>

    <!-- ════════════════════════════════════ GOALS ══ -->
    <div class="section" id="sec-goals">
      <div class="card" id="goals-full">
        <div class="empty"><span class="loader"></span></div>
      </div>
    </div>

    <!-- ════════════════════════════════════ TASKS ══ -->
    <div class="section" id="sec-tasks">

      <div class="card" style="margin-bottom:18px">
        <div class="card-title">Open Tasks</div>
        <div class="table-wrap" id="tasks-full">
          <div class="empty"><span class="loader"></span></div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Bot Tickets</div>
        <div class="table-wrap" id="tickets-full">
          <div class="empty"><span class="loader"></span></div>
        </div>
      </div>

    </div>

    <!-- ════════════════════════════════════ MEMORY ══ -->
    <div class="section" id="sec-memory">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <div class="card-title">Persistent Memory <span id="mem-count" style="color:var(--primary);font-weight:600"></span></div>
        </div>
        <div id="mem-list">
          <div class="empty"><span class="loader"></span></div>
        </div>
        <div class="add-form">
          <input id="mem-content" class="input input-grow" placeholder="Add memory — fact, preference, or instruction..." />
          <select id="mem-cat" class="input">
            <option value="fact">🧠 Fact</option>
            <option value="preference">⚙️ Preference</option>
            <option value="instruction">📌 Instruction</option>
            <option value="event">📅 Event</option>
          </select>
          <select id="mem-imp" class="input">
            <option value="8">High</option>
            <option value="5" selected>Normal</option>
            <option value="2">Low</option>
          </select>
          <button class="btn btn-primary" onclick="addMemory()">+ Add</button>
        </div>
      </div>
    </div>

  </main>
</div>

<div class="toast" id="toast"></div>

<script>
const TOKEN = '__TOKEN__';
const API   = '/dashboard/api';

// ── Nav ────────────────────────────────────────────────────────────────────
const TITLES = {
  dashboard: 'Dashboard',
  finances:  'Finances',
  goals:     'Goals',
  tasks:     'Tasks',
  memory:    'Memory',
};

function nav(id) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('sec-' + id).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => {
    if (n.textContent.trim().toLowerCase().includes(id.toLowerCase())) n.classList.add('active');
  });
  document.getElementById('page-title').textContent = TITLES[id] || id;
  if (id === 'finances' && !window._finLoaded) loadFinances();
  if (id === 'memory'   && !window._memLoaded) loadMemories();
}

// ── Helpers ────────────────────────────────────────────────────────────────
function toast(msg, err) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = err ? 'var(--danger)' : 'var(--success)';
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2800);
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function money(n, digits = 0) {
  if (n == null || isNaN(n)) return '—';
  return '$' + Number(n).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});
}

function pnlColor(n) { return Number(n) >= 0 ? 'var(--success)' : 'var(--danger)'; }

function statusBadge(s) {
  const map = {
    QUEUED: 'badge-orange', SENT: 'badge-blue', IN_PROGRESS: 'badge-blue',
    DONE: 'badge-green', FAILED: 'badge-red',
  };
  return `<span class="badge ${map[s] || 'badge-blue'}">${esc(s)}</span>`;
}

// ── Main data ──────────────────────────────────────────────────────────────
let _data = null;
let _accounts = null;
let _chart = null;
let memories = [];

async function loadAll() {
  const [dataRes, accRes] = await Promise.all([
    fetch(`${API}/data?token=${TOKEN}`),
    fetch(`${API}/snaptrade/accounts?token=${TOKEN}`),
  ]);
  _data     = await dataRes.json();
  _accounts = await accRes.json();

  renderTopbar();
  renderMetrics();
  renderDashGoals();
  renderInsights();
  renderDashTickets();
  renderChart();
  document.getElementById('refresh-time').textContent =
    'Refreshed ' + new Date().toLocaleTimeString();
}

function renderTopbar() {
  const name = _data.user?.name || 'Operator';
  document.getElementById('user-name').textContent = name;
  document.getElementById('user-avatar').textContent = (name[0] || '?').toUpperCase();

  const connected = _accounts?.accounts?.length > 0;
  document.getElementById('conn-status').textContent =
    connected ? `${_accounts.accounts.length} account(s) linked` : 'No accounts linked';
}

function renderMetrics() {
  const d = _data;
  const accs = _accounts?.accounts || [];

  // Net worth from SnapTrade
  let netWorth = 0;
  accs.forEach(a => { a.balances.forEach(b => { netWorth += b.total_value || 0; }); });
  const nwEl = document.getElementById('m-networth');
  if (netWorth) {
    nwEl.textContent = money(netWorth);
    nwEl.classList.add('green');
  } else {
    nwEl.innerHTML = `<span style="color:var(--muted);font-size:16px">Connect accounts</span>`;
    document.getElementById('m-networth-sub').innerHTML =
      `<span onclick="nav('finances')" style="color:var(--primary);cursor:pointer">Link via Finances →</span>`;
  }

  // Expenses
  const exp = d.spending_this_month || 0;
  const expEl = document.getElementById('m-expenses');
  expEl.textContent = exp > 0 ? money(exp, 0) : '—';
  expEl.style.color = exp > 3000 ? 'var(--warning)' : 'var(--text)';
  const cats = d.spending_by_category || [];
  document.getElementById('m-expenses-sub').innerHTML =
    cats.length ? `<span style="color:var(--muted)">${cats.length} categories this month</span>` : '<span style="color:var(--muted)">no records this month</span>';

  // Goals avg
  const goals = d.goals || [];
  let avgPct = 0;
  if (goals.length) {
    const pcts = goals.map(g => g.target > 0 ? Math.min(100, (g.current / g.target) * 100) : 0);
    avgPct = Math.round(pcts.reduce((a, b) => a + b, 0) / pcts.length);
  }
  const goalsEl = document.getElementById('m-goals');
  goalsEl.textContent = goals.length ? avgPct + '%' : '—';

  // Tasks / tickets
  const tasks   = d.tasks || [];
  const tickets = d.tickets || [];
  document.getElementById('m-tasks').textContent = tasks.length;
  document.getElementById('m-tickets-sub').textContent =
    tickets.length ? `${tickets.length} bot ticket(s) open` : 'no open tickets';

  // Livelihood score — weighted formula
  let score = 0;
  if (goals.length) score += Math.round(avgPct * 0.5);       // 0–50 pts from goals
  if (netWorth > 0) score += 20;                             // 20 pts for linked accounts
  if (tasks.length < 5) score += 15;                         // 15 pts for low task backlog
  if (exp > 0 && netWorth > 0 && exp / (netWorth * 0.01) < 30) score += 15; // 15 pts for good expense ratio
  score = Math.min(99, score);
  document.getElementById('livelihood-score').textContent = goals.length || netWorth ? score : '—';
}

function renderChart() {
  const ctx = document.getElementById('mainChart');
  if (_chart) { _chart.destroy(); _chart = null; }

  const cats = (_data?.spending_by_category || []).slice(0, 7);
  const goals = _data?.goals || [];
  const accs = _accounts?.accounts || [];

  if (cats.length >= 2) {
    // Spending by category — doughnut
    document.getElementById('chart-label').textContent = 'Spending This Month';
    _chart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: cats.map(c => c.category),
        datasets: [{
          data: cats.map(c => c.total),
          backgroundColor: ['#38bdf8','#22c55e','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6'],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#94a3b8', font: { size: 12 } } },
        },
        cutout: '65%',
      },
    });
  } else if (goals.length) {
    // Goals progress — horizontal bar
    document.getElementById('chart-label').textContent = 'Goals Progress';
    const pcts = goals.map(g => g.target > 0 ? Math.min(100, Math.round((g.current / g.target) * 100)) : 0);
    _chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: goals.map(g => g.title.length > 22 ? g.title.slice(0, 22) + '…' : g.title),
        datasets: [{
          label: '% complete',
          data: pcts,
          backgroundColor: pcts.map(p => p >= 80 ? '#22c55e' : p >= 50 ? '#38bdf8' : '#f59e0b'),
          borderRadius: 6,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#94a3b8', callback: v => v + '%' }, max: 100, grid: { color: 'rgba(255,255,255,.05)' } },
          y: { ticks: { color: '#94a3b8' }, grid: { display: false } },
        },
      },
    });
  } else if (accs.length) {
    // Account balances bar
    document.getElementById('chart-label').textContent = 'Account Balances';
    _chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: accs.map(a => a.name),
        datasets: [{
          label: 'Total Value',
          data: accs.map(a => a.balances.reduce((s, b) => s + (b.total_value || 0), 0)),
          backgroundColor: '#38bdf8',
          borderRadius: 8,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
          y: { ticks: { color: '#94a3b8', callback: v => '$' + (v/1000).toFixed(0) + 'k' }, grid: { color: 'rgba(255,255,255,.05)' } },
        },
      },
    });
  } else {
    ctx.closest('.chart-wrap').innerHTML =
      '<div class="empty" style="padding-top:80px">Add goals or connect accounts to see charts</div>';
  }
}

function renderInsights() {
  const el = document.getElementById('insights-list');
  const d  = _data;
  const accs = _accounts?.accounts || [];
  const insights = [];

  const goals = d.goals || [];
  const topGoal = goals[0];
  if (topGoal) {
    const pct = topGoal.target > 0 ? Math.round((topGoal.current / topGoal.target) * 100) : 0;
    insights.push({ text: `Your top goal "<b>${esc(topGoal.title)}</b>" is ${pct}% complete.`, type: pct >= 80 ? 'good' : '' });
  }

  const exp = d.spending_this_month || 0;
  if (exp > 0) {
    const cats = d.spending_by_category || [];
    const top = cats[0];
    insights.push({ text: `Spent <b>${money(exp, 0)}</b> this month${top ? ` — biggest category: ${esc(top.category)}` : ''}.`, type: exp > 5000 ? 'warn' : '' });
  }

  const tickets = d.tickets || [];
  if (tickets.length) {
    insights.push({ text: `<b>${tickets.length}</b> bot task${tickets.length > 1 ? 's' : ''} active. Check Tasks for details.`, type: '' });
  }

  let netWorth = 0;
  accs.forEach(a => { a.balances.forEach(b => { netWorth += b.total_value || 0; }); });
  if (netWorth > 0) {
    insights.push({ text: `Portfolio total across all accounts: <b>${money(netWorth)}</b>.`, type: 'good' });
  } else {
    insights.push({ text: 'Connect Chase or other accounts in <b>Finances</b> to see your full net worth.', type: '' });
  }

  if (!insights.length) {
    el.innerHTML = '<div class="empty">No insights yet — add goals and spending data to begin.</div>';
    return;
  }
  el.innerHTML = insights.slice(0, 4).map(i =>
    `<div class="insight ${i.type || ''}">${i.text}</div>`
  ).join('');
}

function renderDashGoals() {
  const el = document.getElementById('dash-goals');
  const goals = (_data?.goals || []).slice(0, 5);
  if (!goals.length) { el.innerHTML = '<div class="empty">No active goals — tell STARFIRE to set one</div>'; return; }
  el.innerHTML = goals.map(g => {
    const pct = g.target > 0 ? Math.min(100, Math.round((g.current / g.target) * 100)) : 0;
    return `<div class="goal-item">
      <div class="goal-row">
        <span class="goal-name">${esc(g.title)}</span>
        <span class="goal-pct">${pct}%</span>
      </div>
      <div class="progress">
        <div class="progress-fill ${pct < 30 ? 'warn' : ''}" style="width:${pct}%"></div>
      </div>
    </div>`;
  }).join('');
}

function renderDashTickets() {
  const el = document.getElementById('dash-tickets');
  const tickets = (_data?.tickets || []).slice(0, 5);
  if (!tickets.length) { el.innerHTML = '<div class="empty" style="padding:16px 0">All clear — no active tickets</div>'; return; }
  el.innerHTML = `<table>
    <tr><th>#</th><th>Title</th><th>Bot</th><th>Status</th><th>Priority</th></tr>
    ${tickets.map(t => `<tr>
      <td style="color:var(--muted)">${t.id}</td>
      <td>${esc(t.title)}</td>
      <td><span class="badge badge-blue">${esc(t.assigned_to)}</span></td>
      <td>${statusBadge(t.status)}</td>
      <td>${t.priority}</td>
    </tr>`).join('')}
  </table>`;
}

// ── Goals full view ────────────────────────────────────────────────────────
function renderGoalsFull() {
  const el = document.getElementById('goals-full');
  const goals = _data?.goals || [];
  if (!goals.length) {
    el.innerHTML = '<div class="card-title" style="margin-bottom:8px">Goals</div><div class="empty">No active goals — tell STARFIRE to create one via Telegram</div>';
    return;
  }
  el.innerHTML = `<div class="card-title" style="margin-bottom:16px">Goals (${goals.length} active)</div>` +
    goals.map(g => {
      const pct = g.target > 0 ? Math.min(100, Math.round((g.current / g.target) * 100)) : 0;
      return `<div class="goal-item">
        <div class="goal-row">
          <span class="goal-name">${esc(g.title)}</span>
          <span>${g.current} / ${g.target} ${esc(g.unit || '')}&nbsp;·&nbsp;<b>${pct}%</b></span>
        </div>
        <div class="progress">
          <div class="progress-fill ${pct < 30 ? 'warn' : ''}" style="width:${pct}%"></div>
        </div>
      </div>`;
    }).join('');
}

// ── Tasks full view ────────────────────────────────────────────────────────
function renderTasksFull() {
  const tasksEl   = document.getElementById('tasks-full');
  const ticketsEl = document.getElementById('tickets-full');
  const tasks   = _data?.tasks || [];
  const tickets = _data?.tickets || [];

  if (!tasks.length) {
    tasksEl.innerHTML = '<div class="empty">No pending tasks</div>';
  } else {
    tasksEl.innerHTML = `<table>
      <tr><th>Task</th><th>Priority</th><th>Due</th></tr>
      ${tasks.map(t => `<tr>
        <td>${esc(t.title)}</td>
        <td style="color:${t.priority >= 8 ? 'var(--danger)' : 'var(--muted)'}">${t.priority}</td>
        <td style="color:var(--muted)">${t.due ? t.due.slice(0,10) : '—'}</td>
      </tr>`).join('')}
    </table>`;
  }

  if (!tickets.length) {
    ticketsEl.innerHTML = '<div class="empty">No open tickets</div>';
  } else {
    ticketsEl.innerHTML = `<table>
      <tr><th>#</th><th>Title</th><th>Assigned To</th><th>Status</th></tr>
      ${tickets.map(t => `<tr>
        <td style="color:var(--muted)">${t.id}</td>
        <td>${esc(t.title)}</td>
        <td><span class="badge badge-blue">${esc(t.assigned_to)}</span></td>
        <td>${statusBadge(t.status)}</td>
      </tr>`).join('')}
    </table>`;
  }
}

// ── Finances ───────────────────────────────────────────────────────────────
window._finLoaded = false;

async function loadFinances() {
  window._finLoaded = true;
  renderFinances(_accounts?.accounts || []);
}

function renderFinances(accounts) {
  const panel = document.getElementById('finances-panel');
  const btn   = document.getElementById('btn-connect-fin');

  if (!accounts.length) {
    panel.innerHTML = `
      <div class="card" style="text-align:center;padding:40px 20px">
        <div style="font-size:36px;margin-bottom:12px">🏦</div>
        <div style="font-size:18px;font-weight:700;margin-bottom:8px">Connect Your Accounts</div>
        <div style="color:var(--muted);font-size:14px;margin-bottom:24px;line-height:1.6">
          Link Chase, Fidelity, Schwab, and 200+ brokerages.<br>Read-only access via SnapTrade.
        </div>
        <div class="broker-grid" style="max-width:520px;margin:0 auto 20px">
          <div class="broker-tile" onclick="connectBroker('JPMORGAN_CHASE')">
            <div class="broker-icon">🏛</div>
            <div class="broker-name">Chase</div>
            <div class="broker-hint">Click to connect</div>
          </div>
          <div class="broker-tile" onclick="connectBroker('FIDELITY')">
            <div class="broker-icon">📈</div>
            <div class="broker-name">Fidelity</div>
            <div class="broker-hint">Click to connect</div>
          </div>
          <div class="broker-tile" onclick="connectBroker('SCHWAB')">
            <div class="broker-icon">💼</div>
            <div class="broker-name">Schwab</div>
            <div class="broker-hint">Click to connect</div>
          </div>
          <div class="broker-tile" onclick="connectBroker()">
            <div class="broker-icon">➕</div>
            <div class="broker-name">All 200+</div>
            <div class="broker-hint">Browse all</div>
          </div>
        </div>
      </div>`;
    return;
  }

  btn.textContent = '+ Add Account';

  let totalPortfolio = 0;
  accounts.forEach(a => { a.balances.forEach(b => { totalPortfolio += b.total_value || 0; }); });

  let html = '';
  if (accounts.length > 1) {
    html += `<div class="card" style="margin-bottom:16px">
      <div style="display:flex;gap:30px;flex-wrap:wrap">
        <div><div class="card-title">Total Portfolio</div><div style="font-size:28px;font-weight:700;color:var(--success)">${money(totalPortfolio)}</div></div>
        <div><div class="card-title">Accounts</div><div style="font-size:28px;font-weight:700">${accounts.length}</div></div>
      </div>
    </div>`;
  }

  accounts.forEach(acc => {
    const totalAcc = acc.balances.reduce((s, b) => s + (b.total_value || 0), 0);
    const totalCash = acc.balances.reduce((s, b) => s + (b.cash || 0), 0);
    const totalMv   = acc.balances.reduce((s, b) => s + (b.market_value || 0), 0);

    html += `<div class="account-card">
      <div class="account-header">
        <div>
          <div class="account-name">${esc(acc.name)}</div>
          <div class="account-meta">${esc(acc.brokerage)}${acc.type ? ' · ' + esc(acc.type) : ''}</div>
        </div>
        <div style="text-align:right">
          <div class="account-total">${money(totalAcc || totalCash)}</div>
          <div style="font-size:11px;color:var(--muted)">Total Value</div>
        </div>
      </div>
      <div class="balance-row">
        <div class="bal-item"><div class="bal-label">Cash</div><div class="bal-val">${money(totalCash)}</div></div>
        <div class="bal-item"><div class="bal-label">Investments</div><div class="bal-val">${money(totalMv)}</div></div>
      </div>`;

    if (acc.positions.length) {
      html += `<div class="section-label">Positions</div>
        <div class="table-wrap"><table>
          <tr><th>Symbol</th><th>Units</th><th>Avg Price</th><th>Open P/L</th></tr>
          ${acc.positions.map(p => `<tr>
            <td><b>${esc(p.symbol)}</b></td>
            <td>${p.fractional_units || '—'}</td>
            <td>${p.average_purchase_price ? money(p.average_purchase_price, 2) : '—'}</td>
            <td style="color:${pnlColor(p.open_pnl)}">${p.open_pnl != null ? (p.open_pnl >= 0 ? '+' : '') + money(p.open_pnl, 2) : '—'}</td>
          </tr>`).join('')}
        </table></div>`;
    }

    html += `</div>`;
  });

  // Transactions button
  html += `<div style="margin-top:14px">
    <button class="btn btn-outline btn-sm" onclick="loadActivities()" id="btn-acts">View Recent Transactions</button>
    <div id="acts-panel" style="margin-top:12px"></div>
  </div>`;

  panel.innerHTML = html;
}

async function connectBroker(broker) {
  const btn = document.getElementById('btn-connect-fin');
  if (btn) { btn.textContent = 'Opening…'; btn.disabled = true; }
  try {
    let url = `${API}/snaptrade/connect?token=${TOKEN}`;
    if (broker) url += `&broker=${broker}`;
    const res = await fetch(url);
    if (!res.ok) { toast((await res.json()).detail || 'Failed', true); return; }
    const data = await res.json();
    if (data.redirect_url) {
      window.open(data.redirect_url, '_blank', 'width=600,height=700,noopener');
      toast('SnapTrade portal opened — connect your account and return here');
      setTimeout(() => { window._finLoaded = false; loadAll(); }, 8000);
    }
  } catch (e) { toast('Could not open portal', true); }
  finally {
    if (btn) { btn.disabled = false; btn.textContent = '+ Add Account'; }
  }
}

async function loadActivities() {
  const panel = document.getElementById('acts-panel');
  const btn   = document.getElementById('btn-acts');
  if (btn) { btn.textContent = 'Loading…'; btn.disabled = true; }
  try {
    const res = await fetch(`${API}/snaptrade/activities?token=${TOKEN}`);
    const d   = await res.json();
    const acts = d.activities || [];
    if (!acts.length) { panel.innerHTML = '<div class="empty">No recent transactions found</div>'; return; }
    panel.innerHTML = `<div class="section-label">Recent Transactions</div>
      <div class="table-wrap"><table>
        <tr><th>Date</th><th>Type</th><th>Description</th><th>Amount</th><th>Account</th></tr>
        ${acts.map(a => `<tr>
          <td style="color:var(--muted)">${(a.date || '').slice(0,10)}</td>
          <td>${esc(a.type)}</td>
          <td>${esc(a.description || a.symbol || '—')}</td>
          <td style="color:${pnlColor(a.amount)}">${a.amount >= 0 ? '+' : ''}${money(a.amount, 2)} ${esc(a.currency)}</td>
          <td style="color:var(--muted);font-size:12px">${esc(a.account)}</td>
        </tr>`).join('')}
      </table></div>`;
  } catch (e) { panel.innerHTML = '<div class="empty">Failed to load</div>'; }
  finally { if (btn) { btn.disabled = false; btn.textContent = 'Refresh Transactions'; } }
}

// ── Memory ─────────────────────────────────────────────────────────────────
window._memLoaded = false;

async function loadMemories() {
  window._memLoaded = true;
  const res = await fetch(`${API}/memories?token=${TOKEN}`);
  memories = await res.json();
  renderMemories();
}

function renderMemories() {
  const el = document.getElementById('mem-list');
  document.getElementById('mem-count').textContent = memories.length ? `(${memories.length})` : '';
  if (!memories.length) { el.innerHTML = '<div class="empty">No memories yet</div>'; return; }
  el.innerHTML = memories.map(m => `
    <div class="memory-item" id="mi-${m.id}">
      <span class="mem-cat cat-${m.category}">${m.category}</span>
      <div class="mem-text" id="mt-${m.id}">${esc(m.content)}</div>
      <div class="mem-actions">
        <button class="btn-icon" onclick="editMem(${m.id})" title="Edit">✏️</button>
        <button class="btn-icon del" onclick="deleteMem(${m.id})" title="Delete">🗑</button>
      </div>
    </div>`).join('');
}

async function addMemory() {
  const c = document.getElementById('mem-content').value.trim();
  if (!c) { toast('Enter content first', true); return; }
  const res = await fetch(`${API}/memories?token=${TOKEN}`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      content: c,
      category: document.getElementById('mem-cat').value,
      importance: parseInt(document.getElementById('mem-imp').value),
    })
  });
  if (res.ok) { document.getElementById('mem-content').value = ''; toast('Saved ✓'); await loadMemories(); }
  else toast('Failed to save', true);
}

function editMem(id) {
  const m = memories.find(x => x.id === id);
  if (!m) return;
  const el = document.getElementById('mt-' + id);
  el.innerHTML = `<textarea class="mem-edit" id="me-${id}" rows="2">${esc(m.content)}</textarea>
    <div style="display:flex;gap:6px;margin-top:6px">
      <button class="btn btn-primary btn-sm" onclick="saveMem(${id})">Save</button>
      <button class="btn btn-outline btn-sm" onclick="renderMemories()">Cancel</button>
    </div>`;
  document.getElementById('me-' + id).focus();
}

async function saveMem(id) {
  const val = document.getElementById('me-' + id).value.trim();
  if (!val) return;
  const res = await fetch(`${API}/memories/${id}?token=${TOKEN}`, {
    method: 'PUT', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({content: val})
  });
  if (res.ok) { toast('Updated ✓'); await loadMemories(); }
  else toast('Update failed', true);
}

async function deleteMem(id) {
  if (!confirm('Delete this memory?')) return;
  const res = await fetch(`${API}/memories/${id}?token=${TOKEN}`, { method: 'DELETE' });
  if (res.ok) { toast('Deleted'); await loadMemories(); }
  else toast('Failed', true);
}

// ── Init ───────────────────────────────────────────────────────────────────
document.getElementById('mem-content').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); addMemory(); }
});

(async () => {
  await loadAll();
  // Populate sections that are rendered from _data
  renderGoalsFull();
  renderTasksFull();
})();

setInterval(() => { loadAll().then(() => { renderGoalsFull(); renderTasksFull(); }); }, 60000);
</script>
</body>
</html>
"""
