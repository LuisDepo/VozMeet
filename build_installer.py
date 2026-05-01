#!/usr/bin/env python3
"""Build the VozMeet v1.3 installer shell script."""
import base64, tarfile, io, os

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

b64 = base64.b64encode(buf.getvalue()).decode()
lines = [b64[i:i+76] for i in range(0, len(b64), 76)]
b64_block = "\n".join(lines)

script = r"""#!/usr/bin/env bash
# VozMeet v1.3 — instalador completo (sys.path + port-free fix)
set -euo pipefail

INSTALL_DIR="$HOME/AppsBMS/VozMeet/VozMeet-claude-vozmeet-macos-app-EOB7u"
APP_BUNDLE="$INSTALL_DIR/VozMeet.app"
VENV="$INSTALL_DIR/.venv"

echo "=== VozMeet v1.3 Installer ==="
echo "Destino: $INSTALL_DIR"

if [ ! -d "$INSTALL_DIR" ]; then
  echo "ERROR: El directorio no existe: $INSTALL_DIR"
  exit 1
fi

cd "$INSTALL_DIR"

# ── Extraer archivos ───────────────────────────────────────────────────────────
python3 << 'PYEOF'
import base64, tarfile, io
B64 = (
""" + '"""' + b64_block + '"""' + r"""
)
data = base64.b64decode(B64.replace("\n",""))
buf = io.BytesIO(data)
ok = 0
with tarfile.open(fileobj=buf, mode="r:gz") as tar:
    for m in tar.getmembers():
        tar.extract(m, path=".", filter="data")
        print(f"  OK  {m.name} ({m.size}b)")
        ok += 1
print(f"Extraidos {ok} archivos.")
PYEOF

# ── Recrear .app bundle ────────────────────────────────────────────────────────
echo ""
echo "Recreando VozMeet.app..."
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

PYTHON_BIN="$VENV/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
  echo "ERROR: No se encontro $PYTHON_BIN"
  exit 1
fi

cat > "$APP_BUNDLE/Contents/MacOS/VozMeet" << SCRIPT
#!$PYTHON_BIN
import sys, os
os.chdir("$INSTALL_DIR")
sys.path.insert(0, "$INSTALL_DIR")
from app.launcher import main
main()
SCRIPT
chmod +x "$APP_BUNDLE/Contents/MacOS/VozMeet"

cat > "$APP_BUNDLE/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>          <string>VozMeet</string>
  <key>CFBundleDisplayName</key>   <string>VozMeet</string>
  <key>CFBundleIdentifier</key>    <string>com.bms.vozmeet</string>
  <key>CFBundleVersion</key>       <string>1.3</string>
  <key>CFBundleExecutable</key>    <string>VozMeet</string>
  <key>CFBundleIconFile</key>      <string>VozMeet</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSUIElement</key>           <false/>
</dict>
</plist>
PLIST

ICON_SRC="$INSTALL_DIR/app/static/icons/VozMeet.icns"
if [ -f "$ICON_SRC" ]; then
  cp "$ICON_SRC" "$APP_BUNDLE/Contents/Resources/VozMeet.icns"
  echo "  Icono copiado."
fi

echo ""
echo "Copiando VozMeet.app a /Applications..."
rm -rf /Applications/VozMeet.app
cp -R "$APP_BUNDLE" /Applications/VozMeet.app
echo "  /Applications/VozMeet.app actualizado."

lsregister="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
[ -f "$lsregister" ] && "$lsregister" -f /Applications/VozMeet.app 2>/dev/null || true
killall Dock 2>/dev/null || true

echo ""
echo "======================================"
echo "  VozMeet v1.3 instalado correctamente"
echo "======================================"
echo "Abre /Applications/VozMeet.app para iniciar."
"""

out = "/tmp/vozmeet_v13_final.sh"
with open(out, "w") as f:
    f.write(script)

lines_count = script.count("\n")
print(f"Escrito: {out}  ({len(script)} bytes, {lines_count} lineas)")
