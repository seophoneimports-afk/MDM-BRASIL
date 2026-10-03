import os
import sys
import PyInstaller.__main__

WINDOWS_DIR = os.path.dirname(os.path.abspath(__file__))
SPEC_FILE = os.path.join(WINDOWS_DIR, "MDM_FRP_BRASIL_DEVICE_SERVICE_MANAGER.spec")

print("=" * 60)
print("Compilando novo executável moderno MDM & FRP BRASIL...")
print(f"Spec: {SPEC_FILE}")
print("=" * 60)

PyInstaller.__main__.run([
    "--clean",
    "--noconfirm",
    SPEC_FILE
])

candidates = [
    os.path.join(WINDOWS_DIR, "dist", "MDM_FRP_BRASIL_DEVICE_SERVICE_MANAGER.exe"),
    os.path.join(os.getcwd(), "dist", "MDM_FRP_BRASIL_DEVICE_SERVICE_MANAGER.exe"),
    os.path.abspath("dist/MDM_FRP_BRASIL_DEVICE_SERVICE_MANAGER.exe")
]
out_exe = None
for c in candidates:
    if os.path.exists(c):
        out_exe = c
        break

desktop_exe = os.path.join(os.path.expanduser("~"), "Desktop", "MDM & FRP BRASIL.exe")
server_exe = os.path.abspath(os.path.join(WINDOWS_DIR, "..", "server", "static", "MDM_FRP_BRASIL.exe"))

import shutil
if out_exe and os.path.exists(out_exe):
    try:
        shutil.copy2(out_exe, desktop_exe)
        print(f"[OK] Atualizado no Desktop: {desktop_exe}")
    except Exception as e:
        print(f"[AVISO] Desktop copy: {e}")
    try:
        os.makedirs(os.path.dirname(server_exe), exist_ok=True)
        shutil.copy2(out_exe, server_exe)
        print(f"[OK] Atualizado no Server Static: {server_exe}")
    except Exception as e:
        print(f"[AVISO] Server copy: {e}")

print("\n" + "=" * 60)
print("[SUCESSO] EXECUTÁVEL COM NOVA INTERFACE GERADO!")
print("=" * 60)
