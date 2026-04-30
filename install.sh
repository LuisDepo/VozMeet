#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# VozMeet — Instalador automático para macOS
# Uso: cd ~/VozMeet && chmod +x install.sh && ./install.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}→${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
error()   { echo -e "${RED}✗ ERROR:${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }

# ── Paso 1: verificar ubicación ────────────────────────────────────────────────
header "[ 1/14 ] Verificando ubicación del proyecto"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_DIR="$HOME/VozMeet"

# Detectar iCloud Drive
if echo "$SCRIPT_DIR" | grep -qi "iCloud\|Mobile Documents\|com~apple~CloudDocs"; then
    error "El proyecto está en iCloud Drive."
    echo ""
    echo "  iCloud Drive causa errores de sandbox en macOS y NO es compatible."
    echo "  Mueve la carpeta VozMeet a tu carpeta de inicio:"
    echo ""
    echo "    mv \"$SCRIPT_DIR\" ~/VozMeet"
    echo "    cd ~/VozMeet && ./install.sh"
    echo ""
    exit 1
fi

if [ "$SCRIPT_DIR" != "$EXPECTED_DIR" ]; then
    warn "El proyecto no está en ~/VozMeet (está en $SCRIPT_DIR)."
    echo "  Se recomienda instalar en ~/VozMeet para evitar problemas."
    read -r -p "  ¿Continuar de todas formas? [s/N]: " cont
    [[ "$cont" =~ ^[sS]$ ]] || exit 1
fi

cd "$SCRIPT_DIR"
success "Ubicación correcta: $SCRIPT_DIR"

# ── Paso 2: arquitectura ───────────────────────────────────────────────────────
header "[ 2/14 ] Detectando arquitectura del sistema"

ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
    success "Apple Silicon (M-series) detectado"
elif [ "$ARCH" = "x86_64" ]; then
    success "Intel x86_64 detectado"
else
    warn "Arquitectura desconocida: $ARCH — continuando de todas formas"
fi

# ── Paso 3: Homebrew ───────────────────────────────────────────────────────────
header "[ 3/14 ] Verificando Homebrew"

if ! command -v brew &>/dev/null; then
    warn "Homebrew no está instalado."
    read -r -p "  ¿Instalar Homebrew ahora? [S/n]: " inst_brew
    if [[ "$inst_brew" =~ ^[nN]$ ]]; then
        error "Homebrew es necesario para instalar Python y ffmpeg. Instálalo desde https://brew.sh"
        exit 1
    fi
    info "Instalando Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Añadir brew al PATH para Apple Silicon
    if [ "$ARCH" = "arm64" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
fi
success "Homebrew disponible: $(brew --version | head -1)"

# ── Paso 4: Python 3.11+ ──────────────────────────────────────────────────────
header "[ 4/14 ] Verificando Python 3.11+"

PYTHON_BIN=""
for py in python3.13 python3.12 python3.11; do
    if command -v "$py" &>/dev/null; then
        PYVER="$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        PYMAJ="${PYVER%%.*}"
        PYMIN="${PYVER##*.}"
        if [ "$PYMAJ" -ge 3 ] && [ "$PYMIN" -ge 11 ]; then
            PYTHON_BIN="$(command -v "$py")"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    if command -v python3 &>/dev/null; then
        PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        PYMAJ="${PYVER%%.*}"; PYMIN="${PYVER##*.}"
        if [ "$PYMAJ" -ge 3 ] && [ "$PYMIN" -ge 11 ]; then
            PYTHON_BIN="$(command -v python3)"
        fi
    fi
fi

if [ -z "$PYTHON_BIN" ]; then
    info "Instalando Python 3.11 via Homebrew..."
    brew install python@3.11
    PYTHON_BIN="$(brew --prefix python@3.11)/bin/python3.11"
fi

success "Python disponible: $PYTHON_BIN ($("$PYTHON_BIN" --version))"

# ── Paso 5: ffmpeg ─────────────────────────────────────────────────────────────
header "[ 5/14 ] Verificando ffmpeg"

if ! command -v ffmpeg &>/dev/null; then
    info "Instalando ffmpeg via Homebrew..."
    brew install ffmpeg
fi
success "ffmpeg disponible: $(ffmpeg -version 2>&1 | head -1)"

# ── Paso 6: Entorno virtual ────────────────────────────────────────────────────
header "[ 6/14 ] Creando entorno virtual Python"

if [ ! -d ".venv" ]; then
    info "Creando .venv con $PYTHON_BIN..."
    "$PYTHON_BIN" -m venv .venv
fi

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
VENV_PIP="$SCRIPT_DIR/.venv/bin/pip"
success "Entorno virtual listo: $VENV_PYTHON"

# ── Paso 7: Instalar dependencias ─────────────────────────────────────────────
header "[ 7/14 ] Instalando dependencias de Python"

info "Actualizando pip..."
"$VENV_PIP" install --upgrade pip --quiet

info "Instalando dependencias desde requirements.txt..."
info "(Esto puede tardar varios minutos en la primera instalación)"
"$VENV_PIP" install -r requirements.txt

success "Dependencias instaladas"

# ── Paso 8: Verificar pywebview ───────────────────────────────────────────────
header "[ 8/14 ] Verificando pywebview"

if ! "$VENV_PYTHON" -c "import webview; print('pywebview OK:', webview.__version__)" 2>/dev/null; then
    warn "pywebview necesita dependencias adicionales de PyObjC"
    info "Instalando pyobjc-core, pyobjc-framework-Cocoa, pyobjc-framework-WebKit..."
    "$VENV_PIP" install --upgrade \
        "pyobjc-core>=10.0" \
        "pyobjc-framework-Cocoa>=10.0" \
        "pyobjc-framework-WebKit>=10.0" \
        "pywebview>=5.0.0"
fi

"$VENV_PYTHON" -c "import webview; print('pywebview OK:', webview.__version__)"
success "pywebview verificado"

# ── Paso 9: Token HuggingFace ─────────────────────────────────────────────────
header "[ 9/14 ] Configurando token de HuggingFace"

if [ -f ".env" ]; then
    EXISTING_TOKEN="$(grep '^HF_TOKEN=' .env 2>/dev/null | cut -d'=' -f2 | tr -d ' ')"
else
    EXISTING_TOKEN=""
fi

if [ -n "$EXISTING_TOKEN" ] && [ "$EXISTING_TOKEN" != "tu_token_aqui" ]; then
    success "Token HuggingFace ya configurado en .env"
else
    echo ""
    echo "  Para la diarización de hablantes, VozMeet necesita un token gratuito de HuggingFace."
    echo ""
    echo "  Pasos:"
    echo "  1. Crea una cuenta gratuita en: https://huggingface.co/join"
    echo "  2. Obtén un token en:           https://huggingface.co/settings/tokens (tipo: Read)"
    echo "  3. Acepta los términos en:"
    echo "       https://huggingface.co/pyannote/speaker-diarization-3.1"
    echo "       https://huggingface.co/pyannote/segmentation-3.0"
    echo ""
    read -r -p "  Ingresa tu HF_TOKEN (o presiona Enter para configurarlo después): " hf_token
    hf_token="${hf_token// /}"

    if [ -n "$hf_token" ] && [ "$hf_token" != "tu_token_aqui" ]; then
        echo "HF_TOKEN=$hf_token" > .env
        success "Token guardado en .env"
    else
        cp .env.example .env 2>/dev/null || echo "HF_TOKEN=tu_token_aqui" > .env
        warn "Token no configurado. Edita el archivo .env antes de usar la app."
    fi
fi

# ── Paso 10: Pre-descargar modelos ────────────────────────────────────────────
header "[10/14 ] Pre-descarga de modelos de IA"

echo ""
warn "Los modelos ocupan aprox. 6 GB y pueden tardar 10-30 minutos en descargarse."
warn "Solo se descargan una vez. Después la app funciona sin internet."
read -r -p "  ¿Descargar los modelos ahora? [S/n]: " dl_models

if [[ ! "$dl_models" =~ ^[nN]$ ]]; then
    HF_TOKEN_VAL="$(grep '^HF_TOKEN=' .env 2>/dev/null | cut -d'=' -f2 | tr -d ' ')"

    info "Descargando faster-whisper large-v3..."
    "$VENV_PYTHON" -c "
from faster_whisper import WhisperModel
print('  Descargando Whisper large-v3 (aprox. 3 GB)...')
m = WhisperModel('large-v3', device='cpu', compute_type='int8')
print('  Whisper large-v3 listo.')
" || warn "No se pudo descargar Whisper. Se descargará al primer uso."

    if [ -n "$HF_TOKEN_VAL" ] && [ "$HF_TOKEN_VAL" != "tu_token_aqui" ]; then
        info "Descargando pyannote speaker-diarization-3.1..."
        "$VENV_PYTHON" -c "
import os; os.environ['HF_TOKEN'] = '$HF_TOKEN_VAL'
from pyannote.audio import Pipeline
print('  Descargando pyannote (aprox. 1 GB)...')
p = Pipeline.from_pretrained('pyannote/speaker-diarization-3.1', token='$HF_TOKEN_VAL')
print('  pyannote listo.')
" || warn "No se pudo descargar pyannote. Verifica tu token y que aceptaste los términos."
    else
        warn "Token HF no configurado — omitiendo descarga de pyannote."
    fi

    info "Descargando SpeechBrain ECAPA-TDNN..."
    "$VENV_PYTHON" -c "
from speechbrain.pretrained import EncoderClassifier
import os
print('  Descargando ECAPA-TDNN (aprox. 100 MB)...')
m = EncoderClassifier.from_hparams(
    source='speechbrain/spkrec-ecapa-voxceleb',
    savedir=os.path.expanduser('~/.cache/speechbrain/ecapa-tdnn'),
    run_opts={'device':'cpu'}
)
print('  ECAPA-TDNN listo.')
" || warn "No se pudo descargar ECAPA-TDNN. Se descargará al primer uso."

    success "Pre-descarga completada"
else
    info "Pre-descarga omitida. Los modelos se descargarán al primer uso."
fi

# ── Paso 11: Inicializar base de datos ────────────────────────────────────────
header "[11/14 ] Inicializando base de datos"

mkdir -p data/uploads data/processed data/transcripts data/voice_samples

"$VENV_PYTHON" -c "
import sys; sys.path.insert(0, '.')
from app.database.db import init_db
init_db()
print('Base de datos inicializada.')
"
success "Base de datos SQLite lista en data/vozmeet.db"

# ── Paso 12: Construir VozMeet.app ────────────────────────────────────────────
header "[12/14 ] Construyendo VozMeet.app"

APP_DIR="$SCRIPT_DIR/VozMeet.app"
CONTENTS="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES_DIR="$CONTENTS/Resources"

mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

# Info.plist
cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>VozMeet</string>
    <key>CFBundleDisplayName</key><string>VozMeet</string>
    <key>CFBundleIdentifier</key><string>com.vozmeet.app</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundleShortVersionString</key><string>1.0.0</string>
    <key>CFBundleExecutable</key><string>VozMeet</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSRequiresAquaSystemAppearance</key><false/>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>NSMicrophoneUsageDescription</key><string>VozMeet no usa el micrófono directamente.</string>
</dict>
</plist>
PLIST

success "Info.plist generado"

# Ejecutable Python con ruta absoluta al intérprete del venv
LAUNCHER_SCRIPT="$MACOS_DIR/VozMeet"
cat > "$LAUNCHER_SCRIPT" << LAUNCHER_EOF
#!${VENV_PYTHON}
# VozMeet launcher — generado por install.sh
# Intérprete: ${VENV_PYTHON}
import sys, os
os.chdir("${SCRIPT_DIR}")
sys.path.insert(0, "${SCRIPT_DIR}")

# Cargar variables de entorno
env_file = os.path.join("${SCRIPT_DIR}", ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

from app.launcher import main
main()
LAUNCHER_EOF

chmod +x "$LAUNCHER_SCRIPT"
success "Ejecutable VozMeet generado en $LAUNCHER_SCRIPT"

# Generar ícono SVG → PNG → ICNS (usando sips si está disponible)
ICON_SVG="$RESOURCES_DIR/AppIcon.svg"
cat > "$ICON_SVG" << 'ICON_EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
  <rect width="1024" height="1024" rx="240" fill="#007AFF"/>
  <path d="M512 160a128 128 0 0 1 128 128v256a128 128 0 0 1-256 0V288a128 128 0 0 1 128-128z" fill="white"/>
  <path d="M320 448a32 32 0 0 1 64 0 128 128 0 0 0 256 0 32 32 0 0 1 64 0 192 192 0 0 1-160 189.8V704h64a32 32 0 0 1 0 64H416a32 32 0 0 1 0-64h64v-66.2A192 192 0 0 1 320 448z" fill="white"/>
</svg>
ICON_EOF

if command -v sips &>/dev/null && command -v iconutil &>/dev/null; then
    ICONSET_DIR="$RESOURCES_DIR/AppIcon.iconset"
    mkdir -p "$ICONSET_DIR"
    # Crear PNG temporal desde SVG usando qlmanage o rsvg-convert si disponible
    TMP_PNG="$RESOURCES_DIR/icon_1024.png"
    if command -v rsvg-convert &>/dev/null; then
        rsvg-convert -w 1024 -h 1024 "$ICON_SVG" -o "$TMP_PNG"
    elif command -v convert &>/dev/null; then
        convert -size 1024x1024 "$ICON_SVG" "$TMP_PNG" 2>/dev/null || true
    fi

    if [ -f "$TMP_PNG" ]; then
        for size in 16 32 64 128 256 512 1024; do
            sips -z "$size" "$size" "$TMP_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" &>/dev/null
            if [ "$size" -le 512 ]; then
                double=$((size * 2))
                sips -z "$double" "$double" "$TMP_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" &>/dev/null
            fi
        done
        iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES_DIR/AppIcon.icns" 2>/dev/null && \
            success "AppIcon.icns generado" || warn "No se pudo generar AppIcon.icns"
        rm -rf "$ICONSET_DIR" "$TMP_PNG"
    else
        warn "No se pudo generar el ícono PNG. Se usará el ícono por defecto."
    fi
else
    warn "sips/iconutil no disponibles. Se usará ícono por defecto."
fi

# Quitar atributo quarantine
if command -v xattr &>/dev/null; then
    xattr -dr com.apple.quarantine "$APP_DIR" 2>/dev/null || true
    success "Atributo quarantine removido de VozMeet.app"
fi

success "VozMeet.app construido en $APP_DIR"

# ── Paso 13: Instalar en /Applications (opcional) ────────────────────────────
header "[13/14 ] Instalación en /Applications"

read -r -p "  ¿Instalar VozMeet en /Applications? [S/n]: " install_apps
if [[ ! "$install_apps" =~ ^[nN]$ ]]; then
    if [ -d "/Applications/VozMeet.app" ]; then
        info "Removiendo versión anterior..."
        rm -rf "/Applications/VozMeet.app"
    fi
    cp -r "$APP_DIR" /Applications/
    success "VozMeet instalado en /Applications/VozMeet.app"
else
    info "Puedes copiarla manualmente: cp -r VozMeet.app /Applications/"
fi

# ── Paso 14: Resumen final ────────────────────────────────────────────────────
header "[14/14 ] ¡Instalación completada!"

echo ""
echo -e "${GREEN}${BOLD}  VozMeet está listo para usar.${RESET}"
echo ""
echo "  ┌─────────────────────────────────────────────────────────────┐"
echo "  │  Cómo usar VozMeet:                                         │"
echo "  │                                                             │"
echo "  │  1. Haz doble click en VozMeet.app (en esta carpeta)       │"
echo "  │     o en /Applications/VozMeet si lo instalaste ahí        │"
echo "  │                                                             │"
echo "  │  2. Arrastra una grabación MP3 o MP4 a la ventana          │"
echo "  │                                                             │"
echo "  │  3. Espera el procesamiento (puede tardar varios minutos)   │"
echo "  │                                                             │"
echo "  │  4. Identifica las voces detectadas                        │"
echo "  │                                                             │"
echo "  │  5. Descarga la transcripción (TXT/MD/JSON)                │"
echo "  │     y súbela a Google NotebookLM                           │"
echo "  └─────────────────────────────────────────────────────────────┘"
echo ""

if grep -q "tu_token_aqui" .env 2>/dev/null; then
    echo -e "  ${YELLOW}⚠ PENDIENTE: Configura tu token HuggingFace en .env${RESET}"
    echo "    Edita el archivo .env y reemplaza 'tu_token_aqui' con tu token."
    echo ""
fi

echo -e "  ${BLUE}Proyecto:${RESET} $SCRIPT_DIR"
echo -e "  ${BLUE}App:${RESET}     $APP_DIR"
echo ""
