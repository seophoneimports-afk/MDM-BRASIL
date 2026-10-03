import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from server.database import init_db
from server.routes import auth_routes, client_routes, admin_routes, exe_routes, webhook_routes

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

# Mount Static Files (Images, Styles, EXE download)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include API Routers
app.include_router(auth_routes.router)
app.include_router(client_routes.router)
app.include_router(admin_routes.router)
app.include_router(exe_routes.router)
app.include_router(webhook_routes.router)

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

# Web Portal HTML Views
@app.get("/client", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/register", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
def serve_client_portal():
    from server.database import get_db_connection
    theme = "cinema_stealth"
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = 'site_theme'")
            row = cursor.fetchone()
            if row and row["value"]:
                theme = row["value"]
    except Exception:
        pass

    path = os.path.join(TEMPLATES_DIR, "client_portal.html")
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    # Dynamic server-side injection of active theme
    html = html.replace('data-theme="cinema_stealth"', f'data-theme="{theme}"')
    if 'data-theme=' not in html:
        html = html.replace('<body', f'<body data-theme="{theme}"')
    return html

@app.get("/headers", response_class=HTMLResponse)
def serve_headers_showcase():
    path = os.path.join(TEMPLATES_DIR, "header_showcase.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/layouts", response_class=HTMLResponse)
def serve_layouts_showcase():
    path = os.path.join(TEMPLATES_DIR, "layouts_showcase.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/slider-options", response_class=HTMLResponse)
def serve_slider_options():
    path = os.path.join(TEMPLATES_DIR, "slider_options.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/admin", response_class=HTMLResponse)
def serve_admin_portal():
    path = os.path.join(TEMPLATES_DIR, "admin_portal.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
