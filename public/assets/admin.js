'use strict';

const state = { config: null, leads: [] };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function get(obj, path, fallback = '') {
  return path.split('.').reduce((acc, key) => (acc && acc[key] !== undefined ? acc[key] : undefined), obj) ?? fallback;
}
function set(obj, path, value) {
  const parts = path.split('.');
  let current = obj;
  parts.slice(0, -1).forEach((part) => {
    if (!current[part] || typeof current[part] !== 'object') current[part] = {};
    current = current[part];
  });
  current[parts.at(-1)] = value;
}
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}
function message(text, type = '') {
  const el = $('[data-admin-message]');
  if (!el) return;
  el.textContent = text;
  el.className = `form-message admin-status ${type}`;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.ok === false) throw new Error(json.error || 'Erro na requisição.');
  return json;
}

async function loadConfig() {
  const json = await api('/api/admin/config');
  state.config = json.config;
  fillEditor();
  showAdmin();
}

function showAdmin() {
  $('[data-login-panel]').classList.add('hidden');
  $('[data-admin-panel]').classList.remove('hidden');
}

function showLogin() {
  $('[data-login-panel]').classList.remove('hidden');
  $('[data-admin-panel]').classList.add('hidden');
}

function fillEditor() {
  const cfg = state.config;
  $$('[data-path]').forEach((field) => {
    const value = get(cfg, field.dataset.path, '');
    if (field.type === 'checkbox') field.checked = Boolean(value);
    else field.value = value;
  });
  renderSections();
  renderPlans();
  fillLists();
}

function collectEditor() {
  const cfg = structuredClone(state.config);
  $$('[data-path]').forEach((field) => {
    let value = field.type === 'checkbox' ? field.checked : field.value;
    if (field.type === 'range') value = Number(value);
    set(cfg, field.dataset.path, value);
  });
  collectLists(cfg);
  cfg.plans = collectPlans();
  return cfg;
}

function renderSections() {
  const root = $('[data-render-admin="sections"]');
  if (!root) return;
  const labels = {
    stats: 'Estatísticas', pain: 'Dor do cliente', features: 'Recursos', tools: 'Ferramentas',
    brands: 'Marcas', steps: 'Passos', plans: 'Planos', faq: 'FAQ', legal: 'Aviso legal'
  };
  root.innerHTML = Object.entries(labels).map(([key, label]) => `
    <label class="toggle-item"><input type="checkbox" data-path="sections.${key}" ${get(state.config, `sections.${key}`, true) ? 'checked' : ''}> ${label}</label>
  `).join('');
}

function renderPlans() {
  const root = $('[data-render-admin="plans"]');
  if (!root) return;
  root.innerHTML = (state.config.plans || []).map((plan, index) => `
    <article class="plan-editor" data-plan-index="${index}">
      <div class="admin-row">
        <strong>Plano ${index + 1}</strong>
        <button class="button danger" type="button" data-remove-plan="${index}">Remover</button>
      </div>
      <div class="admin-grid">
        <label>Nome<input data-plan-field="name" value="${escapeHtml(plan.name)}"></label>
        <label>Preço<input data-plan-field="price" value="${escapeHtml(plan.price)}"></label>
        <label>Período<input data-plan-field="period" value="${escapeHtml(plan.period || '')}"></label>
        <label>Etiqueta<input data-plan-field="tag" value="${escapeHtml(plan.tag || '')}"></label>
        <label class="toggle-item"><input type="checkbox" data-plan-field="featured" ${plan.featured ? 'checked' : ''}> Destacar plano</label>
        <label>Benefícios — um por linha<textarea data-plan-field="benefits">${escapeHtml((plan.benefits || []).join('\n'))}</textarea></label>
      </div>
    </article>
  `).join('');
  $$('[data-remove-plan]').forEach((button) => {
    button.addEventListener('click', () => {
      const index = Number(button.dataset.removePlan);
      state.config.plans.splice(index, 1);
      renderPlans();
    });
  });
}

function collectPlans() {
  return $$('[data-plan-index]').map((card) => {
    const plan = {};
    $$('[data-plan-field]', card).forEach((field) => {
      const key = field.dataset.planField;
      if (key === 'featured') plan[key] = field.checked;
      else if (key === 'benefits') plan[key] = field.value.split('\n').map((line) => line.trim()).filter(Boolean);
      else plan[key] = field.value.trim();
    });
    return plan;
  }).filter((plan) => plan.name && plan.price);
}

function fillLists() {
  const cfg = state.config;
  const mappings = {
    'stats': (cfg.stats || []).map((x) => `${x.number} | ${x.label}`).join('\n'),
    'pain.items': get(cfg, 'pain.items', []).join('\n'),
    'features': (cfg.features || []).map((x) => `${x.icon || '✓'} | ${x.title} | ${x.text}`).join('\n'),
    'tools.items': get(cfg, 'tools.items', []).join('\n'),
    'brands': (cfg.brands || []).join('\n'),
    'steps': (cfg.steps || []).map((x) => `${x.title} | ${x.text}`).join('\n'),
    'faq': (cfg.faq || []).map((x) => `${x.q} | ${x.a}`).join('\n')
  };
  Object.entries(mappings).forEach(([key, value]) => {
    const el = $(`[data-list="${key}"]`);
    if (el) el.value = value;
  });
}

function splitLines(value) {
  return String(value || '').split('\n').map((line) => line.trim()).filter(Boolean);
}

function collectLists(cfg) {
  const stats = $('[data-list="stats"]');
  if (stats) cfg.stats = splitLines(stats.value).map((line) => {
    const [number, ...rest] = line.split('|').map((x) => x.trim());
    return { number, label: rest.join(' | ') };
  }).filter((x) => x.number && x.label);

  const pain = $('[data-list="pain.items"]');
  if (pain) cfg.pain.items = splitLines(pain.value);

  const features = $('[data-list="features"]');
  if (features) cfg.features = splitLines(features.value).map((line) => {
    const [icon, title, ...rest] = line.split('|').map((x) => x.trim());
    return { icon, title, text: rest.join(' | ') };
  }).filter((x) => x.title && x.text);

  const tools = $('[data-list="tools.items"]');
  if (tools) cfg.tools.items = splitLines(tools.value);

  const brands = $('[data-list="brands"]');
  if (brands) cfg.brands = splitLines(brands.value);

  const steps = $('[data-list="steps"]');
  if (steps) cfg.steps = splitLines(steps.value).map((line) => {
    const [title, ...rest] = line.split('|').map((x) => x.trim());
    return { title, text: rest.join(' | ') };
  }).filter((x) => x.title && x.text);

  const faq = $('[data-list="faq"]');
  if (faq) cfg.faq = splitLines(faq.value).map((line) => {
    const [q, ...rest] = line.split('|').map((x) => x.trim());
    return { q, a: rest.join(' | ') };
  }).filter((x) => x.q && x.a);
}

async function saveConfig() {
  try {
    message('Salvando...');
    const config = collectEditor();
    const json = await api('/api/admin/config', { method: 'PUT', body: JSON.stringify({ config }) });
    state.config = json.config;
    fillEditor();
    message('Alterações salvas com sucesso. Abra o site para conferir.', 'ok');
  } catch (err) {
    message(err.message, 'error');
  }
}

async function loadLeads() {
  const root = $('[data-leads]');
  if (!root) return;
  try {
    root.innerHTML = '<p>Carregando...</p>';
    const json = await api('/api/admin/leads');
    state.leads = json.leads || [];
    root.innerHTML = state.leads.length ? state.leads.map((lead) => `
      <div class="lead-row">
        <div>
          <strong>${escapeHtml(lead.name)}</strong><br>
          <small>${escapeHtml(lead.phone)} • ${escapeHtml(lead.plan || 'Sem plano')}</small>
          <p>${escapeHtml(lead.message || '')}</p>
        </div>
        <small>${new Date(lead.createdAt).toLocaleString('pt-BR')}</small>
      </div>
    `).join('') : '<p>Nenhum lead recebido ainda.</p>';
  } catch (err) {
    root.innerHTML = `<p class="form-message error">${escapeHtml(err.message)}</p>`;
  }
}

function bindTabs() {
  $$('[data-tab]').forEach((button) => {
    button.addEventListener('click', () => {
      $$('[data-tab]').forEach((b) => b.classList.remove('active'));
      $$('[data-tab-content]').forEach((c) => c.classList.remove('active'));
      button.classList.add('active');
      $(`[data-tab-content="${button.dataset.tab}"]`).classList.add('active');
      if (button.dataset.tab === 'leads') loadLeads();
    });
  });
}

function bindLogin() {
  $('[data-login-form]').addEventListener('submit', async (event) => {
    event.preventDefault();
    const msg = $('[data-login-message]');
    msg.textContent = 'Entrando...';
    msg.className = 'form-message';
    try {
      const data = Object.fromEntries(new FormData(event.currentTarget));
      await api('/api/admin/login', { method: 'POST', body: JSON.stringify(data) });
      msg.textContent = '';
      await loadConfig();
    } catch (err) {
      msg.textContent = err.message;
      msg.classList.add('error');
    }
  });
}

function bindActions() {
  $('[data-save]').addEventListener('click', saveConfig);
  $('[data-add-plan]').addEventListener('click', () => {
    state.config.plans.push({ name: 'Novo plano', price: 'R$ 0,00', period: '/mês', tag: '', featured: false, benefits: ['Benefício 1'] });
    renderPlans();
  });
  $('[data-refresh-leads]').addEventListener('click', loadLeads);
  $('[data-logout]').addEventListener('click', async () => {
    await api('/api/admin/logout', { method: 'POST', body: '{}' }).catch(() => null);
    showLogin();
  });
}

async function init() {
  bindLogin();
  bindTabs();
  bindActions();
  try {
    await loadConfig();
  } catch (_) {
    showLogin();
  }
}

document.addEventListener('DOMContentLoaded', init);
