/**
 * FlowMemo — Main Application Logic
 *
 * Handles all frontend interactions:
 * - Session management
 * - Project/note/task CRUD
 * - PowerContext memory save/recall UI
 * - Weekly report generation
 * - Copy/download functionality
 */

const API = '';
let state = {
  visitorId: null,
  sessionId: null,
  projectId: null,
  projects: [],
  notes: [],
  tasks: [],
  decisions: [],
  risks: [],
  stats: { notes: 0, tasks: 0, done: 0, risks: 0 },
  memoryStatus: { configured: false, health: {} },
  memoryLogs: [],
  report: '',
  reportStats: {},
  memoryApplied: false,
};

// ── Init ──
document.addEventListener('DOMContentLoaded', async () => {
  await initSession();
  await loadProjects();
  await checkMemoryStatus();
  bindEvents();
});

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

async function initSession() {
  try {
    const data = await api('/api/session', { method: 'POST' });
    state.visitorId = data.visitor_id;
    state.sessionId = data.session_id;
  } catch (e) {
    showToast('会话初始化失败: ' + e.message, 'error');
  }
}

// ── Projects ──
async function loadProjects() {
  try {
    const data = await api('/api/projects');
    state.projects = data.projects;
    if (data.projects.length > 0) {
      state.projectId = data.projects[0].id;
      renderProjectSelect();
      await loadProjectData();
    }
  } catch (e) {
    showToast('加载项目失败: ' + e.message, 'error');
  }
}

async function loadProjectData() {
  if (!state.projectId) return;
  await Promise.all([
    loadNotes(),
    loadTasks(),
    loadDecisions(),
    loadRisks(),
    loadStats(),
  ]);
}

function renderProjectSelect() {
  const sel = document.getElementById('projectSelect');
  sel.innerHTML = state.projects.map(p =>
    `<option value="${esc(p.id)}" ${p.id === state.projectId ? 'selected' : ''}>${esc(p.name)}</option>`
  ).join('');
}

// ── Notes ──
async function loadNotes() {
  const data = await api(`/api/projects/${state.projectId}/notes`);
  state.notes = data.notes;
  renderNotes();
}

function renderNotes() {
  const container = document.getElementById('notesList');
  if (state.notes.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无记录，请导入演示或添加新记录</div>';
    return;
  }
  container.innerHTML = state.notes.map(n => `
    <div class="note-item" data-id="${esc(n.id)}">
      <button class="btn btn-sm btn-danger btn-delete" onclick="deleteNote('${esc(n.id)}')">删除</button>
      <div class="note-item-title">${esc(n.title)}</div>
      <div class="note-item-meta">${n.source === 'fixture' ? '演示数据' : '用户输入'} ${n.note_date ? '· ' + esc(n.note_date) : ''}</div>
      <div class="note-item-content">${esc(n.content)}</div>
    </div>
  `).join('');
}

async function addNote() {
  const titleEl = document.getElementById('noteTitle');
  const contentEl = document.getElementById('noteContent');
  const title = titleEl.value.trim();
  const content = contentEl.value.trim();
  if (!title || !content) {
    showToast('请输入标题和内容', 'error');
    return;
  }
  try {
    const result = await api(`/api/projects/${state.projectId}/notes`, {
      method: 'POST',
      body: JSON.stringify({ title, content }),
    });
    titleEl.value = '';
    contentEl.value = '';
    showToast(`记录已添加，解析出 ${result.tasks_created} 个待办`, 'success');
    await loadProjectData();
  } catch (e) {
    showToast('添加失败: ' + e.message, 'error');
  }
}

async function importFixture() {
  try {
    const result = await api(`/api/projects/${state.projectId}/notes/import-fixture`, { method: 'POST' });
    showToast(`已导入 ${result.imported} 条记录、${result.tasks} 个待办、${result.decisions} 条决策、${result.risks} 条风险`, 'success');
    await loadProjectData();
  } catch (e) {
    showToast('导入失败: ' + e.message, 'error');
  }
}

async function deleteNote(noteId) {
  try {
    await api(`/api/projects/${state.projectId}/notes/${noteId}`, { method: 'DELETE' });
    showToast('记录已删除', 'info');
    await loadProjectData();
  } catch (e) {
    showToast('删除失败: ' + e.message, 'error');
  }
}

// ── Tasks ──
async function loadTasks() {
  const data = await api(`/api/projects/${state.projectId}/tasks`);
  state.tasks = data.tasks;
  renderTasks();
}

function renderTasks() {
  const container = document.getElementById('tasksList');
  if (state.tasks.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无待办事项</div>';
    return;
  }
  container.innerHTML = state.tasks.map(t => {
    const isDone = t.status === 'done';
    const prClass = t.priority === '高' ? 'tag-priority-high' : t.priority === '中' ? 'tag-priority-mid' : 'tag-priority-low';
    return `
    <div class="task-item ${isDone ? 'done' : ''}" data-id="${esc(t.id)}">
      <div class="task-checkbox ${isDone ? 'checked' : ''}" onclick="toggleTask('${esc(t.id)}', '${isDone ? 'pending' : 'done'}')"></div>
      <div class="task-info">
        <div class="task-title" ondblclick="editTaskInline('${esc(t.id)}')">${esc(t.title)}</div>
        <div class="task-meta">
          ${t.assignee ? `<span class="tag tag-assignee">${esc(t.assignee)}</span>` : ''}
          ${t.due_date && t.due_date !== '待确认' ? `<span class="tag tag-date">${esc(t.due_date)}</span>` : ''}
          <span class="tag ${prClass}">${esc(t.priority)}</span>
          ${t.note_title ? `<span class="tag tag-source">${esc(t.note_title)}</span>` : ''}
        </div>
        <div class="task-edit-row" id="edit-${esc(t.id)}" style="display:none">
          <input type="text" id="edit-title-${esc(t.id)}" value="${esc(t.title)}" placeholder="标题">
          <input type="text" id="edit-assignee-${esc(t.id)}" value="${esc(t.assignee || '')}" placeholder="负责人" style="width:80px">
          <input type="date" id="edit-date-${esc(t.id)}" value="${esc(t.due_date || '')}">
          <select id="edit-priority-${esc(t.id)}">
            <option ${t.priority === '高' ? 'selected' : ''}>高</option>
            <option ${t.priority === '中' ? 'selected' : ''}>中</option>
            <option ${t.priority === '低' ? 'selected' : ''}>低</option>
          </select>
          <button class="btn btn-sm btn-primary" onclick="saveTaskEdit('${esc(t.id)}')">保存</button>
          <button class="btn btn-sm" onclick="cancelTaskEdit('${esc(t.id)}')">取消</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

async function toggleTask(taskId, newStatus) {
  try {
    await api(`/api/projects/${state.projectId}/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: newStatus }),
    });
    await loadTasks();
    await loadStats();
  } catch (e) {
    showToast('更新失败: ' + e.message, 'error');
  }
}

function editTaskInline(taskId) {
  const el = document.getElementById('edit-' + taskId);
  if (el) el.style.display = el.style.display === 'none' ? 'flex' : 'none';
}

function cancelTaskEdit(taskId) {
  const el = document.getElementById('edit-' + taskId);
  if (el) el.style.display = 'none';
}

async function saveTaskEdit(taskId) {
  try {
    const title = document.getElementById('edit-title-' + taskId).value.trim();
    const assignee = document.getElementById('edit-assignee-' + taskId).value.trim();
    const due_date = document.getElementById('edit-date-' + taskId).value;
    const priority = document.getElementById('edit-priority-' + taskId).value;
    if (!title) { showToast('标题不能为空', 'error'); return; }
    await api(`/api/projects/${state.projectId}/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title, assignee, due_date, priority }),
    });
    showToast('任务已更新', 'success');
    await loadTasks();
  } catch (e) {
    showToast('保存失败: ' + e.message, 'error');
  }
}

// ── Decisions & Risks ──
async function loadDecisions() {
  const data = await api(`/api/projects/${state.projectId}/decisions`);
  state.decisions = data.decisions;
  renderDecisions();
}

function renderDecisions() {
  const container = document.getElementById('decisionsList');
  if (state.decisions.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无决策记录</div>';
    return;
  }
  container.innerHTML = state.decisions.map(d => `
    <div class="decision-item">
      ${esc(d.content)}
      <div class="item-source">${d.note_title ? '来源：' + esc(d.note_title) : ''}</div>
    </div>
  `).join('');
}

async function loadRisks() {
  const data = await api(`/api/projects/${state.projectId}/risks`);
  state.risks = data.risks;
  renderRisks();
}

function renderRisks() {
  const container = document.getElementById('risksList');
  if (state.risks.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无风险项</div>';
    return;
  }
  container.innerHTML = state.risks.map(r => `
    <div class="risk-item">
      ${esc(r.content)}
      <div class="item-source">${r.note_title ? '来源：' + esc(r.note_title) : ''}</div>
    </div>
  `).join('');
}

// ── Stats ──
async function loadStats() {
  const data = await api(`/api/projects/${state.projectId}/stats`);
  state.stats = data;
  renderStats();
}

function renderStats() {
  document.getElementById('kpiNotes').textContent = state.stats.notes;
  document.getElementById('kpiTasks').textContent = state.stats.tasks;
  document.getElementById('kpiDone').textContent = state.stats.done;
  document.getElementById('kpiRisks').textContent = state.stats.risks;
}

// ── Memory ──
async function checkMemoryStatus() {
  try {
    const data = await api('/api/memory/status');
    state.memoryStatus = data;
    state.memoryLogs = data.recent_logs || [];
    renderMemoryStatus();
  } catch (e) {
    state.memoryStatus = { configured: false, health: { status: 'error' } };
    renderMemoryStatus();
  }
}

function renderMemoryStatus() {
  const badge = document.getElementById('memoryBadge');
  const connected = state.memoryStatus.configured && state.memoryStatus.health?.status === 'connected';
  badge.className = 'memory-badge ' + (connected ? 'connected' : 'disconnected');
  badge.innerHTML = `<span class="dot"></span>${connected ? 'PowerContext 已连接' : 'PowerContext 未连接'}`;

  const statusEl = document.getElementById('memoryStatusText');
  if (connected) {
    statusEl.className = 'memory-status ok';
    statusEl.textContent = 'PowerContext 服务已连接，可以保存和召回长期记忆。';
  } else if (state.memoryStatus.configured) {
    statusEl.className = 'memory-status err';
    const h = state.memoryStatus.health || {};
    statusEl.textContent = `PowerContext 配置已设置但连接异常：${h.status || '未知'}。基础功能仍可使用。`;
  } else {
    statusEl.className = 'memory-status info';
    statusEl.textContent = 'PowerContext 未配置（需设置 POWERCONTEXT_URL 环境变量）。基础任务管理和周报功能可正常演示，记忆功能暂不可用。';
  }

  renderEvidenceDrawer();
}

function renderEvidenceDrawer() {
  const container = document.getElementById('evidenceContent');
  if (state.memoryLogs.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无记忆操作记录</div>';
    return;
  }
  container.innerHTML = state.memoryLogs.map(log => `
    <div class="evidence-item">
      <span class="evidence-action">${esc(log.action)}</span>
      <span class="evidence-endpoint"> → ${esc(log.endpoint || 'N/A')}</span>
      <span class="${log.success ? 'evidence-success' : 'evidence-fail'}">
        ${log.success ? '成功' : '失败'}
      </span>
    </div>
  `).join('');
}

async function savePreference() {
  const input = document.getElementById('memoryInput');
  const text = input.value.trim();
  if (!text) { showToast('请输入要保存的偏好', 'error'); return; }
  try {
    const result = await api('/api/memory/save', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
    if (result.success) {
      showToast('偏好已保存到 PowerContext', 'success');
      input.value = '';
    } else {
      showToast(result.error || '保存失败', 'error');
    }
    await checkMemoryStatus();
  } catch (e) {
    showToast('保存失败: ' + e.message, 'error');
  }
}

async function recallMemory() {
  try {
    const result = await api('/api/memory/recall', {
      method: 'POST',
      body: JSON.stringify({ query: '周报偏好 写作顺序' }),
    });
    if (result.success && result.content) {
      showToast('记忆已召回，将应用于周报生成', 'success');
    } else if (result.status === 'empty' || result.status === 'not_configured') {
      showToast('暂无历史记忆或记忆服务未连接', 'info');
    } else {
      showToast('未找到相关记忆', 'info');
    }
    await checkMemoryStatus();
    return result;
  } catch (e) {
    showToast('召回失败: ' + e.message, 'error');
    return null;
  }
}

// ── Report ──
async function generateReport() {
  try {
    const result = await api(`/api/projects/${state.projectId}/report`, { method: 'POST' });
    state.report = result.report;
    state.reportStats = result.stats;
    state.memoryApplied = result.memory_applied;
    renderReport();
    showToast('周报已生成', 'success');
  } catch (e) {
    showToast('生成周报失败: ' + e.message, 'error');
  }
}

function renderReport() {
  const container = document.getElementById('reportContent');
  if (!state.report) {
    container.innerHTML = '<div class="empty-state">点击「生成周报」按钮创建</div>';
    return;
  }
  const s = state.reportStats;
  const statsLine = `基于 ${s.notes || 0} 条记录、${s.tasks || 0} 个任务、${s.recalled_memories || 0} 条已召回记忆`;
  let html = `<div style="margin-bottom:12px;padding:8px 12px;background:var(--bg);border-radius:8px;font-size:12px;color:var(--text-muted)">${esc(statsLine)}`;
  if (state.memoryApplied) {
    html += ` <span style="color:var(--accent-light);font-weight:600">· 记忆偏好已应用</span>`;
  }
  html += `</div>`;
  html += `<div class="report-preview">${esc(state.report)}</div>`;
  container.innerHTML = html;
}

async function copyReport() {
  if (!state.report) { showToast('请先生成周报', 'error'); return; }
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
  if (!state.report) { showToast('请先生成周报', 'error'); return; }
  const blob = new Blob([state.report], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `周报_${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('周报已下载', 'success');
}

// ── Events ──
function bindEvents() {
  document.getElementById('btnImport').addEventListener('click', importFixture);
  document.getElementById('btnAddNote').addEventListener('click', addNote);
  document.getElementById('btnSavePref').addEventListener('click', savePreference);
  document.getElementById('btnRecall').addEventListener('click', recallMemory);
  document.getElementById('btnGenerate').addEventListener('click', generateReport);
  document.getElementById('btnCopy').addEventListener('click', copyReport);
  document.getElementById('btnDownload').addEventListener('click', downloadReport);
  document.getElementById('projectSelect').addEventListener('change', async (e) => {
    state.projectId = e.target.value;
    await loadProjectData();
  });
  document.getElementById('evidenceToggle').addEventListener('click', () => {
    document.getElementById('evidenceContent').classList.toggle('open');
  });
}

// ── Toast ──
function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => { toast.remove(); }, 3500);
}

// ── Utils ──
function esc(str) {
  if (str == null) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}
