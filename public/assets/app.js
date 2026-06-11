let site = null;
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

function get(obj, path, fallback = '') {
  return path.split('.').reduce((acc, key) => acc && acc[key] !== undefined ? acc[key] : undefined, obj) ?? fallback;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"]+/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char] || char));
}

function applyTheme(config) {
  const theme = config.theme || {};
  Object.entries(theme).forEach(([key, value]) => {
    document.documentElement.style.setProperty(`--${key}`, value);
  });
  if (config.seo?.title) document.title = config.seo.title;
  const desc = document.querySelector('meta[name="description"]');
  if (desc && config.seo?.description) desc.content = config.seo.description;
}

function whatsappUrl(config, message = '') {
  const number = String(config.brand?.whatsapp || '').replace(/\D/g, '');
  const text = message || `Olá! Quero informações sobre os planos da ${config.brand?.name || 'MDM & FRP BRASIL'}.`;
  return `https://wa.me/${number}?text=${encodeURIComponent(text)}`;
}

function fillText(config) {
  $$('[data-text]').forEach(el => {
    const path = el.dataset.text;
    const value = get(config, path, el.textContent);
    el.textContent = value;
  });
  $$('[data-button]').forEach(el => {
    const value = get(config, el.dataset.button, el.textContent);
    el.textContent = value;
  });
  $$('[data-brand-logo]').forEach(img => {
    if (config.brand?.logo) img.src = config.brand.logo;
    if (config.brand?.name) img.alt = config.brand.name;
  });
  $$('[data-whatsapp]').forEach(link => {
    link.href = whatsappUrl(config);
    link.target = '_blank';
    link.rel = 'noopener';
  });
}

function renderNav(config) {
  const nav = $('[data-nav]');
  if (!nav) return;
  nav.innerHTML = (config.nav || []).map(item => `<a href="${escapeHtml(item.href)}">${escapeHtml(item.label)}</a>`).join('');
}

function renderTools(config, tools) {
  const wrap = $('[data-tools]');
  if (!wrap) return;
  const activeTools = (tools || []).filter(t => t.active !== false);
  wrap.innerHTML = activeTools.map(tool => {
    const target = tool.download_link || whatsappUrl(config, `Olá! Quero informações sobre ${tool.title}.`);
    return `<a class="tool-card" href="${escapeHtml(target)}" target="_blank" rel="noopener">
      <div class="tool-letter">${escapeHtml(tool.letter || (tool.title || 'M')[0])}</div>
      <div class="tool-body"><h3>${escapeHtml(tool.title)}</h3><span>${escapeHtml(tool.description || 'MDM • FRP • BRASIL')}</span></div>
      <div class="tool-media">${tool.image ? '<img src="' + escapeHtml(tool.image) + '" alt="">' : 'sem mídia'}</div>
    </a>`;
  }).join('') || '<p class="muted">Nenhuma ferramenta cadastrada.</p>';
}

function renderMarquee(config) {
  const wrap = $('[data-marquee]');
  if (!wrap) return;
  const items = [...(config.marquee || []), ...(config.marquee || [])];
  wrap.innerHTML = items.map(item => `<span>${escapeHtml(item)}</span>`).join('');
}

function renderHero(config) {
  $('[data-tags]').innerHTML = (config.hero?.tags || []).map(t => `<span>${escapeHtml(t)}</span>`).join('');
  $('[data-trust]').innerHTML = (config.hero?.trust || []).map(t => `<span>${escapeHtml(t)}</span>`).join('');
}

function renderPain(config) {
  $('[data-pain]').innerHTML = (config.pain?.items || []).map(item => `<article class="pain-card"><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.text)}</p></article>`).join('');
}

function renderReceive(config) {
  $('[data-receive]').innerHTML = (config.receive?.items || []).map((item, i) => `<article class="receive-card"><div class="receive-icon">${i + 1}</div><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.text)}</p></div></article>`).join('');
}

function renderBrands(config) {
  $('[data-brands]').innerHTML = (config.brands?.items || []).map(item => `<span>${escapeHtml(item)}</span>`).join('');
}

function renderSteps(config) {
  $('[data-steps]').innerHTML = (config.steps?.items || []).map(item => `<article class="step-card"><div class="step-num">${escapeHtml(item.number)}</div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.text)}</p></article>`).join('');
}

function renderPlans(config) {
  const plans = config.plans || [];
  $('[data-plans]').innerHTML = plans.map(plan => {
    const href = plan.checkout || whatsappUrl(config, `Olá! Quero assinar o plano ${plan.name}.`);
    return `<article class="plan-card ${plan.featured ? 'featured' : ''}">
      <span class="plan-tag">${escapeHtml(plan.tag || '')}</span>
      <h3>${escapeHtml(plan.name)}</h3>
      <p class="old-price">${escapeHtml(plan.oldPrice || '')}</p>
      <p class="price">${escapeHtml(plan.price || '')}</p>
      <span class="period">${escapeHtml(plan.period || '')}</span>
      <ul>${(plan.benefits || []).map(b => `<li>${escapeHtml(b)}</li>`).join('')}</ul>
      <a class="btn btn-primary full" href="${escapeHtml(href)}" target="_blank" rel="noopener">Garantir meu acesso</a>
    </article>`;
  }).join('');
  const select = $('[data-plan-select]');
  if (select) select.innerHTML = plans.map(p => `<option>${escapeHtml(p.name)}</option>`).join('') || '<option>Planos</option>';
}

function renderEthics(config) {
  $('[data-ethics]').innerHTML = (config.ethics?.items || []).map(item => `<article class="ethics-card"><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.text)}</p></article>`).join('');
}

function renderFaq(config) {
  $('[data-faq]').innerHTML = (config.faq?.items || []).map((item, i) => `<article class="faq-item ${i === 0 ? 'open' : ''}"><button class="faq-question" type="button"><span>${escapeHtml(item.q)}</span><b>+</b></button><div class="faq-answer">${escapeHtml(item.a)}</div></article>`).join('');
  $$('.faq-question').forEach(btn => btn.addEventListener('click', () => btn.closest('.faq-item').classList.toggle('open')));
}

function applySections(config) {
  const sections = config.sections || {};
  $$('[data-section]').forEach(el => {
    const key = el.dataset.section;
    if (sections[key] === false) el.style.display = 'none';
    else el.style.display = '';
  });
}

function bindLeadForm(config) {
  const form = $('[data-lead-form]');
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const status = $('[data-form-status]');
    status.textContent = 'Enviando...';
    const payload = Object.fromEntries(new FormData(form));
    try {
      const res = await fetch('/api/leads', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Não foi possível enviar.');
      status.textContent = 'Contato salvo! Agora você pode chamar no WhatsApp.';
      form.reset();
      setTimeout(() => window.open(whatsappUrl(config, `Olá! Meu nome é ${payload.name}. Quero informações sobre ${payload.interest}.`), '_blank'), 700);
    } catch (err) {
      status.textContent = err.message;
    }
  });
}

function bindMenu() {
  const btn = $('[data-menu]');
  const nav = $('[data-nav]');
  if (btn && nav) btn.addEventListener('click', () => nav.classList.toggle('open'));
}

async function init() {
  bindMenu();
  const res = await fetch('/api/site');
  const data = await res.json();
  site = data;
  const config = data.config || {};
  applyTheme(config);
  fillText(config);
  renderNav(config);
  renderTools(config, data.tools || []);
  renderMarquee(config);
  renderHero(config);
  renderPain(config);
  renderReceive(config);
  renderBrands(config);
  renderSteps(config);
  renderPlans(config);
  renderEthics(config);
  renderFaq(config);
  applySections(config);
  bindLeadForm(config);
}

document.addEventListener('DOMContentLoaded', init);
