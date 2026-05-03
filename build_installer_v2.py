#!/usr/bin/env python3
"""Build the VozMeet v1.3 DEFINITIVE installer — pure Python, no shell heredocs."""
import base64, tarfile, io, textwrap
from pathlib import Path

files = [
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
    for f in files:
        tar.add(f)

TAR_B64 = base64.b64encode(buf.getvalue()).decode()

# The Python installer script — does everything without shell heredocs
PY_INSTALLER = r'''
import base64, tarfile, io, os, stat, shutil, subprocess, sys, time
from pathlib import Path

INSTALL_DIR = Path.home() / "AppsBMS/VozMeet/VozMeet-claude-vozmeet-macos-app-EOB7u"
VENV_PY = str(INSTALL_DIR / ".venv/bin/python")

print("=== VozMeet v1.3 Instalador definitivo ===")
print(f"Directorio: {INSTALL_DIR}")

if not INSTALL_DIR.exists():
    print(f"ERROR: No existe {INSTALL_DIR}"); sys.exit(1)
if not Path(VENV_PY).exists():
    print(f"ERROR: No existe {VENV_PY}"); sys.exit(1)
print(f"  Python venv: OK")

os.chdir(str(INSTALL_DIR))

# 1. Matar procesos en puerto 8765
print("\n[1] Liberando puerto 8765...")
try:
    r = subprocess.run(["lsof", "-ti", "tcp:8765"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        for pid in r.stdout.strip().split("\n"):
            pid = pid.strip()
            if pid:
                subprocess.run(["kill", "-9", pid], capture_output=True)
                print(f"  Proceso {pid} terminado.")
        time.sleep(0.8)
    else:
        print("  Puerto libre.")
except Exception as e:
    print(f"  (lsof error: {e})")

# 2. Extraer archivos de la app
print("\n[2] Extrayendo archivos...")
B64 = "TAR_B64_PLACEHOLDER"
data = base64.b64decode(B64.replace("\n",""))
buf = io.BytesIO(data)
with tarfile.open(fileobj=buf, mode="r:gz") as tar:
    for m in tar.getmembers():
        tar.extract(m, path=".", filter="data")
        print(f"  OK  {m.name}  ({m.size} bytes)")

# 3. Crear .app bundle usando Python (sin heredoc de shell)
print("\n[3] Creando VozMeet.app...")
APP = INSTALL_DIR / "VozMeet.app"
(APP / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
(APP / "Contents/Resources").mkdir(parents=True, exist_ok=True)

launcher = APP / "Contents/MacOS/VozMeet"
launcher.write_text(
    "#!" + VENV_PY + "\n"
    "import sys, os\n"
    "os.chdir('" + str(INSTALL_DIR) + "')\n"
    "sys.path.insert(0, '" + str(INSTALL_DIR) + "')\n"
    "from app.launcher import main\n"
    "main()\n"
)
launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
print(f"  Launcher escrito: {launcher}")
print(f"  Primera linea: {launcher.read_text().splitlines()[0]!r}")

(APP / "Contents/Info.plist").write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
    '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0"><dict>\n'
    '  <key>CFBundleName</key>          <string>VozMeet</string>\n'
    '  <key>CFBundleDisplayName</key>   <string>VozMeet</string>\n'
    '  <key>CFBundleIdentifier</key>    <string>com.bms.vozmeet</string>\n'
    '  <key>CFBundleVersion</key>       <string>1.3</string>\n'
    '  <key>CFBundleExecutable</key>    <string>VozMeet</string>\n'
    '  <key>CFBundleIconFile</key>      <string>VozMeet</string>\n'
    '  <key>NSHighResolutionCapable</key><true/>\n'
    '  <key>LSUIElement</key>           <false/>\n'
    '</dict></plist>\n'
)
print("  Info.plist: OK")

icon_src = INSTALL_DIR / "app/static/icons/VozMeet.icns"
if icon_src.exists():
    shutil.copy2(str(icon_src), str(APP / "Contents/Resources/VozMeet.icns"))
    print("  Icono: OK")
else:
    print("  Icono: no encontrado (se usara icono default)")

# 4. Copiar a /Applications
print("\n[4] Instalando en /Applications...")
dest = Path("/Applications/VozMeet.app")
if dest.exists():
    shutil.rmtree(str(dest))
shutil.copytree(str(APP), str(dest))

dest_launcher = dest / "Contents/MacOS/VozMeet"
ok_exists = dest_launcher.exists()
ok_exec   = os.access(str(dest_launcher), os.X_OK)
first_line = dest_launcher.read_text().splitlines()[0] if ok_exists else "???"
print(f"  Launcher existe   : {ok_exists}")
print(f"  Es ejecutable     : {ok_exec}")
print(f"  Primera linea     : {first_line!r}")

# 5. Registrar con LaunchServices y refrescar Dock
lsreg = ("/System/Library/Frameworks/CoreServices.framework"
         "/Frameworks/LaunchServices.framework/Support/lsregister")
if os.path.exists(lsreg):
    subprocess.run([lsreg, "-f", str(dest)], capture_output=True)
subprocess.run(["killall", "Dock"], capture_output=True)

if ok_exists and ok_exec:
    print("\n======================================")
    print("  VozMeet v1.3 instalado correctamente")
    print("======================================")
    print("Ejecuta:  open /Applications/VozMeet.app")
else:
    print("\nERROR: algo salio mal con el launcher.")
    sys.exit(1)
'''

# Embed real tar b64 into the installer
py_installer = PY_INSTALLER.replace("TAR_B64_PLACEHOLDER", TAR_B64)

# Base64-encode the Python installer itself
installer_b64 = base64.b64encode(py_installer.encode()).decode()

# Wrap in a single zsh-safe command
# Single quotes around b64 mean zsh never interprets the content
oneliner = f"echo '{installer_b64}' | base64 -d | python3"

out = "/tmp/vozmeet_v13_definitive.sh"
with open(out, "w") as f:
    f.write(oneliner + "\n")

print(f"Oneliner escrito en: {out}")
print(f"Longitud del comando: {len(oneliner)} caracteres")
print(f"\nContenido:")
print(oneliner)
