DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>STARFIRE OS</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root {
  --bg:        #000000;
  --bg1:       #080808;
  --bg2:       #0f0f0f;
  --bg3:       #161616;
  --bg4:       #1c1c1c;
  --border:    rgba(255,255,255,.07);
  --border2:   rgba(255,255,255,.13);
  --border-h:  rgba(255,255,255,.18);
  --primary:   #e63946;
  --prim-dim:  rgba(230,57,70,.09);
  --prim-glow: rgba(230,57,70,.22);
  --violet:    #7c3aed;
  --success:   #22c55e;
  --warning:   #f59e0b;
  --danger:    #ef4444;
  --purple:    #a78bfa;
  --cyan:      #22d3ee;
  --text:      #f1f5f9;
  --muted:     #64748b;
  --muted2:    #94a3b8;
  --mono:      'JetBrains Mono', monospace;
  --r:         10px;
  --r-lg:      14px;
  --r-xl:      18px;
  --shadow:    0 1px 3px rgba(0,0,0,.6), 0 4px 12px rgba(0,0,0,.4);
  --shadow-lg: 0 4px 16px rgba(0,0,0,.7), 0 8px 32px rgba(0,0,0,.5);
  --transition: all .18s ease;
}

*, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }
html { scroll-behavior:smooth; }
body {
  font-family:'Inter', sans-serif;
  background:var(--bg);
  color:var(--text);
  min-height:100vh;
  line-height:1.5;
  -webkit-font-smoothing:antialiased;
}

/* ─── Layout ──────────────────────────────── */
.shell {
  display:grid;
  grid-template-columns:248px 1fr;
  min-height:100vh;
}

/* ─── Sidebar ─────────────────────────────── */
.sidebar {
  background:var(--bg1);
  border-right:1px solid var(--border);
  padding:20px 12px 20px;
  display:flex;
  flex-direction:column;
  position:sticky;
  top:0;
  height:100vh;
  overflow-y:auto;
}
.sidebar::-webkit-scrollbar { width:3px; }
.sidebar::-webkit-scrollbar-track { background:transparent; }
.sidebar::-webkit-scrollbar-thumb { background:var(--border2); border-radius:2px; }

/* Logo */
.logo {
  display:flex;
  align-items:center;
  gap:11px;
  padding:4px 8px 20px;
  border-bottom:1px solid var(--border);
  margin-bottom:16px;
}
.logo-mark {
  width:34px; height:34px;
  background:linear-gradient(135deg, #e63946 0%, #7c3aed 100%);
  border-radius:9px;
  display:flex; align-items:center; justify-content:center;
  font-size:17px; flex-shrink:0;
  box-shadow:0 2px 12px rgba(230,57,70,.35);
}
.logo-title {
  font-size:14px; font-weight:800; letter-spacing:.8px;
  background:linear-gradient(90deg, #f8fafc 0%, #e63946 100%);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
}
.logo-sub {
  font-size:9.5px; color:var(--muted); letter-spacing:1.5px;
  text-transform:uppercase; margin-top:1px;
}

/* Nav sections */
.nav-group { margin-bottom:4px; }
.nav-label {
  font-size:9.5px; font-weight:700; letter-spacing:1.4px;
  text-transform:uppercase; color:var(--muted);
  padding:12px 10px 5px;
  display:block;
}

.nav-item {
  display:flex; align-items:center; gap:9px;
  padding:9px 10px; border-radius:var(--r);
  cursor:pointer; color:var(--muted2); font-size:13px; font-weight:500;
  transition:var(--transition); border:none; background:none;
  width:100%; text-align:left; margin-bottom:1px;
  position:relative;
}
.nav-item::before {
  content:''; position:absolute; left:0; top:50%;
  transform:translateY(-50%) scaleY(0);
  width:2.5px; height:60%; background:var(--primary);
  border-radius:0 2px 2px 0;
  transition:transform .18s ease;
}
.nav-item:hover {
  background:rgba(255,255,255,.04);
  color:var(--text);
}
.nav-item.active {
  background:var(--prim-dim);
  color:var(--primary);
}
.nav-item.active::before { transform:translateY(-50%) scaleY(1); }
.nav-icon { font-size:15px; width:18px; text-align:center; flex-shrink:0; }

/* Sidebar footer */
.sidebar-footer {
  margin-top:auto;
  padding-top:14px;
  border-top:1px solid var(--border);
}
.sys-status {
  display:flex; align-items:center; gap:7px;
  font-size:11.5px; color:var(--muted); margin-bottom:6px;
}
.dot {
  width:6px; height:6px; border-radius:50%; flex-shrink:0;
}
.dot-green  { background:var(--success); box-shadow:0 0 6px rgba(34,197,94,.6); }
.dot-red    { background:var(--danger); }
.dot-muted  { background:var(--muted); }
.refresh-ts {
  font-size:10.5px; color:var(--muted); font-family:var(--mono);
}

/* ─── Main ────────────────────────────────── */
.main {
  padding:28px 32px;
  background:var(--bg);
  overflow-y:auto;
  min-width:0;
}

/* Topbar */
.topbar {
  display:flex; justify-content:space-between; align-items:flex-start;
  margin-bottom:24px;
}
.page-heading { font-size:20px; font-weight:700; }
.page-sub { font-size:12.5px; color:var(--muted); margin-top:3px; }

.user-chip {
  display:flex; align-items:center; gap:10px;
  background:var(--bg2); border:1px solid var(--border2);
  border-radius:40px; padding:5px 14px 5px 5px;
  flex-shrink:0;
}
.avatar {
  width:30px; height:30px; border-radius:50%;
  background:linear-gradient(135deg, #e63946, #7c3aed);
  display:flex; align-items:center; justify-content:center;
  font-weight:700; font-size:12px; flex-shrink:0;
}
.user-name { font-size:12.5px; font-weight:600; }
.user-sub  { font-size:10.5px; color:var(--muted); }

/* ─── Section visibility ──────────────────── */
.section { display:none; animation:fadeIn .2s ease; }
.section.active { display:block; }
@keyframes fadeIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }

/* ─── Cards ───────────────────────────────── */
.card {
  background:var(--bg2);
  border:1px solid var(--border);
  border-radius:var(--r-lg);
  padding:18px 20px;
  transition:border-color .2s;
}
.card:hover { border-color:var(--border2); }
.card + .card { margin-top:14px; }
.card-label {
  font-size:10.5px; font-weight:600; text-transform:uppercase;
  letter-spacing:1px; color:var(--muted); margin-bottom:5px;
}
.card-title {
  font-size:14.5px; font-weight:600; margin-bottom:14px;
}

/* Metric cards */
.metrics-4 {
  display:grid; grid-template-columns:repeat(4,1fr);
  gap:12px; margin-bottom:14px;
}
.metrics-3 {
  display:grid; grid-template-columns:repeat(3,1fr);
  gap:12px; margin-bottom:14px;
}
.metric-card {
  background:var(--bg2); border:1px solid var(--border);
  border-radius:var(--r-lg); padding:16px 18px;
  transition:var(--transition);
}
.metric-card:hover {
  border-color:var(--border2);
  transform:translateY(-1px);
  box-shadow:var(--shadow);
}
.metric-val {
  font-size:28px; font-weight:800; margin-top:4px;
  line-height:1.05; letter-spacing:-.5px;
  font-family:var(--mono);
}
.metric-note { font-size:11.5px; color:var(--muted); margin-top:5px; }

/* ─── Color helpers ───────────────────────── */
.green  { color:var(--success) !important; }
.red    { color:var(--primary) !important; }
.orange { color:var(--warning) !important; }
.blue   { color:var(--cyan) !important; }
.purple { color:var(--purple) !important; }
.muted  { color:var(--muted) !important; }

/* ─── Grid layouts ────────────────────────── */
.two-col       { display:grid; grid-template-columns:3fr 2fr; gap:14px; margin-bottom:14px; }
.two-col-equal { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:14px; }

/* ─── Chart ───────────────────────────────── */
.chart-wrap { height:240px; position:relative; }

/* ─── Insights ────────────────────────────── */
.insight {
  padding:11px 14px; border-radius:8px;
  background:var(--bg3); border-left:3px solid var(--primary);
  font-size:13px; line-height:1.6; margin-bottom:9px;
}
.insight.warn { border-left-color:var(--warning); }
.insight.good { border-left-color:var(--success); }

/* ─── Progress ────────────────────────────── */
.goal-item { margin-bottom:15px; }
.goal-row  {
  display:flex; justify-content:space-between;
  font-size:12.5px; margin-bottom:6px;
}
.progress {
  height:5px; background:var(--bg4);
  border-radius:20px; overflow:hidden;
}
.progress-fill {
  height:100%;
  background:linear-gradient(90deg, var(--success), #34d399);
  border-radius:20px;
  transition:width .7s cubic-bezier(.4,0,.2,1);
  position:relative;
}
.progress-fill::after {
  content:'';
  position:absolute; right:0; top:50%;
  transform:translateY(-50%);
  width:7px; height:7px; border-radius:50%;
  background:inherit;
  box-shadow:0 0 6px rgba(34,197,94,.6);
}
.progress-fill.warn  { background:linear-gradient(90deg,var(--warning),#fb923c); }
.progress-fill.warn::after { box-shadow:0 0 6px rgba(245,158,11,.6); }
.progress-fill.low   { background:linear-gradient(90deg,var(--danger),#f97316); }
.progress-fill.low::after  { box-shadow:0 0 6px rgba(239,68,68,.6); }

/* ─── Badges ──────────────────────────────── */
.badge {
  display:inline-block; padding:2px 9px;
  border-radius:20px; font-size:10.5px;
  font-weight:600; letter-spacing:.2px;
}
.badge-green  { background:rgba(34,197,94,.12);  color:#4ade80; }
.badge-blue   { background:rgba(56,189,248,.12);  color:#7dd3fc; }
.badge-orange { background:rgba(245,158,11,.12);  color:#fbbf24; }
.badge-purple { background:rgba(167,139,250,.12); color:#c4b5fd; }
.badge-red    { background:rgba(239,68,68,.12);   color:#f87171; }
.badge-muted  { background:rgba(100,116,139,.12); color:var(--muted2); }
.badge-pink   { background:rgba(236,72,153,.12);  color:#f9a8d4; }

/* ─── Tables ──────────────────────────────── */
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:12.5px; }
th {
  text-align:left; font-size:10.5px; text-transform:uppercase;
  letter-spacing:.6px; color:var(--muted); padding:6px 10px;
  border-bottom:1px solid var(--border); white-space:nowrap;
}
td { padding:10px 10px; border-bottom:1px solid rgba(255,255,255,.04); vertical-align:middle; }
tr:last-child td { border-bottom:none; }
tr:hover td { background:rgba(255,255,255,.025); }

/* ─── Forms ───────────────────────────────── */
.input {
  background:var(--bg3); border:1px solid var(--border2);
  color:var(--text); border-radius:var(--r);
  padding:9px 12px; font-size:12.5px; font-family:inherit;
  outline:none; transition:border-color .15s, box-shadow .15s;
  width:100%;
}
.input:focus {
  border-color:var(--primary);
  box-shadow:0 0 0 3px var(--prim-dim);
}
.input-grow  { flex:1; min-width:0; width:auto; }
textarea.input { resize:vertical; min-height:80px; }
select.input  { cursor:pointer; }

/* ─── Buttons ─────────────────────────────── */
.btn {
  padding:8px 16px; border-radius:var(--r); border:none;
  cursor:pointer; font-size:12.5px; font-weight:600;
  transition:var(--transition); font-family:inherit;
  white-space:nowrap; display:inline-flex; align-items:center; gap:5px;
}
.btn:hover:not(:disabled) { opacity:.85; transform:translateY(-1px); }
.btn:active:not(:disabled) { transform:scale(.98) !important; }
.btn:disabled { opacity:.35; cursor:default; }
.btn-primary {
  background:var(--primary); color:#fff;
  box-shadow:0 2px 8px rgba(230,57,70,.3);
}
.btn-primary:hover:not(:disabled) {
  box-shadow:0 4px 14px rgba(230,57,70,.45);
}
.btn-outline { background:transparent; border:1px solid var(--border2); color:var(--text); }
.btn-success { background:var(--success); color:#051a0c; }
.btn-ghost   { background:rgba(255,255,255,.05); color:var(--muted2); border:none; }
.btn-sm  { padding:6px 12px; font-size:11.5px; }
.btn-xs  { padding:4px 8px;  font-size:11px; }

/* ─── Flex helpers ────────────────────────── */
.row         { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.row-between { display:flex; justify-content:space-between; align-items:center; }

/* ─── Memory ──────────────────────────────── */
.memory-item {
  display:flex; align-items:flex-start; gap:10px;
  background:var(--bg3); border:1px solid var(--border);
  border-radius:var(--r); padding:11px 13px; margin-bottom:7px;
  transition:border-color .15s;
}
.memory-item:hover { border-color:var(--border2); }
.mem-cat {
  font-size:9.5px; font-weight:700; letter-spacing:.6px;
  text-transform:uppercase; padding:2px 7px; border-radius:4px;
  flex-shrink:0; margin-top:2px;
}
.cat-fact        { background:rgba(56,189,248,.12);  color:#7dd3fc; }
.cat-preference  { background:rgba(167,139,250,.12); color:#c4b5fd; }
.cat-instruction { background:rgba(245,158,11,.12);  color:#fbbf24; }
.cat-event       { background:rgba(34,197,94,.12);   color:#4ade80; }
.mem-text  { flex:1; font-size:13px; line-height:1.55; }
.mem-actions { display:flex; gap:3px; flex-shrink:0; }
.btn-icon {
  background:none; border:none; cursor:pointer;
  color:var(--muted); padding:4px 6px; border-radius:6px;
  font-size:12.5px; transition:color .15s, background .15s;
}
.btn-icon:hover { color:var(--text); background:rgba(255,255,255,.07); }
.btn-icon.del:hover { color:var(--danger); background:rgba(239,68,68,.1); }
.mem-edit {
  background:var(--bg3); border:1px solid var(--primary);
  color:var(--text); border-radius:6px; padding:4px 8px;
  font-size:12.5px; width:100%; outline:none; font-family:inherit;
}

/* ─── Habit row ───────────────────────────── */
.habit-row {
  display:flex; align-items:center; gap:12px;
  padding:11px 0; border-bottom:1px solid var(--border);
}
.habit-row:last-child { border-bottom:none; }
.streak-badge {
  background:var(--prim-dim); color:var(--primary);
  border-radius:6px; padding:3px 9px; font-size:11.5px;
  font-weight:700; font-family:var(--mono); flex-shrink:0;
}

/* ─── Score ring ──────────────────────────── */
.score-ring {
  display:flex; flex-direction:column; align-items:center;
  justify-content:center; padding:20px 0 12px;
}
.score-num {
  font-size:56px; font-weight:800; color:var(--primary);
  line-height:1; font-family:var(--mono); letter-spacing:-2px;
}
.score-sub {
  font-size:10px; color:var(--muted); margin-top:8px;
  text-transform:uppercase; letter-spacing:1.2px;
}

/* ─── Toast ───────────────────────────────── */
.toast {
  position:fixed; bottom:22px; right:22px;
  background:var(--bg3); border:1px solid var(--border2);
  border-radius:var(--r); padding:11px 18px; font-size:12.5px;
  opacity:0; transform:translateY(8px); transition:all .22s;
  pointer-events:none; z-index:9999;
  max-width:300px; box-shadow:var(--shadow-lg);
}
.toast.show { opacity:1; transform:none; }
.toast.success { border-color:var(--success); }
.toast.error   { border-color:var(--danger); }

/* ─── Empty / loader ──────────────────────── */
.empty {
  color:var(--muted); font-size:12.5px;
  text-align:center; padding:28px 0;
}
.loader {
  display:inline-block; width:13px; height:13px;
  border:2px solid rgba(255,255,255,.08);
  border-top-color:var(--primary);
  border-radius:50%; animation:spin .65s linear infinite;
}
@keyframes spin { to { transform:rotate(360deg); } }

/* ─── Divider ─────────────────────────────── */
.divider { height:1px; background:var(--border); margin:14px 0; }

/* ─── Journal entry ───────────────────────── */
.journal-entry { padding:11px 0; border-bottom:1px solid var(--border); }
.journal-entry:last-child { border-bottom:none; }
.journal-meta {
  display:flex; justify-content:space-between;
  font-size:10.5px; color:var(--muted); margin-bottom:5px;
}
.journal-text { font-size:13px; line-height:1.6; color:var(--muted2); }

/* ─── Pill tabs ───────────────────────────── */
.tabs {
  display:flex; gap:4px; background:var(--bg3);
  border-radius:var(--r); padding:4px; margin-bottom:16px;
  width:fit-content;
}
.tab {
  padding:5px 14px; border-radius:7px; border:none;
  cursor:pointer; font-size:12px; font-weight:500;
  color:var(--muted); background:none; transition:var(--transition);
  font-family:inherit;
}
.tab.active { background:var(--bg2); color:var(--text); }

/* ─── Scrollbar (main) ────────────────────── */
.main::-webkit-scrollbar { width:4px; }
.main::-webkit-scrollbar-track { background:transparent; }
.main::-webkit-scrollbar-thumb { background:var(--border2); border-radius:2px; }

/* ─── Responsive ──────────────────────────── */
@media (max-width:1200px) { .metrics-4 { grid-template-columns:repeat(2,1fr); } }
@media (max-width:960px) {
  .shell { grid-template-columns:1fr; }
  .sidebar { display:none; }
  .two-col, .two-col-equal { grid-template-columns:1fr; }
  .main { padding:18px 16px; }
  .metrics-3 { grid-template-columns:1fr 1fr; }
  .metric-val { font-size:22px; }
}
</style>
</head>
<body>
<div class="shell">

  <!-- ── SIDEBAR ─────────────────────────── -->
  <aside class="sidebar">
    <div class="logo">
      <div class="logo-mark">⚡</div>
      <div>
        <div class="logo-title">STARFIRE</div>
        <div class="logo-sub">AI OS</div>
      </div>
    </div>

    <nav>
      <div class="nav-group">
        <span class="nav-label">Overview</span>
        <button class="nav-item active" onclick="nav('dashboard')">
          <span class="nav-icon">⬡</span> Dashboard
        </button>
      </div>

      <div class="nav-group">
        <span class="nav-label">Life</span>
        <button class="nav-item" onclick="nav('goals')">
          <span class="nav-icon">🎯</span> Goals
        </button>
        <button class="nav-item" onclick="nav('life')">
          <span class="nav-icon">💚</span> Life OS
        </button>
        <button class="nav-item" onclick="nav('tasks')">
          <span class="nav-icon">✅</span> Tasks
        </button>
      </div>

      <div class="nav-group">
        <span class="nav-label">Intelligence</span>
        <button class="nav-item" onclick="nav('memory')">
          <span class="nav-icon">🧠</span> Memory
        </button>
        <button class="nav-item" onclick="nav('knowledge')">
          <span class="nav-icon">📚</span> Knowledge
        </button>
        <button class="nav-item" onclick="nav('briefing')">
          <span class="nav-icon">⚡</span> AI Briefing
        </button>
      </div>

      <div class="nav-group">
        <span class="nav-label">Operations</span>
        <button class="nav-item" onclick="nav('business')">
          <span class="nav-icon">🏢</span> Business OS
        </button>
        <button class="nav-item" onclick="nav('automations')">
          <span class="nav-icon">⚙️</span> Automations
        </button>
      </div>
    </nav>

    <div class="sidebar-footer">
      <div class="sys-status">
        <span class="dot dot-green"></span>
        <span id="conn-status">System Online</span>
      </div>
      <div class="sys-status" id="google-status" style="display:none">
        <span class="dot" id="google-dot"></span>
        <span id="google-label">Google</span>
      </div>
      <div class="refresh-ts" id="refresh-time">—</div>
    </div>
  </aside>

  <!-- ── MAIN ─────────────────────────────── -->
  <main class="main">

    <!-- ═══════════════ DASHBOARD ═══════════ -->
    <div class="section active" id="sec-dashboard">
      <div class="topbar">
        <div>
          <div class="page-heading" id="dash-greeting">Good morning</div>
          <div class="page-sub" id="dash-date">—</div>
        </div>
        <div class="user-chip">
          <div class="avatar" id="user-avatar">?</div>
          <div>
            <div class="user-name" id="user-name">—</div>
            <div class="user-sub">STARFIRE OS</div>
          </div>
        </div>
      </div>

      <!-- Metrics row -->
      <div class="metrics-4" style="margin-bottom:14px">
        <div class="metric-card">
          <div class="card-label">Goals Progress</div>
          <div class="metric-val red" id="m-goals">—</div>
          <div class="metric-note" id="m-goals-note">avg completion</div>
        </div>
        <div class="metric-card">
          <div class="card-label">Open Tasks</div>
          <div class="metric-val" id="m-tasks">—</div>
          <div class="metric-note" id="m-tasks-note">—</div>
        </div>
        <div class="metric-card">
          <div class="card-label">Spending MTD</div>
          <div class="metric-val" id="m-spend">—</div>
          <div class="metric-note" id="m-spend-note">this month</div>
        </div>
        <div class="metric-card">
          <div class="card-label">Livelihood Score</div>
          <div class="metric-val purple" id="m-score">—</div>
          <div class="metric-note">wellness index</div>
        </div>
      </div>

      <!-- Chart + Insights -->
      <div class="two-col">
        <div class="card">
          <div class="row-between" style="margin-bottom:14px">
            <div class="card-title" style="margin-bottom:0" id="chart-label">Progress</div>
          </div>
          <div class="chart-wrap"><canvas id="mainChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-title">AI Insights</div>
          <div id="insights-list"><div class="empty"><span class="loader"></span></div></div>
        </div>
      </div>

      <!-- Goals + Score -->
      <div class="two-col-equal">
        <div class="card">
          <div class="card-title">Active Goals</div>
          <div id="dash-goals"><div class="empty"><span class="loader"></span></div></div>
        </div>
        <div class="card">
          <div class="card-title">Livelihood Score</div>
          <div class="score-ring">
            <div class="score-num" id="score-big">—</div>
            <div class="score-sub">AI Wellness Index</div>
          </div>
          <div id="score-breakdown" style="margin-top:8px"></div>
        </div>
      </div>

      <!-- Bot tickets -->
      <div class="card">
        <div class="card-title">Active Bot Tickets</div>
        <div id="dash-tickets"><div class="empty"><span class="loader"></span></div></div>
      </div>
    </div>

    <!-- ═══════════════ GOALS ═════════════════ -->
    <div class="section" id="sec-goals">
      <div class="topbar">
        <div>
          <div class="page-heading">Goals</div>
          <div class="page-sub">Track progress toward every target</div>
        </div>
      </div>
      <div class="card" id="goals-full"><div class="empty"><span class="loader"></span></div></div>
    </div>

    <!-- ═══════════════ LIFE OS ══════════════ -->
    <div class="section" id="sec-life">
      <div class="topbar">
        <div>
          <div class="page-heading">Life OS</div>
          <div class="page-sub">Habits · Journal · Health</div>
        </div>
      </div>

      <div class="card" style="margin-bottom:14px">
        <div class="row-between" style="margin-bottom:14px">
          <div class="card-title" style="margin-bottom:0">Habits</div>
          <button class="btn btn-primary btn-sm" onclick="showAddHabit()">+ Add</button>
        </div>
        <div id="habit-add-form" style="display:none;margin-bottom:14px">
          <div class="row">
            <input id="habit-name" class="input input-grow" placeholder="Habit name" />
            <select id="habit-freq" class="input" style="width:120px">
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </select>
            <button class="btn btn-primary btn-sm" onclick="saveHabit()">Save</button>
            <button class="btn btn-outline btn-sm" onclick="document.getElementById('habit-add-form').style.display='none'">Cancel</button>
          </div>
        </div>
        <div id="habits-list"><div class="empty"><span class="loader"></span></div></div>
      </div>

      <div class="two-col-equal">
        <div class="card">
          <div class="row-between" style="margin-bottom:14px">
            <div class="card-title" style="margin-bottom:0">Journal</div>
            <button class="btn btn-primary btn-sm" onclick="showJournalForm()">+ Entry</button>
          </div>
          <div id="journal-form" style="display:none;margin-bottom:14px">
            <textarea id="jrnl-content" class="input" placeholder="How are you feeling today?"></textarea>
            <div class="row" style="margin-top:8px">
              <input id="jrnl-mood"     class="input" style="width:80px" type="number" min="1" max="10" placeholder="Mood" />
              <input id="jrnl-energy"   class="input" style="width:80px" type="number" min="1" max="10" placeholder="Energy" />
              <input id="jrnl-gratitude" class="input input-grow" placeholder="Grateful for…" />
            </div>
            <div class="row" style="margin-top:8px">
              <button class="btn btn-primary btn-sm" onclick="saveJournal()">Save</button>
              <button class="btn btn-outline btn-sm" onclick="document.getElementById('journal-form').style.display='none'">Cancel</button>
            </div>
          </div>
          <div id="journal-list"><div class="empty"><span class="loader"></span></div></div>
        </div>
        <div class="card">
          <div class="row-between" style="margin-bottom:14px">
            <div class="card-title" style="margin-bottom:0">Health</div>
            <button class="btn btn-primary btn-sm" onclick="showHealthForm()">+ Log</button>
          </div>
          <div id="health-form" style="display:none;margin-bottom:14px">
            <div class="row">
              <select id="h-type" class="input input-grow">
                <option value="weight">Weight (lbs)</option>
                <option value="sleep_hours">Sleep (hrs)</option>
                <option value="steps">Steps</option>
                <option value="heart_rate">Heart Rate (bpm)</option>
                <option value="water_oz">Water (oz)</option>
              </select>
              <input id="h-value" class="input" style="width:90px" type="number" placeholder="Value" step="0.1" />
              <button class="btn btn-primary btn-sm" onclick="saveHealth()">Log</button>
              <button class="btn btn-outline btn-sm" onclick="document.getElementById('health-form').style.display='none'">Cancel</button>
            </div>
          </div>
          <div id="health-list"><div class="empty"><span class="loader"></span></div></div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ TASKS ════════════════ -->
    <div class="section" id="sec-tasks">
      <div class="topbar">
        <div>
          <div class="page-heading">Tasks</div>
          <div class="page-sub">Open tasks and bot tickets</div>
        </div>
      </div>
      <div class="card" style="margin-bottom:14px">
        <div class="card-title">Open Tasks</div>
        <div class="table-wrap" id="tasks-full"><div class="empty"><span class="loader"></span></div></div>
      </div>
      <div class="card">
        <div class="card-title">Bot Tickets</div>
        <div class="table-wrap" id="tickets-full"><div class="empty"><span class="loader"></span></div></div>
      </div>
    </div>

    <!-- ═══════════════ MEMORY ═══════════════ -->
    <div class="section" id="sec-memory">
      <div class="topbar">
        <div>
          <div class="page-heading">Memory</div>
          <div class="page-sub">What STARFIRE remembers about you</div>
        </div>
      </div>
      <div class="card">
        <div class="row-between" style="margin-bottom:14px">
          <div class="card-title" style="margin-bottom:0">
            Stored Memories
            <span id="mem-count" style="color:var(--primary);font-family:var(--mono);font-weight:700;margin-left:4px"></span>
          </div>
        </div>
        <div id="mem-list"><div class="empty"><span class="loader"></span></div></div>
        <div class="divider"></div>
        <div class="row">
          <input id="mem-content" class="input input-grow" placeholder="Add memory — fact, preference, instruction…" />
          <select id="mem-cat" class="input" style="width:130px">
            <option value="fact">🧠 Fact</option>
            <option value="preference">⚙️ Preference</option>
            <option value="instruction">📌 Instruction</option>
            <option value="event">📅 Event</option>
          </select>
          <select id="mem-imp" class="input" style="width:90px">
            <option value="8">High</option>
            <option value="5" selected>Normal</option>
            <option value="2">Low</option>
          </select>
          <button class="btn btn-primary" onclick="addMemory()">+ Add</button>
        </div>
      </div>
    </div>

    <!-- ═══════════════ KNOWLEDGE ════════════ -->
    <div class="section" id="sec-knowledge">
      <div class="topbar">
        <div>
          <div class="page-heading">Knowledge</div>
          <div class="page-sub">Notes, ideas, documents — semantic search powered</div>
        </div>
      </div>
      <div class="card">
        <div class="row" style="margin-bottom:14px">
          <input id="know-search" class="input input-grow" placeholder="Search knowledge base…" oninput="searchKnowledge()" />
          <button class="btn btn-primary btn-sm" onclick="showAddKnowledge()">+ Add</button>
        </div>
        <div id="know-add-form" style="display:none;margin-bottom:14px;background:var(--bg3);border-radius:var(--r);padding:14px">
          <input id="know-title" class="input" style="margin-bottom:8px" placeholder="Title" />
          <textarea id="know-content" class="input" placeholder="Content…"></textarea>
          <div class="row" style="margin-top:8px">
            <select id="know-type" class="input" style="width:130px">
              <option value="note">Note</option>
              <option value="idea">Idea</option>
              <option value="document">Document</option>
              <option value="research">Research</option>
              <option value="reference">Reference</option>
            </select>
            <input id="know-tags" class="input input-grow" placeholder="Tags (comma-separated)" />
            <button class="btn btn-primary btn-sm" onclick="saveKnowledge()">Save</button>
            <button class="btn btn-outline btn-sm" onclick="hideAddKnowledge()">Cancel</button>
          </div>
        </div>
        <div id="know-list"><div class="empty"><span class="loader"></span></div></div>
      </div>
    </div>

    <!-- ═══════════════ AI BRIEFING ══════════ -->
    <div class="section" id="sec-briefing">
      <div class="topbar">
        <div>
          <div class="page-heading">AI Briefing</div>
          <div class="page-sub">Briefings, CFO analysis, and research synthesis</div>
        </div>
      </div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">Generate Briefing</div>
        <div class="row" style="margin-bottom:14px">
          <select id="brief-type" class="input" style="width:150px">
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
          </select>
          <button class="btn btn-primary" id="btn-brief" onclick="runBriefing()">Generate</button>
        </div>
        <div id="brief-output" style="display:none">
          <div style="font-size:10.5px;color:var(--muted);margin-bottom:10px;font-family:var(--mono)" id="brief-ts"></div>
          <div id="brief-text" style="line-height:1.8;font-size:13.5px;white-space:pre-wrap;color:var(--muted2)"></div>
        </div>
      </div>

      <div class="two-col-equal">
        <div class="card">
          <div class="card-title">CFO Agent</div>
          <div style="color:var(--muted);font-size:12.5px;margin-bottom:14px;line-height:1.6">
            Full financial analysis — spending trends, P&amp;L, cash flow, and recommendations.
          </div>
          <button class="btn btn-primary btn-sm" id="btn-cfo" onclick="runAgent('cfo','btn-cfo','cfo-out')">Run CFO Analysis</button>
          <div id="cfo-out" style="display:none;margin-top:14px;font-size:12.5px;line-height:1.7;color:var(--muted2);white-space:pre-wrap"></div>
        </div>
        <div class="card">
          <div class="card-title">Research Agent</div>
          <div style="color:var(--muted);font-size:12.5px;margin-bottom:14px;line-height:1.6">
            Semantic search across your knowledge base — synthesises notes, ideas, and documents.
          </div>
          <div class="row" style="margin-bottom:10px">
            <input id="research-q" class="input input-grow" placeholder="Research query…" />
          </div>
          <button class="btn btn-primary btn-sm" id="btn-research" onclick="runAgent('research','btn-research','research-out')">Run Research</button>
          <div id="research-out" style="display:none;margin-top:14px;font-size:12.5px;line-height:1.7;color:var(--muted2);white-space:pre-wrap"></div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ BUSINESS OS ══════════ -->
    <div class="section" id="sec-business">
      <div class="topbar">
        <div>
          <div class="page-heading">Business OS</div>
          <div class="page-sub">Revenue, clients, and invoices</div>
        </div>
      </div>
      <div id="biz-overview" style="margin-bottom:14px"></div>
      <div class="card" style="margin-bottom:14px">
        <div class="row-between" style="margin-bottom:14px">
          <div class="card-title" style="margin-bottom:0">Businesses</div>
          <button class="btn btn-primary btn-sm" onclick="showAddBiz()">+ Add</button>
        </div>
        <div id="biz-add-form" style="display:none;margin-bottom:14px;background:var(--bg3);border-radius:var(--r);padding:14px">
          <div class="row">
            <input id="biz-name" class="input input-grow" placeholder="Business name" />
            <input id="biz-mrr" class="input" style="width:110px" type="number" placeholder="MRR ($)" />
            <select id="biz-type" class="input" style="width:130px">
              <option value="saas">SaaS</option>
              <option value="service">Service</option>
              <option value="ecommerce">E-commerce</option>
              <option value="other">Other</option>
            </select>
            <button class="btn btn-primary btn-sm" onclick="saveBiz()">Save</button>
            <button class="btn btn-outline btn-sm" onclick="document.getElementById('biz-add-form').style.display='none'">Cancel</button>
          </div>
        </div>
        <div id="biz-list"><div class="empty"><span class="loader"></span></div></div>
      </div>
      <div class="card">
        <div class="card-title">Invoices</div>
        <div id="invoice-list"><div class="empty"><span class="loader"></span></div></div>
      </div>
    </div>

    <!-- ═══════════════ AUTOMATIONS ══════════ -->
    <div class="section" id="sec-automations">
      <div class="topbar">
        <div>
          <div class="page-heading">Automations</div>
          <div class="page-sub">Trigger rules and run history</div>
        </div>
      </div>
      <div class="card" style="margin-bottom:14px">
        <div class="row-between" style="margin-bottom:14px">
          <div class="card-title" style="margin-bottom:0">Active Rules</div>
          <button class="btn btn-primary btn-sm" onclick="installPresets()">+ Install Presets</button>
        </div>
        <div id="auto-list"><div class="empty"><span class="loader"></span></div></div>
      </div>
      <div class="card">
        <div class="card-title">Recent Runs</div>
        <div id="auto-runs"><div class="empty"><span class="loader"></span></div></div>
      </div>
    </div>

  </main>
</div>

<div class="toast" id="toast"></div>

<script>
const TOKEN = '__TOKEN__';
const API   = '/dashboard/api';

// ── Nav ──────────────────────────────────────────────────────────────────────
function nav(id) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const sec = document.getElementById('sec-' + id);
  if (sec) sec.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => {
    if (n.textContent.trim().toLowerCase().replace(/\\s/g,'').includes(id.toLowerCase().replace(/\\s/g,'')))
      n.classList.add('active');
  });
  if (id === 'memory'      && !window._memLoaded)    loadMemories();
  if (id === 'knowledge'   && !window._knowLoaded)   loadKnowledge();
  if (id === 'life'        && !window._lifeLoaded)   loadLife();
  if (id === 'business'    && !window._bizLoaded)    loadBusiness();
  if (id === 'automations' && !window._autoLoaded)   loadAutomations();
}

// ── Utilities ────────────────────────────────────────────────────────────────
function toast(msg, type) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show ' + (type || 'success');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), 2800);
}

function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML;
}

function money(n, d = 0) {
  if (n == null || isNaN(n)) return '—';
  return '$' + Number(n).toLocaleString('en-US', {minimumFractionDigits:d, maximumFractionDigits:d});
}

function statusBadge(s) {
  const map = { QUEUED:'badge-orange', SENT:'badge-blue', IN_PROGRESS:'badge-blue', DONE:'badge-green', FAILED:'badge-red' };
  return `<span class="badge ${map[s]||'badge-muted'}">${esc(s)}</span>`;
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

// ── Core data ────────────────────────────────────────────────────────────────
let _data = null;
let _chart = null;
let memories = [];

async function loadAll() {
  try {
    const res = await fetch(`${API}/data?token=${TOKEN}`);
    _data = await res.json();
  } catch { _data = {}; }

  renderTopbar();
  renderMetrics();
  renderDashGoals();
  renderInsights();
  renderDashTickets();
  renderChart();
  document.getElementById('refresh-time').textContent =
    'Last sync ' + new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
}

function renderTopbar() {
  const name = _data?.user?.name || 'Operator';
  document.getElementById('user-name').textContent = name;
  document.getElementById('user-avatar').textContent = (name[0]||'?').toUpperCase();
  document.getElementById('dash-greeting').textContent = greeting() + ', ' + name.split(' ')[0];
  const now = new Date();
  document.getElementById('dash-date').textContent =
    now.toLocaleDateString('en-US', {weekday:'long', month:'long', day:'numeric', year:'numeric'});
}

function renderMetrics() {
  const d = _data || {};
  const goals   = d.goals   || [];
  const tasks   = d.tasks   || [];
  const tickets = d.tickets || [];

  let avgPct = 0;
  if (goals.length) {
    const pcts = goals.map(g => g.target > 0 ? Math.min(100,(g.current/g.target)*100) : 0);
    avgPct = Math.round(pcts.reduce((a,b)=>a+b,0)/pcts.length);
  }
  document.getElementById('m-goals').textContent = goals.length ? avgPct + '%' : '—';
  document.getElementById('m-goals-note').textContent = goals.length
    ? `across ${goals.length} goal${goals.length>1?'s':''}` : 'no active goals';

  document.getElementById('m-tasks').textContent = tasks.length || '0';
  document.getElementById('m-tasks-note').textContent =
    tickets.length ? `${tickets.length} ticket${tickets.length>1?'s':''} open` : 'no open tickets';

  const exp = d.spending_this_month || 0;
  const spEl = document.getElementById('m-spend');
  spEl.textContent = exp > 0 ? money(exp) : '—';
  spEl.style.color = exp > 5000 ? 'var(--danger)' : exp > 3000 ? 'var(--warning)' : 'var(--text)';
  const cats = d.spending_by_category || [];
  document.getElementById('m-spend-note').textContent =
    cats.length ? `${cats.length} categor${cats.length>1?'ies':'y'}` : 'no records yet';

  let score = 15;
  if (goals.length) score += Math.round(avgPct * 0.4);
  if (tasks.length < 5) score += 20;
  if (exp > 0) score += 15;
  if (tickets.length === 0) score += 10;
  score = Math.min(99, score);
  const scEl = document.getElementById('m-score');
  scEl.textContent = score;
  const scColor = score >= 70 ? 'var(--success)' : score >= 50 ? 'var(--warning)' : 'var(--danger)';
  scEl.style.color = scColor;
  document.getElementById('score-big').textContent = score;
  document.getElementById('score-big').style.color = scColor;
  document.getElementById('score-breakdown').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11.5px;color:var(--muted)">
      <div>Goals <b style="color:var(--text)">${avgPct}%</b></div>
      <div>Tasks <b style="color:var(--text)">${tasks.length}</b></div>
      <div>Spend <b style="color:var(--text)">${money(exp)}</b></div>
      <div>Tickets <b style="color:var(--text)">${tickets.length}</b></div>
    </div>`;
}

function renderChart() {
  const ctx = document.getElementById('mainChart');
  if (_chart) { _chart.destroy(); _chart = null; }
  const goals = _data?.goals || [];
  const cats  = (_data?.spending_by_category || []).slice(0,7);

  Chart.defaults.color = '#64748b';
  Chart.defaults.borderColor = 'rgba(255,255,255,.05)';

  if (cats.length >= 2) {
    document.getElementById('chart-label').textContent = 'Spending This Month';
    _chart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: cats.map(c => c.category),
        datasets:[{
          data: cats.map(c=>c.total),
          backgroundColor:['#e63946','#22c55e','#f59e0b','#7c3aed','#a78bfa','#ec4899','#22d3ee'],
          borderWidth:0,
          hoverOffset:6,
        }],
      },
      options:{
        responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{ labels:{ color:'#64748b', font:{size:11}, boxWidth:10 }}},
        cutout:'65%',
      },
    });
  } else if (goals.length) {
    document.getElementById('chart-label').textContent = 'Goals Progress';
    const pcts = goals.map(g => g.target>0 ? Math.min(100,Math.round((g.current/g.target)*100)) : 0);
    _chart = new Chart(ctx, {
      type: 'bar',
      data:{
        labels: goals.map(g => g.title.length>22 ? g.title.slice(0,22)+'…' : g.title),
        datasets:[{
          label:'% complete', data:pcts,
          backgroundColor:pcts.map(p => p>=80?'rgba(34,197,94,.8)':p>=50?'rgba(230,57,70,.8)':'rgba(245,158,11,.8)'),
          borderRadius:6, borderSkipped:false,
        }],
      },
      options:{
        indexAxis:'y', responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{ display:false }},
        scales:{
          x:{ ticks:{color:'#64748b',callback:v=>v+'%'}, max:100, grid:{color:'rgba(255,255,255,.04)'}},
          y:{ ticks:{color:'#94a3b8'}, grid:{display:false}},
        },
      },
    });
  } else {
    ctx.closest('.chart-wrap').innerHTML =
      '<div class="empty" style="padding-top:80px">Add goals or log spending to see charts</div>';
  }
}

function renderInsights() {
  const el = document.getElementById('insights-list');
  const d = _data || {};
  const insights = [];
  const goals   = d.goals   || [];
  const tasks   = d.tasks   || [];
  const tickets = d.tickets || [];
  const exp     = d.spending_this_month || 0;
  const cats    = d.spending_by_category || [];

  if (goals.length) {
    const top = goals[0];
    const pct = top.target>0 ? Math.round((top.current/top.target)*100) : 0;
    insights.push({text:`Top goal <b>${esc(top.title)}</b> is ${pct}% complete.`, type:pct>=80?'good':''});
  }
  if (exp > 0) {
    const topCat = cats[0];
    insights.push({text:`Spent <b>${money(exp)}</b> this month${topCat?` — largest: <b>${esc(topCat.category)}</b>`:''}`, type:exp>5000?'warn':''});
  }
  if (tickets.length) {
    insights.push({text:`<b>${tickets.length}</b> bot ticket${tickets.length>1?'s':''} need attention.`, type:'warn'});
  }
  if (tasks.length === 0) {
    insights.push({text:'Task queue is clear — nothing pending.', type:'good'});
  } else if (tasks.length > 10) {
    insights.push({text:`<b>${tasks.length}</b> open tasks — consider clearing the backlog.`, type:'warn'});
  }
  if (!insights.length) {
    el.innerHTML = '<div class="empty">Add goals and spending to see insights</div>';
    return;
  }
  el.innerHTML = insights.slice(0,4).map(i =>
    `<div class="insight ${i.type||''}">${i.text}</div>`).join('');
}

function renderDashGoals() {
  const el = document.getElementById('dash-goals');
  const goals = (_data?.goals||[]).slice(0,5);
  if (!goals.length) {
    el.innerHTML = '<div class="empty">No goals — tell STARFIRE to create one via Telegram</div>';
    return;
  }
  el.innerHTML = goals.map(g => {
    const pct = g.target>0 ? Math.min(100,Math.round((g.current/g.target)*100)) : 0;
    return `<div class="goal-item">
      <div class="goal-row">
        <span style="font-weight:500">${esc(g.title)}</span>
        <span style="color:var(--muted2);font-family:var(--mono);font-size:11.5px">${pct}%</span>
      </div>
      <div class="progress">
        <div class="progress-fill ${pct<30?'low':pct<60?'warn':''}" style="width:${pct}%"></div>
      </div>
    </div>`;
  }).join('');
}

function renderDashTickets() {
  const el = document.getElementById('dash-tickets');
  const tickets = (_data?.tickets||[]).slice(0,5);
  if (!tickets.length) {
    el.innerHTML = '<div class="empty">All clear — no active tickets</div>';
    return;
  }
  el.innerHTML = `<div class="table-wrap"><table>
    <tr><th>#</th><th>Title</th><th>Bot</th><th>Status</th><th>Priority</th></tr>
    ${tickets.map(t=>`<tr>
      <td style="color:var(--muted);font-family:var(--mono)">${t.id}</td>
      <td>${esc(t.title)}</td>
      <td><span class="badge badge-blue">${esc(t.assigned_to)}</span></td>
      <td>${statusBadge(t.status)}</td>
      <td style="font-family:var(--mono);color:var(--muted)">${t.priority}</td>
    </tr>`).join('')}
  </table></div>`;
}

// ── Goals full ───────────────────────────────────────────────────────────────
function renderGoalsFull() {
  const el = document.getElementById('goals-full');
  const goals = _data?.goals || [];
  if (!goals.length) {
    el.innerHTML = '<div class="empty">No active goals — tell STARFIRE to set one via Telegram</div>';
    return;
  }
  el.innerHTML = `<div class="card-title">Goals (${goals.length})</div>` +
    goals.map(g => {
      const pct = g.target>0 ? Math.min(100,Math.round((g.current/g.target)*100)) : 0;
      return `<div class="goal-item">
        <div class="goal-row">
          <span style="font-weight:500">${esc(g.title)}</span>
          <span style="font-family:var(--mono);font-size:11.5px;color:var(--muted2)">
            ${g.current} / ${g.target} ${esc(g.unit||'')} &middot; <b>${pct}%</b>
          </span>
        </div>
        <div class="progress">
          <div class="progress-fill ${pct<30?'low':pct<60?'warn':''}" style="width:${pct}%"></div>
        </div>
      </div>`;
    }).join('');
}

// ── Tasks full ───────────────────────────────────────────────────────────────
function renderTasksFull() {
  const tasks   = _data?.tasks   || [];
  const tickets = _data?.tickets || [];

  const tEl = document.getElementById('tasks-full');
  if (!tasks.length) {
    tEl.innerHTML = '<div class="empty">No pending tasks</div>';
  } else {
    tEl.innerHTML = `<table>
      <tr><th>Task</th><th>Priority</th><th>Due</th></tr>
      ${tasks.map(t=>`<tr>
        <td>${esc(t.title)}</td>
        <td style="color:${t.priority>=8?'var(--danger)':t.priority>=5?'var(--warning)':'var(--muted)'}; font-family:var(--mono)">${t.priority}</td>
        <td style="color:var(--muted);font-family:var(--mono)">${t.due?t.due.slice(0,10):'—'}</td>
      </tr>`).join('')}
    </table>`;
  }

  const tckEl = document.getElementById('tickets-full');
  if (!tickets.length) {
    tckEl.innerHTML = '<div class="empty">No open tickets</div>';
  } else {
    tckEl.innerHTML = `<table>
      <tr><th>#</th><th>Title</th><th>Assigned To</th><th>Status</th></tr>
      ${tickets.map(t=>`<tr>
        <td style="color:var(--muted);font-family:var(--mono)">${t.id}</td>
        <td>${esc(t.title)}</td>
        <td><span class="badge badge-blue">${esc(t.assigned_to)}</span></td>
        <td>${statusBadge(t.status)}</td>
      </tr>`).join('')}
    </table>`;
  }
}

// ── Memory ───────────────────────────────────────────────────────────────────
window._memLoaded = false;

async function loadMemories() {
  window._memLoaded = true;
  try {
    const res = await fetch(`${API}/memories?token=${TOKEN}`);
    memories = await res.json();
    renderMemories();
  } catch {
    document.getElementById('mem-list').innerHTML = '<div class="empty">Failed to load memories</div>';
  }
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
  if (!c) { toast('Enter content first', 'error'); return; }
  const res = await fetch(`${API}/memories?token=${TOKEN}`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ content:c, category:document.getElementById('mem-cat').value, importance:parseInt(document.getElementById('mem-imp').value) }),
  });
  if (res.ok) { document.getElementById('mem-content').value=''; toast('Memory saved ✓'); await loadMemories(); }
  else toast('Failed to save', 'error');
}

function editMem(id) {
  const m = memories.find(x=>x.id===id);
  if (!m) return;
  document.getElementById('mt-'+id).innerHTML =
    `<textarea class="mem-edit" id="me-${id}" rows="2">${esc(m.content)}</textarea>
     <div class="row" style="margin-top:6px">
       <button class="btn btn-primary btn-xs" onclick="saveMem(${id})">Save</button>
       <button class="btn btn-outline btn-xs" onclick="renderMemories()">Cancel</button>
     </div>`;
  document.getElementById('me-'+id).focus();
}

async function saveMem(id) {
  const val = document.getElementById('me-'+id).value.trim();
  if (!val) return;
  const res = await fetch(`${API}/memories/${id}?token=${TOKEN}`, {
    method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({content:val}),
  });
  if (res.ok) { toast('Updated ✓'); await loadMemories(); }
  else toast('Update failed', 'error');
}

async function deleteMem(id) {
  if (!confirm('Delete this memory?')) return;
  const res = await fetch(`${API}/memories/${id}?token=${TOKEN}`, { method:'DELETE' });
  if (res.ok) { toast('Deleted'); await loadMemories(); }
  else toast('Failed', 'error');
}

// ── Knowledge ────────────────────────────────────────────────────────────────
window._knowLoaded = false;
let _knowItems = [];

async function loadKnowledge() {
  window._knowLoaded = true;
  try {
    const res = await fetch(`/api/knowledge?token=${TOKEN}`);
    _knowItems = await res.json();
    renderKnowledge(_knowItems);
  } catch {
    document.getElementById('know-list').innerHTML = '<div class="empty">Failed to load</div>';
  }
}

function renderKnowledge(items) {
  const el = document.getElementById('know-list');
  if (!items.length) {
    el.innerHTML = '<div class="empty">No knowledge items yet — add notes, ideas, or documents</div>';
    return;
  }
  const typeColor = {note:'badge-blue',idea:'badge-purple',document:'badge-green',research:'badge-orange',reference:'badge-muted'};
  el.innerHTML = items.map(k => `
    <div class="memory-item">
      <div style="flex:1">
        <div class="row" style="margin-bottom:5px">
          <span class="badge ${typeColor[k.item_type]||'badge-blue'}">${esc(k.item_type)}</span>
          <b style="font-size:13.5px">${esc(k.title)}</b>
        </div>
        <div style="font-size:12.5px;color:var(--muted2);line-height:1.55">${esc((k.content||'').slice(0,180))}${k.content?.length>180?'…':''}</div>
        ${k.tags?.length?`<div style="margin-top:6px">${k.tags.map(t=>`<span class="badge badge-muted" style="margin-right:3px">${esc(t)}</span>`).join('')}</div>`:''}
      </div>
      <button class="btn-icon del" onclick="deleteKnowledge(${k.id})">🗑</button>
    </div>`).join('');
}

function searchKnowledge() {
  const q = document.getElementById('know-search').value.toLowerCase().trim();
  if (!q) { renderKnowledge(_knowItems); return; }
  renderKnowledge(_knowItems.filter(k=>k.title.toLowerCase().includes(q)||(k.content||'').toLowerCase().includes(q)));
}
function showAddKnowledge() { document.getElementById('know-add-form').style.display='block'; document.getElementById('know-title').focus(); }
function hideAddKnowledge() { document.getElementById('know-add-form').style.display='none'; }

async function saveKnowledge() {
  const title   = document.getElementById('know-title').value.trim();
  const content = document.getElementById('know-content').value.trim();
  if (!title||!content) { toast('Title and content required','error'); return; }
  const tags = document.getElementById('know-tags').value.split(',').map(t=>t.trim()).filter(Boolean);
  const res = await fetch(`/api/knowledge?token=${TOKEN}`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title,content,item_type:document.getElementById('know-type').value,tags}),
  });
  if (res.ok) {
    toast('Saved ✓'); hideAddKnowledge();
    document.getElementById('know-title').value='';
    document.getElementById('know-content').value='';
    window._knowLoaded=false; loadKnowledge();
  } else toast('Save failed','error');
}

async function deleteKnowledge(id) {
  if (!confirm('Delete this item?')) return;
  const res = await fetch(`/api/knowledge/${id}?token=${TOKEN}`,{method:'DELETE'});
  if (res.ok){toast('Deleted');window._knowLoaded=false;loadKnowledge();}
  else toast('Failed','error');
}

// ── Life OS ──────────────────────────────────────────────────────────────────
window._lifeLoaded = false;

async function loadLife() {
  window._lifeLoaded = true;
  await Promise.all([loadHabits(), loadJournal(), loadHealth()]);
}

async function loadHabits() {
  try {
    const res = await fetch(`/api/life/habits?token=${TOKEN}`);
    renderHabits(await res.json());
  } catch {
    document.getElementById('habits-list').innerHTML='<div class="empty">Failed to load</div>';
  }
}

function renderHabits(habits) {
  const el = document.getElementById('habits-list');
  if (!habits.length) { el.innerHTML='<div class="empty">No habits yet — click + Add</div>'; return; }
  el.innerHTML = habits.map(h => {
    const streak = h.current_streak||0;
    return `<div class="habit-row">
      <div style="flex:1">
        <div style="font-weight:600;font-size:13.5px">${esc(h.name)}</div>
        <div style="font-size:11.5px;color:var(--muted);margin-top:2px">${esc(h.frequency)} &middot; ${h.total_completions||0} completions</div>
      </div>
      <div class="streak-badge">${streak} 🔥</div>
      <button class="btn btn-success btn-sm" onclick="completeHabit(${h.id})">✓ Done</button>
    </div>`;
  }).join('');
}

async function completeHabit(id) {
  const res = await fetch(`/api/life/habits/${id}/complete?token=${TOKEN}`,{method:'POST'});
  if (res.ok){toast('Habit logged ✓ 🔥');await loadHabits();}
  else toast('Failed','error');
}

function showAddHabit() {
  document.getElementById('habit-add-form').style.display='block';
  document.getElementById('habit-name').focus();
}

async function saveHabit() {
  const name = document.getElementById('habit-name').value.trim();
  if (!name){toast('Name required','error');return;}
  const res = await fetch(`/api/life/habits?token=${TOKEN}`,{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,frequency:document.getElementById('habit-freq').value}),
  });
  if (res.ok){
    toast('Habit created ✓');
    document.getElementById('habit-add-form').style.display='none';
    document.getElementById('habit-name').value='';
    await loadHabits();
  } else toast('Failed','error');
}

async function loadJournal() {
  try {
    const res = await fetch(`/api/life/journal?token=${TOKEN}&limit=5`);
    const entries = await res.json();
    const el = document.getElementById('journal-list');
    if (!entries.length){el.innerHTML='<div class="empty">No journal entries yet</div>';return;}
    el.innerHTML = entries.map(j=>`
      <div class="journal-entry">
        <div class="journal-meta">
          <span>${(j.entry_date||j.created_at||'').slice(0,10)}</span>
          <span>${j.mood?'😊 '+j.mood+'/10':''} ${j.energy?'⚡'+j.energy+'/10':''}</span>
        </div>
        <div class="journal-text">${esc((j.content||'').slice(0,200))}${j.content?.length>200?'…':''}</div>
        ${j.gratitude?`<div style="font-size:11.5px;color:var(--muted);margin-top:4px">🙏 ${esc(j.gratitude)}</div>`:''}
      </div>`).join('');
  } catch {
    document.getElementById('journal-list').innerHTML='<div class="empty">Failed to load</div>';
  }
}

function showJournalForm(){document.getElementById('journal-form').style.display='block';document.getElementById('jrnl-content').focus();}

async function saveJournal() {
  const content = document.getElementById('jrnl-content').value.trim();
  if (!content){toast('Write something first','error');return;}
  const body = {
    content,
    entry_date:new Date().toISOString().slice(0,10),
    mood:parseInt(document.getElementById('jrnl-mood').value)||null,
    energy:parseInt(document.getElementById('jrnl-energy').value)||null,
    gratitude:document.getElementById('jrnl-gratitude').value.trim()||null,
  };
  const res = await fetch(`/api/life/journal?token=${TOKEN}`,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),
  });
  if (res.ok){
    toast('Entry saved ✓');
    document.getElementById('journal-form').style.display='none';
    ['jrnl-content','jrnl-mood','jrnl-energy','jrnl-gratitude'].forEach(id=>document.getElementById(id).value='');
    await loadJournal();
  } else toast('Failed','error');
}

async function loadHealth() {
  try {
    const res = await fetch(`/api/life/health?token=${TOKEN}&limit=10`);
    const metrics = await res.json();
    const el = document.getElementById('health-list');
    if (!metrics.length){el.innerHTML='<div class="empty">No health data — click + Log</div>';return;}
    el.innerHTML=`<table>
      <tr><th>Metric</th><th>Value</th><th>Date</th></tr>
      ${metrics.map(m=>`<tr>
        <td style="text-transform:capitalize">${esc(m.metric_type.replace(/_/g,' '))}</td>
        <td><b style="font-family:var(--mono)">${m.value}</b> <span style="color:var(--muted)">${esc(m.unit||'')}</span></td>
        <td style="color:var(--muted);font-family:var(--mono)">${(m.recorded_at||m.created_at||'').slice(0,10)}</td>
      </tr>`).join('')}
    </table>`;
  } catch {
    document.getElementById('health-list').innerHTML='<div class="empty">Failed to load</div>';
  }
}

function showHealthForm(){document.getElementById('health-form').style.display='block';document.getElementById('h-value').focus();}

async function saveHealth() {
  const value = parseFloat(document.getElementById('h-value').value);
  if (isNaN(value)){toast('Enter a value','error');return;}
  const typeMap = {weight:'lbs',sleep_hours:'hrs',steps:'steps',heart_rate:'bpm',water_oz:'oz'};
  const mtype = document.getElementById('h-type').value;
  const res = await fetch(`/api/life/health?token=${TOKEN}`,{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({metric_type:mtype,value,unit:typeMap[mtype]||'',recorded_at:new Date().toISOString()}),
  });
  if (res.ok){
    toast('Logged ✓');
    document.getElementById('health-form').style.display='none';
    document.getElementById('h-value').value='';
    await loadHealth();
  } else toast('Failed','error');
}

// ── Business OS ──────────────────────────────────────────────────────────────
window._bizLoaded = false;

async function loadBusiness() {
  window._bizLoaded = true;
  try {
    const [ovRes,bizRes,invRes] = await Promise.all([
      fetch(`/api/business/overview?token=${TOKEN}`),
      fetch(`/api/business/businesses?token=${TOKEN}`),
      fetch(`/api/business/invoices?token=${TOKEN}`),
    ]);
    renderBizOverview(await ovRes.json());
    renderBizList(await bizRes.json());
    renderInvoices(await invRes.json());
  } catch {
    document.getElementById('biz-list').innerHTML='<div class="empty">Failed to load</div>';
  }
}

function renderBizOverview(ov) {
  const el = document.getElementById('biz-overview');
  if (!ov||ov.total_businesses===0){el.innerHTML='';return;}
  el.innerHTML=`<div class="metrics-4">
    <div class="metric-card"><div class="card-label">Total MRR</div><div class="metric-val green">${money(ov.total_mrr||0)}</div></div>
    <div class="metric-card"><div class="card-label">Total ARR</div><div class="metric-val blue">${money(ov.total_arr||0)}</div></div>
    <div class="metric-card"><div class="card-label">Businesses</div><div class="metric-val">${ov.total_businesses||0}</div></div>
    <div class="metric-card"><div class="card-label">Open Invoices</div><div class="metric-val orange">${money(ov.open_invoices_value||0)}</div></div>
  </div>`;
}

function renderBizList(biz) {
  const el = document.getElementById('biz-list');
  if (!biz.length){el.innerHTML='<div class="empty">No businesses yet — click + Add</div>';return;}
  el.innerHTML=biz.map(b=>`
    <div style="display:flex;align-items:center;gap:14px;padding:12px 0;border-bottom:1px solid var(--border)">
      <div style="flex:1">
        <div style="font-weight:600;font-size:14px">${esc(b.name)}</div>
        <div style="font-size:11.5px;color:var(--muted)">${esc(b.business_type||'')} &middot; ${esc(b.status||'active')}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:16px;font-weight:700;color:var(--success);font-family:var(--mono)">${money(b.mrr||0)}<span style="font-size:10.5px;color:var(--muted)">/mo</span></div>
        <div style="font-size:11px;color:var(--muted)">ARR ${money(b.arr||0)}</div>
      </div>
    </div>`).join('');
}

function renderInvoices(inv) {
  const el = document.getElementById('invoice-list');
  if (!inv.length){el.innerHTML='<div class="empty">No invoices yet</div>';return;}
  const smap = {paid:'badge-green',sent:'badge-blue',draft:'badge-orange',overdue:'badge-red'};
  el.innerHTML=`<table>
    <tr><th>Invoice</th><th>Amount</th><th>Status</th><th>Due</th></tr>
    ${inv.slice(0,10).map(i=>`<tr>
      <td style="font-family:var(--mono)">${esc(i.invoice_number||'#'+i.id)}</td>
      <td><b style="font-family:var(--mono)">${money(i.amount||0,2)}</b></td>
      <td><span class="badge ${smap[i.status]||'badge-muted'}">${esc(i.status)}</span></td>
      <td style="color:var(--muted);font-family:var(--mono)">${(i.due_date||'').slice(0,10)||'—'}</td>
    </tr>`).join('')}
  </table>`;
}

function showAddBiz(){document.getElementById('biz-add-form').style.display='block';document.getElementById('biz-name').focus();}

async function saveBiz() {
  const name=document.getElementById('biz-name').value.trim();
  if (!name){toast('Name required','error');return;}
  const mrr=parseFloat(document.getElementById('biz-mrr').value)||0;
  const res=await fetch(`/api/business/businesses?token=${TOKEN}`,{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,mrr,arr:mrr*12,business_type:document.getElementById('biz-type').value}),
  });
  if (res.ok){
    toast('Business added ✓');
    document.getElementById('biz-add-form').style.display='none';
    document.getElementById('biz-name').value='';
    document.getElementById('biz-mrr').value='';
    window._bizLoaded=false;loadBusiness();
  } else toast('Failed','error');
}

// ── Automations ──────────────────────────────────────────────────────────────
window._autoLoaded = false;

async function loadAutomations() {
  window._autoLoaded = true;
  try {
    const [aRes,rRes] = await Promise.all([
      fetch(`/api/automations?token=${TOKEN}`),
      fetch(`/api/automations/history?token=${TOKEN}&limit=10`),
    ]);
    renderAutomations(await aRes.json());
    renderAutoRuns(await rRes.json());
  } catch {
    document.getElementById('auto-list').innerHTML='<div class="empty">Failed to load</div>';
  }
}

function renderAutomations(autos) {
  const el=document.getElementById('auto-list');
  if (!autos.length){
    el.innerHTML='<div class="empty">No automations — click <b>Install Presets</b> to add built-in rules</div>';
    return;
  }
  el.innerHTML=autos.map(a=>`
    <div style="display:flex;align-items:center;gap:12px;padding:11px 0;border-bottom:1px solid var(--border)">
      <div style="flex:1">
        <div style="font-weight:600;font-size:13.5px">${esc(a.name)}</div>
        <div style="font-size:11.5px;color:var(--muted);margin-top:2px">
          ${esc(a.trigger_type)} → ${esc(a.action_type)} &middot;
          ${a.is_active?'<span style="color:var(--success)">Active</span>':'<span style="color:var(--muted)">Paused</span>'}
        </div>
      </div>
      <button class="btn btn-outline btn-sm" onclick="runAutomation(${a.id})">▶ Run</button>
    </div>`).join('');
}

function renderAutoRuns(runs) {
  const el=document.getElementById('auto-runs');
  if (!runs.length){el.innerHTML='<div class="empty">No runs yet</div>';return;}
  el.innerHTML=`<table>
    <tr><th>Automation</th><th>Result</th><th>When</th></tr>
    ${runs.map(r=>`<tr>
      <td>${esc(r.automation_name||r.automation_id)}</td>
      <td><span class="badge ${r.was_triggered?'badge-green':'badge-orange'}">${r.was_triggered?'Triggered':'Skipped'}</span></td>
      <td style="color:var(--muted);font-family:var(--mono)">${(r.created_at||'').slice(0,16).replace('T',' ')}</td>
    </tr>`).join('')}
  </table>`;
}

async function installPresets() {
  const btn=event.target;btn.textContent='Installing…';btn.disabled=true;
  try {
    const res=await fetch(`/api/automations/presets?token=${TOKEN}`,{method:'POST'});
    const d=await res.json();
    toast(`Installed ${d.installed||0} preset(s) ✓`);
    window._autoLoaded=false;loadAutomations();
  } catch{toast('Failed','error');}
  finally{btn.textContent='+ Install Presets';btn.disabled=false;}
}

async function runAutomation(id) {
  const res=await fetch(`/api/automations/${id}/run?token=${TOKEN}`,{method:'POST'});
  if(res.ok){toast('Triggered ✓');await loadAutomations();}
  else toast('Failed','error');
}

// ── AI Briefing ──────────────────────────────────────────────────────────────
async function runBriefing() {
  const btn=document.getElementById('btn-brief');
  const type=document.getElementById('brief-type').value;
  btn.textContent='Generating…';btn.disabled=true;
  document.getElementById('brief-output').style.display='none';
  try {
    const res=await fetch(`/api/briefing/generate?briefing_type=${type}&token=${TOKEN}`);
    if(!res.ok){toast((await res.json()).detail||'Failed','error');return;}
    const d=await res.json();
    document.getElementById('brief-ts').textContent=
      type.charAt(0).toUpperCase()+type.slice(1)+' briefing · '+new Date(d.generated_at).toLocaleString();
    document.getElementById('brief-text').textContent=d.report;
    document.getElementById('brief-output').style.display='block';
    toast('Briefing ready ✓');
  } catch{toast('Generation failed','error');}
  finally{btn.textContent='Generate';btn.disabled=false;}
}

async function runAgent(name,btnId,outId) {
  const btn=document.getElementById(btnId);
  const out=document.getElementById(outId);
  const extra=name==='research'?{query:document.getElementById('research-q').value}:{};
  btn.textContent='Running…';btn.disabled=true;out.style.display='none';
  try {
    const res=await fetch(`/api/briefing/agent/${name}?token=${TOKEN}`,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input_data:extra}),
    });
    if(!res.ok){toast((await res.json()).detail||'Failed','error');return;}
    const d=await res.json();
    out.style.display='block';
    out.innerHTML=
      `<div style="font-size:10.5px;color:var(--muted);margin-bottom:8px;font-family:var(--mono)">Status: ${esc(d.status)} · ${d.duration_ms||0}ms</div>`+
      esc(d.report||'No output');
    toast(name.toUpperCase()+' agent complete ✓');
  } catch{toast('Agent failed','error');}
  finally{btn.textContent=name==='cfo'?'Run CFO Analysis':'Run Research';btn.disabled=false;}
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.getElementById('mem-content').addEventListener('keydown', e => {
  if (e.key==='Enter'&&!e.shiftKey){e.preventDefault();addMemory();}
});

(async () => {
  await loadAll();
  renderGoalsFull();
  renderTasksFull();
})();

setInterval(()=>{ loadAll().then(()=>{renderGoalsFull();renderTasksFull();}); }, 60000);
</script>
</body>
</html>
"""
