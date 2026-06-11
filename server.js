'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { URL } = require('url');

const ROOT = __dirname;
const PUBLIC_DIR = path.join(ROOT, 'public');
const DATA_DIR = path.join(ROOT, 'data');
const CONFIG_PATH = path.join(DATA_DIR, 'site-config.json');
const LEADS_PATH = path.join(DATA_DIR, 'leads.json');

const PORT = Number(process.env.PORT || 3000);
const ADMIN_USER = process.env.ADMIN_USER || 'admin';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin12345';
const SESSION_SECRET = process.env.SESSION_SECRET || 'dev-secret-change-this-in-production-please-32chars';
const IS_PROD = process.env.NODE_ENV === 'production';

const RATE_WINDOW_MS = 15 * 60 * 1000;
const RATE_MAX = 180;
const rateBuckets = new Map();

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8'
};

function ensureDataFiles() {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(CONFIG_PATH)) {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(defaultConfig(), null, 2));
  }
  if (!fs.existsSync(LEADS_PATH)) fs.writeFileSync(LEADS_PATH, '[]');
}

function defaultConfig() {
  return {
    seo: {
      title: 'MDM & FRP Brasil | Soluções técnicas autorizadas',
      description: 'Plataforma profissional para atendimento técnico autorizado, suporte e gestão de serviços em dispositivos móveis.',
      siteUrl: process.env.SITE_URL || 'http://localhost:3000'
    },
    brand: {
      name: 'MDM & FRP Brasil',
      shortName: 'MDM FRP',
      whatsapp: '5519994783127',
      email: 'atendimento@seudominio.com.br',
      badge: 'Atendimento técnico responsável'
    },
    theme: {
      primary: '#16f29a',
      secondary: '#42a5ff',
      accent: '#f6c84c',
      background: '#08111f',
      surface: '#101c2e',
      text: '#f4f8ff',
      muted: '#aab7c9',
      radius: 24,
      density: 'confortavel',
      layout: 'premium'
    },
    hero: {
      eyebrow: 'Central profissional para técnicos',
      title: 'Site profissional para atendimento técnico, planos e suporte autorizado.',
      subtitle: 'Organize seus serviços, apresente planos, capture contatos e direcione clientes para o WhatsApp com uma experiência moderna, rápida e segura.',
      primaryButton: 'Chamar no WhatsApp',
      secondaryButton: 'Ver planos',
      imageTitle: 'Painel técnico',
      imageText: 'Atendimento responsável, documentação do cliente e operação segura.'
    },
    stats: [
      { number: '24h', label: 'Atendimento rápido' },
      { number: '+15', label: 'Marcas no catálogo' },
      { number: '100%', label: 'Foco em uso autorizado' }
    ],
    pain: {
      title: 'Seu cliente precisa confiar antes de chamar.',
      description: 'Um site bem estruturado passa profissionalismo, explica limites do serviço e reduz dúvidas antes do atendimento.',
      items: [
        'Página pronta para apresentar serviços e planos',
        'Contato direto pelo WhatsApp configurado',
        'Painel admin para editar textos, cores e preços',
        'Backend com salvamento real das alterações'
      ]
    },
    features: [
      {
        icon: '🛡️',
        title: 'Operação responsável',
        text: 'Textos preparados para reforçar atendimento técnico com autorização e comprovação do cliente.'
      },
      {
        icon: '⚡',
        title: 'Rápido e responsivo',
        text: 'Interface otimizada para celular, computador e compartilhamento direto no WhatsApp.'
      },
      {
        icon: '🎛️',
        title: 'Painel admin real',
        text: 'Altere marca, cores, planos, benefícios, FAQ e chamadas sem editar código.'
      },
      {
        icon: '🔐',
        title: 'Headers de segurança',
        text: 'Backend com proteção básica, sessões assinadas, CSP e limites de requisição.'
      }
    ],
    tools: {
      title: 'O que o site entrega para sua operação',
      description: 'Uma presença digital profissional para vender melhor, organizar dúvidas e captar contatos.',
      items: [
        'Landing page premium',
        'Admin com login',
        'Edição de layout',
        'Gestão de planos',
        'Formulário de leads',
        'Integração WhatsApp',
        'FAQ editável',
        'Aviso legal'
      ]
    },
    brands: ['Samsung', 'Motorola', 'Xiaomi', 'LG', 'Realme', 'OPPO', 'Vivo', 'Infinix', 'Tecno', 'Positivo', 'Multilaser', 'Lenovo'],
    steps: [
      { title: '1. Cliente chama', text: 'O visitante escolhe o plano ou envia dúvida pelo formulário/WhatsApp.' },
      { title: '2. Você qualifica', text: 'Confirma documentação, autorização e detalhes do aparelho antes de qualquer atendimento.' },
      { title: '3. Atendimento seguro', text: 'O serviço é feito apenas em aparelhos próprios, autorizados e com responsabilidade.' }
    ],
    plans: [
      {
        name: 'Essencial',
        price: 'R$ 29,90',
        period: '/mês',
        tag: 'Para começar',
        featured: false,
        benefits: ['Página profissional', 'Contato por WhatsApp', 'FAQ completo', 'Atualização manual']
      },
      {
        name: 'Profissional',
        price: 'R$ 59,90',
        period: '/mês',
        tag: 'Mais escolhido',
        featured: true,
        benefits: ['Tudo do Essencial', 'Painel admin', 'Captação de leads', 'Layout editável', 'Planos editáveis']
      },
      {
        name: 'Premium',
        price: 'R$ 99,90',
        period: '/mês',
        tag: 'Operação completa',
        featured: false,
        benefits: ['Tudo do Profissional', 'Prioridade no atendimento', 'Mais seções', 'Suporte para publicação']
      }
    ],
    faq: [
      {
        q: 'O painel admin salva de verdade?',
        a: 'Sim. Nesta versão com backend, as alterações são salvas no arquivo data/site-config.json do servidor.'
      },
      {
        q: 'Consigo mudar cores e layout?',
        a: 'Sim. Você pode alterar cores principais, raio dos cards, textos, planos, benefícios e FAQ pelo painel.'
      },
      {
        q: 'O site funciona no celular?',
        a: 'Sim. A interface foi feita pensando primeiro em celular, mas também fica profissional no computador.'
      },
      {
        q: 'Posso usar para serviços técnicos?',
        a: 'Sim, desde que os atendimentos sejam legais, autorizados e com comprovação do proprietário do aparelho.'
      }
    ],
    legal: {
      title: 'Uso legal e autorizado',
      text: 'A MDM & FRP Brasil atua apenas com orientação, atendimento técnico responsável e serviços autorizados pelo proprietário legítimo do dispositivo. Não realizamos nem incentivamos uso indevido, acesso não autorizado, fraude, desbloqueio de aparelhos de terceiros ou contorno ilegal de sistemas de segurança.'
    },
    sections: {
      stats: true,
      pain: true,
      features: true,
      tools: true,
      brands: true,
      steps: true,
      plans: true,
      faq: true,
      legal: true
    }
  };
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (_) {
    return fallback;
  }
}

function writeJson(file, data) {
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
  fs.renameSync(tmp, file);
}

function securityHeaders(contentType = 'text/plain; charset=utf-8') {
  return {
    'Content-Type': contentType,
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=()',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Resource-Policy': 'same-origin',
    'Cache-Control': 'no-store',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
  };
}

function send(res, status, body, contentType) {
  const headers = securityHeaders(contentType || 'text/plain; charset=utf-8');
  res.writeHead(status, headers);
  res.end(body);
}

function sendJson(res, status, payload) {
  send(res, status, JSON.stringify(payload), 'application/json; charset=utf-8');
}

function clientIp(req) {
  const forwarded = req.headers['x-forwarded-for'];
  if (forwarded) return String(forwarded).split(',')[0].trim();
  return req.socket.remoteAddress || 'unknown';
}

function rateLimit(req, res) {
  const ip = clientIp(req);
  const now = Date.now();
  const current = rateBuckets.get(ip) || { count: 0, reset: now + RATE_WINDOW_MS };
  if (now > current.reset) {
    current.count = 0;
    current.reset = now + RATE_WINDOW_MS;
  }
  current.count += 1;
  rateBuckets.set(ip, current);
  if (current.count > RATE_MAX) {
    sendJson(res, 429, { ok: false, error: 'Muitas requisições. Tente novamente em alguns minutos.' });
    return false;
  }
  return true;
}

function parseCookies(req) {
  const header = req.headers.cookie || '';
  return Object.fromEntries(header.split(';').filter(Boolean).map((part) => {
    const idx = part.indexOf('=');
    if (idx === -1) return [part.trim(), ''];
    return [part.slice(0, idx).trim(), decodeURIComponent(part.slice(idx + 1))];
  }));
}

function sign(value) {
  return crypto.createHmac('sha256', SESSION_SECRET).update(value).digest('base64url');
}

function createSession(username) {
  const payload = Buffer.from(JSON.stringify({ username, exp: Date.now() + 1000 * 60 * 60 * 8 })).toString('base64url');
  return `${payload}.${sign(payload)}`;
}

function verifySession(req) {
  const cookies = parseCookies(req);
  const token = cookies.session;
  if (!token || !token.includes('.')) return false;
  const [payload, signature] = token.split('.');
  const expected = sign(payload);
  try {
    if (!crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return false;
    const data = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    return data.username === ADMIN_USER && data.exp > Date.now();
  } catch (_) {
    return false;
  }
}

function safeCompare(a, b) {
  const aa = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (aa.length !== bb.length) return false;
  return crypto.timingSafeEqual(aa, bb);
}

function readBody(req, maxBytes = 150_000) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
      if (Buffer.byteLength(body) > maxBytes) {
        reject(new Error('Payload muito grande'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!body) return resolve({});
      try {
        resolve(JSON.parse(body));
      } catch (_) {
        reject(new Error('JSON inválido'));
      }
    });
    req.on('error', reject);
  });
}

function sanitizeText(value, max = 5000) {
  return String(value ?? '').replace(/[<>]/g, '').slice(0, max).trim();
}

function sanitizeConfig(input) {
  const base = defaultConfig();
  const current = readJson(CONFIG_PATH, base);
  const cfg = { ...current, ...input };

  cfg.seo = { ...current.seo, ...(input.seo || {}) };
  cfg.brand = { ...current.brand, ...(input.brand || {}) };
  cfg.theme = { ...current.theme, ...(input.theme || {}) };
  cfg.hero = { ...current.hero, ...(input.hero || {}) };
  cfg.pain = { ...current.pain, ...(input.pain || {}) };
  cfg.tools = { ...current.tools, ...(input.tools || {}) };
  cfg.legal = { ...current.legal, ...(input.legal || {}) };
  cfg.sections = { ...current.sections, ...(input.sections || {}) };

  cfg.seo.title = sanitizeText(cfg.seo.title, 90) || base.seo.title;
  cfg.seo.description = sanitizeText(cfg.seo.description, 180) || base.seo.description;
  cfg.seo.siteUrl = sanitizeText(cfg.seo.siteUrl, 200) || base.seo.siteUrl;

  cfg.brand.name = sanitizeText(cfg.brand.name, 80) || base.brand.name;
  cfg.brand.shortName = sanitizeText(cfg.brand.shortName, 30) || base.brand.shortName;
  cfg.brand.email = sanitizeText(cfg.brand.email, 100);
  cfg.brand.badge = sanitizeText(cfg.brand.badge, 80);
  cfg.brand.whatsapp = String(cfg.brand.whatsapp || '').replace(/\D/g, '').slice(0, 14) || '5519994783127';

  for (const key of ['primary', 'secondary', 'accent', 'background', 'surface', 'text', 'muted']) {
    const value = String(cfg.theme[key] || '');
    cfg.theme[key] = /^#[0-9a-fA-F]{6}$/.test(value) ? value : base.theme[key];
  }
  cfg.theme.radius = Math.min(40, Math.max(6, Number(cfg.theme.radius || 24)));
  cfg.theme.density = ['compacto', 'confortavel', 'espacoso'].includes(cfg.theme.density) ? cfg.theme.density : 'confortavel';
  cfg.theme.layout = ['premium', 'direto', 'corporativo'].includes(cfg.theme.layout) ? cfg.theme.layout : 'premium';

  for (const key of ['eyebrow', 'title', 'subtitle', 'primaryButton', 'secondaryButton', 'imageTitle', 'imageText']) {
    cfg.hero[key] = sanitizeText(cfg.hero[key], key === 'subtitle' ? 350 : 120);
  }

  cfg.stats = Array.isArray(cfg.stats) ? cfg.stats.slice(0, 6).map((item) => ({
    number: sanitizeText(item.number, 20),
    label: sanitizeText(item.label, 60)
  })).filter((item) => item.number && item.label) : base.stats;

  cfg.pain.title = sanitizeText(cfg.pain.title, 120);
  cfg.pain.description = sanitizeText(cfg.pain.description, 300);
  cfg.pain.items = Array.isArray(cfg.pain.items) ? cfg.pain.items.slice(0, 8).map((x) => sanitizeText(x, 120)).filter(Boolean) : base.pain.items;

  cfg.features = Array.isArray(cfg.features) ? cfg.features.slice(0, 8).map((item) => ({
    icon: sanitizeText(item.icon, 10),
    title: sanitizeText(item.title, 80),
    text: sanitizeText(item.text, 220)
  })).filter((item) => item.title && item.text) : base.features;

  cfg.tools.title = sanitizeText(cfg.tools.title, 120);
  cfg.tools.description = sanitizeText(cfg.tools.description, 250);
  cfg.tools.items = Array.isArray(cfg.tools.items) ? cfg.tools.items.slice(0, 16).map((x) => sanitizeText(x, 80)).filter(Boolean) : base.tools.items;

  cfg.brands = Array.isArray(cfg.brands) ? cfg.brands.slice(0, 24).map((x) => sanitizeText(x, 40)).filter(Boolean) : base.brands;

  cfg.steps = Array.isArray(cfg.steps) ? cfg.steps.slice(0, 6).map((item) => ({
    title: sanitizeText(item.title, 80),
    text: sanitizeText(item.text, 220)
  })).filter((item) => item.title && item.text) : base.steps;

  cfg.plans = Array.isArray(cfg.plans) ? cfg.plans.slice(0, 6).map((plan) => ({
    name: sanitizeText(plan.name, 60),
    price: sanitizeText(plan.price, 40),
    period: sanitizeText(plan.period, 30),
    tag: sanitizeText(plan.tag, 50),
    featured: Boolean(plan.featured),
    benefits: Array.isArray(plan.benefits) ? plan.benefits.slice(0, 10).map((x) => sanitizeText(x, 120)).filter(Boolean) : []
  })).filter((plan) => plan.name && plan.price) : base.plans;

  cfg.faq = Array.isArray(cfg.faq) ? cfg.faq.slice(0, 10).map((item) => ({
    q: sanitizeText(item.q, 140),
    a: sanitizeText(item.a, 500)
  })).filter((item) => item.q && item.a) : base.faq;

  cfg.legal.title = sanitizeText(cfg.legal.title, 120);
  cfg.legal.text = sanitizeText(cfg.legal.text, 700);

  Object.keys(cfg.sections).forEach((k) => { cfg.sections[k] = Boolean(cfg.sections[k]); });
  return cfg;
}

async function handleApi(req, res, pathname) {
  try {
    if (pathname === '/api/health' && req.method === 'GET') {
      return sendJson(res, 200, { ok: true, status: 'online' });
    }

    if (pathname === '/api/config' && req.method === 'GET') {
      return sendJson(res, 200, { ok: true, config: readJson(CONFIG_PATH, defaultConfig()) });
    }

    if (pathname === '/api/leads' && req.method === 'POST') {
      const body = await readBody(req, 20_000);
      const lead = {
        id: crypto.randomUUID(),
        createdAt: new Date().toISOString(),
        name: sanitizeText(body.name, 80),
        phone: sanitizeText(body.phone, 40),
        plan: sanitizeText(body.plan, 60),
        message: sanitizeText(body.message, 500)
      };
      if (!lead.name || !lead.phone) return sendJson(res, 400, { ok: false, error: 'Informe nome e telefone.' });
      const leads = readJson(LEADS_PATH, []);
      leads.unshift(lead);
      writeJson(LEADS_PATH, leads.slice(0, 500));
      return sendJson(res, 201, { ok: true, message: 'Contato recebido com sucesso.' });
    }

    if (pathname === '/api/admin/login' && req.method === 'POST') {
      const body = await readBody(req, 10_000);
      const valid = safeCompare(body.username || '', ADMIN_USER) && safeCompare(body.password || '', ADMIN_PASSWORD);
      if (!valid) return sendJson(res, 401, { ok: false, error: 'Usuário ou senha inválidos.' });
      const token = createSession(ADMIN_USER);
      const cookie = `session=${encodeURIComponent(token)}; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800${IS_PROD ? '; Secure' : ''}`;
      const headers = securityHeaders('application/json; charset=utf-8');
      headers['Set-Cookie'] = cookie;
      res.writeHead(200, headers);
      return res.end(JSON.stringify({ ok: true }));
    }

    if (pathname === '/api/admin/logout' && req.method === 'POST') {
      const headers = securityHeaders('application/json; charset=utf-8');
      headers['Set-Cookie'] = `session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0${IS_PROD ? '; Secure' : ''}`;
      res.writeHead(200, headers);
      return res.end(JSON.stringify({ ok: true }));
    }

    if (pathname.startsWith('/api/admin')) {
      if (!verifySession(req)) return sendJson(res, 401, { ok: false, error: 'Faça login no painel.' });

      if (pathname === '/api/admin/config' && req.method === 'GET') {
        return sendJson(res, 200, { ok: true, config: readJson(CONFIG_PATH, defaultConfig()) });
      }

      if (pathname === '/api/admin/config' && req.method === 'PUT') {
        const body = await readBody(req, 200_000);
        const config = sanitizeConfig(body.config || body);
        writeJson(CONFIG_PATH, config);
        return sendJson(res, 200, { ok: true, config });
      }

      if (pathname === '/api/admin/leads' && req.method === 'GET') {
        return sendJson(res, 200, { ok: true, leads: readJson(LEADS_PATH, []).slice(0, 200) });
      }
    }

    return sendJson(res, 404, { ok: false, error: 'Rota não encontrada.' });
  } catch (err) {
    return sendJson(res, 400, { ok: false, error: err.message || 'Erro na requisição.' });
  }
}

function serveStatic(req, res, pathname) {
  let filePath = pathname === '/' ? path.join(PUBLIC_DIR, 'index.html') : path.join(PUBLIC_DIR, decodeURIComponent(pathname));
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(PUBLIC_DIR)) return send(res, 403, 'Acesso negado.', 'text/plain; charset=utf-8');

  if (!fs.existsSync(resolved) || fs.statSync(resolved).isDirectory()) {
    filePath = path.join(PUBLIC_DIR, '404.html');
    if (!fs.existsSync(filePath)) return send(res, 404, 'Página não encontrada.', 'text/plain; charset=utf-8');
    return send(res, 404, fs.readFileSync(filePath), 'text/html; charset=utf-8');
  }

  const ext = path.extname(resolved).toLowerCase();
  const type = MIME[ext] || 'application/octet-stream';
  const headers = securityHeaders(type);
  if (['.css', '.js', '.svg', '.png', '.jpg', '.jpeg', '.ico'].includes(ext)) headers['Cache-Control'] = 'public, max-age=86400, immutable';
  res.writeHead(200, headers);
  fs.createReadStream(resolved).pipe(res);
}

ensureDataFiles();

const server = http.createServer(async (req, res) => {
  if (!rateLimit(req, res)) return;
  const parsed = new URL(req.url, `http://${req.headers.host}`);
  const pathname = parsed.pathname;
  if (pathname.startsWith('/api/')) return handleApi(req, res, pathname);
  return serveStatic(req, res, pathname);
});

server.listen(PORT, () => {
  console.log(`MDM & FRP Brasil online em http://localhost:${PORT}`);
  console.log(`Painel admin: http://localhost:${PORT}/admin.html`);
  if (ADMIN_PASSWORD === 'admin12345') {
    console.log('ATENÇÃO: troque ADMIN_PASSWORD em produção. Senha padrão apenas para teste local.');
  }
});
