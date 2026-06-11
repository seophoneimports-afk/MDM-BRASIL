'use strict';

const state = { config: null };

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function get(obj, path, fallback = '') {
  return path.split('.').reduce((acc, key) => (acc && acc[key] !== undefined ? acc[key] : undefined), obj) ?? fallback;
}

function applyTheme(config) {
  const theme = config.theme || {};
  const root = document.documentElement;
  root.style.setProperty('--primary', theme.primary || '#16f29a');
  root.style.setProperty('--secondary', theme.secondary || '#42a5ff');
  root.style.setProperty('--accent', theme.accent || '#f6c84c');
  root.style.setProperty('--bg', theme.background || '#08111f');
  root.style.setProperty('--surface', theme.surface || '#101c2e');
  root.style.setProperty('--text', theme.text || '#f4f8ff');
  root.style.setProperty('--muted', theme.muted || '#aab7c9');
  root.style.setProperty('--radius', `${Number(theme.radius || 24)}px`);
  document.body.classList.toggle('density-compacto', theme.density === 'compacto');
  document.body.classList.toggle('density-espacoso', theme.density === 'espacoso');
  document.body.classList.toggle('layout-direto', theme.layout === 'direto');
  document.body.classList.toggle('layout-corporativo', theme.layout === 'corporativo');
}

function setTextFields(config) {
  $$('[data-field]').forEach((el) => {
    const value = get(config, el.dataset.field);
    if (value !== undefined) el.textContent = value;
  });
  const title = get(config, 'seo.title', get(config, 'brand.name', 'MDM & FRP Brasil'));
  const desc = get(config, 'seo.description', 'Site profissional com backend e painel admin.');
  document.title = title;
  const meta = $('meta[name="description"]');
  if (meta) meta.setAttribute('content', desc);
  $$('.brand-text').forEach((el) => { el.textContent = get(config, 'brand.name', 'MDM & FRP Brasil'); });
  $$('.brand-mark').forEach((el) => { el.textContent = get(config, 'brand.shortName', 'MF').slice(0, 2).toUpperCase(); });
}

function whatsappHref(config, plan = '') {
  const number = String(get(config, 'brand.whatsapp', '5519994783127')).replace(/\D/g, '');
  const message = `Olá! Vim pelo site da ${get(config, 'brand.name', 'MDM & FRP Brasil')}${plan ? ` e tenho interesse no plano ${plan}` : ''}. Pode me atender?`;
  return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
}

function renderStats(config) {
  const root = $('[data-render="stats"]');
  if (!root) return;
  root.innerHTML = (config.stats || []).map((item) => `
    <article class="stat-card reveal">
      <strong>${escapeHtml(item.number)}</strong>
      <span>${escapeHtml(item.label)}</span>
    </article>
  `).join('');
}

function renderPainItems(config) {
  const root = $('[data-render="painItems"]');
  if (!root) return;
  root.innerHTML = (get(config, 'pain.items', []) || []).map((item) => `<div class="check-item">${escapeHtml(item)}</div>`).join('');
}

function renderFeatures(config) {
  const root = $('[data-render="features"]');
  if (!root) return;
  root.innerHTML = (config.features || []).map((item) => `
    <article class="feature-card reveal">
      <span class="feature-icon">${escapeHtml(item.icon || '✓')}</span>
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.text)}</p>
    </article>
  `).join('');
}

function renderTools(config) {
  const root = $('[data-render="tools"]');
  if (!root) return;
  root.innerHTML = (get(config, 'tools.items', []) || []).map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join('');
}

function renderBrands(config) {
  const root = $('[data-render="brands"]');
  if (!root) return;
  root.innerHTML = (config.brands || []).map((item) => `<span class="brand-pill">${escapeHtml(item)}</span>`).join('');
}

function renderSteps(config) {
  const root = $('[data-render="steps"]');
  if (!root) return;
  root.innerHTML = (config.steps || []).map((item) => `
    <article class="step-card reveal">
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.text)}</p>
    </article>
  `).join('');
}

function renderPlans(config) {
  const root = $('[data-render="plans"]');
  const select = $('[data-plan-select]');
  if (root) {
    root.innerHTML = (config.plans || []).map((plan) => `
      <article class="plan-card reveal ${plan.featured ? 'featured' : ''}">
        ${plan.tag ? `<span class="plan-tag">${escapeHtml(plan.tag)}</span>` : ''}
        <h3>${escapeHtml(plan.name)}</h3>
        <div class="price">${escapeHtml(plan.price)} <small>${escapeHtml(plan.period || '')}</small></div>
        <ul class="benefits">${(plan.benefits || []).map((b) => `<li>${escapeHtml(b)}</li>`).join('')}</ul>
        <a class="button ${plan.featured ? 'primary' : 'ghost'}" href="${whatsappHref(config, plan.name)}" target="_blank" rel="noopener">Tenho interesse</a>
      </article>
    `).join('');
  }
  if (select) {
    select.innerHTML = '<option value="">Selecione</option>' + (config.plans || []).map((p) => `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)}</option>`).join('');
  }
}

function renderFaq(config) {
  const root = $('[data-render="faq"]');
  if (!root) return;
  root.innerHTML = (config.faq || []).map((item, index) => `
    <article class="faq-item ${index === 0 ? 'open' : ''}">
      <button class="faq-question" type="button"><span>${escapeHtml(item.q)}</span><span>+</span></button>
      <div class="faq-answer">${escapeHtml(item.a)}</div>
    </article>
  `).join('');
  $$('.faq-question', root).forEach((button) => {
    button.addEventListener('click', () => button.closest('.faq-item').classList.toggle('open'));
  });
}

function toggleSections(config) {
  $$('[data-section]').forEach((el) => {
    const key = el.dataset.section;
    el.hidden = config.sections && config.sections[key] === false;
  });
}

function bindWhatsApp(config) {
  $$('[data-whatsapp-link]').forEach((link) => {
    link.href = whatsappHref(config);
    link.target = '_blank';
    link.rel = 'noopener';
    if (link.classList.contains('primary') && link.textContent.trim().includes('WhatsApp')) {
      link.textContent = get(config, 'hero.primaryButton', 'Chamar no WhatsApp');
    }
  });
}

function bindLeadForm(config) {
  const form = $('[data-lead-form]');
  if (!form) return;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = $('[data-form-message]');
    message.textContent = 'Enviando...';
    message.className = 'form-message';
    const data = Object.fromEntries(new FormData(form));
    try {
      const res = await fetch('/api/leads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || 'Não foi possível enviar.');
      message.textContent = 'Recebido! Vamos te chamar em breve.';
      message.classList.add('ok');
      form.reset();
    } catch (err) {
      message.textContent = err.message;
      message.classList.add('error');
    }
  });
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}

function revealOnScroll() {
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        io.unobserve(entry.target);
      }
    });
  }, { threshold: .12 });
  $$('.reveal').forEach((el) => io.observe(el));
}

function bindMenu() {
  const button = $('[data-menu-button]');
  const nav = $('[data-nav]');
  if (!button || !nav) return;
  button.addEventListener('click', () => nav.classList.toggle('open'));
  $$('a', nav).forEach((a) => a.addEventListener('click', () => nav.classList.remove('open')));
}

async function init() {
  bindMenu();
  try {
    const res = await fetch('/api/config');
    const json = await res.json();
    if (!json.ok) throw new Error('Configuração indisponível.');
    state.config = json.config;
    applyTheme(state.config);
    setTextFields(state.config);
    renderStats(state.config);
    renderPainItems(state.config);
    renderFeatures(state.config);
    renderTools(state.config);
    renderBrands(state.config);
    renderSteps(state.config);
    renderPlans(state.config);
    renderFaq(state.config);
    toggleSections(state.config);
    bindWhatsApp(state.config);
    bindLeadForm(state.config);
    revealOnScroll();
  } catch (err) {
    document.body.insertAdjacentHTML('afterbegin', `<div style="padding:14px;text-align:center;background:#4b1111;color:#fff">${escapeHtml(err.message)}</div>`);
  }
}

document.addEventListener('DOMContentLoaded', init);
