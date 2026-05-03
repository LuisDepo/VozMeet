#!/usr/bin/env python3
"""
Build VozMeet-Installer.app — a real macOS .app that installs VozMeet v1.3.
Double-click → native macOS dialog when done. No Terminal required.
Output: /tmp/VozMeet-Installer.zip  (user unzips, right-click > Open)
"""
import base64, tarfile, io, os, stat, shutil, zipfile
from pathlib import Path

# ── 1. Build tar.gz of app files ──────────────────────────────────────────────
FILES = [
    "app/api/recordings.py",
    "app/api/update.py",
    "app/core/pipeline.py",
    "app/core/transcriber.py",
    "app/launcher.py",
    "app/main.py",
    "app/static/css/app.css",
    "app/static/index.html",
    "app/static/js/app.js",
]
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for f in FILES:
        tar.add(f)
TAR_B64 = base64.b64encode(buf.getvalue()).decode()
print(f"tar.gz: {len(buf.getvalue())} bytes  →  b64: {len(TAR_B64)} chars")

# ── 2. Python installer script (runs inside the .app, NO Terminal) ────────────
INSTALLER_PY = '''#!/usr/bin/python3
# VozMeet v1.3 — Installer App
# This script runs when the user double-clicks VozMeet-Installer.app
import base64, tarfile, io, os, stat, shutil, subprocess, sys, time
from pathlib import Path

def _dialog(msg, title="VozMeet Installer"):
    subprocess.run(
        ["osascript", "-e",
         f\'display dialog "{msg}" buttons {{"OK"}} \' +
         f\'default button "OK" with title "{title}"\'],
        capture_output=True)

def _notify(msg):
    subprocess.run(
        ["osascript", "-e",
         f\'display notification "{msg}" with title "VozMeet Installer"\'],
        capture_output=True)

INSTALL_DIR = Path.home() / "AppsBMS/VozMeet/VozMeet-claude-vozmeet-macos-app-EOB7u"
VENV_PY    = str(INSTALL_DIR / ".venv/bin/python")

# ── Pre-flight checks ──────────────────────────────────────────────────────────
if not INSTALL_DIR.exists():
    _dialog(
        "No se encontro el directorio de instalacion:\\n" + str(INSTALL_DIR) +
        "\\n\\nEjecuta primero el instalador original de VozMeet.",
        "VozMeet Installer — Error")
    sys.exit(1)

if not Path(VENV_PY).exists():
    _dialog(
        "No se encontro el entorno Python (.venv).\\n\\n" + VENV_PY,
        "VozMeet Installer — Error")
    sys.exit(1)

_notify("Instalando VozMeet v1.3...")
os.chdir(str(INSTALL_DIR))

# ── Kill any process on port 8765 ─────────────────────────────────────────────
try:
    r = subprocess.run(["lsof", "-ti", "tcp:8765"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        for pid in r.stdout.strip().split("\\n"):
            if pid.strip():
                subprocess.run(["kill", "-9", pid.strip()], capture_output=True)
        time.sleep(0.8)
except Exception:
    pass

# ── Extract app files ──────────────────────────────────────────────────────────
B64 = "TAR_B64_PLACEHOLDER"
data = base64.b64decode(B64)
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
    tar.extractall(".", filter="data")

# ── Build .app bundle via Python (no shell heredoc) ───────────────────────────
APP = INSTALL_DIR / "VozMeet.app"
(APP / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
(APP / "Contents/Resources").mkdir(parents=True, exist_ok=True)

launcher = APP / "Contents/MacOS/VozMeet"
launcher.write_text(
    "#!" + VENV_PY + "\\n"
    "import sys, os\\n"
    "os.chdir(\'" + str(INSTALL_DIR) + "\')\\n"
    "sys.path.insert(0, \'" + str(INSTALL_DIR) + "\')\\n"
    "from app.launcher import main\\n"
    "main()\\n"
)
launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

(APP / "Contents/Info.plist").write_text(
    \'<?xml version="1.0" encoding="UTF-8"?>\\n\'
    \'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\\n\'
    \'  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\\n\'
    \'<plist version="1.0"><dict>\\n\'
    \'  <key>CFBundleName</key>          <string>VozMeet</string>\\n\'
    \'  <key>CFBundleDisplayName</key>   <string>VozMeet</string>\\n\'
    \'  <key>CFBundleIdentifier</key>    <string>com.bms.vozmeet</string>\\n\'
    \'  <key>CFBundleVersion</key>       <string>1.3</string>\\n\'
    \'  <key>CFBundleExecutable</key>    <string>VozMeet</string>\\n\'
    \'  <key>CFBundleIconFile</key>      <string>VozMeet</string>\\n\'
    \'  <key>NSHighResolutionCapable</key><true/>\\n\'
    \'  <key>LSUIElement</key>           <false/>\\n\'
    \'</dict></plist>\\n\'
)

icon_src = INSTALL_DIR / "app/static/icons/VozMeet.icns"
if icon_src.exists():
    shutil.copy2(str(icon_src), str(APP / "Contents/Resources/VozMeet.icns"))

# ── Copy to /Applications ──────────────────────────────────────────────────────
dest = Path("/Applications/VozMeet.app")
if dest.exists():
    shutil.rmtree(str(dest))
shutil.copytree(str(APP), str(dest))

# ── Register with LaunchServices & refresh Dock ───────────────────────────────
lsreg = (
    "/System/Library/Frameworks/CoreServices.framework"
    "/Frameworks/LaunchServices.framework/Support/lsregister"
)
if os.path.exists(lsreg):
    subprocess.run([lsreg, "-f", str(dest)], capture_output=True)
subprocess.run(["killall", "Dock"], capture_output=True)

# ── Done ───────────────────────────────────────────────────────────────────────
_dialog(
    "VozMeet v1.3 instalado correctamente.\\n\\n"
    "Abre VozMeet desde la carpeta Aplicaciones.",
    "Instalacion completada")
'''

installer_py = INSTALLER_PY.replace("TAR_B64_PLACEHOLDER", TAR_B64)

# ── 3. Build the .app directory structure in /tmp ─────────────────────────────
app_root = Path("/tmp/VozMeet-Installer.app")
macos    = app_root / "Contents/MacOS"
macos.mkdir(parents=True, exist_ok=True)

exe = macos / "VozMeet-Installer"
exe.write_text(installer_py)
exe.chmod(exe.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

(app_root / "Contents/Info.plist").write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
    '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0"><dict>\n'
    '  <key>CFBundleName</key>          <string>VozMeet Installer</string>\n'
    '  <key>CFBundleDisplayName</key>   <string>VozMeet Installer</string>\n'
    '  <key>CFBundleIdentifier</key>    <string>com.bms.vozmeet.installer</string>\n'
    '  <key>CFBundleVersion</key>       <string>1.3</string>\n'
    '  <key>CFBundleExecutable</key>    <string>VozMeet-Installer</string>\n'
    '  <key>NSHighResolutionCapable</key><true/>\n'
    '  <key>LSUIElement</key>           <true/>\n'
    '</dict></plist>\n'
)
print(f".app built at: {app_root}")
print(f"Executable:    {exe}  (executable={os.access(str(exe), os.X_OK)})")

# ── 4. Zip the .app ────────────────────────────────────────────────────────────
zip_path = Path("/tmp/VozMeet-Installer.zip")
with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
    for path in app_root.rglob("*"):
        arcname = path.relative_to(app_root.parent)
        zf.write(str(path), str(arcname))
        # Preserve executable bit via external_attr
        if path.is_file():
            mode = path.stat().st_mode
            zf.getinfo(str(arcname)).external_attr = (mode & 0xFFFF) << 16

print(f"ZIP:           {zip_path}  ({zip_path.stat().st_size:,} bytes)")
print(f"\nDone. Upload {zip_path} to GitHub and share the download link.")
