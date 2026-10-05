import os
import sys
import json
import time
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog
from PIL import Image, ImageTk
import qrcode
import webbrowser
import customtkinter as ctk
import io
import base64

# Local modules
from AdbManager import AdbManager
from pix_generator import generate_pix_emv, parse_currency
from ApiClient import ApiClient

try:
    import tkintermapview
    HAS_MAPVIEW = True
except Exception:
    tkintermapview = None
    HAS_MAPVIEW = False

THEMES = {
    "cyber_dark": {
        "name": "1. Cyber Tactical (NOC Pro)",
        "bg": "#060911",
        "card": "#0C1220",
        "card_inner": "#080C16",
        "border": "#14223A",
        "accent": "#00E676",
        "cyan": "#00E5FF",
        "blue": "#0284C7",
        "map_layer": "carto_dark",
        "label": "1. CYBER DARK"
    },
    "titanium_slate": {
        "name": "2. Titanium Slate (Studio Clean)",
        "bg": "#0B1120",
        "card": "#1E293B",
        "card_inner": "#0F172A",
        "border": "#334155",
        "accent": "#38BDF8",
        "cyan": "#38BDF8",
        "blue": "#2563EB",
        "map_layer": "google_normal",
        "label": "2. SLATE STUDIO"
    },
    "gold_executive": {
        "name": "3. Gold Executive (VIP Fintech)",
        "bg": "#070B18",
        "card": "#111827",
        "card_inner": "#0B0F19",
        "border": "#374151",
        "accent": "#F59E0B",
        "cyan": "#10B981",
        "blue": "#D97706",
        "map_layer": "google_satellite",
        "label": "3. GOLD VIP"
    }
}

# Setup CustomTkinter Theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

CONFIG_FILE = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MDM_FRP_BRASIL_DSM", "config.json")
AUDIT_FILE = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MDM_FRP_BRASIL_DSM", "audit_log.txt")


class DeviceServiceManagerApp:
    def __init__(self, root):
        self.root = root
        self.WIN_LOGIN_W = 440
        self.WIN_LOGIN_H = 630
        self.WIN_MAIN_W = 1220
        self.WIN_MAIN_H = 750

        # Start application exclusively in compact login gate mode, centered on user monitor
        self.root.update_idletasks()
        scr_w = self.root.winfo_screenwidth()
        scr_h = self.root.winfo_screenheight()
        pos_x = max(0, (scr_w - self.WIN_LOGIN_W) // 2)
        pos_y = max(0, (scr_h - self.WIN_LOGIN_H) // 2)
        self.root.geometry(f"{self.WIN_LOGIN_W}x{self.WIN_LOGIN_H}+{pos_x}+{pos_y}")
        self.root.resizable(False, False)
        self.root.title("MDM & FRP BRASIL — AUTENTICAÇÃO")

        # Set official app icon
        for base_p in [os.path.dirname(__file__), os.path.join(os.path.dirname(__file__), "resources"), os.getcwd()]:
            ico_file = os.path.join(base_p, "app_icon.ico")
            if os.path.exists(ico_file):
                try:
                    self.root.iconbitmap(ico_file)
                    break
                except Exception:
                    pass

        self.adb = AdbManager()
        self.api_client = ApiClient()
        self.selected_device_serial = None
        self.devices_cache = []
        self.current_qr_path = ""
        self.current_emv_payload = ""
        self.qr_ctk_image = None
        self.logo_ctk_image = None

        self.saved_config = self.load_saved_config()
        self.last_devices_fingerprint = None
        self.pending_release = {"serial": None, "active": False}

        # Location Management State
        self.current_location = None
        self.location_history = []
        self.map_zoom_level = 1.0

        # Cloud Devices Management State
        self.cloud_devices_cache = []
        self.cloud_selected_device = None
        self.cloud_filter_text = ""
        self.cloud_filter_status = "TODOS"
        self.cloud_polling_active = False

        # Visual Themes & Dynamic Palette (Default: Modelo 2 Titanium Slate Studio)
        self.current_theme_key = self.saved_config.get("ui_theme", "titanium_slate")
        if self.current_theme_key not in THEMES:
            self.current_theme_key = "titanium_slate"
        thm = THEMES[self.current_theme_key]

        self.CLR_BG = thm["bg"]
        self.CLR_CARD = thm["card"]
        self.CLR_CARD_INNER = thm["card_inner"]
        self.CLR_BORDER = thm["border"]
        self.CLR_BORDER_GREEN = thm["accent"]
        self.CLR_GREEN = thm["accent"]
        self.CLR_GREEN_HOVER = "#00C853"
        self.CLR_CYAN = thm["cyan"]
        self.CLR_BLUE = thm["blue"]
        self.CLR_BLUE_HOVER = "#0369A1"
        self.CLR_TEXT_WHITE = "#F8FAFC"
        self.CLR_TEXT_MUTED = "#94A3B8"
        self.current_map_marker = None

        self.root.configure(fg_color=self.CLR_BG)

        self._build_modern_ui()
        self._load_initial_values()

        # Background device detection loop
        self.polling_active = True
        self.poll_thread = threading.Thread(target=self._device_polling_worker, daemon=True)
        self.poll_thread.start()

    def safe_after(self, ms, func, *args):
        try:
            if hasattr(self, 'root') and self.root and self.root.winfo_exists():
                return self.root.after(ms, func, *args)
        except Exception:
            return None

    # ========================================================
    # MODERN UI BUILDER (COMPACT & RESPONSIVE)
    # ========================================================
    def _build_modern_ui(self):
        # 1. MAIN SHELL (REVEALED AFTER LOGIN)
        self.main_shell = ctk.CTkFrame(self.root, fg_color=self.CLR_BG)

        # 2. LEFT SIDEBAR NAVIGATION (MODELO 2: TITANIUM SLATE STUDIO RAIL)
        self.sidebar_nav = ctk.CTkFrame(
            self.main_shell,
            width=200,
            fg_color="#0F172A",
            corner_radius=12,
            border_width=1,
            border_color="#334155"
        )
        self.sidebar_nav.pack(side="left", fill="y", padx=(6, 6), pady=6)
        self.sidebar_nav.pack_propagate(False)

        # Brand header in sidebar
        brand_frame = ctk.CTkFrame(self.sidebar_nav, fg_color="transparent")
        brand_frame.pack(fill="x", padx=14, pady=(16, 18))

        lbl_b_title = ctk.CTkLabel(
            brand_frame,
            text="🛡️ MDM & FRP",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#FFFFFF"
        )
        lbl_b_title.pack(anchor="w")

        lbl_b_sub = ctk.CTkLabel(
            brand_frame,
            text="SLATE STUDIO V2.2",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#38BDF8"
        )
        lbl_b_sub.pack(anchor="w")

        # Sidebar navigation buttons
        self.nav_buttons = {}
        nav_items = [
            ("bench", "⚡ Bancada USB", lambda: self._switch_view("bench")),
            ("cloud", "☁️ Aparelhos Nuvem", lambda: self._switch_view("cloud")),
            ("maps", "📍 Google Maps", lambda: self._switch_view("maps")),
            ("pix", "⚙️ Chave PIX & Loja", lambda: self._switch_view("pix")),
            ("recharge", "💎 Planos & Recarga", lambda: self._switch_view("recharge")),
            ("history", "📜 Logs Auditoria", lambda: self._switch_view("history")),
        ]

        for key, label, cmd in nav_items:
            btn = ctk.CTkButton(
                self.sidebar_nav,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                fg_color="#1E293B" if key == "bench" else "transparent",
                hover_color="#334155",
                text_color="#38BDF8" if key == "bench" else "#94A3B8",
                anchor="w",
                corner_radius=8,
                height=38,
                command=cmd
            )
            btn.pack(fill="x", padx=10, pady=4)
            self.nav_buttons[key] = btn

        # Spacer in sidebar
        sidebar_spacer = ctk.CTkFrame(self.sidebar_nav, fg_color="transparent")
        sidebar_spacer.pack(fill="both", expand=True)

        # Card de Identificação do Lojista Conectado
        self.sidebar_user_frame = ctk.CTkFrame(
            self.sidebar_nav,
            fg_color="#080E1B",
            corner_radius=8,
            border_width=1,
            border_color="#1E293B"
        )
        self.sidebar_user_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.lbl_side_user = ctk.CTkLabel(
            self.sidebar_user_frame,
            text="👤 Técnico Convidado",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        self.lbl_side_user.pack(fill="x", padx=10, pady=(6, 1))

        self.lbl_side_bal = ctk.CTkLabel(
            self.sidebar_user_frame,
            text="🪙 Saldo: 0 Créditos",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#00E676",
            anchor="w"
        )
        self.lbl_side_bal.pack(fill="x", padx=10, pady=(0, 6))

        # Bottom sidebar buttons
        btn_site = ctk.CTkButton(
            self.sidebar_nav,
            text="🌐 Abrir Site Cloud",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#1E293B",
            hover_color="#334155",
            text_color="#00E5FF",
            anchor="w",
            height=32,
            command=self.open_client_portal_in_browser
        )
        btn_site.pack(fill="x", padx=10, pady=(0, 6))

        btn_wa = ctk.CTkButton(
            self.sidebar_nav,
            text="💬 WhatsApp Suporte",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#022414",
            hover_color="#059669",
            text_color="#00E676",
            anchor="w",
            height=32,
            command=self.open_whatsapp_support
        )
        btn_wa.pack(fill="x", padx=10, pady=(0, 14))

        # 3. MAIN CONTENT AREA (TO THE RIGHT OF THE SIDEBAR)
        self.main_content_frame = ctk.CTkFrame(self.main_shell, fg_color="transparent")
        self.main_content_frame.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=6)

        # Header Frame inside main content
        self.header_frame = ctk.CTkFrame(
            self.main_content_frame,
            fg_color="#0F172A",
            corner_radius=10,
            border_width=1,
            border_color="#334155"
        )
        self.header_frame.pack(fill="x", pady=(0, 8))

        header_inner = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        header_inner.pack(fill="x", padx=12, pady=8)

        # Left: Breadcrumbs / Title
        title_box = ctk.CTkFrame(header_inner, fg_color="transparent")
        title_box.pack(side="left", fill="y")

        self.lbl_view_title = ctk.CTkLabel(
            title_box,
            text="⚡ BANCADA USB • GESTÃO & DESBLOQUEIO",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#FFFFFF"
        )
        self.lbl_view_title.pack(anchor="w")

        self.lbl_view_sub = ctk.CTkLabel(
            title_box,
            text="Reconhecimento ADB em tempo real e injeção DPC Knox",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.CLR_CYAN
        )
        self.lbl_view_sub.pack(anchor="w")

        # Right: Account & Telemetry
        status_box = ctk.CTkFrame(header_inner, fg_color="transparent")
        status_box.pack(side="right")

        self.btn_account = ctk.CTkButton(
            status_box,
            text="👤 Entrar / Login",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#1E293B",
            hover_color="#334155",
            corner_radius=6,
            height=28,
            command=self.open_login_dialog
        )
        self.btn_account.pack(side="left", padx=(0, 6))

        self.lbl_wallet_badge = ctk.CTkLabel(
            status_box,
            text="🪙 0 Créditos",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#022414",
            text_color=self.CLR_GREEN,
            corner_radius=6,
            padx=10,
            pady=5
        )
        self.lbl_wallet_badge.pack(side="left", padx=(0, 6))

        self.btn_recharge = ctk.CTkButton(
            status_box,
            text="⚡ Recarregar PIX",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#059669",
            hover_color=self.CLR_GREEN,
            corner_radius=6,
            height=28,
            width=110,
            command=self.open_inapp_recharge_dialog
        )
        self.btn_recharge.pack(side="left", padx=(0, 8))

        self.lbl_connection_badge = ctk.CTkLabel(
            status_box,
            text="● VERIFICANDO ADB...",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#121E31",
            text_color=self.CLR_TEXT_MUTED,
            corner_radius=6,
            padx=12,
            pady=5
        )
        self.lbl_connection_badge.pack(side="left", padx=(0, 6))

        btn_refresh = ctk.CTkButton(
            status_box,
            text="🔄 Atualizar",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=self.CLR_BLUE,
            hover_color=self.CLR_BLUE_HOVER,
            corner_radius=6,
            width=85,
            height=28,
            command=self.refresh_devices_async
        )
        btn_refresh.pack(side="left")

        # 4. VIEWS CONTAINER
        self.views_container = ctk.CTkFrame(self.main_content_frame, fg_color="transparent")
        self.views_container.pack(fill="both", expand=True)

        self.view_bench = ctk.CTkFrame(self.views_container, fg_color="transparent")
        self.view_cloud = ctk.CTkFrame(self.views_container, fg_color="transparent")
        self.view_maps = ctk.CTkFrame(self.views_container, fg_color="transparent")
        self.view_pix = ctk.CTkFrame(self.views_container, fg_color="transparent")
        self.view_recharge = ctk.CTkFrame(self.views_container, fg_color="transparent")
        self.view_history = ctk.CTkFrame(self.views_container, fg_color="transparent")

        # Compatibility aliases so existing builder methods work seamlessly
        self.tab_gestao = self.view_bench
        self.tab_cloud = self.view_cloud
        self.tab_loc = self.view_maps
        self.tabview = self

        # 5. LOGIN GATE
        self._build_login_gate_ui()

        # 6. BUILD EACH VIEW
        self._build_tab_gestao()
        self._build_tab_cloud()
        self._build_tab_location()
        self._build_tab_pix()
        self._build_tab_recharge()
        self._build_tab_history()

        # Start with login gate
        self.show_login_gate()

    def set(self, tab_name):
        """Compatibility shim for old tabview.set() calls."""
        if "LOCALIZ" in tab_name or "MAP" in tab_name:
            self._switch_view("maps")
        elif "CLOUD" in tab_name or "NUVEM" in tab_name:
            self._switch_view("cloud")
        elif "PIX" in tab_name:
            self._switch_view("pix")
        else:
            self._switch_view("bench")

    def _switch_view(self, target_key):
        self.current_view_key = target_key
        for key, btn in self.nav_buttons.items():
            if key == target_key:
                btn.configure(fg_color="#1E293B", text_color="#38BDF8")
            else:
                btn.configure(fg_color="transparent", text_color="#94A3B8")

        for f in [self.view_bench, self.view_cloud, self.view_maps, self.view_pix, self.view_recharge, self.view_history]:
            f.pack_forget()

        if target_key == "bench":
            self.view_bench.pack(fill="both", expand=True)
            self.lbl_view_title.configure(text="⚡ BANCADA USB • GESTÃO & DESBLOQUEIO")
            self.lbl_view_sub.configure(text="Reconhecimento ADB em tempo real e injeção DPC Knox")
        elif target_key == "cloud":
            self.view_cloud.pack(fill="both", expand=True)
            self.lbl_view_title.configure(text="☁️ APARELHOS NA NUVEM • CONTROLE REMOTO")
            self.lbl_view_sub.configure(text="Dispositivos sincronizados na conta do lojista sem necessidade de cabo")
            self.refresh_cloud_devices_async()
        elif target_key == "maps":
            self.view_maps.pack(fill="both", expand=True)
            self.lbl_view_title.configure(text="📍 GOOGLE MAPS • LOCALIZAÇÃO REAL")
            self.lbl_view_sub.configure(text="Rastreamento GPS via hardware com visualização de ruas e satélite")
        elif target_key == "pix":
            self.view_pix.pack(fill="both", expand=True)
            self.lbl_view_title.configure(text="⚙️ CONFIGURAÇÃO DE CHAVE PIX & LOJA")
            self.lbl_view_sub.configure(text="Defina seus dados para recebimento direto de pagamentos nos aparelhos")
        elif target_key == "recharge":
            self.view_recharge.pack(fill="both", expand=True)
            self.lbl_view_title.configure(text="💎 PLANOS & RECARGA PIX AUTOMÁTICA")
            self.lbl_view_sub.configure(text="Recarregue créditos instantaneamente via PIX direto no aplicativo")
        elif target_key == "history":
            self.view_history.pack(fill="both", expand=True)
            self.lbl_view_title.configure(text="📜 LOGS DE AUDITORIA & REGISTRO DE COMANDOS")
            self.lbl_view_sub.configure(text="Histórico completo de comandos executados na bancada e na nuvem")
            self.refresh_history_tab()

    def _build_tab_pix(self):
        container = ctk.CTkFrame(self.view_pix, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=2, pady=2)

        card = ctk.CTkFrame(container, fg_color=self.CLR_CARD, corner_radius=12, border_width=1, border_color=self.CLR_BORDER)
        card.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            card,
            text="⚙️  CONFIGURAÇÃO DE RECEBIMENTO PIX PESSOAL",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.CLR_CYAN
        ).pack(anchor="w", padx=20, pady=(16, 6))

        ctk.CTkLabel(
            card,
            text="Configure a sua própria chave PIX. Quando você emitir uma ordem de serviço ou bloquear um aparelho,\no cliente final pagará diretamente na sua conta bancária sem intermediários.",
            font=ctk.CTkFont(size=11),
            text_color=self.CLR_TEXT_MUTED,
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 16))

        form_box = ctk.CTkFrame(card, fg_color="transparent")
        form_box.pack(fill="x", padx=20, pady=8)

        # Chave PIX
        ctk.CTkLabel(form_box, text="Sua Chave PIX (Telefone, CPF, CNPJ, E-mail ou EVP):", font=ctk.CTkFont(size=11, weight="bold"), text_color="#FFF").pack(anchor="w", pady=(0, 3))
        self.ent_pix_alt = ctk.CTkEntry(form_box, font=ctk.CTkFont(size=12), fg_color=self.CLR_CARD_INNER, border_color=self.CLR_BORDER, corner_radius=8, height=34)
        self.ent_pix_alt.insert(0, self.saved_config.get("pix", ""))
        self.ent_pix_alt.pack(fill="x", pady=(0, 12))

        # Nome Titular
        ctk.CTkLabel(form_box, text="Nome do Titular / Razão Social:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#FFF").pack(anchor="w", pady=(0, 3))
        self.ent_merchant_alt = ctk.CTkEntry(form_box, font=ctk.CTkFont(size=12), fg_color=self.CLR_CARD_INNER, border_color=self.CLR_BORDER, corner_radius=8, height=34)
        self.ent_merchant_alt.insert(0, self.saved_config.get("merchant", "Central Cell Premium"))
        self.ent_merchant_alt.pack(fill="x", pady=(0, 12))

        # Cidade
        ctk.CTkLabel(form_box, text="Cidade do Titular:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#FFF").pack(anchor="w", pady=(0, 3))
        self.ent_city_alt = ctk.CTkEntry(form_box, font=ctk.CTkFont(size=12), fg_color=self.CLR_CARD_INNER, border_color=self.CLR_BORDER, corner_radius=8, height=34)
        self.ent_city_alt.insert(0, self.saved_config.get("city", "Americana"))
        self.ent_city_alt.pack(fill="x", pady=(0, 16))

        btn_box = ctk.CTkFrame(form_box, fg_color="transparent")
        btn_box.pack(fill="x")

        def _save_pix_from_tab():
            val = self.ent_pix_alt.get().strip()
            merch = self.ent_merchant_alt.get().strip()
            city = self.ent_city_alt.get().strip()
            if hasattr(self, 'ent_pix') and self.ent_pix:
                self.ent_pix.delete(0, "end")
                self.ent_pix.insert(0, val)
            if hasattr(self, 'ent_merchant') and self.ent_merchant:
                self.ent_merchant.delete(0, "end")
                self.ent_merchant.insert(0, merch)
            if hasattr(self, 'ent_city') and self.ent_city:
                self.ent_city.delete(0, "end")
                self.ent_city.insert(0, city)
            self.save_pix_config()
            self.log("[CONFIG] Chave PIX atualizada com sucesso!")

        btn_save = ctk.CTkButton(
            btn_box,
            text="💾 Salvar Minha Chave PIX",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=self.CLR_GREEN,
            hover_color=self.CLR_GREEN_HOVER,
            corner_radius=8,
            height=36,
            command=_save_pix_from_tab
        )
        btn_save.pack(side="left", padx=(0, 10))

        btn_gen = ctk.CTkButton(
            btn_box,
            text="⚡ Gerar QR Code PIX de Teste",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=self.CLR_BLUE,
            hover_color=self.CLR_BLUE_HOVER,
            corner_radius=8,
            height=36,
            command=self.generate_qr_click
        )
        btn_gen.pack(side="left")

    def _build_tab_recharge(self):
        container = ctk.CTkFrame(self.view_recharge, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=2, pady=2)
        container.columnconfigure(0, weight=5)
        container.columnconfigure(1, weight=5)
        container.rowconfigure(0, weight=1)

        # Left Column: Pacotes de Recarga
        card_pkgs = ctk.CTkFrame(container, fg_color=self.CLR_CARD, corner_radius=12, border_width=1, border_color=self.CLR_BORDER)
        card_pkgs.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=6)

        ctk.CTkLabel(
            card_pkgs,
            text="💎  PACOTES DE CRÉDITOS & RECARGA PIX",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.CLR_CYAN
        ).pack(anchor="w", padx=16, pady=(16, 4))

        ctk.CTkLabel(
            card_pkgs,
            text="Selecione um pacote com bônus para liberação imediata em até 10 segundos:",
            font=ctk.CTkFont(size=10),
            text_color=self.CLR_TEXT_MUTED
        ).pack(anchor="w", padx=16, pady=(0, 12))

        self.recharge_tab_pkg = tk.IntVar(value=10)
        packages = [
            (5, "5 Créditos (+1 BÔNUS = 6)", "R$ 25,00", "+1 Bônus Grátis"),
            (10, "10 Créditos (+2 BÔNUS = 12)", "R$ 50,00", "🔥 MAIS POPULAR"),
            (20, "20 Créditos (+4 BÔNUS = 24)", "R$ 100,00", "+4 Bônus Grátis"),
            (50, "50 Créditos (+10 BÔNUS = 60)", "R$ 250,00", "💎 MELHOR CUSTO")
        ]

        pbox = ctk.CTkFrame(card_pkgs, fg_color=self.CLR_CARD_INNER, corner_radius=8, border_width=1, border_color="#1E293B")
        pbox.pack(fill="x", padx=16, pady=(0, 12))

        for qty, title, price, tag in packages:
            r = ctk.CTkRadioButton(
                pbox,
                text=f"{title} — {price}   [{tag}]",
                variable=self.recharge_tab_pkg,
                value=qty,
                font=ctk.CTkFont(size=11, weight="bold" if qty == 10 else "normal"),
                text_color=self.CLR_GREEN if qty == 10 else self.CLR_TEXT_WHITE
            )
            r.pack(anchor="w", padx=16, pady=8)

        btn_buy = ctk.CTkButton(
            card_pkgs,
            text="⚡ GERAR QR CODE PIX AGORA",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color=self.CLR_GREEN,
            corner_radius=8,
            height=38,
            command=self._generate_tab_pix_recharge
        )
        btn_buy.pack(fill="x", padx=16, pady=(0, 8))

        # Right Column: QR Code & Copia e Cola ao Vivo
        card_qr = ctk.CTkFrame(container, fg_color=self.CLR_CARD, corner_radius=12, border_width=1, border_color=self.CLR_BORDER)
        card_qr.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=6)

        ctk.CTkLabel(
            card_qr,
            text="📱  PAGAMENTO PIX EM TEMPO REAL",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.CLR_GREEN
        ).pack(anchor="w", padx=16, pady=(16, 4))

        # QR Code Display Box
        self.recharge_qr_box = ctk.CTkFrame(card_qr, fg_color="#FFFFFF", corner_radius=10, width=170, height=170)
        self.recharge_qr_box.pack(pady=10)
        self.recharge_qr_box.pack_propagate(False)

        self.lbl_recharge_qr_img = ctk.CTkLabel(self.recharge_qr_box, text="Aguardando\nseleção de pacote", font=ctk.CTkFont(size=10), text_color="#64748B")
        self.lbl_recharge_qr_img.pack(expand=True)

        self.lbl_recharge_status = ctk.CTkLabel(
            card_qr,
            text="Aguardando geração do PIX...",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.CLR_CYAN
        )
        self.lbl_recharge_status.pack(pady=4)

        # Copia e Cola Entry
        self.ent_recharge_payload = ctk.CTkEntry(
            card_qr,
            font=ctk.CTkFont(family="Consolas", size=9),
            placeholder_text="Código Copia-e-Cola aparecerá aqui...",
            fg_color=self.CLR_CARD_INNER,
            border_color="#1E293B",
            corner_radius=6,
            height=30
        )
        self.ent_recharge_payload.pack(fill="x", padx=16, pady=4)

        btn_copy = ctk.CTkButton(
            card_qr,
            text="📋 Copiar Código PIX",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1E293B",
            hover_color="#334155",
            corner_radius=6,
            height=32,
            command=self._copy_tab_recharge_code
        )
        btn_copy.pack(fill="x", padx=16, pady=(0, 6))

        btn_check = ctk.CTkButton(
            card_qr,
            text="🔄 Atualizar Saldo da Conta",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=self.CLR_BLUE,
            hover_color=self.CLR_BLUE_HOVER,
            corner_radius=6,
            height=32,
            command=self._check_tab_recharge_balance
        )
        btn_check.pack(fill="x", padx=16, pady=(0, 10))

    def _generate_tab_pix_recharge(self):
        if not self.api_client.is_logged_in():
            self.show_login_gate()
            return
        qty = self.recharge_tab_pkg.get()
        self.lbl_recharge_status.configure(text=f"Gerando PIX para {qty} créditos...", text_color=self.CLR_CYAN)

        def work():
            ok, res = self.api_client.create_pix_order(qty)
            def done():
                if ok and isinstance(res, dict):
                    payload = res.get("pix_copia_e_cola", "")
                    qr_b64 = res.get("qr_code_base64", "")
                    self.ent_recharge_payload.delete(0, "end")
                    self.ent_recharge_payload.insert(0, payload)
                    self.lbl_recharge_status.configure(text="⏳ PIX Gerado! Aguardando pagamento...", text_color="#F59E0B")
                    if qr_b64:
                        try:
                            raw = base64.b64decode(qr_b64)
                            img = Image.open(io.BytesIO(raw)).resize((150, 150))
                            self._tab_recharge_ctk_img = ctk.CTkImage(img, size=(150, 150))
                            self.lbl_recharge_qr_img.configure(image=self._tab_recharge_ctk_img, text="")
                        except Exception as e:
                            self.lbl_recharge_qr_img.configure(text="[QR Code Gerado]")
                    self._start_tab_pix_polling(res.get("txid", ""))
                else:
                    err = res.get("detail", "Falha na comunicação") if isinstance(res, dict) else str(res)
                    self.lbl_recharge_status.configure(text=f"Erro: {err}", text_color="#EF4444")
            self.safe_after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def _copy_tab_recharge_code(self):
        c = self.ent_recharge_payload.get().strip()
        if c:
            self.root.clipboard_clear()
            self.root.clipboard_append(c)
            messagebox.showinfo("Copiado", "Código PIX Copia-e-Cola copiado para a Área de Transferência!")

    def _check_tab_recharge_balance(self):
        if self.api_client.is_logged_in():
            ok, user = self.api_client.get_current_user()
            if ok and isinstance(user, dict):
                bal = user.get("balance_credits", 0)
                self.api_client.user = user
                self._update_auth_ui()
                self.lbl_recharge_status.configure(text=f"✓ Saldo atualizado: {bal} Créditos", text_color=self.CLR_GREEN)

    def _start_tab_pix_polling(self, txid):
        if not txid:
            return
        def poll():
            for _ in range(30):
                time.sleep(3)
                ok, st = self.api_client.get_pix_status(txid)
                if ok and isinstance(st, dict) and st.get("status") == "PAID":
                    def on_paid():
                        self.lbl_recharge_status.configure(text="✓ Pagamento Confirmado! Créditos Liberados!", text_color=self.CLR_GREEN)
                        self._check_tab_recharge_balance()
                    self.safe_after(0, on_paid)
                    break
        threading.Thread(target=poll, daemon=True).start()

    def _build_tab_history(self):
        container = ctk.CTkFrame(self.view_history, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=2, pady=2)

        card = ctk.CTkFrame(container, fg_color=self.CLR_CARD, corner_radius=12, border_width=1, border_color=self.CLR_BORDER)
        card.pack(fill="both", expand=True, padx=8, pady=8)

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 8))

        ctk.CTkLabel(
            hdr,
            text="📜  LOGS DE AUDITORIA & REGISTRO DE COMANDOS",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.CLR_CYAN
        ).pack(side="left")

        btn_clear = ctk.CTkButton(
            hdr,
            text="🗑️ Limpar Tela",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1E293B",
            hover_color="#334155",
            width=90,
            height=26,
            command=lambda: self.txt_history_log.delete("1.0", tk.END)
        )
        btn_clear.pack(side="right", padx=(6, 0))

        btn_ref = ctk.CTkButton(
            hdr,
            text="🔄 Atualizar Logs",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=self.CLR_BLUE,
            hover_color=self.CLR_BLUE_HOVER,
            width=110,
            height=26,
            command=self.refresh_history_tab
        )
        btn_ref.pack(side="right")

        self.txt_history_log = ctk.CTkTextbox(
            card,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=self.CLR_CARD_INNER,
            border_color="#101C30",
            corner_radius=8,
            text_color="#E2E8F0"
        )
        self.txt_history_log.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.refresh_history_tab()

    def refresh_history_tab(self):
        if not hasattr(self, 'txt_history_log') or not self.txt_history_log:
            return
        self.txt_history_log.delete("1.0", tk.END)
        content = ""
        if os.path.exists(AUDIT_FILE):
            try:
                with open(AUDIT_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                pass
        if not content.strip():
            content = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SISTEMA] Sistema iniciado. Aguardando operações de bancada ou comandos em nuvem.\n"
        self.txt_history_log.insert(tk.END, content)
        self.txt_history_log.see(tk.END)

    def _build_tab_gestao(self):
        container = ctk.CTkFrame(self.tab_gestao, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=2, pady=2)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        left_col = ctk.CTkFrame(container, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        right_col = ctk.CTkFrame(container, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # --- LEFT CARD 1: DISPOSITIVO ANDROID CONECTADO (COMPACT 2-COLUMNS) ---
        card_dev = ctk.CTkFrame(left_col, fg_color=self.CLR_CARD, corner_radius=10, border_width=1, border_color=self.CLR_BORDER)
        card_dev.pack(fill="x", pady=(0, 8))

        tk_hdr1 = ctk.CTkLabel(card_dev, text="📱  DISPOSITIVO ANDROID CONECTADO", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.CLR_CYAN)
        tk_hdr1.pack(anchor="w", padx=12, pady=(8, 4))

        combo_box = ctk.CTkFrame(card_dev, fg_color="transparent")
        combo_box.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkLabel(combo_box, text="Aparelho:", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.CLR_TEXT_MUTED).pack(side="left", padx=(0, 6))
        self.combo_devices = ctk.CTkOptionMenu(
            combo_box,
            values=["Nenhum aparelho detectado"],
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0F172A",
            button_color=self.CLR_BLUE,
            button_hover_color=self.CLR_BLUE_HOVER,
            corner_radius=6,
            height=28,
            command=self._on_device_selected
        )
        self.combo_devices.pack(side="left", fill="x", expand=True)

        # 2-Column Device info grid
        det_box = ctk.CTkFrame(card_dev, fg_color=self.CLR_CARD_INNER, corner_radius=8, border_width=1, border_color="#101C30")
        det_box.pack(fill="x", padx=12, pady=(0, 8))
        det_box.columnconfigure(0, weight=1)
        det_box.columnconfigure(1, weight=1)

        self.dev_labels = {}
        col1_fields = [
            ("STATUS ADB:", "lbl_st_adb"),
            ("MODELO:", "lbl_st_model"),
            ("FABRICANTE:", "lbl_st_mfg"),
            ("ANDROID:", "lbl_st_android"),
            ("SERIAL / ID:", "lbl_st_serial")
        ]
        col2_fields = [
            ("APK SERVIÇO:", "lbl_st_apk"),
            ("ESTADO CELULAR:", "lbl_st_cell"),
            ("STATUS BACKEND:", "lbl_st_backend"),
            ("ID OPERAÇÃO:", "lbl_st_op"),
            ("", "empty_slot")
        ]

        f_c1 = ctk.CTkFrame(det_box, fg_color="transparent")
        f_c1.grid(row=0, column=0, sticky="nsew", padx=8, pady=4)
        for title, key in col1_fields:
            rf = ctk.CTkFrame(f_c1, fg_color="transparent")
            rf.pack(fill="x", pady=1)
            ctk.CTkLabel(rf, text=title, font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color="#64748B", width=95, anchor="w").pack(side="left")
            lbl_v = ctk.CTkLabel(rf, text="—", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=self.CLR_TEXT_WHITE, anchor="w")
            lbl_v.pack(side="left", fill="x", expand=True)
            self.dev_labels[key] = lbl_v

        f_c2 = ctk.CTkFrame(det_box, fg_color="transparent")
        f_c2.grid(row=0, column=1, sticky="nsew", padx=8, pady=4)
        for title, key in col2_fields:
            if not title:
                continue
            rf = ctk.CTkFrame(f_c2, fg_color="transparent")
            rf.pack(fill="x", pady=1)
            ctk.CTkLabel(rf, text=title, font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color="#64748B", width=105, anchor="w").pack(side="left")
            lbl_v = ctk.CTkLabel(rf, text="—", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=self.CLR_TEXT_WHITE, anchor="w")
            lbl_v.pack(side="left", fill="x", expand=True)
            self.dev_labels[key] = lbl_v

        # --- LEFT CARD 2: CONFIGURAÇÃO DO SERVIÇO & PIX (2-COLUMN GRID) ---
        card_cfg = ctk.CTkFrame(left_col, fg_color=self.CLR_CARD, corner_radius=10, border_width=1, border_color=self.CLR_BORDER)
        card_cfg.pack(fill="both", expand=True)

        ctk.CTkLabel(card_cfg, text="⚙️  CONFIGURAÇÃO DO SERVIÇO & CHAVE PIX", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.CLR_CYAN).pack(anchor="w", padx=12, pady=(8, 4))

        cfg_grid = ctk.CTkFrame(card_cfg, fg_color="transparent")
        cfg_grid.pack(fill="x", padx=12, pady=2)
        cfg_grid.columnconfigure(0, weight=1)
        cfg_grid.columnconfigure(1, weight=1)

        # Row 1: Cliente & Serviço
        f_cli = ctk.CTkFrame(cfg_grid, fg_color="transparent")
        f_cli.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=2)
        ctk.CTkLabel(f_cli, text="Nome do Cliente:", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.CLR_TEXT_MUTED).pack(anchor="w")
        self.ent_client = ctk.CTkEntry(f_cli, font=ctk.CTkFont(size=11), fg_color=self.CLR_CARD_INNER, border_color=self.CLR_BORDER, corner_radius=6, height=28)
        self.ent_client.insert(0, self.saved_config.get("client", "Cliente Autorizado"))
        self.ent_client.pack(fill="x")

        f_srv = ctk.CTkFrame(cfg_grid, fg_color="transparent")
        f_srv.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=2)
        ctk.CTkLabel(f_srv, text="Nome do Serviço:", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.CLR_TEXT_MUTED).pack(anchor="w")
        self.ent_service = ctk.CTkEntry(f_srv, font=ctk.CTkFont(size=11), fg_color=self.CLR_CARD_INNER, border_color=self.CLR_BORDER, corner_radius=6, height=28)
        self.ent_service.insert(0, self.saved_config.get("service", "Desbloqueio e Suporte Remoto"))
        self.ent_service.pack(fill="x")

        # Row 2: Valor R$ & Chave Pix
        f_val = ctk.CTkFrame(cfg_grid, fg_color="transparent")
        f_val.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=2)
        ctk.CTkLabel(f_val, text="Valor do Atendimento (R$):", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.CLR_TEXT_MUTED).pack(anchor="w")
        self.ent_value = ctk.CTkEntry(f_val, font=ctk.CTkFont(size=11, weight="bold"), fg_color=self.CLR_CARD_INNER, border_color=self.CLR_BORDER, text_color=self.CLR_GREEN, corner_radius=6, height=28)
        self.ent_value.insert(0, self.saved_config.get("value", "150.00"))
        self.ent_value.pack(fill="x")

        f_pix = ctk.CTkFrame(cfg_grid, fg_color="transparent")
        f_pix.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=2)
        ctk.CTkLabel(f_pix, text="💳 Sua Chave Pix (Personalize Livremente):", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.CLR_GREEN).pack(anchor="w")
        self.ent_pix = ctk.CTkEntry(f_pix, font=ctk.CTkFont(size=11), fg_color=self.CLR_CARD_INNER, border_color=self.CLR_BORDER_GREEN, text_color=self.CLR_GREEN, corner_radius=6, height=28)
        self.ent_pix.insert(0, self.saved_config.get("pix", "19994783127"))
        self.ent_pix.pack(fill="x")

        # Row 3: Titular & Cidade
        f_mer = ctk.CTkFrame(cfg_grid, fg_color="transparent")
        f_mer.grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=2)
        ctk.CTkLabel(f_mer, text="👤 Titular / Nome da Assistência:", font=ctk.CTkFont(size=10), text_color=self.CLR_TEXT_MUTED).pack(anchor="w")
        self.ent_merchant = ctk.CTkEntry(f_mer, font=ctk.CTkFont(size=10), fg_color=self.CLR_CARD_INNER, border_color=self.CLR_BORDER, corner_radius=6, height=26)
        self.ent_merchant.insert(0, self.saved_config.get("merchant", "MDM FRP BRASIL"))
        self.ent_merchant.pack(fill="x")

        f_cid = ctk.CTkFrame(cfg_grid, fg_color="transparent")
        f_cid.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=2)
        ctk.CTkLabel(f_cid, text="🏙️ Cidade do Titular:", font=ctk.CTkFont(size=10), text_color=self.CLR_TEXT_MUTED).pack(anchor="w")
        self.ent_city = ctk.CTkEntry(f_cid, font=ctk.CTkFont(size=10), fg_color=self.CLR_CARD_INNER, border_color=self.CLR_BORDER, corner_radius=6, height=26)
        self.ent_city.insert(0, self.saved_config.get("city", "AMERICANA"))
        self.ent_city.pack(fill="x")

        btn_pix_row = ctk.CTkFrame(card_cfg, fg_color="transparent")
        btn_pix_row.pack(fill="x", padx=12, pady=(6, 8))
        btn_pix_row.columnconfigure(0, weight=1)
        btn_pix_row.columnconfigure(1, weight=1)

        btn_save_my_pix = ctk.CTkButton(
            btn_pix_row,
            text="💾 SALVAR MINHA CHAVE PIX",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#059669",
            hover_color=self.CLR_GREEN,
            text_color="#FFFFFF",
            corner_radius=6,
            height=30,
            command=self.action_save_custom_pix
        )
        btn_save_my_pix.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        btn_gen_pix = ctk.CTkButton(
            btn_pix_row,
            text="⚡ GERAR QR CODE PIX",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#0284C7",
            hover_color=self.CLR_CYAN,
            text_color="#FFFFFF",
            corner_radius=6,
            height=30,
            command=self.action_generate_pix
        )
        btn_gen_pix.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        # --- RIGHT CARD 1: PRÉVIA DO QR CODE PIX (COMPACT) ---
        card_qr = ctk.CTkFrame(right_col, fg_color=self.CLR_CARD, corner_radius=10, border_width=1, border_color=self.CLR_BORDER)
        card_qr.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(card_qr, text="💳  PRÉVIA DO QR CODE PIX (BANCO CENTRAL / EMV)", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.CLR_CYAN).pack(anchor="w", padx=12, pady=(6, 4))

        qr_row = ctk.CTkFrame(card_qr, fg_color="transparent")
        qr_row.pack(fill="x", padx=12, pady=(0, 6))

        # QR Image display (Compact 95x95)
        self.lbl_qr_image = ctk.CTkLabel(
            qr_row,
            text="QR Code\nAguardando",
            font=ctk.CTkFont(size=10),
            fg_color="#040711",
            corner_radius=6,
            width=95,
            height=95
        )
        self.lbl_qr_image.pack(side="left", padx=(0, 10))

        qr_text_box = ctk.CTkFrame(qr_row, fg_color="transparent")
        qr_text_box.pack(side="left", fill="both", expand=True)

        self.lbl_pix_status = ctk.CTkLabel(qr_text_box, text="✓ QR Code Pix Pronto!", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.CLR_GREEN, anchor="w")
        self.lbl_pix_status.pack(fill="x")

        self.lbl_pix_val_display = ctk.CTkLabel(qr_text_box, text="Valor Vinculado: R$ 0,00", font=ctk.CTkFont(size=13, weight="bold"), text_color="#38BDF8", anchor="w")
        self.lbl_pix_val_display.pack(fill="x", pady=(1, 3))

        self.txt_emv_preview = ctk.CTkEntry(qr_text_box, font=ctk.CTkFont(family="Consolas", size=9), fg_color=self.CLR_CARD_INNER, border_color="#101C30", corner_radius=6, height=24)
        self.txt_emv_preview.pack(fill="x", pady=(1, 3))

        btn_copy = ctk.CTkButton(
            qr_text_box,
            text="📋 Copiar Código Pix",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0F172A",
            hover_color="#1E293B",
            corner_radius=6,
            height=24,
            command=self.copy_pix_payload
        )
        btn_copy.pack(anchor="w")

        # --- RIGHT CARD 2: PAINEL DE CONTROLE (COMPACT BUTTONS) ---
        card_actions = ctk.CTkFrame(right_col, fg_color=self.CLR_CARD, corner_radius=10, border_width=1, border_color=self.CLR_BORDER)
        card_actions.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(card_actions, text="🛡️  PAINEL DE CONTROLE DO APARELHO (KIOSK & LIBERAÇÃO)", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.CLR_CYAN).pack(anchor="w", padx=12, pady=(6, 4))

        btn_grid_top = ctk.CTkFrame(card_actions, fg_color="transparent")
        btn_grid_top.pack(fill="x", padx=12, pady=(0, 4))
        btn_grid_top.columnconfigure(0, weight=1)
        btn_grid_top.columnconfigure(1, weight=1)

        btn_inst = ctk.CTkButton(
            btn_grid_top,
            text="📲 1. INSTALAR APK",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0F243A",
            hover_color="#1E3A8A",
            corner_radius=6,
            height=30,
            command=self.action_install_apk
        )
        btn_inst.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        btn_act = ctk.CTkButton(
            btn_grid_top,
            text="📱 2. DEFINIR ATIVO",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0F243A",
            hover_color="#1E3A8A",
            corner_radius=6,
            height=30,
            command=self.action_set_active
        )
        btn_act.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        btn_send_lock = ctk.CTkButton(
            card_actions,
            text="🔒 3. ENVIAR BLOQUEIO PENDENTE (TELA VERDE + PIX)",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            text_color="#FFFFFF",
            corner_radius=6,
            height=32,
            command=self.action_send_pending
        )
        btn_send_lock.pack(fill="x", padx=12, pady=(0, 4))

        # BOTÃO PRINCIPAL DE LIBERAÇÃO — DESTAQUE VERDE NEON
        btn_pay_release = ctk.CTkButton(
            card_actions,
            text="💎 4. CONFIRMAR PAGAMENTO (LIBERAR APARELHO & MANTER ADM)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color=self.CLR_GREEN,
            text_color="#FFFFFF",
            corner_radius=8,
            border_width=1,
            border_color="#10B981",
            height=34,
            command=self.action_confirm_operation
        )
        btn_pay_release.pack(fill="x", padx=12, pady=(0, 6))

        # Seção de Comandos Remotos em Nuvem (Sem USB / Online)
        f_remote = ctk.CTkFrame(card_actions, fg_color="#0A1828", corner_radius=8, border_width=1, border_color="#1E3A8A")
        f_remote.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(f_remote, text="🌐 COMANDOS REMOTOS NUVEM (SEM CABO USB / VIA 4G OU WI-FI)", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.CLR_CYAN).pack(anchor="w", padx=10, pady=(6, 4))

        f_rem_btns = ctk.CTkFrame(f_remote, fg_color="transparent")
        f_rem_btns.pack(fill="x", padx=10, pady=(0, 6))
        f_rem_btns.columnconfigure(0, weight=1)
        f_rem_btns.columnconfigure(1, weight=1)

        btn_rem_lock = ctk.CTkButton(
            f_rem_btns,
            text="🔒 BLOQUEAR REMOTO (NUVEM)",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#991B1B",
            hover_color="#DC2626",
            text_color="#FFFFFF",
            corner_radius=6,
            height=28,
            command=self.action_remote_lock_cloud
        )
        btn_rem_lock.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        btn_rem_unlock = ctk.CTkButton(
            f_rem_btns,
            text="🔓 LIBERAR REMOTO (NUVEM)",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#047857",
            hover_color="#059669",
            text_color="#FFFFFF",
            corner_radius=6,
            height=28,
            command=self.action_remote_unlock_cloud
        )
        btn_rem_unlock.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        # --- RIGHT CARD 3: TERMINAL DE OPERAÇÕES EM TEMPO REAL ---
        card_term = ctk.CTkFrame(right_col, fg_color=self.CLR_CARD, corner_radius=10, border_width=1, border_color=self.CLR_BORDER)
        card_term.pack(fill="both", expand=True)

        ctk.CTkLabel(card_term, text="📜  TERMINAL DE OPERAÇÕES EM TEMPO REAL", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.CLR_CYAN).pack(anchor="w", padx=12, pady=(6, 2))

        self.txt_log = ctk.CTkTextbox(
            card_term,
            fg_color=self.CLR_CARD_INNER,
            border_color="#101C30",
            corner_radius=6,
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color="#E2E8F0"
        )
        self.txt_log.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.log("[SISTEMA] MDM & FRP BRASIL — Device Service Manager pronto.")
        self.log(f"[ADB] Ferramenta embutida: {self.adb.adb_path}")
        self.log("[ADMIN] Ao confirmar pagamento, o aparelho é liberado e o APK permanece em segundo plano como Administrador.")

    # ========================================================
    # TAB 2: LOCALIZAÇÃO & GOOGLE MAPS (COMPACT)
    # ========================================================
    def _build_tab_location(self):
        container = ctk.CTkFrame(self.tab_loc, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=2, pady=2)
        container.columnconfigure(0, weight=4)
        container.columnconfigure(1, weight=5)
        container.rowconfigure(0, weight=1)

        left_col = ctk.CTkFrame(container, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        right_col = ctk.CTkFrame(container, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # --- CARD TELEMETRIA & ENDEREÇO ---
        card_telemetry = ctk.CTkFrame(left_col, fg_color=self.CLR_CARD, corner_radius=10, border_width=1, border_color=self.CLR_BORDER_GREEN)
        card_telemetry.pack(fill="both", expand=True)

        hdr_loc = ctk.CTkFrame(card_telemetry, fg_color="transparent")
        hdr_loc.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(hdr_loc, text="📍  LOCALIZAÇÃO DO DISPOSITIVO", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.CLR_GREEN).pack(side="left")
        self.lbl_loc_conn_badge = ctk.CTkLabel(hdr_loc, text="● VERIFICANDO", font=ctk.CTkFont(size=9, weight="bold"), fg_color="#022414", text_color=self.CLR_GREEN, corner_radius=6, padx=6, pady=1)
        self.lbl_loc_conn_badge.pack(side="right")

        # Telemetry Box (2-column layout for coordinates & stats)
        tbox = ctk.CTkFrame(card_telemetry, fg_color=self.CLR_CARD_INNER, corner_radius=8, border_width=1, border_color="#0A3319")
        tbox.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.lbl_loc_device = ctk.CTkLabel(tbox, text="Dispositivo: —", font=ctk.CTkFont(size=11, weight="bold"), text_color="#FFFFFF", anchor="w")
        self.lbl_loc_device.pack(fill="x", padx=10, pady=(6, 1))

        self.lbl_loc_dev_id = ctk.CTkLabel(tbox, text="ID: —", font=ctk.CTkFont(family="Consolas", size=9), text_color="#A7F3D0", anchor="w")
        self.lbl_loc_dev_id.pack(fill="x", padx=10, pady=1)

        ctk.CTkFrame(tbox, height=1, fg_color="#0A3319").pack(fill="x", padx=10, pady=4)

        # Coordinates Display
        row_coords = ctk.CTkFrame(tbox, fg_color="transparent")
        row_coords.pack(fill="x", padx=10, pady=1)
        self.lbl_loc_lat = ctk.CTkLabel(row_coords, text="Lat: —", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color=self.CLR_GREEN, anchor="w")
        self.lbl_loc_lat.pack(side="left", fill="x", expand=True)
        self.lbl_loc_lon = ctk.CTkLabel(row_coords, text="Lon: —", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color=self.CLR_GREEN, anchor="w")
        self.lbl_loc_lon.pack(side="left", fill="x", expand=True)

        row_meta = ctk.CTkFrame(tbox, fg_color="transparent")
        row_meta.pack(fill="x", padx=10, pady=1)
        self.lbl_loc_accuracy = ctk.CTkLabel(row_meta, text="Precisão: —", font=ctk.CTkFont(size=10), text_color="#E2E8F0", anchor="w")
        self.lbl_loc_accuracy.pack(side="left", fill="x", expand=True)
        self.lbl_loc_provider = ctk.CTkLabel(row_meta, text="Provedor: —", font=ctk.CTkFont(size=10), text_color="#94A3B8", anchor="w")
        self.lbl_loc_provider.pack(side="left", fill="x", expand=True)

        row_meta2 = ctk.CTkFrame(tbox, fg_color="transparent")
        row_meta2.pack(fill="x", padx=10, pady=1)
        self.lbl_loc_battery = ctk.CTkLabel(row_meta2, text="Bateria: —%", font=ctk.CTkFont(size=10), text_color="#94A3B8", anchor="w")
        self.lbl_loc_battery.pack(side="left", fill="x", expand=True)
        self.lbl_loc_timestamp = ctk.CTkLabel(row_meta2, text="Atualizado: —", font=ctk.CTkFont(size=9), text_color="#64748B", anchor="w")
        self.lbl_loc_timestamp.pack(side="left", fill="x", expand=True)

        self.lbl_loc_report = ctk.CTkLabel(tbox, text="Status: Aguardando solicitação...", font=ctk.CTkFont(size=9, slant="italic"), text_color="#38BDF8", anchor="w")
        self.lbl_loc_report.pack(fill="x", padx=10, pady=2)

        ctk.CTkFrame(tbox, height=1, fg_color="#0A3319").pack(fill="x", padx=10, pady=4)

        # Address Section
        ctk.CTkLabel(tbox, text="📬  ENDEREÇO COMPLETO", font=ctk.CTkFont(size=10, weight="bold"), text_color="#A7F3D0", anchor="w").pack(fill="x", padx=10, pady=(1, 2))

        self.lbl_loc_street = ctk.CTkLabel(tbox, text="Rua: —", font=ctk.CTkFont(size=10, weight="bold"), text_color="#FFFFFF", anchor="w")
        self.lbl_loc_street.pack(fill="x", padx=10, pady=1)

        row_addr_m = ctk.CTkFrame(tbox, fg_color="transparent")
        row_addr_m.pack(fill="x", padx=10, pady=1)
        self.lbl_loc_number = ctk.CTkLabel(row_addr_m, text="Nº: —", font=ctk.CTkFont(size=10), text_color="#E2E8F0", anchor="w", width=80)
        self.lbl_loc_number.pack(side="left")
        self.lbl_loc_neighborhood = ctk.CTkLabel(row_addr_m, text="Bairro: —", font=ctk.CTkFont(size=10), text_color="#E2E8F0", anchor="w")
        self.lbl_loc_neighborhood.pack(side="left", fill="x", expand=True)

        row_addr_c = ctk.CTkFrame(tbox, fg_color="transparent")
        row_addr_c.pack(fill="x", padx=10, pady=1)
        self.lbl_loc_city = ctk.CTkLabel(row_addr_c, text="Cidade/UF: —", font=ctk.CTkFont(size=10), text_color="#E2E8F0", anchor="w")
        self.lbl_loc_city.pack(side="left", fill="x", expand=True)
        self.lbl_loc_cep = ctk.CTkLabel(row_addr_c, text="CEP: —", font=ctk.CTkFont(size=10), text_color="#94A3B8", anchor="w")
        self.lbl_loc_cep.pack(side="left")

        self.lbl_loc_fulladdr = ctk.CTkLabel(tbox, text="Endereço: —", font=ctk.CTkFont(size=9, slant="italic"), text_color="#64748B", anchor="w", wraplength=380, justify="left")
        self.lbl_loc_fulladdr.pack(fill="x", padx=10, pady=(2, 6))

        # Buttons
        btn_loc_box = ctk.CTkFrame(card_telemetry, fg_color="transparent")
        btn_loc_box.pack(fill="x", padx=12, pady=(0, 8))

        self.btn_loc_refresh = ctk.CTkButton(
            btn_loc_box,
            text="📡 ATUALIZAR LOCALIZAÇÃO (SOLICITAR AGORA)",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#052E16",
            hover_color=self.CLR_GREEN,
            text_color=self.CLR_GREEN,
            corner_radius=6,
            border_width=1,
            border_color="#10B981",
            height=32,
            command=self.action_request_location
        )
        self.btn_loc_refresh.pack(fill="x", pady=(0, 4))

        self.btn_loc_maps = ctk.CTkButton(
            btn_loc_box,
            text="🗺️ ABRIR NO GOOGLE MAPS",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=self.CLR_BLUE,
            hover_color=self.CLR_BLUE_HOVER,
            corner_radius=6,
            height=30,
            command=self.open_in_google_maps
        )
        self.btn_loc_maps.pack(fill="x")

        # --- RIGHT CARD: MAPA DE PRECISÃO & GOOGLE MAPS REAL ---
        card_map = ctk.CTkFrame(right_col, fg_color=self.CLR_CARD, corner_radius=10, border_width=1, border_color=self.CLR_BORDER)
        card_map.pack(fill="both", expand=True)

        map_hdr = ctk.CTkFrame(card_map, fg_color="transparent")
        map_hdr.pack(fill="x", padx=10, pady=(6, 4))

        ctk.CTkLabel(
            map_hdr,
            text="📍 MAPA DE PRECISÃO GPS (GOOGLE MAPS & SATÉLITE)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.CLR_CYAN
        ).pack(side="left")

        # Map layer toggle buttons
        layer_box = ctk.CTkFrame(map_hdr, fg_color="transparent")
        layer_box.pack(side="right")

        btn_layer_g = ctk.CTkButton(
            layer_box, text="🗺️ Ruas", width=54, height=22, font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#0F172A", hover_color="#1E293B",
            command=lambda: self.set_map_layer("google_normal")
        )
        btn_layer_g.pack(side="left", padx=2)

        btn_layer_s = ctk.CTkButton(
            layer_box, text="🛰️ Satélite", width=62, height=22, font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#0F172A", hover_color="#1E293B",
            command=lambda: self.set_map_layer("google_satellite")
        )
        btn_layer_s.pack(side="left", padx=2)

        btn_layer_d = ctk.CTkButton(
            layer_box, text="🌙 Dark", width=50, height=22, font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#0F172A", hover_color="#1E293B",
            command=lambda: self.set_map_layer("carto_dark")
        )
        btn_layer_d.pack(side="left", padx=2)

        btn_center = ctk.CTkButton(
            layer_box, text="🎯 Focar", width=52, height=22, font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#052E16", hover_color=self.CLR_GREEN, text_color=self.CLR_GREEN,
            command=self.center_map_on_device
        )
        btn_center.pack(side="left", padx=(4, 0))

        if HAS_MAPVIEW:
            self.map_widget = tkintermapview.TkinterMapView(
                card_map,
                corner_radius=8,
                bg_color=self.CLR_CARD
            )
            self.map_widget.pack(fill="both", expand=True, padx=8, pady=(0, 4))
            # Set default tile server based on active theme
            init_layer = THEMES.get(self.current_theme_key, {}).get("map_layer", "google_normal")
            self.set_map_layer(init_layer)
            self.map_widget.set_position(-22.9068, -47.0616) # Campinas, SP
            self.map_widget.set_zoom(14)
            self.map_canvas = None
        else:
            self.map_widget = None
            self.map_canvas = tk.Canvas(
                card_map,
                bg="#020804",
                bd=0,
                highlightthickness=1,
                highlightbackground="#0A3319"
            )
            self.map_canvas.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self.lbl_map_status_bar = ctk.CTkLabel(
            card_map,
            text="🛰️ GPS Pronto • Arraste para navegar no mapa • Role o mouse para Zoom",
            font=ctk.CTkFont(size=9),
            text_color=self.CLR_TEXT_MUTED
        )
        self.lbl_map_status_bar.pack(anchor="w", padx=10, pady=(0, 4))

        self._draw_tactical_map(None, None, 0, "", "OFFLINE")

    # ========================================================
    # TAB 2: APARELHOS NA NUVEM (GESTÃO REMOTA DO LOGISTA)
    # ========================================================
    def _build_tab_cloud(self):
        container = ctk.CTkFrame(self.tab_cloud, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=2, pady=2)
        container.rowconfigure(1, weight=1)
        container.columnconfigure(0, weight=1)

        # --- TOP HEADER BAR: INFO DO LOGISTA & FILTROS ---
        top_bar = ctk.CTkFrame(container, fg_color=self.CLR_CARD, corner_radius=10, border_width=1, border_color=self.CLR_BORDER)
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # Row 1: Logista Info & Resumo de Aparelhos
        r1 = ctk.CTkFrame(top_bar, fg_color="transparent")
        r1.pack(fill="x", padx=12, pady=(8, 4))

        self.lbl_cloud_user_info = ctk.CTkLabel(
            r1,
            text="👤 Logista: Faça login para sincronizar | 🪙 Saldo: — | 🌐 Nuvem: CONECTADA",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.CLR_CYAN,
            anchor="w"
        )
        self.lbl_cloud_user_info.pack(side="left", fill="x", expand=True)

        self.lbl_cloud_stats_badge = ctk.CTkLabel(
            r1,
            text="📱 Total: 0  |  🔒 Bloqueados: 0  |  🟢 Liberados: 0",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0F1F35",
            text_color="#38BDF8",
            corner_radius=6,
            padx=10,
            pady=3
        )
        self.lbl_cloud_stats_badge.pack(side="right")

        # Row 2: Busca, Filtros e Botões de Ação
        r2 = ctk.CTkFrame(top_bar, fg_color="transparent")
        r2.pack(fill="x", padx=12, pady=(0, 8))

        self.ent_cloud_search = ctk.CTkEntry(
            r2,
            placeholder_text="🔍 Filtrar por Modelo, Serial/IMEI, Logista ou Cidade...",
            font=ctk.CTkFont(size=11),
            fg_color="#0A101D",
            border_color="#1E293B",
            corner_radius=6,
            height=28
        )
        self.ent_cloud_search.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.ent_cloud_search.bind("<KeyRelease>", lambda e: self._filter_cloud_devices())

        self.combo_cloud_filter = ctk.CTkOptionMenu(
            r2,
            values=["Todos os Status", "🔒 Apenas Bloqueados", "🟢 Apenas Liberados", "📍 Apenas com GPS"],
            font=ctk.CTkFont(size=11),
            fg_color="#0F172A",
            button_color=self.CLR_BLUE,
            button_hover_color=self.CLR_BLUE_HOVER,
            corner_radius=6,
            height=28,
            width=160,
            command=lambda v: self._filter_cloud_devices()
        )
        self.combo_cloud_filter.pack(side="left", padx=(0, 6))

        btn_cloud_refresh = ctk.CTkButton(
            r2,
            text="🔄 Atualizar Nuvem",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=self.CLR_BLUE,
            hover_color=self.CLR_BLUE_HOVER,
            corner_radius=6,
            height=28,
            width=130,
            command=self.refresh_cloud_devices_async
        )
        btn_cloud_refresh.pack(side="left", padx=(0, 6))

        btn_cloud_add = ctk.CTkButton(
            r2,
            text="➕ Cadastrar Aparelho",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#059669",
            hover_color=self.CLR_GREEN,
            corner_radius=6,
            height=28,
            width=140,
            command=self.open_register_cloud_device_dialog
        )
        btn_cloud_add.pack(side="left")

        # --- MAIN SPLIT CONTAINER (2 COLUMNS) ---
        main_split = ctk.CTkFrame(container, fg_color="transparent")
        main_split.grid(row=1, column=0, sticky="nsew")
        main_split.columnconfigure(0, weight=5)  # Lista (55%)
        main_split.columnconfigure(1, weight=4)  # Painel de Comandos (45%)
        main_split.rowconfigure(0, weight=1)

        # LEFT: Scrollable list of cloud devices
        left_box = ctk.CTkFrame(main_split, fg_color="transparent")
        left_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        hdr_list = ctk.CTkFrame(left_box, fg_color="transparent")
        hdr_list.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            hdr_list,
            text="📱 DISPOSITIVOS VINCULADOS NA NUVEM",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.CLR_CYAN
        ).pack(side="left")

        self.lbl_cloud_device_count = ctk.CTkLabel(
            hdr_list,
            text="0 encontrados",
            font=ctk.CTkFont(size=10),
            text_color=self.CLR_TEXT_MUTED
        )
        self.lbl_cloud_device_count.pack(side="right")

        self.cloud_scroll = ctk.CTkScrollableFrame(
            left_box,
            fg_color="#060C16",
            corner_radius=8,
            border_width=1,
            border_color=self.CLR_BORDER
        )
        self.cloud_scroll.pack(fill="both", expand=True)

        # RIGHT: Command and Telemetry Panel
        right_box = ctk.CTkFrame(main_split, fg_color="transparent")
        right_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        card_cmd = ctk.CTkFrame(right_box, fg_color=self.CLR_CARD, corner_radius=10, border_width=1, border_color=self.CLR_BORDER)
        card_cmd.pack(fill="both", expand=True)

        ctk.CTkLabel(
            card_cmd,
            text="🎯  CENTRO DE COMANDOS DO APARELHO (ONLINE)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.CLR_CYAN
        ).pack(anchor="w", padx=12, pady=(8, 4))

        # Selected Device Summary
        sel_info_box = ctk.CTkFrame(card_cmd, fg_color=self.CLR_CARD_INNER, corner_radius=8, border_width=1, border_color="#101C30")
        sel_info_box.pack(fill="x", padx=12, pady=(0, 6))

        self.lbl_cloud_sel_model = ctk.CTkLabel(
            sel_info_box,
            text="📱 Selecione um aparelho na lista",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        self.lbl_cloud_sel_model.pack(fill="x", padx=10, pady=(6, 2))

        self.lbl_cloud_sel_serial = ctk.CTkLabel(
            sel_info_box,
            text="Serial / IMEI: —",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=self.CLR_CYAN,
            anchor="w"
        )
        self.lbl_cloud_sel_serial.pack(fill="x", padx=10, pady=1)

        self.lbl_cloud_sel_owner = ctk.CTkLabel(
            sel_info_box,
            text="Logista: —",
            font=ctk.CTkFont(size=10),
            text_color=self.CLR_TEXT_MUTED,
            anchor="w"
        )
        self.lbl_cloud_sel_owner.pack(fill="x", padx=10, pady=1)

        row_stat = ctk.CTkFrame(sel_info_box, fg_color="transparent")
        row_stat.pack(fill="x", padx=10, pady=2)

        self.lbl_cloud_sel_status = ctk.CTkLabel(
            row_stat,
            text="Status: —",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        self.lbl_cloud_sel_status.pack(side="left")

        self.lbl_cloud_sel_battery = ctk.CTkLabel(
            row_stat,
            text="🔋 —%",
            font=ctk.CTkFont(size=10),
            text_color="#94A3B8"
        )
        self.lbl_cloud_sel_battery.pack(side="right")

        self.lbl_cloud_sel_loc = ctk.CTkLabel(
            sel_info_box,
            text="📍 Localização: —",
            font=ctk.CTkFont(size=9),
            text_color="#64748B",
            anchor="w"
        )
        self.lbl_cloud_sel_loc.pack(fill="x", padx=10, pady=(1, 6))

        # Command Action Buttons Grid
        f_actions = ctk.CTkFrame(card_cmd, fg_color="transparent")
        f_actions.pack(fill="x", padx=12, pady=(0, 6))
        f_actions.columnconfigure(0, weight=1)
        f_actions.columnconfigure(1, weight=1)

        # 1. BLOQUEAR REMOTO
        self.btn_cloud_cmd_lock = ctk.CTkButton(
            f_actions,
            text="🔒 BLOQUEAR (NUVEM)",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#991B1B",
            hover_color="#DC2626",
            text_color="#FFFFFF",
            corner_radius=6,
            height=30,
            command=self.cloud_action_lock
        )
        self.btn_cloud_cmd_lock.grid(row=0, column=0, sticky="ew", padx=(0, 3), pady=2)

        # 2. LIBERAR REMOTO
        self.btn_cloud_cmd_unlock = ctk.CTkButton(
            f_actions,
            text="🔓 LIBERAR (NUVEM)",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#047857",
            hover_color="#059669",
            text_color="#FFFFFF",
            corner_radius=6,
            height=30,
            command=self.cloud_action_unlock
        )
        self.btn_cloud_cmd_unlock.grid(row=0, column=1, sticky="ew", padx=(3, 0), pady=2)

        # 3. RASTREAR GPS
        self.btn_cloud_cmd_loc = ctk.CTkButton(
            f_actions,
            text="📍 SOLICITAR GPS",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            text_color="#FFFFFF",
            corner_radius=6,
            height=30,
            command=self.cloud_action_request_location
        )
        self.btn_cloud_cmd_loc.grid(row=1, column=0, sticky="ew", padx=(0, 3), pady=2)

        # 4. ABRIR MAPS
        self.btn_cloud_cmd_maps = ctk.CTkButton(
            f_actions,
            text="🗺️ GOOGLE MAPS",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1E293B",
            hover_color="#334155",
            text_color="#38BDF8",
            corner_radius=6,
            height=30,
            command=self.cloud_action_open_maps
        )
        self.btn_cloud_cmd_maps.grid(row=1, column=1, sticky="ew", padx=(3, 0), pady=2)

        # 5. ALARME / SIRENE
        self.btn_cloud_cmd_alarm = ctk.CTkButton(
            f_actions,
            text="🚨 DISPARAR ALARME",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#C2410C",
            hover_color="#EA580C",
            text_color="#FFFFFF",
            corner_radius=6,
            height=30,
            command=self.cloud_action_trigger_alarm
        )
        self.btn_cloud_cmd_alarm.grid(row=2, column=0, sticky="ew", padx=(0, 3), pady=2)

        # 6. ENVIAR MENSAGEM
        self.btn_cloud_cmd_msg = ctk.CTkButton(
            f_actions,
            text="✉️ ENVIAR MENSAGEM",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#4F46E5",
            hover_color="#6366F1",
            text_color="#FFFFFF",
            corner_radius=6,
            height=30,
            command=self.cloud_action_send_message
        )
        self.btn_cloud_cmd_msg.grid(row=2, column=1, sticky="ew", padx=(3, 0), pady=2)

        # 7. CARREGAR NA BANCADA (USB)
        self.btn_cloud_load_bench = ctk.CTkButton(
            card_cmd,
            text="⚡ CARREGAR NA BANCADA USB (IR PARA GESTÃO)",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0F243A",
            hover_color="#1E3A8A",
            text_color=self.CLR_CYAN,
            corner_radius=6,
            border_width=1,
            border_color="#0284C7",
            height=32,
            command=self.cloud_action_load_to_bench
        )
        self.btn_cloud_load_bench.pack(fill="x", padx=12, pady=(2, 6))

        # Cloud Command Output Log
        ctk.CTkLabel(
            card_cmd,
            text="📜 RETORNO DOS COMANDOS CLOUD",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.CLR_TEXT_MUTED
        ).pack(anchor="w", padx=12, pady=(4, 2))

        self.txt_cloud_log = ctk.CTkTextbox(
            card_cmd,
            fg_color=self.CLR_CARD_INNER,
            border_color="#101C30",
            corner_radius=6,
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color="#E2E8F0"
        )
        self.txt_cloud_log.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.cloud_log("[NUVEM] Centro de Dispositivos e Comandos pronto.")

    def cloud_log(self, message):
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            line = f"[{ts}] {message}\n"
            if hasattr(self, 'txt_cloud_log') and self.txt_cloud_log:
                self.txt_cloud_log.insert(tk.END, line)
                self.txt_cloud_log.see(tk.END)
        except Exception:
            pass

    def refresh_cloud_devices_async(self):
        if not self.api_client.is_logged_in():
            self.cloud_log("[AVISO] Faça login para carregar os aparelhos da sua conta.")
            return

        def work():
            ok, devices = self.api_client.get_client_devices()
            def done():
                if ok and isinstance(devices, list):
                    self.cloud_devices_cache = devices
                    user = self.api_client.user or {}
                    name = user.get("name", "Logista")
                    email = user.get("email", "")
                    bal = user.get("balance_credits", 0)
                    if hasattr(self, 'lbl_cloud_user_info') and self.lbl_cloud_user_info:
                        self.lbl_cloud_user_info.configure(
                            text=f"👤 Logista: {name} ({email}) | 🪙 Saldo: {bal} Créditos | 🌐 Nuvem: SINCRONIZADA"
                        )

                    total = len(devices)
                    locked = sum(1 for d in devices if (d.get("lock_status") or "").upper() == "LOCKED")
                    unlocked = total - locked
                    if hasattr(self, 'lbl_cloud_stats_badge') and self.lbl_cloud_stats_badge:
                        self.lbl_cloud_stats_badge.configure(
                            text=f"📱 Total: {total}  |  🔒 Bloqueados: {locked}  |  🟢 Liberados: {unlocked}"
                        )
                    self._filter_cloud_devices()
                    self.cloud_log(f"[SYNC] {total} aparelho(s) sincronizado(s) da nuvem com sucesso.")
                else:
                    self.cloud_log("[ERRO] Falha ao sincronizar aparelhos da nuvem.")
            self.safe_after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def _filter_cloud_devices(self):
        query = self.ent_cloud_search.get().strip().lower() if hasattr(self, 'ent_cloud_search') else ""
        filt = self.combo_cloud_filter.get() if hasattr(self, 'combo_cloud_filter') else "Todos os Status"

        filtered = []
        for d in self.cloud_devices_cache:
            st = (d.get("lock_status") or "").upper()
            if "Bloqueados" in filt and st != "LOCKED":
                continue
            if "Liberados" in filt and st not in ("UNLOCKED", "PAID"):
                continue
            if "GPS" in filt and (d.get("latitude") is None or d.get("longitude") is None):
                continue

            if query:
                haystack = f"{d.get('serial', '')} {d.get('model', '')} {d.get('manufacturer', '')} {d.get('owner_name', '')} {d.get('owner_email', '')} {d.get('city', '')} {d.get('neighborhood', '')}".lower()
                if query not in haystack:
                    continue

            filtered.append(d)

        self._render_cloud_device_cards(filtered)

    def _render_cloud_device_cards(self, devices):
        if not hasattr(self, 'cloud_scroll') or not self.cloud_scroll:
            return
        # Limpar widgets anteriores no scrollable frame
        for child in self.cloud_scroll.winfo_children():
            child.destroy()

        if not devices:
            self.lbl_cloud_device_count.configure(text="0 encontrados")
            empty_box = ctk.CTkFrame(self.cloud_scroll, fg_color="transparent")
            empty_box.pack(fill="both", expand=True, pady=40)
            ctk.CTkLabel(
                empty_box,
                text="☁️ Nenhum aparelho encontrado na nuvem",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.CLR_TEXT_MUTED
            ).pack(pady=(0, 6))
            ctk.CTkLabel(
                empty_box,
                text="Os aparelhos vinculados ao seu login aparecerão aqui em tempo real assim que o APK for ativado.\nVocê também pode cadastrar um aparelho manualmente clicando abaixo.",
                font=ctk.CTkFont(size=10),
                text_color="#64748B",
                justify="center"
            ).pack(pady=(0, 14))
            ctk.CTkButton(
                empty_box,
                text="➕ Cadastrar Aparelho na Nuvem",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#059669",
                hover_color=self.CLR_GREEN,
                corner_radius=6,
                height=30,
                width=200,
                command=self.open_register_cloud_device_dialog
            ).pack()
            return

        self.lbl_cloud_device_count.configure(text=f"{len(devices)} aparelho(s)")

        # Manter seleção se possível ou selecionar o primeiro
        if not self.cloud_selected_device or not any(d.get("serial") == self.cloud_selected_device.get("serial") for d in devices):
            self.cloud_selected_device = devices[0]
            self._update_selected_cloud_panel(devices[0])

        for dev in devices:
            serial = dev.get("serial", "DESCONHECIDO")
            is_sel = (self.cloud_selected_device and self.cloud_selected_device.get("serial") == serial)
            st = (dev.get("lock_status") or "LOCKED").upper()
            is_locked = (st == "LOCKED")

            card = ctk.CTkFrame(
                self.cloud_scroll,
                fg_color="#0A182E" if is_sel else self.CLR_CARD,
                corner_radius=8,
                border_width=2 if is_sel else 1,
                border_color="#00E5FF" if is_sel else self.CLR_BORDER
            )
            card.pack(fill="x", pady=3, padx=2)

            # Clique no card seleciona
            card.bind("<Button-1>", lambda e, d=dev: self._select_cloud_device(d))

            # Header do Card: Modelo & Badge
            c_hdr = ctk.CTkFrame(card, fg_color="transparent")
            c_hdr.pack(fill="x", padx=10, pady=(6, 2))
            c_hdr.bind("<Button-1>", lambda e, d=dev: self._select_cloud_device(d))

            model_txt = f"📱 {dev.get('model', 'Smartphone')} ({dev.get('manufacturer', 'Android')})"
            lbl_m = ctk.CTkLabel(
                c_hdr,
                text=model_txt,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#FFFFFF" if is_sel else "#E2E8F0",
                anchor="w"
            )
            lbl_m.pack(side="left")
            lbl_m.bind("<Button-1>", lambda e, d=dev: self._select_cloud_device(d))

            badge_text = "🔒 BLOQUEADO" if is_locked else "🟢 LIBERADO"
            badge_fg = "#450A0A" if is_locked else "#022C22"
            badge_text_clr = "#F87171" if is_locked else "#34D399"
            lbl_badge = ctk.CTkLabel(
                c_hdr,
                text=badge_text,
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color=badge_fg,
                text_color=badge_text_clr,
                corner_radius=4,
                padx=6,
                pady=1
            )
            lbl_badge.pack(side="right")

            # Linha 2: Serial / Logista
            c_row2 = ctk.CTkFrame(card, fg_color="transparent")
            c_row2.pack(fill="x", padx=10, pady=1)
            c_row2.bind("<Button-1>", lambda e, d=dev: self._select_cloud_device(d))

            lbl_s = ctk.CTkLabel(
                c_row2,
                text=f"Serial: {serial}",
                font=ctk.CTkFont(family="Consolas", size=9),
                text_color=self.CLR_CYAN,
                anchor="w"
            )
            lbl_s.pack(side="left")
            lbl_s.bind("<Button-1>", lambda e, d=dev: self._select_cloud_device(d))

            owner_str = f"👤 {dev.get('owner_name', 'Logista')} ({dev.get('owner_email', '')})"
            lbl_o = ctk.CTkLabel(
                c_row2,
                text=owner_str,
                font=ctk.CTkFont(size=9),
                text_color=self.CLR_TEXT_MUTED,
                anchor="e"
            )
            lbl_o.pack(side="right")
            lbl_o.bind("<Button-1>", lambda e, d=dev: self._select_cloud_device(d))

            # Linha 3: Telemetria (Bateria, Rede, Local)
            c_row3 = ctk.CTkFrame(card, fg_color="transparent")
            c_row3.pack(fill="x", padx=10, pady=1)
            c_row3.bind("<Button-1>", lambda e, d=dev: self._select_cloud_device(d))

            bat = dev.get("battery_level")
            bat_str = f"🔋 {bat}%" if bat is not None else "🔋 —"
            net_str = dev.get("network_status") or "Online"
            loc_str = dev.get("city") or "Localização gravada"

            lbl_t = ctk.CTkLabel(
                c_row3,
                text=f"{bat_str} | {net_str} | 📍 {loc_str}",
                font=ctk.CTkFont(size=9),
                text_color="#94A3B8",
                anchor="w"
            )
            lbl_t.pack(side="left")
            lbl_t.bind("<Button-1>", lambda e, d=dev: self._select_cloud_device(d))

            # Linha 4: Botões Rápidos Inline
            c_btns = ctk.CTkFrame(card, fg_color="transparent")
            c_btns.pack(fill="x", padx=10, pady=(3, 6))

            btn_l = ctk.CTkButton(
                c_btns,
                text="🔒 Bloquear",
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color="#7F1D1D",
                hover_color="#DC2626",
                text_color="#FFFFFF",
                corner_radius=4,
                height=22,
                width=75,
                command=lambda d=dev: self.cloud_quick_lock(d)
            )
            btn_l.pack(side="left", padx=(0, 4))

            btn_u = ctk.CTkButton(
                c_btns,
                text="🔓 Liberar",
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color="#064E3B",
                hover_color="#059669",
                text_color="#FFFFFF",
                corner_radius=4,
                height=22,
                width=75,
                command=lambda d=dev: self.cloud_quick_unlock(d)
            )
            btn_u.pack(side="left", padx=(0, 4))

            btn_gps = ctk.CTkButton(
                c_btns,
                text="📍 GPS",
                font=ctk.CTkFont(size=9),
                fg_color="#075985",
                hover_color="#0284C7",
                corner_radius=4,
                height=22,
                width=60,
                command=lambda d=dev: self.cloud_quick_gps(d)
            )
            btn_gps.pack(side="left", padx=(0, 4))

            btn_b = ctk.CTkButton(
                c_btns,
                text="⚡ Bancada",
                font=ctk.CTkFont(size=9),
                fg_color="#1E293B",
                hover_color="#334155",
                text_color=self.CLR_CYAN,
                corner_radius=4,
                height=22,
                width=75,
                command=lambda d=dev: self.cloud_quick_bench(d)
            )
            btn_b.pack(side="right")

    def _select_cloud_device(self, dev):
        self.cloud_selected_device = dev
        self._update_selected_cloud_panel(dev)
        self._filter_cloud_devices()

    def _update_selected_cloud_panel(self, dev):
        if not dev:
            return
        model = dev.get("model", "Android")
        mfg = dev.get("manufacturer", "")
        self.lbl_cloud_sel_model.configure(text=f"📱 {model} ({mfg})")
        self.lbl_cloud_sel_serial.configure(text=f"Serial / IMEI: {dev.get('serial', '—')}")
        self.lbl_cloud_sel_owner.configure(text=f"Logista: {dev.get('owner_name', '—')} ({dev.get('owner_email', '')})")

        st = (dev.get("lock_status") or "LOCKED").upper()
        if st == "LOCKED":
            self.lbl_cloud_sel_status.configure(text="Status: 🔒 BLOQUEADO (KIOSK ATIVO)", text_color="#EF4444")
        else:
            self.lbl_cloud_sel_status.configure(text="Status: 🟢 LIBERADO (USO NORMAL)", text_color="#10B981")

        bat = dev.get("battery_level")
        bat_str = f"🔋 {bat}%" if bat is not None else "🔋 —"
        net_str = dev.get("network_status") or "Wi-Fi / 4G"
        self.lbl_cloud_sel_battery.configure(text=f"{bat_str} | {net_str}")

        addr = dev.get("address_formatted") or dev.get("city") or "Coordenadas não registradas"
        self.lbl_cloud_sel_loc.configure(text=f"📍 {addr}")

    # ========================================================
    # AÇÕES DO PAINEL REMOTO DE NUVEM
    # ========================================================
    def cloud_action_lock(self):
        if not self.cloud_selected_device:
            messagebox.showwarning("Aviso", "Selecione um aparelho na lista primeiro.")
            return
        self.cloud_quick_lock(self.cloud_selected_device)

    def cloud_quick_lock(self, dev):
        serial = dev.get("serial")
        if not serial:
            return
        if not self.api_client.is_logged_in():
            messagebox.showwarning("Login Necessário", "Faça login no sistema para enviar comandos na nuvem.")
            return

        res = messagebox.askyesno(
            "Confirmar Bloqueio Online",
            f"Deseja enviar comando de BLOQUEIO ONLINE para o aparelho:\n\n"
            f"Aparelho: {dev.get('model', 'Smartphone')}\n"
            f"Serial / IMEI: {serial}\n"
            f"Logista: {dev.get('owner_name', '')}\n\n"
            f"O celular travará imediatamente na tela Kiosk com sua chave PIX via internet (sem precisar de USB)."
        )
        if not res:
            return

        self.cloud_log(f"[ORDEM] Enviando BLOQUEIO REMOTO para {serial}...")
        def work():
            ok, resp = self.api_client.lock_device_remote(serial)
            def done():
                if ok:
                    self.cloud_log(f"[SUCESSO] 🔒 Aparelho {serial} BLOQUEADO VIA NUVEM!")
                    dev["lock_status"] = "LOCKED"
                    if self.cloud_selected_device and self.cloud_selected_device.get("serial") == serial:
                        self._update_selected_cloud_panel(dev)
                    self._filter_cloud_devices()
                    messagebox.showinfo("Bloqueio Enviado", f"Comando de bloqueio enviado com sucesso para {serial}!\nO celular bloqueará imediatamente via Wi-Fi/4G.")
                else:
                    self.cloud_log(f"[ERRO] Falha no bloqueio: {resp.get('error', '')}")
                    messagebox.showerror("Erro", f"Falha no bloqueio remoto: {resp.get('error', '')}")
            self.safe_after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def cloud_action_unlock(self):
        if not self.cloud_selected_device:
            messagebox.showwarning("Aviso", "Selecione um aparelho na lista primeiro.")
            return
        self.cloud_quick_unlock(self.cloud_selected_device)

    def cloud_quick_unlock(self, dev):
        serial = dev.get("serial")
        if not serial:
            return
        if not self.api_client.is_logged_in():
            messagebox.showwarning("Login Necessário", "Faça login no sistema para enviar comandos na nuvem.")
            return

        res = messagebox.askyesno(
            "Confirmar Liberação Online",
            f"Deseja enviar comando de LIBERAÇÃO / DESBLOQUEIO para o aparelho:\n\n"
            f"Aparelho: {dev.get('model', 'Smartphone')}\n"
            f"Serial / IMEI: {serial}\n"
            f"Logista: {dev.get('owner_name', '')}\n\n"
            f"O celular será destravado imediatamente via internet (sem precisar de USB)."
        )
        if not res:
            return

        self.cloud_log(f"[ORDEM] Enviando LIBERAÇÃO REMOTA para {serial}...")
        def work():
            ok, resp = self.api_client.unlock_device_remote(serial)
            def done():
                if ok:
                    self.cloud_log(f"[SUCESSO] 🔓 Aparelho {serial} LIBERADO VIA NUVEM!")
                    dev["lock_status"] = "UNLOCKED"
                    if self.cloud_selected_device and self.cloud_selected_device.get("serial") == serial:
                        self._update_selected_cloud_panel(dev)
                    self._filter_cloud_devices()
                    messagebox.showinfo("Liberação Enviada", f"Comando de liberação enviado com sucesso para {serial}!\nO aparelho foi destravado via Wi-Fi/4G.")
                else:
                    self.cloud_log(f"[ERRO] Falha na liberação: {resp.get('error', '')}")
                    messagebox.showerror("Erro", f"Falha na liberação remota: {resp.get('error', '')}")
            self.safe_after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def cloud_action_request_location(self):
        if not self.cloud_selected_device:
            messagebox.showwarning("Aviso", "Selecione um aparelho na lista primeiro.")
            return
        self.cloud_quick_gps(self.cloud_selected_device)

    def cloud_quick_gps(self, dev):
        serial = dev.get("serial")
        if not serial:
            return
        self.cloud_log(f"[ORDEM] Solicitando atualização de GPS para {serial}...")
        def work():
            ok, resp = self.api_client.request_device_location_remote(serial)
            def done():
                if ok:
                    self.cloud_log(f"[SUCESSO] 📡 Sinal de rastreamento enviado para {serial}. Aguardando coordenadas...")
                    self.safe_after(3000, self.refresh_cloud_devices_async)
                else:
                    self.cloud_log(f"[ERRO] Falha ao solicitar GPS: {resp.get('error', '')}")
            self.safe_after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def cloud_action_open_maps(self):
        if not self.cloud_selected_device:
            messagebox.showwarning("Aviso", "Selecione um aparelho na lista primeiro.")
            return
        dev = self.cloud_selected_device
        lat = dev.get("latitude")
        lon = dev.get("longitude")
        if lat is not None and lon is not None:
            try:
                self.tabview.set("📍 LOCALIZAÇÃO")
                self.current_location = {
                    "latitude": lat,
                    "longitude": lon,
                    "street": dev.get("model", "Aparelho na Nuvem"),
                    "city": dev.get("owner_name", "")
                }
                self._draw_tactical_map(lat, lon, 15, "NUVEM", "ONLINE" if dev.get("is_online") else "OFFLINE")
            except Exception:
                pass
            url = f"https://www.google.com/maps?q={lat},{lon}"
            webbrowser.open(url)
            self.cloud_log(f"[MAPS] Abrindo Google Maps: {url}")
        else:
            messagebox.showinfo("Localização", "Este aparelho ainda não enviou coordenadas GPS.\nClique em 'SOLICITAR GPS' para requisitar.")

    def cloud_action_trigger_alarm(self):
        if not self.cloud_selected_device:
            messagebox.showwarning("Aviso", "Selecione um aparelho na lista primeiro.")
            return
        serial = self.cloud_selected_device.get("serial")
        res = messagebox.askyesno(
            "Disparar Alarme Sonoro",
            f"Deseja acionar o alarme / sirene sonora no smartphone:\n\n"
            f"Serial: {serial}\n\n"
            f"O aparelho tocará um bipe de localização em volume alto."
        )
        if not res:
            return

        self.cloud_log(f"[ORDEM] Disparando ALARME SONORO para {serial}...")
        def work():
            ok, resp = self.api_client.send_device_alarm_remote(serial)
            def done():
                if ok:
                    self.cloud_log(f"[SUCESSO] 🚨 Ordem de ALARME enviada com sucesso para {serial}!")
                    messagebox.showinfo("Alarme Enviado", f"Ordem de alarme sonoro enviada para {serial}!\nO smartphone emitirá o som assim que sincronizar com a nuvem.")
                else:
                    self.cloud_log(f"[ERRO] Falha ao disparar alarme: {resp.get('error', '')}")
            self.safe_after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def cloud_action_send_message(self):
        if not self.cloud_selected_device:
            messagebox.showwarning("Aviso", "Selecione um aparelho na lista primeiro.")
            return
        serial = self.cloud_selected_device.get("serial")
        msg = simpledialog.askstring(
            "Enviar Mensagem Remota na Tela",
            f"Digite o texto do aviso que será exibido no aparelho {serial}:",
            initialvalue="Aviso MDM: Favor entrar em contato com a loja para regularizar seu aparelho."
        )
        if not msg or not msg.strip():
            return

        self.cloud_log(f"[ORDEM] Enviando mensagem de tela para {serial}: '{msg.strip()}'...")
        def work():
            ok, resp = self.api_client.send_device_message_remote(serial, msg.strip())
            def done():
                if ok:
                    self.cloud_log(f"[SUCESSO] ✉️ Mensagem entregue na nuvem para {serial}!")
                    messagebox.showinfo("Mensagem Enviada", f"Mensagem enviada com sucesso para {serial}!\nSerá exibida na tela do smartphone.")
                else:
                    self.cloud_log(f"[ERRO] Falha ao enviar mensagem: {resp.get('error', '')}")
            self.safe_after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def cloud_action_load_to_bench(self):
        if not self.cloud_selected_device:
            messagebox.showwarning("Aviso", "Selecione um aparelho na lista primeiro.")
            return
        self.cloud_quick_bench(self.cloud_selected_device)

    def cloud_quick_bench(self, dev):
        serial = dev.get("serial")
        model = dev.get("model", "Android Device")
        self.selected_device_serial = serial
        try:
            self.combo_devices.set(f"{model} ({serial})")
        except Exception:
            pass
        self.tabview.set("⚡ GESTÃO & LIBERAÇÃO")
        self.log(f"[BANCADA] Aparelho da nuvem {serial} ({model}) carregado para operações de bancada!")
        self.cloud_log(f"[BANCADA] Aparelho {serial} transferido para a aba de bancada local USB.")

    def open_register_cloud_device_dialog(self):
        if not self.api_client.is_logged_in():
            messagebox.showwarning("Login Necessário", "Faça login na sua conta para cadastrar aparelhos na nuvem.")
            return

        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Cadastrar Aparelho na Nuvem — MDM & FRP BRASIL")
        dialog.geometry("450x380")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Center on parent
        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        pos_x = max(0, rx + (rw - 450) // 2)
        pos_y = max(0, ry + (rh - 380) // 2)
        dialog.geometry(f"450x380+{pos_x}+{pos_y}")

        f = ctk.CTkFrame(dialog, fg_color=self.CLR_CARD, corner_radius=12)
        f.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(f, text="📱 CADASTRAR NOVO APARELHO NA NUVEM", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.CLR_CYAN).pack(pady=(12, 12))

        ctk.CTkLabel(f, text="Modelo do Aparelho (ex: Samsung Galaxy A15):", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.CLR_TEXT_MUTED, anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        ent_mod = ctk.CTkEntry(f, placeholder_text="Samsung Galaxy A15 5G", font=ctk.CTkFont(size=11), fg_color="#0A101D", height=30)
        ent_mod.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(f, text="Serial / IMEI / Device ID:", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.CLR_TEXT_MUTED, anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        ent_ser = ctk.CTkEntry(f, placeholder_text="R58X12345ABC", font=ctk.CTkFont(family="Consolas", size=11), fg_color="#0A101D", height=30)
        ent_ser.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(f, text="Status Inicial de Segurança:", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.CLR_TEXT_MUTED, anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        combo_st = ctk.CTkOptionMenu(
            f,
            values=["LOCKED (Bloqueado / Kiosk Ativo)", "UNLOCKED (Liberado / Uso Normal)"],
            font=ctk.CTkFont(size=11),
            fg_color="#0F172A",
            button_color=self.CLR_BLUE,
            height=30
        )
        combo_st.pack(fill="x", padx=16, pady=(0, 16))

        def submit():
            mod = ent_mod.get().strip() or "Android Smartphone"
            ser = ent_ser.get().strip()
            st_raw = combo_st.get()
            st_val = "LOCKED" if "LOCKED" in st_raw else "UNLOCKED"

            if not ser:
                messagebox.showwarning("Aviso", "Digite o Serial ou IMEI do aparelho.")
                return

            def work():
                ok, res = self.api_client.register_device_remote(ser, mod, "Android", st_val)
                def done():
                    if ok:
                        messagebox.showinfo("Sucesso", f"Aparelho {mod} ({ser}) cadastrado na sua conta com sucesso!")
                        dialog.destroy()
                        self.refresh_cloud_devices_async()
                    else:
                        messagebox.showerror("Erro", f"Falha ao cadastrar: {res.get('error', '')}")
                self.safe_after(0, done)
            threading.Thread(target=work, daemon=True).start()

        btn_save = ctk.CTkButton(
            f,
            text="💾 Salvar Aparelho na Nuvem",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#059669",
            hover_color=self.CLR_GREEN,
            height=34,
            command=submit
        )
        btn_save.pack(fill="x", padx=16, pady=(0, 6))

    def _start_cloud_polling(self):
        if getattr(self, 'cloud_polling_active', False):
            return
        self.cloud_polling_active = True

        def poll_loop():
            while getattr(self, 'cloud_polling_active', False):
                time.sleep(18)  # Atualização periódica a cada 18 segundos
                if hasattr(self, 'api_client') and self.api_client.is_logged_in():
                    try:
                        self.refresh_cloud_devices_async()
                    except Exception:
                        pass

        threading.Thread(target=poll_loop, daemon=True).start()

    # ========================================================
    # LOGO LOADER
    # ========================================================
    def _load_header_logo(self):
        try:
            base = os.path.dirname(os.path.abspath(__file__))
            candidates = [
                os.path.join(base, "resources", "mdm_frp_brasil_oficial_logo_transp.png"),
                os.path.join(base, "resources", "default_logo.png"),
                getattr(self.adb, "default_logo_path", "")
            ]
            for p in candidates:
                if p and os.path.exists(p):
                    pil_img = Image.open(p)
                    self.logo_ctk_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(55, 38))
                    self.lbl_header_logo.configure(image=self.logo_ctk_image)
                    break
        except Exception:
            pass

    # ========================================================
    # REAL GOOGLE MAPS / SATELLITE & TACTICAL MAP RENDERER
    # ========================================================
    def set_map_layer(self, layer_type):
        if not HAS_MAPVIEW or not hasattr(self, 'map_widget') or not self.map_widget:
            return
        try:
            if layer_type == "google_normal":
                self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=m&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga", max_zoom=22)
            elif layer_type == "google_satellite":
                self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=y&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga", max_zoom=22)
            elif layer_type == "carto_dark":
                self.map_widget.set_tile_server("https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png", max_zoom=19)
            elif layer_type == "osm":
                self.map_widget.set_tile_server("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom=19)
        except Exception as e:
            print(f"Set map layer error: {e}")

    def center_map_on_device(self):
        if not HAS_MAPVIEW or not hasattr(self, 'map_widget') or not self.map_widget:
            return
        if self.current_location and self.current_location.get("latitude"):
            lat = self.current_location["latitude"]
            lon = self.current_location["longitude"]
            self.map_widget.set_position(lat, lon)
            self.map_widget.set_zoom(17)
        elif hasattr(self, 'cloud_selected_device') and self.cloud_selected_device and self.cloud_selected_device.get("latitude"):
            lat = self.cloud_selected_device["latitude"]
            lon = self.cloud_selected_device["longitude"]
            self.map_widget.set_position(lat, lon)
            self.map_widget.set_zoom(17)
        else:
            self.map_widget.set_position(-22.9068, -47.0616)

    def apply_ui_theme(self, theme_key):
        if theme_key not in THEMES:
            return
        self.current_theme_key = theme_key
        thm = THEMES[theme_key]
        self.CLR_BG = thm["bg"]
        self.CLR_CARD = thm["card"]
        self.CLR_CARD_INNER = thm["card_inner"]
        self.CLR_BORDER = thm["border"]
        self.CLR_GREEN = thm["accent"]
        self.CLR_CYAN = thm["cyan"]
        self.CLR_BLUE = thm["blue"]

        # Update root and header background
        try:
            self.root.configure(fg_color=self.CLR_BG)
            if hasattr(self, 'header_frame') and self.header_frame:
                self.header_frame.configure(fg_color=self.CLR_CARD, border_color=self.CLR_BORDER)
        except Exception:
            pass

        # Update theme switcher buttons active style
        try:
            if hasattr(self, 'btn_thm_cyber'):
                self.btn_thm_cyber.configure(
                    fg_color="#00E676" if theme_key == "cyber_dark" else "#0F172A",
                    text_color="#000000" if theme_key == "cyber_dark" else "#94A3B8"
                )
            if hasattr(self, 'btn_thm_slate'):
                self.btn_thm_slate.configure(
                    fg_color="#38BDF8" if theme_key == "titanium_slate" else "#0F172A",
                    text_color="#000000" if theme_key == "titanium_slate" else "#94A3B8"
                )
            if hasattr(self, 'btn_thm_gold'):
                self.btn_thm_gold.configure(
                    fg_color="#F59E0B" if theme_key == "gold_executive" else "#0F172A",
                    text_color="#000000" if theme_key == "gold_executive" else "#94A3B8"
                )
        except Exception:
            pass

        # Switch map layer automatically to match theme style
        self.set_map_layer(thm["map_layer"])

        # Save to persistent config
        try:
            self.saved_config["ui_theme"] = theme_key
            self._save_current_config()
        except Exception:
            pass

    def _draw_tactical_map(self, lat, lon, acc, provider="GPS", status="ONLINE"):
        # 1. Real interactive Google Maps / Satellite mode
        if HAS_MAPVIEW and hasattr(self, 'map_widget') and self.map_widget:
            if lat is not None and lon is not None and (lat != 0 or lon != 0):
                try:
                    if hasattr(self, 'current_map_marker') and self.current_map_marker:
                        self.current_map_marker.delete()
                        self.current_map_marker = None
                except Exception:
                    pass

                dev_name = "Dispositivo Android"
                try:
                    txt = self.lbl_loc_device.cget("text").replace("Dispositivo: ", "").strip()
                    if txt and txt != "—":
                        dev_name = txt
                except Exception:
                    pass

                marker_text = f"📍 {dev_name}\n±{acc:.0f}m ({provider.upper()})"
                if self.current_location and self.current_location.get("street"):
                    st = self.current_location.get("street")
                    num = self.current_location.get("number", "")
                    marker_text = f"📍 {dev_name}\n{st}, {num}"

                try:
                    self.current_map_marker = self.map_widget.set_marker(
                        lat, lon,
                        text=marker_text,
                        font=("Segoe UI", 9, "bold")
                    )
                    self.map_widget.set_position(lat, lon)
                    if self.map_widget.zoom < 15:
                        self.map_widget.set_zoom(16)
                except Exception as e:
                    print(f"Map marker error: {e}")

                if hasattr(self, 'lbl_map_status_bar') and self.lbl_map_status_bar:
                    self.lbl_map_status_bar.configure(
                        text=f"🎯 Localizado no Mapa: {lat:.6f}, {lon:.6f} | Precisão: ±{acc:.1f}m | Google Maps OK",
                        text_color=self.CLR_GREEN
                    )
            else:
                if hasattr(self, 'lbl_map_status_bar') and self.lbl_map_status_bar:
                    self.lbl_map_status_bar.configure(
                        text="📡 Aguardando coordenadas do aparelho... Clique em 'ATUALIZAR LOCALIZAÇÃO'",
                        text_color=self.CLR_TEXT_MUTED
                    )
            return

        # 2. Fallback to canvas if map_widget is not available
        if hasattr(self, 'map_canvas') and self.map_canvas:
            self.map_canvas.delete("all")
            w = self.map_canvas.winfo_width() or 500
            h = self.map_canvas.winfo_height() or 340
            cx = w // 2
            cy = h // 2

            grid_step = 36
            for x in range(0, w, grid_step):
                self.map_canvas.create_line(x, 0, x, h, fill="#041E0F", width=1)
            for y in range(0, h, grid_step):
                self.map_canvas.create_line(0, y, w, y, fill="#041E0F", width=1)

            r1 = int(50 * self.map_zoom_level)
            r2 = int(100 * self.map_zoom_level)
            r3 = int(150 * self.map_zoom_level)
            self.map_canvas.create_oval(cx - r1, cy - r1, cx + r1, cy + r1, outline="#0A3319", width=1)
            self.map_canvas.create_oval(cx - r2, cy - r2, cx + r2, cy + r2, outline="#0A3319", width=1)
            self.map_canvas.create_oval(cx - r3, cy - r3, cx + r3, cy + r3, outline="#0A3319", width=1)

            self.map_canvas.create_line(cx - 20, cy, cx + 20, cy, fill="#00E676", width=1)
            self.map_canvas.create_line(cx, cy - 20, cx, cy + 20, fill="#00E676", width=1)

            if lat is not None and lon is not None:
                acc_r = max(16, min(120, int(acc * 1.5 * self.map_zoom_level)))
                self.map_canvas.create_oval(cx - acc_r, cy - acc_r, cx + acc_r, cy + acc_r, fill="#00E676", stipple="gray25", outline="#00E676", width=2)
                self.map_canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill="#00E676", outline="#FFFFFF", width=2)
                self.map_canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#FFFFFF")
                self.map_canvas.create_text(cx, cy - 20, text="📍 DISPOSITIVO GERENCIADO", fill="#00E676", font=("Segoe UI", 9, "bold"))
                self.map_canvas.create_text(cx, cy + 20, text=f"{lat:.6f}, {lon:.6f}", fill="#FFFFFF", font=("Consolas", 9, "bold"))
            else:
                self.map_canvas.create_text(cx, cy - 10, text="📡 AGUARDANDO COORDENADAS DO APARELHO...", fill="#94A3B8", font=("Segoe UI", 11, "bold"))
                self.map_canvas.create_text(cx, cy + 16, text="Clique em 'ATUALIZAR LOCALIZAÇÃO' para solicitar agora via GPS.", fill="#475569", font=("Segoe UI", 9))

    # ========================================================
    # LOGGING & AUDIT
    # ========================================================
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        self.safe_after(0, self._append_log, line)

    def _append_log(self, text):
        self.txt_log.insert(tk.END, text)
        self.txt_log.see(tk.END)

    def record_audit(self, action_name, extra_info=""):
        try:
            os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                        f"AÇÃO: {action_name} | "
                        f"CLIENTE: {self.ent_client.get().strip()} | "
                        f"SERVIÇO: {self.ent_service.get().strip()} | "
                        f"VALOR: {self.ent_value.get().strip()} | "
                        f"DISPOSITIVO: {self.selected_device_serial} | "
                        f"INFO: {extra_info}\n")
        except Exception as e:
            self.log(f"[AVISO] Falha ao gravar auditoria: {e}")

    # ========================================================
    # CONFIG STORAGE
    # ========================================================
    def load_saved_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "client": "Cliente Autorizado",
            "service": "Desbloqueio e Suporte Remoto",
            "value": "150.00",
            "pix": "19994783127",
            "merchant": "MDM FRP BRASIL",
            "city": "AMERICANA",
            "ui_theme": "titanium_slate"
        }

    def _save_current_config(self):
        cfg = {
            "client": self.ent_client.get().strip(),
            "service": self.ent_service.get().strip(),
            "value": self.ent_value.get().strip(),
            "pix": self.ent_pix.get().strip(),
            "merchant": self.ent_merchant.get().strip(),
            "city": self.ent_city.get().strip(),
            "ui_theme": getattr(self, 'current_theme_key', 'titanium_slate')
        }
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def _load_initial_values(self):
        self.action_generate_pix()

    # ========================================================
    # PIX ACTIONS
    # ========================================================
    def action_generate_pix(self):
        key = self.ent_pix.get().strip()
        val = self.ent_value.get().strip()
        merchant = self.ent_merchant.get().strip() or "MDM FRP BRASIL"
        city = self.ent_city.get().strip() or "AMERICANA"

        if not key:
            return

        emv = generate_pix_emv(key, val, merchant, city)
        self.current_emv_payload = emv
        self.txt_emv_preview.delete(0, tk.END)
        self.txt_emv_preview.insert(0, emv)

        val_float = parse_currency(val)
        self.lbl_pix_val_display.configure(text=f"Valor Vinculado: R$ {val_float:.2f}")

        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(emv)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        local_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MDM_FRP_BRASIL_DSM")
        os.makedirs(local_dir, exist_ok=True)
        self.current_qr_path = os.path.join(local_dir, "service_qr.png")
        img.save(self.current_qr_path)

        pil_qr = Image.open(self.current_qr_path)
        self.qr_ctk_image = ctk.CTkImage(light_image=pil_qr, dark_image=pil_qr, size=(95, 95))
        self.lbl_qr_image.configure(image=self.qr_ctk_image, text="")

        self._save_current_config()
        self.log(f"[PIX] QR Code gerado para chave: {key} | Valor: R$ {val_float:.2f}")

    def copy_pix_payload(self):
        if self.current_emv_payload:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.current_emv_payload)
            messagebox.showinfo("Pix Copia e Cola", "Código Pix copiado para a área de transferência!")

    # ========================================================
    # DEVICE POLLING WORKER
    # ========================================================
    def _device_polling_worker(self):
        while self.polling_active:
            try:
                if not self.api_client.is_logged_in():
                    time.sleep(2.0)
                    continue
                devices = self.adb.detectDevices()
                fingerprint = ";".join([f"{d['serial']}:{d['status']}" for d in devices])
                if fingerprint != self.last_devices_fingerprint:
                    self.last_devices_fingerprint = fingerprint
                    self.safe_after(0, self._update_devices_ui, devices)
            except Exception:
                pass
            time.sleep(2.0)

    def refresh_devices_async(self):
        def work():
            devices = self.adb.detectDevices()
            self.safe_after(0, self._update_devices_ui, devices)
        threading.Thread(target=work, daemon=True).start()

    def _update_devices_ui(self, devices):
        self.devices_cache = devices
        serials = [d["serial"] for d in devices if d["status"] == "device"]

        if serials:
            self.combo_devices.configure(values=serials)
            if self.selected_device_serial not in serials:
                self.selected_device_serial = serials[0]
                self.combo_devices.set(serials[0])
            self.lbl_connection_badge.configure(
                text=f"● ADB CONECTADO ({len(serials)})",
                fg_color="#022414",
                text_color=self.CLR_GREEN
            )
            self._refresh_selected_device_info()
            self.refresh_location_display()
        else:
            self.combo_devices.configure(values=["Nenhum aparelho detectado"])
            self.combo_devices.set("Nenhum aparelho detectado")
            self.selected_device_serial = None
            self.lbl_connection_badge.configure(
                text="● NENHUM APARELHO CONECTADO",
                fg_color="#1E293B",
                text_color=self.CLR_TEXT_MUTED
            )
            self._clear_device_info_labels()
            self._draw_tactical_map(None, None, 0, "", "OFFLINE")

    def _on_device_selected(self, val):
        if val != "Nenhum aparelho detectado":
            self.selected_device_serial = val
            self._refresh_selected_device_info()
            self.refresh_location_display()

    def _clear_device_info_labels(self):
        for k in self.dev_labels:
            self.dev_labels[k].configure(text="—")

    def _refresh_selected_device_info(self):
        serial = self.selected_device_serial
        if not serial:
            self._clear_device_info_labels()
            return

        info = self.adb.getDeviceInfo(serial)
        self.dev_labels["lbl_st_adb"].configure(text="AUTORIZADO (device)")
        self.dev_labels["lbl_st_model"].configure(text=info.get("model", "—"))
        self.dev_labels["lbl_st_mfg"].configure(text=info.get("manufacturer", "—"))
        self.dev_labels["lbl_st_android"].configure(text=info.get("android", info.get("android_version", "—")))
        self.dev_labels["lbl_st_serial"].configure(text=serial)

        # APK status
        apk_inst = self.adb.isAppInstalled(serial)
        self.dev_labels["lbl_st_apk"].configure(
            text="INSTALADO (Ativo)" if apk_inst else "NÃO INSTALADO",
            text_color=self.CLR_GREEN if apk_inst else "#EF4444"
        )

        st_data = self.adb.queryDeviceState(serial)
        cell_st = st_data.get("state", "DESCONHECIDO")
        self.dev_labels["lbl_st_cell"].configure(text=cell_st)

        back_st = self.adb.getBackendState(serial)
        self.dev_labels["lbl_st_backend"].configure(text=back_st.get("status", "—"))
        self.dev_labels["lbl_st_op"].configure(text=back_st.get("operationId", "—"))

    # ========================================================
    # CLIENT AUTHENTICATION & WALLET INTEGRATION
    # ========================================================
    def _update_auth_ui(self):
        if self.api_client.is_logged_in():
            user = self.api_client.user or {}
            name = user.get("name", "Cliente").split()[0]
            bal = user.get("balance_credits", 0)
            self.btn_account.configure(text=f"👤 {name}", command=self._show_account_menu)
            self.lbl_wallet_badge.configure(text=f"🪙 {bal} Créditos")
            self.lbl_wallet_badge.pack(side="left", padx=(0, 6), before=self.lbl_connection_badge)
            self.btn_recharge.pack(side="left", padx=(0, 6), before=self.lbl_connection_badge)
            if hasattr(self, 'lbl_cloud_user_info') and self.lbl_cloud_user_info:
                self.lbl_cloud_user_info.configure(
                    text=f"👤 Logista: {user.get('name', 'Logista')} ({user.get('email', '')}) | 🪙 Saldo: {bal} Créditos | 🌐 Nuvem: SINCRONIZADA"
                )
            if hasattr(self, 'lbl_side_user') and self.lbl_side_user:
                self.lbl_side_user.configure(text=f"👤 {user.get('name', 'Logista')[:16]}")
            if hasattr(self, 'lbl_side_bal') and self.lbl_side_bal:
                self.lbl_side_bal.configure(text=f"🪙 Saldo: {bal} Créditos")
        else:
            self.btn_account.configure(text="👤 Entrar / Login", command=self.show_login_gate)
            self.lbl_wallet_badge.pack_forget()
            self.btn_recharge.pack_forget()
            if hasattr(self, 'lbl_side_user') and self.lbl_side_user:
                self.lbl_side_user.configure(text="👤 Técnico Convidado")
            if hasattr(self, 'lbl_side_bal') and self.lbl_side_bal:
                self.lbl_side_bal.configure(text="🪙 Saldo: 0 Créditos")

    def open_recharge_portal(self):
        url = getattr(self.api_client, 'base_url', '') or "https://mdm-brasil.onrender.com"
        if not url or "localhost" in url or "127.0.0.1" in url:
            url = "https://mdm-brasil.onrender.com"
        webbrowser.open(f"{url}/client")

    def open_client_portal_in_browser(self):
        url = getattr(self.api_client, 'base_url', '') or "https://mdm-brasil.onrender.com"
        if not url or "localhost" in url or "127.0.0.1" in url:
            url = "https://mdm-brasil.onrender.com"
        webbrowser.open(f"{url}/client")

    def open_whatsapp_support(self):
        webbrowser.open("https://wa.me/5519994783127?text=Olá! Preciso de suporte no MDM FRP Brasil.")

    def save_pix_config(self):
        self.action_save_custom_pix()

    def generate_qr_click(self):
        self.action_generate_pix()

    def _show_account_menu(self):
        user = self.api_client.user or {}
        bal = user.get("balance_credits", 0)
        res = messagebox.askyesno(
            "Conta do Cliente — MDM & FRP BRASIL",
            f"👤 Cliente: {user.get('name')}\n"
            f"📧 E-mail: {user.get('email')}\n"
            f"🪙 Saldo Disponível: {bal} Créditos\n\n"
            "Deseja abrir o Portal do Cliente para recarregar via PIX e ver ordens?\n\n"
            "(Selecione 'Não' se desejar sair da conta)"
        )
        if res:
            self.open_recharge_portal()
        else:
            if messagebox.askyesno("Encerrar Sessão", "Deseja realmente sair da conta e bloquear a ferramenta?"):
                self.api_client.logout()
                self._update_auth_ui()
                self.show_login_gate()
                self.log("[AUTENTICAÇÃO] Sessão encerrada. Sistema bloqueado até novo login.")

    def _build_login_gate_ui(self):
        self.login_gate_frame = ctk.CTkFrame(
            self.root,
            fg_color=self.CLR_CARD,
            corner_radius=16,
            border_width=2,
            border_color="#00E5FF"
        )
        self.center_login_card = self.login_gate_frame

        # Electric lightning pulse animation on card border
        self._pulse_colors = ["#00E5FF", "#38BDF8", "#00F0FF", "#00E676", "#00C853", "#38BDF8", "#00E5FF"]
        self._pulse_idx = 0
        def _animate_pulse():
            try:
                if hasattr(self, 'center_login_card') and self.center_login_card.winfo_exists():
                    c = self._pulse_colors[self._pulse_idx % len(self._pulse_colors)]
                    self.center_login_card.configure(border_color=c)
                    self._pulse_idx += 1
                    self.safe_after(350, _animate_pulse)
            except Exception:
                pass
        self.safe_after(350, _animate_pulse)

        # Load and display official Phantom Logo with unified typography
        logo_loaded = False
        for base_p in [os.path.dirname(__file__), os.path.join(os.path.dirname(__file__), "resources"), os.getcwd()]:
            lp = os.path.join(base_p, "logo.png")
            if os.path.exists(lp):
                try:
                    pil_img = Image.open(lp)
                    self.gate_logo_ctk = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(184, 126))
                    lbl_logo = ctk.CTkLabel(self.login_gate_frame, image=self.gate_logo_ctk, text="")
                    lbl_logo.pack(pady=(14, 2))
                    logo_loaded = True
                    break
                except Exception:
                    pass
        if not logo_loaded:
            ctk.CTkLabel(self.login_gate_frame, text="⚡", font=ctk.CTkFont(size=36)).pack(pady=(14, 2))

        ctk.CTkLabel(
            self.login_gate_frame,
            text="SISTEMA BLOQUEADO • LOGIN DO CLIENTE",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.CLR_GREEN
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            self.login_gate_frame,
            text="Para utilizar os recursos de gestão, desbloqueio e localização,\né obrigatório conectar-se com sua conta de cliente.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self.CLR_TEXT_MUTED,
            justify="center"
        ).pack(padx=20, pady=(0, 10))

        form_box = ctk.CTkFrame(self.login_gate_frame, fg_color="transparent")
        form_box.pack(fill="x", padx=30, pady=(0, 6))

        ctk.CTkLabel(
            form_box,
            text="E-mail:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.CLR_TEXT_MUTED
        ).pack(anchor="w", pady=(0, 2))

        self.gate_ent_email = ctk.CTkEntry(
            form_box,
            placeholder_text="seu@email.com",
            font=ctk.CTkFont(size=12),
            height=32,
            border_color=self.CLR_BORDER
        )
        self.gate_ent_email.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            form_box,
            text="Senha:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.CLR_TEXT_MUTED
        ).pack(anchor="w", pady=(0, 2))

        self.gate_ent_pass = ctk.CTkEntry(
            form_box,
            placeholder_text="••••••••",
            show="•",
            font=ctk.CTkFont(size=12),
            height=32,
            border_color=self.CLR_BORDER
        )
        self.gate_ent_pass.pack(fill="x", pady=(0, 6))

        # Lembrar-me Checkbox
        self.var_remember_me = ctk.BooleanVar(value=bool(self.saved_config.get("remember_me", True)))
        self.chk_remember_me = ctk.CTkCheckBox(
            form_box,
            text="Lembrar credenciais neste computador",
            variable=self.var_remember_me,
            font=ctk.CTkFont(size=11),
            text_color=self.CLR_TEXT_MUTED,
            fg_color="#059669",
            hover_color=self.CLR_GREEN,
            checkmark_color="#FFFFFF"
        )
        self.chk_remember_me.pack(anchor="w", pady=(4, 6))

        # Pre-fill credentials if saved
        saved_email, saved_pass = self.api_client.load_credentials()
        if not saved_email:
            if self.api_client.user and self.api_client.user.get("email"):
                saved_email = self.api_client.user.get("email")
            elif self.saved_config.get("client_email"):
                saved_email = self.saved_config.get("client_email")
        if saved_email:
            self.gate_ent_email.insert(0, saved_email)
        if saved_pass:
            self.gate_ent_pass.insert(0, saved_pass)

        self.gate_ent_email.bind("<Return>", lambda e: self.do_gate_login())
        self.gate_ent_pass.bind("<Return>", lambda e: self.do_gate_login())

        self.lbl_gate_status = ctk.CTkLabel(
            self.login_gate_frame,
            text="",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#EF4444"
        )
        self.lbl_gate_status.pack(pady=(0, 4))

        self.btn_gate_login = ctk.CTkButton(
            self.login_gate_frame,
            text="🔓 ENTRAR E DESBLOQUEAR FERRAMENTA",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#059669",
            hover_color=self.CLR_GREEN,
            height=36,
            command=self.do_gate_login
        )
        self.btn_gate_login.pack(fill="x", padx=30, pady=(0, 6))

        btn_gate_create = ctk.CTkButton(
            self.login_gate_frame,
            text="🌐 Não tem conta? Criar Conta / Comprar Créditos",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="transparent",
            text_color=self.CLR_CYAN,
            hover_color="#0F172A",
            height=24,
            command=self.open_recharge_portal
        )
        btn_gate_create.pack(fill="x", padx=30, pady=(0, 8))

        # Bottom Bar: Server URL (Fixed & Protegido)
        bottom_box = ctk.CTkFrame(self.login_gate_frame, fg_color="transparent")
        bottom_box.pack(fill="x", padx=30, pady=(0, 10))

        self.lbl_gate_server = ctk.CTkLabel(
            bottom_box,
            text=f"🌐 {self.api_client.base_url}",
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color="#64748B"
        )
        self.lbl_gate_server.pack(side="left")

    def show_login_gate(self):
        if hasattr(self, 'main_shell'):
            self.main_shell.pack_forget()
        if hasattr(self, 'header_frame'):
            self.header_frame.pack_forget()

        # Center and resize to login mode
        self.root.update_idletasks()
        scr_w = self.root.winfo_screenwidth()
        scr_h = self.root.winfo_screenheight()
        pos_x = max(0, (scr_w - self.WIN_LOGIN_W) // 2)
        pos_y = max(0, (scr_h - self.WIN_LOGIN_H) // 2)
        self.root.geometry(f"{self.WIN_LOGIN_W}x{self.WIN_LOGIN_H}+{pos_x}+{pos_y}")
        self.root.minsize(self.WIN_LOGIN_W, self.WIN_LOGIN_H)
        self.root.resizable(False, False)
        self.root.title("MDM & FRP BRASIL — AUTENTICAÇÃO")

        self.login_gate_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self._update_auth_ui()

    def unlock_system_from_gate(self):
        self.login_gate_frame.pack_forget()

        # Center and resize to full workspace mode
        self.root.resizable(True, True)
        self.root.minsize(1050, 620)
        self.root.update_idletasks()
        scr_w = self.root.winfo_screenwidth()
        scr_h = self.root.winfo_screenheight()
        pos_x = max(0, (scr_w - self.WIN_MAIN_W) // 2)
        pos_y = max(0, (scr_h - self.WIN_MAIN_H) // 2)
        self.root.geometry(f"{self.WIN_MAIN_W}x{self.WIN_MAIN_H}+{pos_x}+{pos_y}")
        self.root.title("MDM & FRP BRASIL STUDIO — TITANIUM SLATE")

        # Pack main UI elements
        self.main_shell.pack(fill="both", expand=True, padx=6, pady=6)
        self._switch_view("bench")
        self._update_auth_ui()
        self.sync_official_pix()
        self.refresh_devices_async()
        self.refresh_cloud_devices_async()
        self._start_cloud_polling()

    def sync_official_pix(self):
        def work():
            # 1. Verifica se a sessão do usuário possui chave PIX personalizada
            user_pix = None
            if self.api_client.user:
                cust_key = self.api_client.user.get("custom_pix_key")
                if cust_key:
                    user_pix = {
                        "pix_key": cust_key,
                        "merchant_name": self.api_client.user.get("custom_pix_name") or "MDM FRP BRASIL",
                        "merchant_city": self.api_client.user.get("custom_pix_city") or "AMERICANA"
                    }
            if not user_pix:
                ok, res = self.api_client.fetch_official_pix_config()
                if ok and res.get("pix_key"):
                    user_pix = res

            if user_pix and user_pix.get("pix_key"):
                key = user_pix.get("pix_key")
                mer = user_pix.get("merchant_name", "MDM FRP BRASIL")
                city = user_pix.get("merchant_city", "AMERICANA")
                def apply_ui():
                    try:
                        self.ent_pix.configure(state="normal")
                        self.ent_pix.delete(0, tk.END)
                        self.ent_pix.insert(0, key)

                        self.ent_merchant.configure(state="normal")
                        self.ent_merchant.delete(0, tk.END)
                        self.ent_merchant.insert(0, mer)

                        self.ent_city.configure(state="normal")
                        self.ent_city.delete(0, tk.END)
                        self.ent_city.insert(0, city)

                        self.action_generate_pix()
                        self.log(f"[PIX TÉCNICO] ✓ Chave Pix configurada: {key} ({mer} / {city})")
                    except Exception:
                        pass
                self.safe_after(0, apply_ui)
        threading.Thread(target=work, daemon=True).start()

    def action_save_custom_pix(self):
        key = self.ent_pix.get().strip()
        mer = self.ent_merchant.get().strip() or "MDM FRP BRASIL"
        city = self.ent_city.get().strip() or "AMERICANA"

        if not key:
            messagebox.showwarning("Aviso", "Digite a sua chave PIX antes de salvar.")
            return

        self.saved_config["pix"] = key
        self.saved_config["merchant"] = mer
        self.saved_config["city"] = city
        self._save_current_config()

        self.action_generate_pix()
        self.log(f"[CONFIG] Chave PIX salva localmente no PC: {key}")

        if self.api_client.is_logged_in():
            def work():
                ok, res = self.api_client.save_custom_pix(key, mer, city)
                def done():
                    if ok:
                        self.log(f"[NUVEM] ✓ Chave PIX pessoal sincronizada e salva na sua conta na Nuvem!")
                        messagebox.showinfo(
                            "Chave PIX Salva na Nuvem",
                            f"Sua chave PIX foi salva com sucesso no seu perfil e no aplicativo!\n\n"
                            f"Chave: {key}\n"
                            f"Titular: {mer}\n"
                            f"Cidade: {city}\n\n"
                            f"Seus clientes pagarão diretamente para você."
                        )
                    else:
                        self.log(f"[AVISO] Chave salva no PC, pendente de sincronização: {res.get('error', '')}")
                self.safe_after(0, done)
            threading.Thread(target=work, daemon=True).start()
        else:
            messagebox.showinfo(
                "Chave Salva Localmente",
                f"Chave PIX salva no seu computador!\n\nFaça login para sincronizá-la permanentemente com sua conta na nuvem."
            )

    def action_remote_lock_cloud(self):
        serial = self.selected_device_serial
        if not serial:
            serial = simpledialog.askstring("Bloqueio Remoto Online", "Digite o Serial ou ID do aparelho Android a bloquear via nuvem:")
            if not serial or not serial.strip():
                return
            serial = serial.strip()

        if not self.api_client.is_logged_in():
            messagebox.showwarning("Autenticação Necessária", "Faça login na sua conta para enviar comandos remotos online.")
            return

        res = messagebox.askyesno(
            "Confirmar Bloqueio Remoto Online",
            f"Deseja enviar comando de BLOQUEIO REMOTO para o aparelho:\n\n"
            f"Serial / ID: {serial}\n\n"
            f"O aparelho será bloqueado via internet (Wi-Fi ou dados móveis 4G) sem precisar de cabo USB conectado.\n\n"
            f"Deseja prosseguir?"
        )
        if not res:
            return

        self.log(f"[COMANDO REMOTO] Enviando ordem de BLOQUEIO ONLINE para {serial} via nuvem...")
        def work():
            ok, resp = self.api_client.lock_device_remote(serial)
            def done():
                if ok:
                    self.log(f"[NUVEM] 🔒 SUCESSO: Aparelho {serial} BLOQUEADO REMOTAMENTE!")
                    try:
                        self.adb.backend_store.set_device_pending(
                            serial, "Android Device",
                            self.ent_client.get().strip() or "Cliente",
                            self.ent_service.get().strip() or "Bloqueio Remoto",
                            self.ent_value.get().strip() or "150.00",
                            self.ent_pix.get().strip()
                        )
                    except Exception:
                        pass
                    messagebox.showinfo(
                        "Bloqueio Remoto Enviado",
                        f"Comando de bloqueio remoto enviado com sucesso para {serial}!\n\n"
                        f"O APK no smartphone aplicará o bloqueio Kiosk imediatamente via Wi-Fi/4G."
                    )
                else:
                    self.log(f"[ERRO REMOTO] Falha ao enviar bloqueio remoto: {resp.get('error', '')}")
                    messagebox.showerror("Erro", f"Falha ao enviar bloqueio remoto: {resp.get('error', '')}")
            self.safe_after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def action_remote_unlock_cloud(self):
        serial = self.selected_device_serial
        if not serial:
            serial = simpledialog.askstring("Liberação Remota Online", "Digite o Serial ou ID do aparelho Android a liberar via nuvem:")
            if not serial or not serial.strip():
                return
            serial = serial.strip()

        if not self.api_client.is_logged_in():
            messagebox.showwarning("Autenticação Necessária", "Faça login na sua conta para enviar comandos remotos online.")
            return

        res = messagebox.askyesno(
            "Confirmar Liberação Remota Online",
            f"Deseja enviar comando de LIBERAÇÃO / DESBLOQUEIO para o aparelho:\n\n"
            f"Serial / ID: {serial}\n\n"
            f"O aparelho será desbloqueado via internet (Wi-Fi ou 4G) sem precisar de cabo USB conectado.\n\n"
            f"Deseja prosseguir?"
        )
        if not res:
            return

        self.log(f"[COMANDO REMOTO] Enviando ordem de LIBERAÇÃO ONLINE para {serial} via nuvem...")
        def work():
            ok, resp = self.api_client.unlock_device_remote(serial)
            def done():
                if ok:
                    self.log(f"[NUVEM] 🔓 SUCESSO: Aparelho {serial} LIBERADO REMOTAMENTE!")
                    try:
                        self.adb.backend_store.authorize_device(serial, authorized_by="CLOUD_ONLINE")
                    except Exception:
                        pass
                    messagebox.showinfo(
                        "Liberação Remota Enviada",
                        f"Comando de liberação enviado com sucesso para {serial}!\n\n"
                        f"O aparelho foi desbloqueado com sucesso via internet."
                    )
                else:
                    self.log(f"[ERRO REMOTO] Falha ao enviar liberação: {resp.get('error', '')}")
                    messagebox.showerror("Erro", f"Falha ao enviar liberação: {resp.get('error', '')}")
            self.safe_after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def do_gate_login(self):
        email = self.gate_ent_email.get().strip()
        password = self.gate_ent_pass.get().strip()
        if not email or not password:
            self.lbl_gate_status.configure(text="Preencha o e-mail e a senha.", text_color="#EF4444")
            return

        self.lbl_gate_status.configure(text="Autenticando na Cloud API...", text_color="#38BDF8")
        self.btn_gate_login.configure(state="disabled")

        def work():
            ok, msg = self.api_client.login(email, password)
            def done():
                self.btn_gate_login.configure(state="normal")
                if ok:
                    self.lbl_gate_status.configure(text="")
                    remember = getattr(self, 'var_remember_me', None)
                    is_remember = remember.get() if remember else True
                    self.saved_config["remember_me"] = is_remember
                    if is_remember:
                        self.saved_config["client_email"] = email
                        self.api_client.save_credentials(email, password)
                    else:
                        self.saved_config["client_email"] = ""
                        self.gate_ent_pass.delete(0, "end")
                        self.api_client.clear_credentials()
                    self._save_current_config()
                    self.unlock_system_from_gate()
                    self.log(f"[AUTENTICAÇÃO] Login efetuado com sucesso! Cliente: {self.api_client.user.get('name')}.")
                else:
                    self.lbl_gate_status.configure(text=msg, text_color="#EF4444")
            self.safe_after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def gate_change_server(self):
        # Servidor oficial fixado em https://mdm-brasil.onrender.com (pop-up desativado)
        pass

    def _verify_session_async(self):
        ok, bal, err = self.api_client.get_balance()
        if not ok:
            def on_expire():
                self.api_client.logout()
                self.show_login_gate()
                self.lbl_gate_status.configure(text="Sessão anterior expirada. Por favor faça login novamente.", text_color="#EF4444")
            self.safe_after(0, on_expire)
        else:
            self.safe_after(0, self._update_auth_ui)

    def open_login_dialog(self):
        self.show_login_gate()

    def open_inapp_recharge_dialog(self):
        if not self.api_client.is_logged_in():
            self.show_login_gate()
            return

        dialog = ctk.CTkToplevel(self.root)
        dialog.title("MDM & FRP BRASIL — RECARGA PIX")
        dialog.geometry("480x640")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self.current_recharge_dialog = dialog

        # Set official app icon on dialog
        for base_p in [os.path.dirname(__file__), os.path.join(os.path.dirname(__file__), "resources"), os.getcwd()]:
            ico_file = os.path.join(base_p, "app_icon.ico")
            if os.path.exists(ico_file):
                try:
                    dialog.iconbitmap(ico_file)
                    dialog.after(100, lambda f=ico_file: dialog.iconbitmap(f))
                    break
                except Exception:
                    pass

        # Center on screen
        scr_w = dialog.winfo_screenwidth()
        scr_h = dialog.winfo_screenheight()
        pos_x = max(0, (scr_w - 480) // 2)
        pos_y = max(0, (scr_h - 640) // 2)
        dialog.geometry(f"480x640+{pos_x}+{pos_y}")

        card = ctk.CTkFrame(dialog, fg_color=self.CLR_CARD, corner_radius=14, border_width=1, border_color="#00E5FF")
        card.pack(fill="both", expand=True, padx=12, pady=12)

        # Header
        ctk.CTkLabel(card, text="⚡ RECARGA DE CRÉDITOS VIA PIX", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), text_color=self.CLR_CYAN).pack(pady=(14, 2))
        ctk.CTkLabel(card, text="Liberação automática e instantânea pelo Banco Central", font=ctk.CTkFont(size=10), text_color=self.CLR_TEXT_MUTED).pack(pady=(0, 10))

        selected_pkg = tk.IntVar(value=10)

        pkg_frame = ctk.CTkFrame(card, fg_color="#080C16", corner_radius=8, border_width=1, border_color="#1E293B")
        pkg_frame.pack(fill="x", padx=18, pady=(0, 10))

        packages = [
            (5, "5 Créditos (+1 BÔNUS = 6)", "R$ 25,00", "(+1 Grátis)"),
            (10, "10 Créditos (+2 BÔNUS = 12)", "R$ 50,00", "🔥 MAIS POPULAR"),
            (20, "20 Créditos (+4 BÔNUS = 24)", "R$ 100,00", "(+4 Grátis)"),
            (50, "50 Créditos (+10 BÔNUS = 60)", "R$ 250,00", "💎 MELHOR CUSTO")
        ]

        for qty, title, price, tag in packages:
            row = ctk.CTkRadioButton(
                pkg_frame,
                text=f"{title} — {price}  {tag}",
                variable=selected_pkg,
                value=qty,
                font=ctk.CTkFont(size=11, weight="bold" if qty == 10 else "normal"),
                text_color=self.CLR_GREEN if qty == 10 else self.CLR_TEXT_WHITE
            )
            row.pack(anchor="w", padx=16, pady=6)

        qr_container = ctk.CTkFrame(card, fg_color="transparent")
        qr_container.pack(fill="both", expand=True, padx=18, pady=(0, 6))

        lbl_qr = ctk.CTkLabel(qr_container, text="Selecione o pacote acima e clique em 'GERAR PIX'")
        lbl_qr.pack(pady=10)

        ent_payload = ctk.CTkEntry(qr_container, font=ctk.CTkFont(size=9), state="readonly")
        btn_copy = ctk.CTkButton(qr_container, text="📋 Copiar Código PIX", state="disabled")

        lbl_status = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.CLR_CYAN)
        lbl_status.pack(pady=(0, 4))

        poll_timer = [None]
        def cancel_poll():
            if poll_timer[0]:
                try:
                    dialog.after_cancel(poll_timer[0])
                except Exception:
                    pass
        dialog.protocol("WM_DELETE_WINDOW", lambda: (cancel_poll(), dialog.destroy()))

        def do_generate():
            cancel_poll()
            qty = selected_pkg.get()
            lbl_status.configure(text="Gerando cobrança PIX no servidor...", text_color="#38BDF8")
            btn_gen.configure(state="disabled")

            def work():
                ok, res = self.api_client.create_pix_recharge(qty)
                def on_done():
                    btn_gen.configure(state="normal")
                    if ok and res.get("qr_code_base64"):
                        try:
                            qr_bytes = base64.b64decode(res["qr_code_base64"])
                            qr_img = Image.open(io.BytesIO(qr_bytes)).resize((160, 160))
                            ctk_qr = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(160, 160))
                            lbl_qr.configure(image=ctk_qr, text="")
                            lbl_qr.image = ctk_qr
                        except Exception as e:
                            lbl_qr.configure(text=f"Erro ao exibir QR: {e}")

                        copia = res.get("pix_copia_e_cola", "")
                        ent_payload.configure(state="normal")
                        ent_payload.delete(0, "end")
                        ent_payload.insert(0, copia)
                        ent_payload.configure(state="readonly")
                        ent_payload.pack(fill="x", pady=(4, 6))

                        def copy_pix():
                            self.root.clipboard_clear()
                            self.root.clipboard_append(copia)
                            lbl_status.configure(text="✓ Código PIX copiado para a Área de Transferência!", text_color=self.CLR_GREEN)
                        btn_copy.configure(command=copy_pix, state="normal")
                        btn_copy.pack(fill="x", pady=(0, 4))

                        txid = res.get("txid")
                        lbl_status.configure(text="Aguardando confirmação do pagamento...", text_color=self.CLR_CYAN)

                        def check_payment():
                            if not dialog.winfo_exists():
                                return
                            def check_work():
                                st_ok, st_res = self.api_client.check_pix_status(txid)
                                def st_done():
                                    if not dialog.winfo_exists():
                                        return
                                    if st_ok and st_res.get("status") == "PAID":
                                        new_bal = st_res.get("new_balance") or (self.api_client.user.get("balance_credits", 0) + qty)
                                        if self.api_client.user:
                                            self.api_client.user["balance_credits"] = new_bal
                                            self.api_client.save_session()
                                        self._update_auth_ui()
                                        lbl_status.configure(text="✓ PAGAMENTO CONFIRMADO! CRÉDITOS LIBERADOS!", text_color="#00E676")
                                        messagebox.showinfo("Sucesso", f"Pagamento PIX confirmado com sucesso!\n{qty} créditos adicionados à sua conta.")
                                        self.log(f"[PIX RECARGA] Pagamento confirmado! Novo saldo: {new_bal} créditos.")
                                        dialog.destroy()
                                    else:
                                        poll_timer[0] = dialog.after(3000, check_payment)
                                self.safe_after(0, st_done)
                            threading.Thread(target=check_work, daemon=True).start()

                        poll_timer[0] = dialog.after(3000, check_payment)
                    else:
                        lbl_status.configure(text=res.get("error", "Erro ao gerar PIX."), text_color="#EF4444")
                self.safe_after(0, on_done)
            threading.Thread(target=work, daemon=True).start()

        btn_gen = ctk.CTkButton(
            card,
            text="⚡ GERAR QR CODE PIX",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#059669",
            hover_color=self.CLR_GREEN,
            height=36,
            command=do_generate
        )
        btn_gen.pack(fill="x", padx=18, pady=(0, 6))

        btn_web = ctk.CTkButton(
            card,
            text="🌐 Abrir no Navegador Web",
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            text_color="#94A3B8",
            hover_color="#0F172A",
            height=24,
            command=lambda: webbrowser.open(f"{self.api_client.base_url}/client")
        )
        btn_web.pack(pady=(0, 8))

    # ========================================================
    # ACTION BUTTONS (PAINEL DE CONTROLE)
    # ========================================================
    def action_install_apk(self):
        serial = self.selected_device_serial
        if not serial:
            messagebox.showwarning("Aviso", "Nenhum dispositivo Android selecionado.")
            return

        self.log(f"[INSTALL] Instalando APK no dispositivo {serial}...")
        def work():
            ok, msg = self.adb.installApk(serial=serial)
            if ok:
                self.log(f"[INSTALL] APK instalado com sucesso: {msg}")
                self.record_audit("INSTALAR_APK", "Instalado com sucesso")
            else:
                self.log(f"[ERRO] Falha ao instalar APK: {msg}")
            self.safe_after(0, self._refresh_selected_device_info)
        threading.Thread(target=work, daemon=True).start()

    def action_set_active(self):
        serial = self.selected_device_serial
        if not serial:
            messagebox.showwarning("Aviso", "Nenhum dispositivo Android selecionado.")
            return

        self.log(f"[DEVICE] Definindo dispositivo {serial} como ATIVO...")
        self.adb.set_device_pending(
            serial=serial,
            client=self.ent_client.get().strip(),
            service=self.ent_service.get().strip(),
            val=self.ent_value.get().strip(),
            pix=self.ent_pix.get().strip()
        )
        self.record_audit("DEFINIR_ATIVO", "Aparelho em atendimento")
        self.refresh_devices_async()

    def action_send_pending(self):
        serial = self.selected_device_serial
        if not serial:
            messagebox.showwarning("Aviso", "Nenhum dispositivo Android selecionado.")
            return

        # 1. Validação de Autenticação do Cliente
        if not self.api_client.is_logged_in():
            messagebox.showwarning(
                "Autenticação Necessária",
                "Você precisa estar conectado com sua conta de cliente para validar os créditos do atendimento.\n\n"
                "Por favor, faça login ou cadastre-se."
            )
            self.open_login_dialog()
            return

        # 2. Consumo Atômico de 1 Crédito via API Cloud
        info = self.adb.getDeviceInfo(serial)
        model = info.get("model", "Android Device")
        client_name = self.ent_client.get().strip() or "Cliente"
        service_name = self.ent_service.get().strip() or "MDM/FRP Oficial"

        self.log(f"[PLATAFORMA] Verificando carteira e consumindo 1 crédito para {model} ({serial})...")
        ok_c, res_c = self.api_client.consume_credit(
            device_serial=serial,
            device_model=model,
            client_name=client_name,
            service_name=service_name
        )

        if not ok_c:
            if res_c.get("error") == "INSUFFICIENT_CREDITS":
                cur_bal = res_c.get("current_balance", 0)
                resp = messagebox.askyesno(
                    "Saldo Insuficiente de Créditos",
                    f"Seu saldo atual é de {cur_bal} créditos.\n"
                    f"Cada atendimento consome 1 crédito (R$ 5,00).\n\n"
                    f"Deseja abrir o Portal do Cliente para recarregar via PIX agora?"
                )
                if resp:
                    self.open_recharge_portal()
                return
            else:
                messagebox.showerror("Erro de Créditos", res_c.get("message", "Falha ao validar créditos."))
                return

        new_bal = res_c.get("new_balance", 0)
        op_id = res_c.get("operation_id", "OP-2026")
        self.log(f"[CRÉDITOS] ✓ 1 Crédito consumido com sucesso! Saldo restante: {new_bal} créditos (OP: #{op_id})")
        self._update_auth_ui()

        # 3. Execução normal do bloqueio Kiosk
        self.action_generate_pix()
        self.log(f"[KIOSK] Enviando bloqueio pendente para {serial}...")

        def work():
            self.adb.setupReversePort(serial)
            ok, msg = self.adb.sendServicePending(
                serial=serial,
                client=self.ent_client.get().strip(),
                service=self.ent_service.get().strip(),
                value=f"R$ {parse_currency(self.ent_value.get().strip()):.2f}",
                pix=self.ent_pix.get().strip(),
                logo_path=self.adb.default_logo_path,
                qr_path=self.current_qr_path
            )
            if ok:
                self.log(f"[KIOSK] Tela verde de bloqueio ativada no celular com QR Code Pix (OP: #{op_id}).")
                self.record_audit("ENVIAR_BLOQUEIO_PENDENTE", f"Tela Kiosk ativada (OP: {op_id})")
            else:
                self.log(f"[ERRO] Falha ao enviar bloqueio: {msg}")
            self.safe_after(0, self._refresh_selected_device_info)
        threading.Thread(target=work, daemon=True).start()

    def action_confirm_operation(self):
        serial = self.selected_device_serial
        if not serial:
            messagebox.showwarning("Aviso", "Nenhum dispositivo Android selecionado.")
            return

        info = self.adb.getDeviceInfo(serial)
        model = info.get("model", "Android")

        res = messagebox.askyesno(
            "Confirmar Pagamento e Liberação",
            f"Deseja confirmar o pagamento do dispositivo:\n\n"
            f"Modelo: {model}\n"
            f"Serial: {serial}\n\n"
            "✓ A tela do cliente será liberada na hora.\n"
            "✓ O APK será mantido em segundo plano como Administrador (Device Owner).\n\n"
            "Deseja prosseguir?"
        )
        if not res:
            return

        self.log("=" * 45)
        self.log("PAGAMENTO AUTORIZADO")
        self.log(f"DISPOSITIVO: {model}")
        self.log(f"SERIAL / ID: {serial}")
        self.log("STATUS: AUTHORIZED (LIBERADO)")
        self.log("=" * 45)

        def work():
            rec = self.adb.authorizeOperation(serial=serial, authorized_by="ADMIN_EXE")
            op_id = rec.get("operationId", "OP-OFICIAL")
            self.log("[BACKEND] Sincronizando estado AUTHORIZED com o dispositivo...")
            time.sleep(1.0)
            self.log("[DEVICE] APARELHO LIBERADO COM SUCESSO (STATUS: PAGO / LIBERADO)")
            self.log("[ADMIN] APK ocultado da gaveta de aplicativos e mantido como Administrador / Device Owner ativo.")
            self.record_audit("CONFIRMAR_PAGAMENTO", f"Aparelho {serial} (OP: {op_id}) autorizado; tela desbloqueada; APK mantido ativo em Administrador.")
            self.safe_after(0, self._show_release_success_ui)

        threading.Thread(target=work, daemon=True).start()

    def _show_release_success_ui(self):
        self.refresh_devices_async()
        messagebox.showinfo(
            "Operação Concluída",
            "PAGAMENTO CONFIRMADO!\n\n"
            "✓ APARELHO LIBERADO PARA O CLIENTE\n"
            "✓ TELA DE BLOQUEIO KIOSK DESATIVADA\n"
            "✓ APK MANTIDO EM ADMIN / CONTROLE DO DISPOSITIVO"
        )

    # ========================================================
    # LOCATION ACTIONS
    # ========================================================
    def action_request_location(self):
        serial = self.selected_device_serial
        if not serial:
            messagebox.showwarning("Aviso", "Nenhum dispositivo Android selecionado.")
            return

        self.log(f"[LOCATION] LOCATION_REQUEST_SENT -> Solicitando coordenadas ao aparelho {serial}...")
        self.lbl_loc_report.configure(text="Status: Solicitando GPS ao aparelho... (aguarde)")

        def run_req():
            ok, out = self.adb.request_device_location(serial)
            if self.api_client.is_logged_in():
                try:
                    self.api_client.request_device_location_remote(serial)
                except Exception:
                    pass
            for _ in range(8):
                time.sleep(1.2)
                loc_data = self.adb.get_device_location(serial)
                cur = loc_data.get("current") if isinstance(loc_data, dict) else None
                if cur and cur.get("latitude") is not None:
                    break
            self.safe_after(0, self.refresh_location_display)

        threading.Thread(target=run_req, daemon=True).start()

    def refresh_location_display(self):
        serial = self.selected_device_serial
        if not serial:
            self._draw_tactical_map(None, None, 0, "", "OFFLINE")
            return

        info = self.adb.getDeviceInfo(serial)
        dev_id = info.get("serial", serial)
        model = info.get("model", "Android")

        self.lbl_loc_device.configure(text=f"Dispositivo: {model}")
        self.lbl_loc_dev_id.configure(text=f"ID: {dev_id}")

        loc_data = self.adb.get_device_location(dev_id)
        current = loc_data.get("current")

        if current and current.get("latitude") is not None:
            self.current_location = current
            lat = float(current.get("latitude"))
            lon = float(current.get("longitude"))
            acc = float(current.get("accuracy", 10.0))
            prov = str(current.get("provider", "gps"))
            bat = current.get("batteryLevel", "--")
            ts = current.get("timestamp", time.time() * 1000)
            st = current.get("status", "LOCATION_ACQUIRED")
            net = current.get("networkStatus", "online")

            street       = current.get("street", "") or ""
            number       = current.get("number", "") or ""
            neighborhood = current.get("neighborhood", "") or ""
            city         = current.get("city", "") or ""
            state_uf     = current.get("state", "") or ""
            cep          = current.get("cep", "") or ""
            fulladdr     = current.get("fullAddress", "") or ""

            dt_str = datetime.fromtimestamp(ts / 1000.0).strftime("%d/%m/%Y %H:%M:%S")

            self.lbl_loc_lat.configure(text=f"Lat: {lat:.6f}")
            self.lbl_loc_lon.configure(text=f"Lon: {lon:.6f}")
            self.lbl_loc_accuracy.configure(text=f"Precisão: ±{acc:.1f}m")
            self.lbl_loc_provider.configure(text=f"Provedor: {prov.upper()}")
            self.lbl_loc_battery.configure(text=f"Bateria: {bat}%")
            self.lbl_loc_timestamp.configure(text=f"Atualizado: {dt_str}")
            self.lbl_loc_report.configure(text=f"Status: {st}")

            self.lbl_loc_street.configure(text=f"Rua: {street if street else '(detectada)'}")
            self.lbl_loc_number.configure(text=f"Nº: {number if number else 'S/N'}")
            self.lbl_loc_neighborhood.configure(text=f"Bairro: {neighborhood if neighborhood else '-'}")
            city_uf = f"{city} - {state_uf}" if state_uf else city
            self.lbl_loc_city.configure(text=f"Cidade/UF: {city_uf if city_uf.strip() else '-'}")
            self.lbl_loc_cep.configure(text=f"CEP: {cep if cep else '-'}")
            self.lbl_loc_fulladdr.configure(text=f"Endereço: {fulladdr if fulladdr else f'Lat {lat:.6f}, Lon {lon:.6f}'}")

            is_online = (net == "online")
            self.lbl_loc_conn_badge.configure(
                text="● ONLINE" if is_online else "● OFFLINE (Última localização)",
                fg_color="#022414" if is_online else "#2A0808",
                text_color=self.CLR_GREEN if is_online else "#EF4444"
            )

            self._draw_tactical_map(lat, lon, acc, prov, "ONLINE" if is_online else "HISTÓRICO")

            if street:
                self.log(f"[LOCATION] ENDEREÇO: {street}, {number} — {neighborhood}, {city_uf} — CEP {cep}")
        else:
            self._draw_tactical_map(None, None, 0, "", "OFFLINE")

    def open_in_google_maps(self):
        if self.current_location and self.current_location.get("latitude") is not None:
            lat = self.current_location["latitude"]
            lon = self.current_location["longitude"]
            url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            self.log(f"[MAPS] Abrindo Google Maps: {url}")
            webbrowser.open(url)
        else:
            messagebox.showwarning("Localização", "Nenhuma coordenada registrada para abrir no Google Maps.")


def main():
    root = ctk.CTk()
    app = DeviceServiceManagerApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (setattr(app, 'polling_active', False), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
