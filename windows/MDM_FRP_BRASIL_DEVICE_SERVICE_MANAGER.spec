from PyInstaller.utils.hooks import collect_all

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')
crypto_datas, crypto_binaries, crypto_hiddenimports = collect_all('cryptography')
map_datas, map_binaries, map_hiddenimports = collect_all('tkintermapview')

a = Analysis(
    ['C:/Users/seoph/.gemini/antigravity/scratch/mdm_repo_clone/windows/main_window.py'],
    pathex=[],
    binaries=ctk_binaries + crypto_binaries + map_binaries,
    datas=[('resources', 'resources'), ('logo.png', '.'), ('app_icon.ico', '.')] + ctk_datas + crypto_datas + map_datas,
    hiddenimports=ctk_hiddenimports + crypto_hiddenimports + map_hiddenimports + ['PIL', 'PIL._tkinter_finder', 'qrcode', 'darkdetect', 'urllib.request', 'urllib.parse', 'ApiClient', 'cryptography', 'cryptography.fernet', 'tkintermapview', 'geopy'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MDM_FRP_BRASIL_DEVICE_SERVICE_MANAGER',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/seoph/.gemini/antigravity/scratch/mdm-frp-brasil-device-service-manager/windows/app_icon.ico'],
)
