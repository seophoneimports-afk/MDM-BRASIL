import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from server.database import init_db
from server.routes import auth_routes, client_routes, admin_routes, exe_routes, webhook_routes, device_routes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database on startup
    init_db()
    yield

app = FastAPI(
    title="MDM & FRP BRASIL — Cloud Platform API",
    description="API Centralizada para Autenticação, Carteira de Créditos, Pagamentos PIX, Gestão de Ordens e Integração com o EXE",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security Headers Middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Server"] = "Protected-Gateway"
    return response

from server.security_guard import check_for_intrusion, get_hacker_troll_html
from server.auth import log_audit_event

@app.middleware("http")
async def security_intrusion_middleware(request: Request, call_next):
    path = request.url.path
    query = request.url.query
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Fast bypass for static files and mobile device APK sync
    if path.startswith("/static") or path == "/favicon.ico" or path.startswith("/api/device") or path.startswith("/api/v1/device"):
        return await call_next(request)

    # Direct preview route for admin/security trap demonstration
    if path == "/security-trap":
        return await call_next(request)

    is_intrusion, attack_type, detail = check_for_intrusion(path, query)
    if is_intrusion:
        # Record immediately into database audit log
        log_audit_event(
            "SECURITY_INTRUSION_ATTEMPT",
            details={
                "attack_type": attack_type,
                "target_path": path,
                "query_string": query[:250],
                "detail": detail,
                "user_agent": request.headers.get("user-agent", "Unknown"),
                "action_taken": "BLOCKED_WITH_TROLL_PAGE"
            },
            ip_address=client_ip
        )
        accept = request.headers.get("accept", "")
        if "text/html" in accept or path in ("/wp-login.php", "/wp-admin", "/phpmyadmin") or "test_hack=1" in query:
            return HTMLResponse(content=get_hacker_troll_html(client_ip, attack_type, path), status_code=403)
        else:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Acesso Bloqueado!",
                    "message": "Tentando invadir aqui, patrão? 😂 Seu IP foi registrado e enviado para o painel de auditoria do Administrador!",
                    "ip": client_ip,
                    "attack_type": attack_type,
                    "funny_meme": "/static/hacker_blocked.jpg"
                }
            )

    return await call_next(request)

@app.get("/security-trap", response_class=HTMLResponse)
def serve_security_trap(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    return HTMLResponse(content=get_hacker_troll_html(client_ip, "SIMULACAO_TESTE", "/security-trap"), status_code=200)

# Mount Static Files (Images, Styles, EXE download)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include API Routers
app.include_router(auth_routes.router)
app.include_router(client_routes.router)
app.include_router(admin_routes.router)
app.include_router(exe_routes.router)
app.include_router(webhook_routes.router)
app.include_router(device_routes.router)

@app.get("/api/v1/ranking/monthly", tags=["Public Ranking"])
def get_public_monthly_ranking():
    return client_routes.get_monthly_ranking()

from fastapi.responses import FileResponse

# Direct download endpoint for the Windows EXE
@app.get("/download/exe")
def download_exe():
    exe_path = os.path.join(STATIC_DIR, "MDM_FRP_BRASIL.exe")
    if not os.path.exists(exe_path):
        root_exe = os.path.join(os.path.dirname(BASE_DIR), "MDM & FRP BRASIL.exe")
        if os.path.exists(root_exe):
            exe_path = root_exe
    response = FileResponse(
        path=exe_path,
        filename="MDM & FRP BRASIL.exe",
        media_type="application/vnd.microsoft.portable-executable"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Health check
@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "MDM & FRP BRASIL Cloud API",
        "version": "2.0.0",
        "database": "sqlite_wal_active"
    }

# Theme API for dynamic layout switching
@app.get("/api/v1/system/theme")
def get_system_theme():
    from server.database import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'site_theme'")
        row = cursor.fetchone()
        theme = row["value"] if row and row["value"] else "cinema_stealth"
    return {"success": True, "theme": theme}

# Homepage Layout API
@app.get("/api/v1/system/homepage-layout")
def get_public_homepage_layout():
    from server.database import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'homepage_layout'")
        r1 = cursor.fetchone()
        layout = r1["value"] if r1 and r1["value"] else "cinema_split"
        cursor.execute("SELECT value FROM system_settings WHERE key = 'homepage_sections'")
        r2 = cursor.fetchone()
        sections = r2["value"] if r2 and r2["value"] else ""
    return {"success": True, "layout": layout, "sections": sections}

# Public Platform Config API
@app.get("/api/v1/system/public-config")
def get_public_config():
    from server.database import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM system_settings WHERE key IN ('support_whatsapp', 'support_phone', 'support_message', 'platform_name', 'announcement_banner', 'welcome_bonus_credits', 'credit_price_brl', 'site_theme', 'homepage_layout', 'homepage_card_style')")
        rows = cursor.fetchall()
        cfg = {r["key"]: r["value"] for r in rows}
        return {"success": True, "config": cfg}

@app.get("/api/v1/system/card-style")
def get_public_card_style():
    from server.database import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'homepage_card_style'")
        row = cursor.fetchone()
        return {"success": True, "card_style": row["value"] if row and row["value"] else "glass_neon"}

# Web Portal HTML Views
@app.get("/client", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/register", response_class=HTMLResponse)
@app.get("/painel", response_class=HTMLResponse)
@app.get("/conta", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/inicio", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
def serve_client_portal(request: Request):
    from server.database import get_db_connection
    theme = request.query_params.get("preview_theme")
    layout = request.query_params.get("preview_layout") or request.query_params.get("layout")
    card_style = request.query_params.get("preview_cards") or request.query_params.get("card_style")
    supp_wa = None
    supp_phone = None

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if not theme:
                cursor.execute("SELECT value FROM system_settings WHERE key = 'site_theme'")
                row = cursor.fetchone()
                theme = row["value"] if row and row["value"] else "cinema_stealth"
            if not layout:
                cursor.execute("SELECT value FROM system_settings WHERE key = 'homepage_layout'")
                r_lay = cursor.fetchone()
                layout = r_lay["value"] if r_lay and r_lay["value"] else "cinema_split"
            if not card_style:
                cursor.execute("SELECT value FROM system_settings WHERE key = 'homepage_card_style'")
                r_card = cursor.fetchone()
                card_style = r_card["value"] if r_card and r_card["value"] else "glass_neon"
            
            cursor.execute("SELECT key, value FROM system_settings WHERE key IN ('support_whatsapp', 'support_phone')")
            for r in cursor.fetchall():
                if r["key"] == "support_whatsapp" and r["value"]:
                    supp_wa = r["value"]
                elif r["key"] == "support_phone" and r["value"]:
                    supp_phone = r["value"]
    except Exception:
        theme = theme or "cinema_stealth"
        layout = layout or "cinema_split"
        card_style = card_style or "glass_neon"

    path = os.path.join(TEMPLATES_DIR, "client_portal.html")
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    # Dynamic server-side injection of active theme, homepage layout, and card style directly onto <body>
    html = html.replace('<body', f'<body data-theme="{theme}" data-layout="{layout}" data-card-style="{card_style}"', 1)
    
    if supp_wa:
        clean_wa = "".join(filter(str.isdigit, supp_wa))
        if len(clean_wa) in (10, 11) and not clean_wa.startswith("55"):
            clean_wa = "55" + clean_wa
        if clean_wa:
            html = html.replace("5519994783127", clean_wa)
    if supp_phone:
        html = html.replace("(19) 99478-3127", supp_phone)

    return html

@app.get("/headers")
@app.get("/layouts")
@app.get("/slider-options")
@app.get("/dashboards")
@app.get("/dashboard-options")
def redirect_to_home():
    return RedirectResponse(url="/", status_code=302)

@app.get("/white-label")
@app.get("/personalizar-apk")
def redirect_to_white_label():
    return RedirectResponse(url="/?tab=apk_studio", status_code=302)

@app.get("/admin", response_class=HTMLResponse)
def serve_admin_portal():
    path = os.path.join(TEMPLATES_DIR, "admin_portal.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
