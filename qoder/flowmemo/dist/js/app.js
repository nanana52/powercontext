/**
 * FlowMemo - Main Application Logic
 */

const API_BASE = "/functions/v1/app";

let state = {
  visitorId: null,
  projectId: null,
  sessionId: null,
  projects: [],
  notes: [],
  tasks: [],
  decisions: [],
  risks: [],
  powerContextConfigured: false,
  report: "",
  reportGenerated: "",
  memoryApplied: false,
  diagnostics: [],
};

const LS_KEYS = {
  visitorId: "flowmemo_visitorId",
  sessionId: "flowmemo_sessionId_",
  projects: "flowmemo_projects",
  notes: "flowmemo_notes_",
  tasks: "flowmemo_tasks_",
  decisions: "flowmemo_decisions_",
  risks: "flowmemo_risks_",
};

function addDiagnostic(msg, type = "info") {
  const entry = {
    time: new Date().toISOString().split("T")[1].split(".")[0],
    type,
    msg,
  };
  state.diagnostics.unshift(entry);
  if (state.diagnostics.length > 20) state.diagnostics.pop();
  renderDiagnostics();
}

function renderDiagnostics() {
  const el = document.getElementById("diagnosticLog");
  if (!el) return;
  el.innerHTML = state.diagnostics.map(d => 
    '<div class="diag-entry diag-' + d.type + '"><span class="diag-time">' + d.time + '</span> ' + esc(d.msg) + '</div>'
  ).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  try {
    initVisitorId();
    loadProjectsFromStorage();
    // Bind local controls BEFORE any network request. A slow API must not
    // prevent import, task toggles, or local report generation from working.
    bindEvents();
    loadProjectData();
    addDiagnostic('FlowMemo UI initialized', 'success');
  } catch (e) {
    addDiagnostic('UI initialization error: ' + e.message, 'error');
    setConnectionStatus(false, 'UI initialization failed');
    return;
  }
  // Run asynchronously, with timeout and clear failure states.
  void checkPowerContextHealth().then(async () => {
    if (state.powerContextConfigured) {
      await ensureSession();
    }
  }).catch(e => {
    addDiagnostic('Startup error: ' + e.message, 'error');
    setConnectionStatus(false, 'Connection error');
  });
});

function initVisitorId() {
  let vid = localStorage.getItem(LS_KEYS.visitorId);
  if (!vid) {
    vid = 'v_' + crypto.randomUUID().replace(/-/g, '').slice(0, 16);
    localStorage.setItem(LS_KEYS.visitorId, vid);
  }
  state.visitorId = vid;
}

function loadProjectsFromStorage() {
  const raw = localStorage.getItem(LS_KEYS.projects);
  if (raw) {
    try {
      state.projects = JSON.parse(raw);
    } catch {
      state.projects = [];
    }
  }
  if (state.projects.length === 0) {
    const defaultProject = {
      id: 'proj_' + crypto.randomUUID().slice(0, 8),
      name: '默认项目',
      created: new Date().toISOString(),
    };
    state.projects = [defaultProject];
    saveProjectsToStorage();
  }
  state.projectId = state.projects[0].id;
  renderProjectSelect();
}

function saveProjectsToStorage() {
  localStorage.setItem(LS_KEYS.projects, JSON.stringify(state.projects));
}

async function ensureSession() {
  if (!state.projectId || !state.powerContextConfigured) return false;
  const key = LS_KEYS.sessionId + state.projectId;
  const saved = localStorage.getItem(key);
  // A cached token must be checked by the server, not trusted blindly. A
  // rejected token (expired or re-signed after a redeploy) falls back to
  // minting a new session, otherwise every memory action stays blocked forever.
  const plans = saved
    ? [{ projectId: state.projectId, sessionId: saved }, { projectId: state.projectId }]
    : [{ projectId: state.projectId }];
  let lastError = null;
  for (let i = 0; i < plans.length; i++) {
    try {
      const result = await api('/session/ensure', {
        method: 'POST',
        body: JSON.stringify(plans[i]),
      });
      if (!result.ok || !result.verified || !result.sessionId) {
        throw new Error('Session was not verified');
      }
      state.sessionId = result.sessionId;
      localStorage.setItem(key, result.sessionId);
      addDiagnostic(
        i === 0 ? 'Verified memory session' : 'Renewed memory session; old token rejected',
        'success',
      );
      return true;
    } catch (e) {
      lastError = e;
    }
  }
  state.sessionId = null;
  addDiagnostic('Session error: ' + lastError.message, 'error');
  return false;
}

function setConnectionStatus(connected, message) {
  state.powerContextConfigured = connected;
  const statusEl = document.getElementById('memoryStatusText');
  const badgeEl = document.getElementById('memoryBadge');
  if (statusEl) {
    statusEl.textContent = connected ? '\u5df2\u8fde\u63a5 PowerContext' : message;
    statusEl.className = 'memory-status ' + (connected ? 'ok' : 'err');
  }
  if (badgeEl) {
    badgeEl.className = 'memory-badge ' + (connected ? 'connected' : 'disconnected');
    badgeEl.innerHTML = '<span class="dot"></span>' + (connected ? '\u5df2\u8fde\u63a5' : '\u672a\u8fde\u63a5');
  }
}

async function checkPowerContextHealth() {
  addDiagnostic('Checking PowerContext health', 'info');
  try {
    const data = await api('/health');
    const pc = data?.powercontext || {};
    const ready = pc.configured === true && pc.health?.status === 'ready';
    // Every non-ready outcome must name the real failure class; a bare
    // "not ready" would leave the reviewer guessing between misconfig,
    // outage and an upstream error code.
    let reason = '\u670d\u52a1\u672a\u5c31\u7eea';
    if (!ready) {
      if (!pc.configured) reason = 'PowerContext \u672a\u914d\u7f6e';
      else if (pc.reachable === false) reason = 'PowerContext \u4e0d\u53ef\u8fbe\uff1a' + (pc.error || 'network error');
      else if (pc.upstream_json === false) {
        // The tunnel answered instead of PowerContext (e.g. GitHub Codespaces
        // sign-in page), so the body is HTML rather than JSON.
        reason = 'PowerContext \u8fd4\u56de\u975e JSON \u54cd\u5e94\uff08HTTP ' + (pc.upstream_status ?? '?') +
          '\uff0cContent-Type=' + (pc.upstream_content_type || '\u672a\u77e5') + '\uff09';
      } else reason = 'PowerContext /health/ready \u8fd4\u56de HTTP ' + (pc.upstream_status ?? '?');
    }
    setConnectionStatus(ready, ready ? '' : reason);
    addDiagnostic('PowerContext health: ' + (pc.health?.status || 'unknown') +
      (pc.upstream_status ? ' (HTTP ' + pc.upstream_status + ')' : '') +
      (pc.upstream_content_type ? ' type=' + pc.upstream_content_type : '') +
      (pc.request_id ? ' req=' + pc.request_id : ''), ready ? 'success' : 'warning');
  } catch (e) {
    setConnectionStatus(false, '\u8fde\u63a5\u5931\u8d25\uff1a' + e.message);
    addDiagnostic('Health check failed: ' + e.message, 'error');
  }
}

async function api(path, opts = {}) {
  const method = opts.method || 'GET';
  addDiagnostic('API ' + method + ' ' + path, 'info');
  let res;
  try {
    res = await fetch(API_BASE + path, {
      ...opts,
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
      signal: AbortSignal.timeout(12000),
    });
  } catch (e) {
    addDiagnostic('Network error at ' + path + ': ' + e.message, 'error');
    throw new Error('Request timeout or network error');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    const message = typeof data.error === 'string' ? data.error : 'HTTP ' + res.status;
    addDiagnostic('API error ' + res.status + ' ' + message, 'error');
    throw new Error(message);
  }
  addDiagnostic('API ' + res.status + ' ' + path, 'success');
  return data;
}

async function loadProjectData() {
  if (!state.projectId) return;
  loadNotesFromStorage();
  loadTasksFromStorage();
  loadDecisionsFromStorage();
  loadRisksFromStorage();
  renderAll();
}

function loadNotesFromStorage() {
  const raw = localStorage.getItem(LS_KEYS.notes + state.projectId);
  state.notes = raw ? JSON.parse(raw) : [];
}

function saveNotesToStorage() {
  localStorage.setItem(LS_KEYS.notes + state.projectId, JSON.stringify(state.notes));
}

function loadTasksFromStorage() {
  const raw = localStorage.getItem(LS_KEYS.tasks + state.projectId);
  state.tasks = raw ? JSON.parse(raw) : [];
}

function saveTasksToStorage() {
  localStorage.setItem(LS_KEYS.tasks + state.projectId, JSON.stringify(state.tasks));
}

function loadDecisionsFromStorage() {
  const raw = localStorage.getItem(LS_KEYS.decisions + state.projectId);
  state.decisions = raw ? JSON.parse(raw) : [];
}

function saveDecisionsToStorage() {
  localStorage.setItem(LS_KEYS.decisions + state.projectId, JSON.stringify(state.decisions));
}

function loadRisksFromStorage() {
  const raw = localStorage.getItem(LS_KEYS.risks + state.projectId);
  state.risks = raw ? JSON.parse(raw) : [];
}

function saveRisksToStorage() {
  localStorage.setItem(LS_KEYS.risks + state.projectId, JSON.stringify(state.risks));
}

function renderAll() {
  renderProjectSelect();
  renderNotes();
  renderTasks();
  renderDecisions();
  renderRisks();
  renderStats();
}

function renderProjectSelect() {
  const sel = document.getElementById('projectSelect');
  sel.innerHTML = state.projects.map(p =>
    '<option value="' + esc(p.id) + '" ' + (p.id === state.projectId ? 'selected' : '') + '>' + esc(p.name) + '</option>'
  ).join('');
}

function renderNotes() {
  const container = document.getElementById('notesList');
  if (state.notes.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无记录，请导入演示或添加新记录</div>';
    return;
  }
  container.innerHTML = state.notes.map(n =>
    '<div class="note-item" data-id="' + esc(n.id) + '">' +
    '<div class="note-item-title">' + esc(n.title) + '</div>' +
    '<div class="note-item-meta">' + (n.imported ? '演示数据' : '用户输入') + ' · ' + esc(n.created.split('T')[0]) + '</div>' +
    '<div class="note-item-content">' + esc(n.content) + '</div>' +
    '</div>'
  ).join('');
}

function renderTasks() {
  const container = document.getElementById('tasksList');
  if (state.tasks.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无待办事项</div>';
    return;
  }
  container.innerHTML = state.tasks.map(t => {
    const isDone = t.done === true;
    const prClass = t.priority === '高' ? 'tag-priority-high' : t.priority === '低' ? 'tag-priority-low' : 'tag-priority-mid';
    return '<div class="task-item ' + (isDone ? 'done' : '') + '" data-id="' + esc(t.id) + '">' +
      '<div class="task-checkbox ' + (isDone ? 'checked' : '') + '" data-task-id="' + esc(t.id) + '"></div>' +
      '<div class="task-info">' +
      '<div class="task-title">' + esc(t.title) + '</div>' +
      '<div class="task-meta">' +
      (t.assignee ? '<span class="tag tag-assignee">' + esc(t.assignee) + '</span>' : '') +
      (t.due_date ? '<span class="tag tag-date">' + esc(t.due_date) + '</span>' : '') +
      '<span class="tag ' + prClass + '">' + esc(t.priority) + '</span>' +
      '</div></div></div>';
  }).join('');
}

function renderDecisions() {
  const container = document.getElementById('decisionsList');
  if (state.decisions.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无决策记录</div>';
    return;
  }
  container.innerHTML = state.decisions.map(d =>
    '<div class="decision-item">' + esc(d) + '</div>'
  ).join('');
}

function renderRisks() {
  const container = document.getElementById('risksList');
  if (state.risks.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无风险项</div>';
    return;
  }
  container.innerHTML = state.risks.map(r =>
    '<div class="risk-item">' + esc(r) + '</div>'
  ).join('');
}

function renderStats() {
  document.getElementById('kpiNotes').textContent = state.notes.length;
  document.getElementById('kpiTasks').textContent = state.tasks.length;
  document.getElementById('kpiDone').textContent = state.tasks.filter(t => t.done).length;
  document.getElementById('kpiRisks').textContent = state.risks.length;
}

function parseContent(content) {
  const tasks = [];
  const decisions = [];
  const risks = [];
  const lines = content.split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const norm = line.replace(/：/g, ':');
    if (/^待办[:：]/.test(norm)) {
      const text = norm.replace(/^待办[:：]/, '').trim();
      const task = { title: text, done: false, priority: '中', source: 'note' };
      const assignee = text.match(/@([\u4e00-\u9fa5]{2,4})/);
      if (assignee) task.assignee = assignee[1];
      const due = text.match(/(\d{4}-\d{2}-\d{2})/);
      if (due) task.due_date = due[1];
      if (/高/.test(text)) task.priority = '高';
      else if (/低/.test(text)) task.priority = '低';
      tasks.push(task);
    } else if (/^决定[:：]/.test(norm)) {
      decisions.push(norm.replace(/^决定[:：]/, '').trim());
    } else if (/^风险[:：]/.test(norm)) {
      risks.push(norm.replace(/^风险[:：]/, '').trim());
    }
  }
  return { tasks, decisions, risks };
}

const FIXTURE_NOTES = [
  {
    title: '周会纪要 2026-10-28',
    content: '待办：完成 API 文档更新 @张三 2026-11-01\n待办：修复登录页 Bug 优先级高\n决定：采用 OAuth2 方案\n风险：第三方接口不稳定',
  },
  {
    title: '\u5468\u4f1a\u7eaa\u8981 2026-10-30',
    content: '\u5f85\u529e\uff1a\u68c0\u67e5\u62a5\u8868\u6a21\u677f @\u674e\u56db 2026-11-03\n\u5f85\u529e\uff1a\u6574\u7406\u6d4b\u8bd5\u7ed3\u679c \u4f18\u5148\u7ea7\u4f4e\n\u51b3\u5b9a\uff1a\u6bcf\u5468\u4e94\u751f\u6210\u5468\u62a5\n\u98ce\u9669\uff1a\u90e8\u5206\u6d4b\u8bd5\u6570\u636e\u9700\u590d\u6838',
  },
];

async function addNote() {
  const titleEl = document.getElementById('noteTitle');
  const contentEl = document.getElementById('noteContent');
  const title = titleEl.value.trim();
  const content = contentEl.value.trim();
  if (!title || !content) {
    showToast('请输入标题和内容', 'error');
    return;
  }
  
  const noteId = 'note_' + crypto.randomUUID().slice(0, 8);
  const note = {
    id: noteId,
    title,
    content,
    imported: false,
    created: new Date().toISOString(),
  };
  state.notes.unshift(note);
  
  const parsed = parseContent(content);
  for (const t of parsed.tasks) {
    state.tasks.push({ id: 'task_' + crypto.randomUUID().slice(0, 8), ...t });
  }
  for (const d of parsed.decisions) {
    state.decisions.push(d);
  }
  for (const r of parsed.risks) {
    state.risks.push(r);
  }
  
  saveNotesToStorage();
  saveTasksToStorage();
  saveDecisionsToStorage();
  saveRisksToStorage();
  
  titleEl.value = '';
  contentEl.value = '';
  showToast('记录已添加', 'success');
  renderAll();
}

async function importFixture() {
  let imported = 0;
  for (const fix of FIXTURE_NOTES) {
    if (state.notes.some(n => n.title === fix.title)) continue;
    
    const noteId = 'note_' + crypto.randomUUID().slice(0, 8);
    const note = {
      id: noteId,
      title: fix.title,
      content: fix.content,
      imported: true,
      created: new Date().toISOString(),
    };
    state.notes.unshift(note);
    
    const parsed = parseContent(fix.content);
    for (const t of parsed.tasks) {
      state.tasks.push({ id: 'task_' + crypto.randomUUID().slice(0, 8), ...t });
    }
    for (const d of parsed.decisions) {
      state.decisions.push(d);
    }
    for (const r of parsed.risks) {
      state.risks.push(r);
    }
    imported++;
  }
  
  saveNotesToStorage();
  saveTasksToStorage();
  saveDecisionsToStorage();
  saveRisksToStorage();
  
  showToast('已导入 ' + imported + ' 条演示记录', 'success');
  renderAll();
}

function toggleTask(taskId, newDone) {
  const task = state.tasks.find(t => t.id === taskId);
  if (task) {
    task.done = newDone;
    saveTasksToStorage();
    renderTasks();
    renderStats();
  }
}

async function savePreference() {
  if (!state.powerContextConfigured) {
    showToast('\u8bf7\u5148\u8fde\u63a5 PowerContext', 'error');
    return;
  }
  const input = document.getElementById('memoryInput');
  const preference = input.value.trim();
  if (!preference) return showToast('\u8bf7\u8f93\u5165\u504f\u597d', 'error');
  try {
    if (!await ensureSession()) throw new Error('Session verification failed');
    const result = await api('/memory/preference/save', {
      method: 'POST',
      body: JSON.stringify({
        projectId: state.projectId,
        sessionId: state.sessionId,
        preference,
      }),
    });
    if (!result.ok || !result.saved || !result.sessionId) throw new Error('Memory write not confirmed');
    state.sessionId = result.sessionId;
    localStorage.setItem(LS_KEYS.sessionId + state.projectId, result.sessionId);
    input.value = '';
    addDiagnostic('Memory saved in PowerContext; request=' + (result.request_id || 'n/a'), 'success');
    renderEvidence('save', result);
    showToast('\u504f\u597d\u5df2\u4fdd\u5b58\u5230 PowerContext', 'success');
  } catch (e) {
    addDiagnostic('Memory save failed: ' + e.message, 'error');
    showToast('\u4fdd\u5b58\u5931\u8d25\uff1a' + e.message, 'error');
    // Preserve the input so the user can retry.
  }
}

function renderEvidence(action, result) {
  const el = document.getElementById('evidenceContent');
  if (!el) return;
  el.textContent = action + ': ' + (result.ok ? 'ok' : 'failed') +
    ', request_id=' + (result.request_id || 'n/a') +
    ', source=' + (result.source || 'PowerContext') +
    ', count=' + (result.count ?? 'n/a');
}

async function recallMemory() {
  if (!state.powerContextConfigured) {
    showToast('PowerContext \u672a\u8fde\u63a5', 'error');
    return null;
  }
  try {
    if (!await ensureSession()) throw new Error('Session verification failed');
    const result = await api('/memory/preference/recall', {
      method: 'POST',
      body: JSON.stringify({ projectId: state.projectId, sessionId: state.sessionId }),
    });
    if (!result.ok) throw new Error('Memory recall failed');
    renderEvidence('recall', result);
    addDiagnostic('Memory recall: ' + (result.preference ? 'found' : 'empty') +
      ', source=' + (result.source || 'unknown') + ', count=' + (result.count ?? 0),
      result.preference ? 'success' : 'warning');
    if (typeof result.preference === 'string' && result.preference) {
      document.getElementById('memoryInput').value = result.preference;
      showToast('\u5df2\u4ece PowerContext \u53ec\u56de\u504f\u597d', 'success');
      return result.preference;
    }
    showToast('\u672a\u627e\u5230\u5df2\u4fdd\u5b58\u7684\u504f\u597d', 'info');
    return null;
  } catch (e) {
    addDiagnostic('Memory recall failed: ' + e.message, 'error');
    showToast('\u53ec\u56de\u5931\u8d25\uff1a' + e.message, 'error');
    return null;
  }
}

function sectionOrderFromPreference(preference) {
  const defaults = ['\u98ce\u9669', '\u5df2\u5b8c\u6210', '\u8fdb\u884c\u4e2d/\u5f85\u529e', '\u51b3\u7b56', '\u4e0b\u5468\u8ba1\u5212'];
  if (!preference) return defaults;
  const synonyms = [
    ['\u98ce\u9669', ['\u98ce\u9669']],
    ['\u5df2\u5b8c\u6210', ['\u5df2\u5b8c\u6210', '\u6210\u679c', '\u5b8c\u6210\u4e8b\u9879']],
    ['\u8fdb\u884c\u4e2d/\u5f85\u529e', ['\u5f85\u529e', '\u8fdb\u884c\u4e2d']],
    ['\u51b3\u7b56', ['\u51b3\u7b56', '\u51b3\u5b9a']],
    ['\u4e0b\u5468\u8ba1\u5212', ['\u4e0b\u5468', '\u8ba1\u5212']],
  ];
  const occurrences = synonyms.map(([name, words]) => ({
    name,
    pos: Math.min(...words.map(word => {
      const i = preference.indexOf(word);
      return i < 0 ? Number.POSITIVE_INFINITY : i;
    })),
  })).filter(x => Number.isFinite(x.pos)).sort((a,b) => a.pos - b.pos);
  const ordered = occurrences.map(x => x.name);
  // Preserve unmentioned sections; avoid dropping business information.
  return ordered.length ? [...ordered, ...defaults.filter(x => !ordered.includes(x))] : defaults;
}

async function generateReport() {
  let preference = null;
  if (state.powerContextConfigured) {
    preference = await recallMemory();
  }
  
  const now = new Date().toISOString().split('T')[0];
  const sections = sectionOrderFromPreference(preference);
  state.memoryApplied = !!preference;
  if (preference) addDiagnostic('Memory-based report ordering applied', 'success');
  
  let md = '# 周报 ' + now + '\n\n';
  for (const sec of sections) {
    md += '## ' + sec + '\n\n';
    if (sec === '风险') {
      if (state.risks.length === 0) md += '无\n\n';
      else {
        for (const r of state.risks) md += '- ' + r + '\n';
        md += '\n';
      }
    } else if (sec === '已完成') {
      const done = state.tasks.filter(t => t.done);
      if (done.length === 0) md += '无\n\n';
      else {
        for (const t of done) md += '- ' + t.title + '\n';
        md += '\n';
      }
    } else if (sec === '进行中/待办') {
      const pending = state.tasks.filter(t => !t.done);
      if (pending.length === 0) md += '无\n\n';
      else {
        for (const t of pending) {
          md += '- [ ] ' + t.title;
          if (t.assignee) md += ' @' + t.assignee;
          if (t.due_date) md += ' 截止 ' + t.due_date;
          md += '\n';
        }
        md += '\n';
      }
    } else if (sec === '决策') {
      if (state.decisions.length === 0) md += '无\n\n';
      else {
        for (const d of state.decisions) md += '- ' + d + '\n';
        md += '\n';
      }
    } else if (sec === '下周计划') {
      md += '（根据本周待办自动生成）\n\n';
      const pending = state.tasks.filter(t => !t.done);
      for (const t of pending) md += '- ' + t.title + '\n';
      md += '\n';
    }
  }
  
  state.report = md;
  state.reportGenerated = new Date().toISOString();
  renderReport();
  showToast('周报已生成', 'success');
}

function renderReport() {
  const container = document.getElementById('reportContent');
  if (!state.report) {
    container.innerHTML = '<div class="empty-state">点击「生成周报」按钮创建</div>';
    return;
  }
  let html = '<div style="margin-bottom:12px;padding:8px 12px;background:var(--bg);border-radius:8px;font-size:12px;color:var(--text-muted)">';
  html += '生成时间：' + esc(state.reportGenerated.split('T')[0]);
  if (state.memoryApplied) {
    html += ' <span style="color:var(--accent-light);font-weight:600">· PowerContext 记忆偏好已应用</span>';
  } else {
    html += ' <span style="color:var(--text-muted)">· 使用默认章节顺序</span>';
  }
  html += '</div>';
  html += '<div class="report-preview" style="white-space:pre-wrap;font-family:inherit">' + esc(state.report) + '</div>';
  container.innerHTML = html;
}

async function copyReport() {
  if (!state.report) {
    showToast('请先生成周报', 'error');
    return;
  }
  try {
    await navigator.clipboard.writeText(state.report);
    showToast('周报已复制到剪贴板', 'success');
  } catch {
    const ta = document.createElement('textarea');
    ta.value = state.report;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('周报已复制到剪贴板', 'success');
  }
}

async function downloadReport() {
  if (!state.report) {
    showToast('请先生成周报', 'error');
    return;
  }
  const blob = new Blob([state.report], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = '周报_' + new Date().toISOString().slice(0, 10) + '.md';
  a.click();
  URL.revokeObjectURL(url);
  showToast('周报已下载', 'success');
}

function bindEvents() {
  document.getElementById('tasksList').addEventListener('click', event => {
    const checkbox = event.target.closest('.task-checkbox');
    if (!checkbox) return;
    const task = state.tasks.find(t => t.id === checkbox.dataset.taskId);
    if (task) toggleTask(task.id, !task.done);
  });
  const evidence = document.getElementById('evidenceToggle');
  if (evidence) evidence.addEventListener('click', () => {
    const content = document.getElementById('evidenceContent');
    if (!content) return;
    // style.css hides the drawer with display:none, so flipping the `hidden`
    // property alone never reveals it; the .open class is what shows it.
    const opening = !content.classList.contains('open');
    content.classList.toggle('open', opening);
    content.hidden = !opening;
    evidence.textContent = (opening ? '\u25be' : '\u25b8') + ' \u6838\u9a8c\u8bc1\u636e\uff08\u6700\u8fd1 PowerContext \u64cd\u4f5c\u8bb0\u5f55\uff09';
  });
  document.getElementById('btnImport').addEventListener('click', importFixture);
  document.getElementById('btnAddNote').addEventListener('click', addNote);
  document.getElementById('btnSavePref').addEventListener('click', savePreference);
  document.getElementById('btnRecall').addEventListener('click', recallMemory);
  document.getElementById('btnGenerate').addEventListener('click', generateReport);
  document.getElementById('btnCopy').addEventListener('click', copyReport);
  document.getElementById('btnDownload').addEventListener('click', downloadReport);
  document.getElementById('projectSelect').addEventListener('change', async (e) => {
    state.projectId = e.target.value;
    state.sessionId = null;
    await loadProjectData();
    if (state.powerContextConfigured) await ensureSession();
  });
}

function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => { toast.remove(); }, 3500);
}

function esc(str) {
  if (str == null) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}
