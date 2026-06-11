'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { URL } = require('url');

const PORT = Number(process.env.PORT || 10000);
const ROOT = __dirname;
const STATIC_DIR = firstExisting([path.join(ROOT, 'public'), path.join(ROOT, 'público'), path.join(ROOT, 'publico')]);
const DATA_DIR = firstExisting([path.join(ROOT, 'data'), path.join(ROOT, 'dados')]);
const CONFIG_FILE = path.join(DATA_DIR, 'site-config.json');
const TOOLS_FILE = path.join(DATA_DIR, 'tools.json');
const LEADS_FILE = path.join(DATA_DIR, 'leads.json');

const ADMIN_USER = process.env.ADMIN_USER || 'admin';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin12345';
const SESSION_SECRET = process.env.SESSION_SECRET || 'dev-secret-change-me-now';
const COOKIE_NAME = 'mdm_session';
const sessions = new Map();
const rateBucket = new Map();

ensureFiles();

function firstExisting(paths) {
  for (const p of paths) {
    if (fs.existsSync(p)) return p;
  }
  return paths[0];
}

function ensureFiles() {
  fs.mkdirSync(STATIC_DIR, { recursive: true });
  fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(CONFIG_FILE)) fs.writeFileSync(CONFIG_FILE, '{}');
  if (!fs.existsSync(TOOLS_FILE)) fs.writeFileSync(TOOLS_FILE, '[]');
  if (!fs.existsSync(LEADS_FILE)) fs.writeFileSync(LEADS_FILE, '[]');
}

function json(res, status, payload, headers = {}) {
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    ...securityHeaders(),
    ...headers
  });
  res.end(JSON.stringify(payload));
}

function text(res, status, content) {
  res.writeHead(status, {
    'content-type': 'text/plain; charset=utf-8',
    ...securityHeaders()
  });
  res.end(content);
}

function securityHeaders() {
  return {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
    'Content-Security-Policy': [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https:",
      "connect-src 'self' https://wa.me https://api.whatsapp.com",
      "font-src 'self' data:",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self' https://wa.me https://api.whatsapp.com"
    ].join('; ')
  };
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (error) {
    return fallback;
  }
}

function writeJson(file, data) {
  fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8');
}

function parseCookies(req) {
  const header = req.headers.cookie || '';
  return Object.fromEntries(header.split(';').filter(Boolean).map(part => {
    const idx = part.indexOf('=');
    if (idx === -1) return [part.trim(), ''];
    return [part.slice(0, idx).trim(), decodeURIComponent(part.slice(idx + 1))];
  }));
}

function sign(value) {
  return crypto.createHmac('sha256', SESSION_SECRET).update(value).digest('hex');
}

function createSession(username) {
  const id = crypto.randomBytes(24).toString('hex');
  sessions.set(id, { username, createdAt: Date.now() });
  return `${id}.${sign(id)}`;
}

function verifySession(req) {
  const token = parseCookies(req)[COOKIE_NAME];
  if (!token || !token.includes('.')) return false;
  const [id, sig] = token.split('.');
  const expected = sign(id);
  if (!crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))) return false;
  const session = sessions.get(id);
  if (!session) return false;
  const maxAge = 1000 * 60 * 60 * 12;
  if (Date.now() - session.createdAt > maxAge) {
    sessions.delete(id);
    return false;
  }
  return true;
}

function destroySession(req) {
  const token = parseCookies(req)[COOKIE_NAME];
  if (token && token.includes('.')) sessions.delete(token.split('.')[0]);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => {
      body += chunk;
      if (body.length > 2_000_000) {
        reject(new Error('Payload muito grande'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!body) return resolve({});
      try { resolve(JSON.parse(body)); }
      catch (e) { reject(new Error('JSON inválido')); }
    });
    req.on('error', reject);
  });
}

function limited(req, limit = 80, windowMs = 60_000) {
  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket.remoteAddress || 'local';
  const now = Date.now();
  const bucket = rateBucket.get(ip) || { count: 0, resetAt: now + windowMs };
  if (now > bucket.resetAt) {
    bucket.count = 0;
    bucket.resetAt = now + windowMs;
  }
  bucket.count += 1;
  rateBucket.set(ip, bucket);
  return bucket.count > limit;
}

function safeFilePath(urlPath) {
  let decoded = decodeURIComponent(urlPath.split('?')[0]);
  if (decoded === '/') decoded = '/index.html';
  const target = path.normalize(path.join(STATIC_DIR, decoded));
  if (!target.startsWith(STATIC_DIR)) return null;
  return target;
}

function contentType(file) {
  const ext = path.extname(file).toLowerCase();
  const types = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml; charset=utf-8',
    '.ico': 'image/x-icon',
    '.webp': 'image/webp',
    '.txt': 'text/plain; charset=utf-8'
  };
  return types[ext] || 'application/octet-stream';
}

function serveStatic(req, res, pathname) {
  const file = safeFilePath(pathname);
  if (!file) return text(res, 403, 'Acesso negado.');
  fs.stat(file, (err, stat) => {
    if (err || !stat.isFile()) {
      const notFound = path.join(STATIC_DIR, '404.html');
      if (fs.existsSync(notFound)) {
        res.writeHead(404, { 'content-type': 'text/html; charset=utf-8', ...securityHeaders() });
        return fs.createReadStream(notFound).pipe(res);
      }
      return text(res, 404, 'Página não encontrada.');
    }
    const headers = {
      'content-type': contentType(file),
      ...securityHeaders()
    };
    if (/\.(css|js|png|jpg|jpeg|svg|webp|ico)$/.test(file)) {
      headers['cache-control'] = 'public, max-age=3600';
    }
    res.writeHead(200, headers);
    fs.createReadStream(file).pipe(res);
  });
}

function cleanString(value, max = 500) {
  if (typeof value !== 'string') return '';
  return value.replace(/[\u0000-\u001F\u007F]/g, '').trim().slice(0, max);
}

function normalizeTools(tools) {
  if (!Array.isArray(tools)) return [];
  return tools.slice(0, 200).map((tool, index) => ({
    id: cleanString(tool.id || crypto.randomUUID(), 80) || `tool-${index}`,
    letter: cleanString(tool.letter || (tool.title || 'M').charAt(0).toUpperCase(), 2),
    title: cleanString(tool.title, 120),
    description: cleanString(tool.description, 300),
    image: cleanString(tool.image, 500),
    download_link: cleanString(tool.download_link, 500),
    whatsapp: Boolean(tool.whatsapp),
    active: tool.active !== false
  })).filter(t => t.title);
}

function authRequired(req, res) {
  if (!verifySession(req)) {
    json(res, 401, { ok: false, error: 'Faça login no painel.' });
    return false;
  }
  return true;
}

const server = http.createServer(async (req, res) => {
  try {
    if (limited(req)) return json(res, 429, { ok: false, error: 'Muitas requisições. Tente novamente em instantes.' });
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
    const { pathname } = url;

    if (pathname === '/api/health') {
      return json(res, 200, { ok: true, status: 'online', service: 'MDM & FRP BRASIL', staticDir: path.basename(STATIC_DIR), dataDir: path.basename(DATA_DIR) });
    }

    if (pathname === '/api/site' && req.method === 'GET') {
      const config = readJson(CONFIG_FILE, {});
      const tools = normalizeTools(readJson(TOOLS_FILE, []));
      return json(res, 200, { ok: true, config, tools });
    }

    if (pathname === '/api/auth/login' && req.method === 'POST') {
      const body = await readBody(req);
      const username = cleanString(body.username, 120);
      const password = cleanString(body.password, 200);
      if (username !== ADMIN_USER || password !== ADMIN_PASSWORD) {
        return json(res, 401, { ok: false, error: 'Usuário ou senha inválidos.' });
      }
      const token = createSession(username);
      return json(res, 200, { ok: true }, {
        'Set-Cookie': `${COOKIE_NAME}=${encodeURIComponent(token)}; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200${process.env.NODE_ENV === 'production' ? '; Secure' : ''}`
      });
    }

    if (pathname === '/api/auth/logout' && req.method === 'POST') {
      destroySession(req);
      return json(res, 200, { ok: true }, { 'Set-Cookie': `${COOKIE_NAME}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0` });
    }

    if (pathname === '/api/admin/check' && req.method === 'GET') {
      return json(res, 200, { ok: true, logged: verifySession(req) });
    }

    if (pathname === '/api/admin/site' && req.method === 'GET') {
      if (!authRequired(req, res)) return;
      return json(res, 200, { ok: true, config: readJson(CONFIG_FILE, {}), tools: normalizeTools(readJson(TOOLS_FILE, [])), leads: readJson(LEADS_FILE, []) });
    }

    if (pathname === '/api/admin/config' && req.method === 'PUT') {
      if (!authRequired(req, res)) return;
      const body = await readBody(req);
      if (!body || typeof body !== 'object') return json(res, 400, { ok: false, error: 'Configuração inválida.' });
      writeJson(CONFIG_FILE, body);
      return json(res, 200, { ok: true, config: body });
    }

    if (pathname === '/api/admin/tools' && req.method === 'PUT') {
      if (!authRequired(req, res)) return;
      const body = await readBody(req);
      const tools = normalizeTools(Array.isArray(body) ? body : body.tools);
      writeJson(TOOLS_FILE, tools);
      return json(res, 200, { ok: true, tools });
    }

    if (pathname === '/api/leads' && req.method === 'POST') {
      const body = await readBody(req);
      const lead = {
        id: crypto.randomUUID(),
        createdAt: new Date().toISOString(),
        name: cleanString(body.name, 120),
        phone: cleanString(body.phone, 60),
        interest: cleanString(body.interest, 120),
        message: cleanString(body.message, 600)
      };
      if (!lead.name || !lead.phone) return json(res, 400, { ok: false, error: 'Informe nome e telefone.' });
      const leads = readJson(LEADS_FILE, []);
      leads.unshift(lead);
      writeJson(LEADS_FILE, leads.slice(0, 500));
      return json(res, 201, { ok: true, lead });
    }

    return serveStatic(req, res, pathname);
  } catch (error) {
    console.error(error);
    return json(res, 500, { ok: false, error: error.message || 'Erro interno.' });
  }
});

server.listen(PORT, () => {
  console.log(`MDM & FRP BRASIL online em http://localhost:${PORT}`);
  console.log(`Painel admin: http://localhost:${PORT}/admin.html`);
  if (ADMIN_PASSWORD === 'admin12345') console.log('ATENÇÃO: troque ADMIN_PASSWORD em produção.');
});
