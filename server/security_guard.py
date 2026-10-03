import re
from datetime import datetime
from fastapi.responses import HTMLResponse, JSONResponse
from server.auth import log_audit_event

HONEYPOT_PATHS = {
    "/wp-login.php", "/wp-login", "/wp-admin", "/wp-admin/", "/wp-config.php",
    "/phpmyadmin", "/phpmyadmin/", "/pma", "/pma/", "/admin.php",
    "/.env", "/.env.local", "/.env.production", "/.git", "/.git/HEAD", "/.git/config",
    "/config.json", "/server-status", "/setup.php", "/shell.php", "/eval.php",
    "/eval-stdin.php", "/cmd.php", "/wso.php", "/alfa.php", "/c99.php",
    "/xmlrpc.php", "/install.php", "/cgi-bin", "/actuator", "/actuator/health",
    "/console", "/mysql", "/backup.sql", "/db.sql", "/dump.sql", "/database.sqlite",
    "/database.db", "/db.sqlite3", "/backup.zip", "/backup.tar.gz",
    "/solr", "/jenkins", "/boaform",
    # Traps contra scanners de engenharia reversa e enumeração de APIs Swagger / OpenAPI
    "/docs", "/redoc", "/openapi.json", "/swagger", "/swagger-ui",
    "/swagger.json", "/v2/api-docs", "/v3/api-docs", "/api-docs"
}

SQLI_PATTERNS = [
    r"(?i)\bunion\s+(?:all\s+)?select\b",
    r"(?i)'\s*or\s*['\"]?1['\"]?\s*=\s*['\"]?1",
    r"(?i)\bselect\s+.*\s+from\b",
    r"(?i)\bdrop\s+table\b",
    r"(?i)\binformation_schema\b",
    r"(?i)\bbenchmark\s*\(",
    r"(?i)\bsleep\s*\(\s*\d+\s*\)",
    r"(?i);?\s*exec\s*\(",
    r"(?i)--\s*$",
    r"(?i)/\*\s*\*/"
]

TRAVERSAL_PATTERNS = [
    r"\.\./\.\.",
    r"\.\.\\\.\.",
    r"%2e%2e%2f",
    r"(?i)/etc/passwd",
    r"(?i)/windows/system32",
    r"(?i)web\.config",
    r"(?i)/boot\.ini"
]

XSS_PATTERNS = [
    r"(?i)<\s*script\b",
    r"(?i)javascript:",
    r"(?i)onerror\s*=",
    r"(?i)onload\s*=",
    r"(?i)<iframe\b"
]

def check_for_intrusion(path: str, raw_query: str) -> tuple[bool, str, str]:
    """
    Returns (is_intrusion, attack_type, matched_detail)
    """
    path_clean = path.lower().strip()
    query_clean = raw_query.lower().strip()

    # 1. Test / Simulator trap
    if "test_hack=1" in query_clean:
        return True, "TESTE_SIMULADO_INVASAO", "Simulação de tentativa de ataque acionada"

    # 2. Honeypot check
    for h in HONEYPOT_PATHS:
        if path_clean == h or path_clean.startswith(h + "/"):
            return True, "HONEYPOT_HIT", f"Tentativa de acesso a rota vulnerável simulada ({h})"

    # 3. SQL Injection check
    full_target = f"{path_clean}?{query_clean}"
    for pat in SQLI_PATTERNS:
        if re.search(pat, full_target):
            return True, "SQL_INJECTION", f"Padrão SQLi detectado na requisição: {pat}"

    # 4. Path Traversal check
    for pat in TRAVERSAL_PATTERNS:
        if re.search(pat, full_target):
            return True, "PATH_TRAVERSAL", f"Padrão de Directory Traversal detectado: {pat}"

    # 5. XSS Injection check
    for pat in XSS_PATTERNS:
        if re.search(pat, full_target):
            return True, "XSS_INJECTION", f"Padrão de script malicioso/XSS detectado: {pat}"

    return False, "", ""

def get_hacker_troll_html(client_ip: str, attack_type: str, path: str) -> str:
    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🚨 ACESSO BLOQUEADO • MDM & FRP BRASIL FIREWALL</title>
  <link rel="icon" type="image/x-icon" href="/static/favicon.ico">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800;900&family=JetBrains+Mono:wght@600;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --danger: #EF4444;
      --cyan: #00E5FF;
      --green: #00E676;
      --bg: #030712;
      --card: rgba(15, 23, 42, 0.95);
      --border: rgba(239, 68, 68, 0.45);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: radial-gradient(circle at center, #111827 0%, #030712 100%);
      color: #F8FAFC;
      font-family: 'Plus Jakarta Sans', sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      overflow-x: hidden;
    }}
    .troll-card {{
      background: var(--card);
      border: 2px solid var(--danger);
      border-radius: 24px;
      max-width: 680px;
      width: 100%;
      padding: 36px 28px;
      text-align: center;
      box-shadow: 0 0 60px rgba(239, 68, 68, 0.35), 0 20px 50px rgba(0, 0, 0, 0.9);
      position: relative;
      animation: shake 0.6s cubic-bezier(.36,.07,.19,.97) both;
    }}
    @keyframes shake {{
      10%, 90% {{ transform: translate3d(-1px, 0, 0); }}
      20%, 80% {{ transform: translate3d(2px, 0, 0); }}
      30%, 50%, 70% {{ transform: translate3d(-4px, 0, 0); }}
      40%, 60% {{ transform: translate3d(4px, 0, 0); }}
    }}
    .siren-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid var(--danger);
      color: #EF4444;
      padding: 8px 20px;
      border-radius: 30px;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0.5px;
      margin-bottom: 20px;
      animation: pulse 1s infinite alternate;
    }}
    @keyframes pulse {{
      0% {{ box-shadow: 0 0 10px rgba(239, 68, 68, 0.3); }}
      100% {{ box-shadow: 0 0 25px rgba(239, 68, 68, 0.8); }}
    }}
    .meme-img {{
      width: 260px;
      height: 260px;
      object-fit: cover;
      border-radius: 20px;
      border: 3px solid var(--danger);
      margin: 0 auto 20px;
      display: block;
      box-shadow: 0 10px 30px rgba(239, 68, 68, 0.4);
    }}
    h1 {{
      font-size: 28px;
      font-weight: 900;
      color: #FFF;
      margin-bottom: 8px;
      letter-spacing: -0.5px;
    }}
    .punchline {{
      font-size: 15px;
      color: #FCA5A5;
      font-weight: 700;
      margin-bottom: 22px;
      line-height: 1.5;
    }}
    .telemetry-box {{
      background: rgba(0, 0, 0, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 14px;
      padding: 16px 20px;
      text-align: left;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12.5px;
      color: #E2E8F0;
      margin-bottom: 22px;
      line-height: 1.8;
    }}
    .telemetry-row {{
      display: flex;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      padding: 4px 0;
    }}
    .telemetry-row:last-child {{ border-bottom: none; }}
    .telemetry-label {{ color: #94A3B8; }}
    .telemetry-val {{ color: var(--cyan); font-weight: 700; }}
    .telemetry-danger {{ color: var(--danger); font-weight: 800; }}
    .advice-text {{
      font-size: 13.5px;
      color: #94A3B8;
      margin-bottom: 26px;
      line-height: 1.6;
    }}
    .btn-actions {{
      display: flex;
      gap: 14px;
      justify-content: center;
      flex-wrap: wrap;
    }}
    .btn-peace {{
      background: var(--green);
      color: #060911;
      font-weight: 800;
      padding: 12px 24px;
      border-radius: 10px;
      text-decoration: none;
      font-size: 13.5px;
      transition: all 0.2s;
      box-shadow: 0 0 20px rgba(0, 230, 118, 0.35);
    }}
    .btn-peace:hover {{
      transform: translateY(-2px);
      box-shadow: 0 0 30px rgba(0, 230, 118, 0.6);
    }}
    .btn-forgive {{
      background: linear-gradient(135deg, #EF4444 0%, #DC2626 100%);
      color: #FFF;
      font-weight: 800;
      padding: 12px 24px;
      border-radius: 10px;
      text-decoration: none;
      font-size: 13.5px;
      transition: all 0.2s;
      box-shadow: 0 0 20px rgba(239, 68, 68, 0.35);
    }}
    .btn-forgive:hover {{
      transform: translateY(-2px);
      box-shadow: 0 0 30px rgba(239, 68, 68, 0.6);
    }}
  </style>
</head>
<body>
  <div class="troll-card">
    <div class="siren-badge">
      <span>🚨</span>
      <span>INTRUSÃO BLOQUEADA PELO FIREWALL MDM &amp; FRP BRASIL</span>
      <span>🚨</span>
    </div>

    <!-- Funny Hacker Meme Image -->
    <img src="/static/hacker_blocked.jpg" alt="Hacker Pego no Flagrante" class="meme-img">

    <h1>CALMA AÍ, MR. ROBOT DA SHOPEE! 😂🐶</h1>
    <div class="punchline">
      Achou que ia burlar o sistema com script de internet? Nosso cão de guarda da bancada interceptou sua tentativa em 0.001 segundos!
    </div>

    <!-- Telemetria do Invasor -->
    <div class="telemetry-box">
      <div class="telemetry-row">
        <span class="telemetry-label">📡 Endereço IP Detectado:</span>
        <span class="telemetry-danger">{client_ip}</span>
      </div>
      <div class="telemetry-row">
        <span class="telemetry-label">🎯 Alvo Tentado:</span>
        <span class="telemetry-val">{path}</span>
      </div>
      <div class="telemetry-row">
        <span class="telemetry-label">⚡ Tipo de Ataque:</span>
        <span class="telemetry-danger">{attack_type}</span>
      </div>
      <div class="telemetry-row">
        <span class="telemetry-label">⏰ Data do Flagrante:</span>
        <span class="telemetry-val">{now_str}</span>
      </div>
      <div class="telemetry-row">
        <span class="telemetry-label">📋 Registro de Auditoria:</span>
        <span class="telemetry-val" style="color: #F59E0B;">GRAVADO NO PAINEL DO ADMINISTRADOR 🔒</span>
      </div>
    </div>

    <p class="advice-text">
      💡 <strong>Dica de amigo:</strong> Enquanto você gasta seu tempo tentando hackear, os técnicos de verdade estão na bancada ganhando dinheiro desbloqueando aparelhos via PIX! 💸
    </p>

    <div class="btn-actions">
      <a href="/" class="btn-peace">🕊️ Voltar e Usar o Site em Paz</a>
      <a href="https://wa.me/5519994783127?text=Fala%20patr%C3%A3o%2C%20tentei%20dar%20uma%20de%20hacker%20no%20site%20mas%20fui%20pego%20pelo%20caramelo%20kkkk%20quero%20comprar%20cr%C3%A9ditos%20como%20uma%20pessoa%20normal%20%F0%9F%98%82" target="_blank" class="btn-forgive">
        💬 Pedir Desculpas no WhatsApp 😂
      </a>
    </div>
  </div>
</body>
</html>"""
