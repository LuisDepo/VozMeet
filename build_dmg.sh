#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="VozMeet"
VERSION="1.0"
TMP_APP="/tmp/${APP_NAME}.app"
TMP_RW_DMG="/tmp/VozMeet_rw.dmg"
TMP_DMG_DIR="/tmp/vozmeet_dmg"
OUT_DMG="$SCRIPT_DIR/${APP_NAME}-${VERSION}.dmg"
ICON_SRC="$SCRIPT_DIR/app/static/icons"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     Empaquetando VozMeet ${VERSION} DMG         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

rm -rf "$TMP_APP" "$TMP_DMG_DIR" "$TMP_RW_DMG" "$OUT_DMG"
mkdir -p "$TMP_APP/Contents/MacOS"
mkdir -p "$TMP_APP/Contents/Resources/src"

echo "→ Copiando código fuente..."
rsync -a \
    --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.git' --exclude='data/' --exclude='*.dmg' \
    --exclude='VozMeet.app' --exclude='build_dmg.sh' \
    "$SCRIPT_DIR/" "$TMP_APP/Contents/Resources/src/"

echo "→ Configurando ícono..."
if [ -f "$ICON_SRC/VozMeet.icns" ]; then
    cp "$ICON_SRC/VozMeet.icns" "$TMP_APP/Contents/Resources/VozMeet.icns"
    echo "  ✓ VozMeet.icns copiado"
else
    ICONSET="/tmp/VozMeet.iconset"
    mkdir -p "$ICONSET"
    for f in icon_16x16 icon_16x16@2x icon_32x32 icon_32x32@2x \
              icon_128x128 icon_128x128@2x icon_256x256 icon_256x256@2x \
              icon_512x512 icon_512x512@2x; do
        [ -f "$ICON_SRC/${f}.png" ] && cp "$ICON_SRC/${f}.png" "$ICONSET/${f}.png"
    done
    iconutil -c icns "$ICONSET" -o "$TMP_APP/Contents/Resources/VozMeet.icns" 2>/dev/null \
        && echo "  ✓ VozMeet.icns generado" || echo "  ⚠ Sin ícono"
    rm -rf "$ICONSET"
fi

echo "→ Generando Info.plist..."
cat > "$TMP_APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>             <string>VozMeet</string>
  <key>CFBundleDisplayName</key>      <string>VozMeet</string>
  <key>CFBundleIdentifier</key>       <string>com.vozmeet.app</string>
  <key>CFBundleVersion</key>          <string>1.0.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key>       <string>VozMeet</string>
  <key>CFBundleIconFile</key>         <string>VozMeet</string>
  <key>CFBundlePackageType</key>      <string>APPL</string>
  <key>NSHighResolutionCapable</key>  <true/>
  <key>NSRequiresAquaSystemAppearance</key><false/>
  <key>LSMinimumSystemVersion</key>   <string>12.0</string>
</dict>
</plist>
PLIST

echo "→ Creando lanzador..."
cat > "$TMP_APP/Contents/MacOS/VozMeet" << 'LAUNCHER'
#!/bin/bash
BUNDLE="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES="$BUNDLE/Resources"
SRC="$RESOURCES/src"
VENV="$HOME/Library/Application Support/VozMeet/venv"
DATA="$HOME/VozMeet"
LOG="$DATA/data/vozmeet.log"

mkdir -p "$DATA/data"

if [ ! -f "$VENV/bin/python3" ]; then
    INSTALLER="$SRC/install_bundled.sh"
    osascript << APPLESCRIPT
tell application "Terminal"
    activate
    do script "bash '$INSTALLER'"
end tell
APPLESCRIPT
    osascript -e 'display dialog "VozMeet está instalando sus componentes.\n\nSigue las instrucciones en Terminal (15-30 min la primera vez).\n\nCuando termine, vuelve a abrir VozMeet." buttons {"OK"} default button "OK" with icon caution with title "VozMeet — Primera instalación"'
    exit 0
fi

source "$VENV/bin/activate"
cd "$SRC"
exec python3 -m app.launcher >> "$LOG" 2>&1
LAUNCHER

chmod +x "$TMP_APP/Contents/MacOS/VozMeet"

echo "→ Generando install_bundled.sh..."
cat > "$TMP_APP/Contents/Resources/src/install_bundled.sh" << 'INSTALL'
#!/usr/bin/env bash
set -euo pipefail
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${BLUE}→${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }

VENV="$HOME/Library/Application Support/VozMeet/venv"
DATA="$HOME/VozMeet"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCH="$(uname -m)"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║    VozMeet — Instalación inicial         ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""

info "Verificando Homebrew..."
if ! command -v brew &>/dev/null; then
    info "Instalando Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    [ "$ARCH" = "arm64" ] && eval "$(/opt/homebrew/bin/brew shellenv)"
fi
success "Homebrew: $(brew --version | head -1)"

info "Verificando Python 3.11+..."
PYTHON_BIN=""
for py in python3.13 python3.12 python3.11 python3; do
    if command -v "$py" &>/dev/null; then
        VER="$("$py" -c 'import sys; v=sys.version_info; print(v.major*100+v.minor)')"
        [ "$VER" -ge 311 ] && { PYTHON_BIN="$(command -v "$py")"; break; }
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    info "Instalando Python 3.11..."
    brew install python@3.11
    PYTHON_BIN="$(brew --prefix python@3.11)/bin/python3.11"
fi
success "Python: $("$PYTHON_BIN" --version)"

info "Verificando ffmpeg..."
command -v ffmpeg &>/dev/null || brew install ffmpeg
success "ffmpeg listo"

info "Creando entorno virtual..."
mkdir -p "$(dirname "$VENV")"
[ -d "$VENV" ] || "$PYTHON_BIN" -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip --quiet
success "Entorno virtual en $VENV"

info "Instalando dependencias Python (10-15 min)..."
pip install -r "$SRC/requirements.txt"
success "Dependencias instaladas"

mkdir -p "$DATA"
ENV_FILE="$DATA/.env"
if [ ! -f "$ENV_FILE" ] || grep -q "tu_token_aqui" "$ENV_FILE" 2>/dev/null; then
    echo ""
    echo "  Para diarización necesitas un token gratuito de HuggingFace."
    echo "  1. https://huggingface.co/join"
    echo "  2. https://huggingface.co/settings/tokens (tipo Read)"
    echo "  3. Acepta términos:"
    echo "     https://huggingface.co/pyannote/speaker-diarization-3.1"
    echo "     https://huggingface.co/pyannote/segmentation-3.0"
    echo ""
    read -r -p "  Ingresa tu HF_TOKEN: " hf_token
    hf_token="${hf_token// /}"
    [ -n "$hf_token" ] && echo "HF_TOKEN=$hf_token" > "$ENV_FILE" \
        || echo "HF_TOKEN=tu_token_aqui" > "$ENV_FILE"
fi
success "Configuración en $ENV_FILE"

echo ""
warn "Los modelos de IA ocupan ~3 GB y se descargan una sola vez."
read -r -p "  ¿Descargar modelos ahora? [S/n]: " dl
if [[ ! "$dl" =~ ^[nN]$ ]]; then
    HF_TOK="$(grep '^HF_TOKEN=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d ' ')"
    info "Descargando Whisper large-v3-turbo (~800 MB)..."
    python3 -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo','cpu','int8'); print('Whisper listo.')" || warn "Se descargará al primer uso."
    if [ -n "$HF_TOK" ] && [ "$HF_TOK" != "tu_token_aqui" ]; then
        info "Descargando pyannote (~1 GB)..."
        python3 -c "from pyannote.audio import Pipeline; Pipeline.from_pretrained('pyannote/speaker-diarization-3.1',token='$HF_TOK'); print('pyannote listo.')" || warn "Se descargará al primer uso."
    fi
    info "Descargando SpeechBrain (~100 MB)..."
    python3 -c "
from speechbrain.pretrained import EncoderClassifier; import os
EncoderClassifier.from_hparams(source='speechbrain/spkrec-ecapa-voxceleb',savedir=os.path.expanduser('~/.cache/speechbrain/ecapa-tdnn'),run_opts={'device':'cpu'})
print('SpeechBrain listo.')" || warn "Se descargará al primer uso."
fi

info "Inicializando base de datos..."
mkdir -p "$DATA/data/uploads" "$DATA/data/processed" "$DATA/data/transcripts" "$DATA/data/voice_samples"
cd "$SRC"
python3 -c "import sys; sys.path.insert(0,'.'); from app.database.db import init_db; init_db()"
success "Base de datos lista"

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║  ✅  VozMeet instalado correctamente     ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo "  Abre VozMeet desde /Applications y empieza a transcribir."
echo ""
INSTALL
chmod +x "$TMP_APP/Contents/Resources/src/install_bundled.sh"

xattr -cr "$TMP_APP" 2>/dev/null || true
echo "✓ VozMeet.app construido"

echo "→ Creando DMG..."
mkdir -p "$TMP_DMG_DIR"
cp -r "$TMP_APP" "$TMP_DMG_DIR/VozMeet.app"
ln -s /Applications "$TMP_DMG_DIR/Applications"

hdiutil create -size 80m -fs HFS+ -volname "VozMeet" "$TMP_RW_DMG" -quiet
hdiutil attach "$TMP_RW_DMG" -mountpoint "/Volumes/VozMeet" -quiet

cp -r "$TMP_DMG_DIR/VozMeet.app" "/Volumes/VozMeet/"
ln -sf /Applications "/Volumes/VozMeet/Applications"

osascript << 'APPLESCRIPT' 2>/dev/null || true
tell application "Finder"
    tell disk "VozMeet"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set bounds of container window to {100, 100, 760, 500}
        set theViewOptions to icon view options of container window
        set arrangement of theViewOptions to not arranged
        set icon size of theViewOptions to 128
        set position of item "VozMeet.app" of container window to {180, 200}
        set position of item "Applications" of container window to {480, 200}
        close
        open
        update without registering applications
    end tell
end tell
APPLESCRIPT

hdiutil detach "/Volumes/VozMeet" -quiet
hdiutil convert "$TMP_RW_DMG" -format UDZO -o "$OUT_DMG" -quiet

rm -rf "$TMP_APP" "$TMP_DMG_DIR" "$TMP_RW_DMG"

echo ""
echo "╔══════════════════════════════════════════╗"
printf "║  ✅  %-36s║\n" "$(basename "$OUT_DMG") listo"
echo "╚══════════════════════════════════════════╝"
echo "  Tamaño: $(du -sh "$OUT_DMG" | cut -f1)"
echo "  Ruta:   $OUT_DMG"
echo ""
