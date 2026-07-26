/**
 * 旅游攻略多智能体系统 — 前端 v2
 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

// ============================================================
// State
// ============================================================
const S = {
  ws: null, rt: null,
  connected: false, running: false,
  agents: makeAgents(),
};
function makeAgents() {
  return {
    lead: { n:'lead', r:'协调员', i:'🎯', s:'idle', log:[] },
    attraction_expert: { n:'attraction_expert', r:'景点美术', i:'🏯', s:'idle', log:[] },
    transport_expert: { n:'transport_expert', r:'交通出行', i:'🚄', s:'idle', log:[] },
    accommodation_expert: { n:'accommodation_expert', r:'住宿推荐', i:'🏨', s:'idle', log:[] },
    schedule_expert: { n:'schedule_expert', r:'时间规划', i:'📅', s:'idle', log:[] },
  };
}

// ============================================================
// Helpers
// ============================================================
const E = (t, a = {}, c = []) => {
  const e = document.createElement(t);
  for (const [k, v] of Object.entries(a)) {
    if (k === 'c') e.className = v;
    else if (k === 't') e.textContent = v;
    else if (k === 'h') e.innerHTML = v;
    else e.setAttribute(k, v);
  }
  for (const ch of c) e.appendChild(typeof ch === 'string' ? document.createTextNode(ch) : ch);
  return e;
};

// ============================================================
// Toast
// ============================================================
let toastStack = null;
function toast(msg, kind = 'nfo') {
  if (!toastStack) { toastStack = E('div', {c:'toast-stack'}); document.body.appendChild(toastStack); }
  const t = E('div', {c:`toast ${kind}`, t:msg});
  toastStack.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ============================================================
// Connection
// ============================================================
function connBanner(s) {
  const b = $('#conn-banner');
  if (!b) return;
  b.className = 'conn-banner' + (s ? ` ${s} show` : '');
  if (s === 'error') b.textContent = '⚠ 连接断开 · 自动重连中';
  else if (s === 'warn') b.textContent = '⏳ 连接服务器中...';
}

function setDot(s) {
  const d = $('#status-dot');
  const t = $('#status-text');
  if (d) d.className = 'status-dot ' + s;
  if (t) t.textContent = {on:'已连接',busy:'运行中',done:'已完成'}[s] || '';
}

// ============================================================
// Tabs
// ============================================================
function switchTab(name) {
  $$('.tab-bar button').forEach(b => b.classList.toggle('on', b.dataset.tab === name));
  $$('.content-panel').forEach(p => p.classList.toggle('on', p.id === 'panel-'+name));
}
function switchSidebar(name) {
  $$('.sidebar-nav button').forEach(b => b.classList.toggle('on', b.dataset.panel === name));
  $$('.sidebar-panel').forEach(p => p.classList.toggle('on', p.id === name+'-panel'));
  if (name === 'history') loadHistory();
}

// ============================================================
// Agent Panel
// ============================================================
function renderAgents() {
  const ct = $('#agent-list');
  if (!ct) return;
  ct.innerHTML = '';
  for (const k of ['lead','attraction_expert','transport_expert','accommodation_expert','schedule_expert']) {
    const a = S.agents[k];
    const sc = {working:'live',done:'ok',idle:''}[a.s]||'';
    const card = E('div', {c:`agent-card ${sc}`});
    const row = E('div', {c:'agent-row'});
    row.innerHTML = `<span class="agent-icon">${a.i}</span>
      <div class="agent-info"><div class="agent-name">${a.n}</div><div class="agent-role">${a.r}</div></div>
      <span class="agent-tag ${a.s==='working'?'working':a.s==='done'?'done':'idle'}">${ {working:'工作中',done:'完成',idle:'待机'}[a.s] }</span>`;
    card.appendChild(row);
    const logDiv = E('div', {c:'agent-log'});
    for (const l of a.log.slice(-3)) {
      logDiv.appendChild(E('span', {c: l.startsWith('🔧')?'tool':'', t:l}));
    }
    card.appendChild(logDiv);
    ct.appendChild(card);
  }
}
function alog(name, msg) {
  if (S.agents[name]) { S.agents[name].log.push(msg); if (S.agents[name].log.length > 40) S.agents[name].log = S.agents[name].log.slice(-30); }
}
function aset(name, s) { if (S.agents[name]) S.agents[name].s = s; }

// ============================================================
// Chat
// ============================================================
function addChat(type, text) {
  const ct = $('#chat-stream');
  if (!ct) return;
  const emp = ct.querySelector('.empty'); if (emp) emp.remove();
  const cls = {lead:'lead',system:'sys',tool:'tool',plan:'plan-preview'}[type]||'sys';
  const b = E('div', {c:`chat-bubble ${cls}`});
  if (type === 'system') b.innerHTML = `🔹 ${text}`;
  else if (type === 'tool') b.textContent = `🔧 ${text}`;
  else b.textContent = text;
  ct.appendChild(b);
  ct.scrollTop = ct.scrollHeight;
}

// ============================================================
// Tasks
// ============================================================
function renderTasks(summary) {
  const ct = $('#task-grid');
  if (!ct) return;
  const items = [];
  for (const line of summary.split('\n')) {
    const m = line.match(/([○●✓✗])\s+(\w+):\s+(.+?)(\s+\((.+?)\))?(\s+\[依赖:\s*(.+?)\])?$/);
    if (!m) continue;
    const [_, icon, id, subject, _o, owner, _d, deps] = m;
    const st = {'○':'pending','●':'progress','✓':'done','✗':'failed'}[icon]||'pending';
    const row = E('div', {c:'task-row'});
    row.innerHTML = `<div class="task-icon ${st}">${icon}</div>
      <div class="task-body"><div class="task-title">${id}: ${subject}</div>
      <div class="task-sub">${owner?`<span class="owner">👤 ${owner}</span>`:''}${deps?`<span class="deps">🔗 ${deps}</span>`:''}</div></div>`;
    items.push(row);
  }
  ct.innerHTML = items.length ? '' : '<div class="empty"><div class="empty-icon">📋</div><div class="empty-text">等待任务创建...</div></div>';
  const grid = E('div', {c:'task-grid'}); items.forEach(i => grid.appendChild(i));
  ct.appendChild(grid);
}

// ============================================================
// Agent Messages
// ============================================================
function addMsg(from, to, content, type) {
  const ct = $('#msg-stream');
  if (!ct) return;
  const emp = ct.querySelector('.empty'); if (emp) emp.remove();
  const item = E('div', {c:'msg-item'});
  item.innerHTML = `<div class="msg-head">
    <span class="msg-from">${from}</span><span class="msg-arrow">→</span><span class="msg-to">${to}</span>
    <span class="msg-kind">${type}</span></div>
    <div class="msg-text">${(content||'').substring(0, 300)}</div>`;
  ct.appendChild(item);
  ct.scrollTop = ct.scrollHeight;
}

// ============================================================
// Plan
// ============================================================
function renderPlan(content) {
  const ct = $('#plan-doc');
  if (!ct) return;
  let html = content
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/^### (.+)$/gm,'<h3>$1</h3>')
    .replace(/^## (.+)$/gm,'<h2>$1</h2>')
    .replace(/^# (.+)$/gm,'<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/^- (.+)$/gm,'<li>$1</li>')
    .replace(/(<li>.*<\/li>\s*)+/g,'<ul>$&</ul>')
    .replace(/\n\n/g,'</p><p>').replace(/\n/g,'<br>');
  ct.innerHTML = '<p>'+html+'</p>';
}

// ============================================================
// WebSocket
// ============================================================
function connect() {
  connBanner('warn');
  const ws = new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);
  S.ws = ws;
  ws.onopen = () => { S.connected = true; connBanner(''); setDot('on'); if (S.rt) { clearTimeout(S.rt); S.rt = null; } };
  ws.onclose = () => { S.connected = false; setDot(''); if (S.running) connBanner('error'); S.rt = setTimeout(connect, 3000); };
  ws.onerror = () => {};
  ws.onmessage = (ev) => { try { const m = JSON.parse(ev.data); handle(m.type, m.data); } catch(e){} };
}

function handle(type, data) {
  switch (type) {
    case 'status': addChat('system', data); break;
    case 'lead_text': addChat('lead', data.text); alog('lead', `💬 ${data.text.slice(0,60)}`); aset('lead','working'); renderAgents(); break;
    case 'lead_tool': addChat('tool', `${data.tool}: ${data.input}`); alog('lead', `🔧 ${data.tool}`); renderAgents(); break;
    case 'expert_started':
      addChat('system', `${data.icon} <b>${data.name}</b> (${data.role}) 已启动`);
      alog(data.name, '🚀 启动'); if (S.agents[data.name]) { S.agents[data.name].i = data.icon; S.agents[data.name].r = data.role; }
      aset(data.name, 'working'); renderAgents(); toast(`${data.name} 启动`, 'nfo'); break;
    case 'expert_text': alog(data.name, `💬 ${data.text.slice(0,60)}`); aset(data.name,'working'); renderAgents(); break;
    case 'expert_tool': alog(data.name, `🔧 ${data.tool}`); aset(data.name,'working'); renderAgents(); break;
    case 'expert_completed':
      addChat('system', `${S.agents[data.name]?.i||'✅'} <b>${data.name}</b> 完成`);
      alog(data.name, '✅ 完成'); aset(data.name,'done'); renderAgents(); toast(`${data.name} 完成`, 'ok'); break;
    case 'agent_message': addMsg(data.from, data.to, data.content, data.type); break;
    case 'task_board': renderTasks(data); break;
    case 'plan_ready':
      renderPlan(data); switchTab('plan'); S.running = false; setDot('done');
      toggleBtns(false); addChat('system', '✅ 攻略生成完成 · 已保存到历史记录'); toast('攻略生成完成', 'ok'); break;
    case 'done': S.running = false; setDot('done'); toggleBtns(false); break;
    case 'error': addChat('system', `❌ ${data}`); toast(data, 'err'); break;
    case 'started': S.running = true; setDot('busy'); toggleBtns(true); break;
    case 'stopped': S.running = false; setDot('on'); toggleBtns(false); toast('已停止', 'nfo'); break;
  }
}

// ============================================================
// Buttons
// ============================================================
function toggleBtns(running) {
  const send = $('#send-btn'), stop = $('#stop-btn');
  if (send) { send.disabled = running; send.style.display = running ? 'none' : ''; }
  if (stop) stop.style.display = running ? '' : 'none';
}

// ============================================================
// Send / Stop
// ============================================================
function sendMessage() {
  const input = $('#user-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text || S.running) return;
  if (!S.connected) { toast('未连接服务器', 'err'); return; }
  // Reset
  S.agents = makeAgents();
  $$('#chat-stream,#task-grid,#msg-stream').forEach(el => el.innerHTML = '');
  $('#plan-doc').innerHTML = '<div class="empty"><div class="empty-icon">📄</div><div class="empty-text">正在生成...</div></div>';
  renderAgents(); switchTab('chat');
  addChat('lead', `📝 ${text}`);
  S.ws.send(JSON.stringify({action:'start',input:text}));
  input.value = '';
}
function stopAgent() { if (S.ws && S.running) { S.ws.send(JSON.stringify({action:'stop'})); toast('正在停止...', 'nfo'); } }
function fillSuggestion(t) { const i = $('#user-input'); if (i) { i.value = t; sendMessage(); } }

// ============================================================
// History
// ============================================================
async function loadHistory() {
  try {
    const r = await fetch('/api/sessions');
    const d = await r.json();
    renderHistory(d.sessions||[]);
  } catch(e){}
}
function renderHistory(sessions) {
  const ct = $('#history-list');
  if (!ct) return;
  if (!sessions.length) { ct.innerHTML = '<div class="empty"><div class="empty-icon">📭</div><div class="empty-text">暂无记录</div></div>'; return; }
  ct.innerHTML = '';
  for (const s of sessions) {
    const dt = s.created_at ? s.created_at.slice(0,16).replace('T',' ') : '';
    const st = {completed:'完成',running:'进行中',stopped:'已停止'}[s.status]||s.status;
    const item = E('div', {c:'history-item'});
    item.innerHTML = `<div class="hi-title">${(s.user_input||'').slice(0,45)}</div>
      <div class="hi-meta"><span>${dt}</span><span class="hi-status ${s.status}">${st}</span></div>`;
    item.onclick = () => loadSession(s.id);
    ct.appendChild(item);
  }
}
async function loadSession(id) {
  if (S.running) { stopAgent(); await new Promise(r=>setTimeout(r,500)); }
  try {
    const r = await fetch(`/api/sessions/${id}`);
    const d = await r.json();
    if (d.error) { toast(d.error,'err'); return; }
    S.agents = makeAgents();
    $$('#chat-stream,#msg-stream').forEach(el => el.innerHTML = '');
    if (d.chat_messages) for (const m of d.chat_messages) addChat(m.msg_type, m.content);
    if (d.agent_logs) for (const l of d.agent_logs) {
      alog(l.agent_name, `[${l.event_type}] ${(l.content||'').slice(0,80)}`);
      if (l.event_type==='completed') aset(l.agent_name,'done');
      else if (l.event_type==='started') aset(l.agent_name,'working');
      if (l.icon) S.agents[l.agent_name].i = l.icon;
    }
    renderAgents();
    if (d.task_board) renderTasks(d.task_board);
    if (d.plan) { renderPlan(d.plan); switchTab('plan'); }
    switchSidebar('agents'); setDot('done'); toast('已加载', 'nfo');
  } catch(e) { toast('加载失败', 'err'); }
}

// ============================================================
// Init
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  renderAgents();
  connect();
  // Tab clicks
  $$('.tab-bar button').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));
  // Sidebar nav clicks
  $$('.sidebar-nav button').forEach(b => b.addEventListener('click', () => switchSidebar(b.dataset.panel)));
  // Enter key
  const input = $('#user-input');
  if (input) input.addEventListener('keydown', e => { if (e.key==='Enter' && !S.running) sendMessage(); });
});
