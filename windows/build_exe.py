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
    os.path.join(os.getcwd(), "dist", "MDM_FRP_BRASIL_DEVICE_SERVICE_MANAGER.exe"),
    os.path.join(WINDOWS_DIR, "dist", "MDM_FRP_BRASIL_DEVICE_SERVICE_MANAGER.exe"),
    os.path.abspath("dist/MDM_FRP_BRASIL_DEVICE_SERVICE_MANAGER.exe")
]
existing_candidates = [c for c in candidates if os.path.exists(c)]
if existing_candidates:
    existing_candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    out_exe = existing_candidates[0]
else:
    out_exe = None

desktop_exe = os.path.join(os.path.expanduser("~"), "Desktop", "MDM & FRP BRASIL.exe")
desktop_exe2 = os.path.join(os.path.expanduser("~"), "Desktop", "MDM_FRP_BRASIL_DEVICE_SERVICE_MANAGER.exe")
downloads_exe = os.path.join(os.path.expanduser("~"), "Downloads", "MDM & FRP BRASIL.exe")
downloads_exe_13 = os.path.join(os.path.expanduser("~"), "Downloads", "MDM & FRP BRASIL (13).exe")
anydesk_exe = r"C:\Users\seoph\Documents\MDM\Anydesk varios pc\MDM_FRP_BRASIL.exe"
server_exe = os.path.abspath(os.path.join(WINDOWS_DIR, "..", "server", "static", "MDM_FRP_BRASIL.exe"))

import shutil
if out_exe and os.path.exists(out_exe):
    targets = [
        (desktop_exe, "Desktop"),
        (desktop_exe2, "Desktop DSM"),
        (downloads_exe, "Downloads"),
        (downloads_exe_13, "Downloads (13)"),
        (anydesk_exe, "Documents (Anydesk varios pc)"),
        (server_exe, "Server Static")
    ]
    for target, label in targets:
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(out_exe, target)
            print(f"[OK] Atualizado em {label}: {target}")
        except Exception as e:
            print(f"[AVISO] {label} copy: {e}")

print("\n" + "=" * 60)
print("[SUCESSO] EXECUTÁVEL COM NOVA INTERFACE GERADO!")
print("=" * 60)
