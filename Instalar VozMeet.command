#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# VozMeet — Instalador con doble click
# Coloca este archivo en cualquier lugar y haz doble click
# ──────────────────────────────────────────────────────────────────────────────

# Colores
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}→${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
error()   { echo -e "${RED}✗ ERROR:${RESET} $*"; }
header()  { echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n$*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }
pause()   { echo -e "\n${YELLOW}Presiona ENTER para continuar...${RESET}"; read -r; }

clear
echo -e "${BOLD}"
echo "  ██╗   ██╗ ██████╗ ███████╗███╗   ███╗███████╗███████╗████████╗"
echo "  ██║   ██║██╔═══██╗╚══███╔╝████╗ ████║██╔════╝██╔════╝╚══██╔══╝"
echo "  ██║   ██║██║   ██║  ███╔╝ ██╔████╔██║█████╗  █████╗     ██║   "
echo "  ╚██╗ ██╔╝██║   ██║ ███╔╝  ██║╚██╔╝██║██╔══╝  ██╔══╝     ██║   "
echo "   ╚████╔╝ ╚██████╔╝███████╗██║ ╚═╝ ██║███████╗███████╗   ██║   "
echo "    ╚═══╝   ╚═════╝ ╚══════╝╚═╝     ╚═╝╚══════╝╚══════╝   ╚═╝   "
echo -e "${RESET}"
echo "  Transcriptor inteligente de reuniones — 100% local"
echo ""
echo "  Este instalador hará todo automáticamente:"
echo "   • Instalará Homebrew, Python y ffmpeg si no están"
echo "   • Descargará el código de VozMeet"
echo "   • Instalará todas las dependencias"
echo "   • Descargará los modelos de IA (~6 GB, solo una vez)"
echo "   • Construirá VozMeet.app"
echo ""
echo -e "  ${YELLOW}Tiempo estimado: 20-45 minutos (según tu conexión)${RESET}"
echo ""
pause

# ── Detectar iCloud ────────────────────────────────────────────────────────────
header "Verificando ubicación"

INSTALL_DIR="$HOME/VozMeet"

if echo "$HOME" | grep -qi "iCloud\|Mobile Documents\|com~apple~CloudDocs"; then
    error "Tu carpeta de inicio parece estar en iCloud."
    error "Contacta soporte. Saliendo."
    pause; exit 1
fi

success "Carpeta de instalación: $INSTALL_DIR"

# ── Arquitectura ───────────────────────────────────────────────────────────────
ARCH="$(uname -m)"
[ "$ARCH" = "arm64" ] && success "Apple Silicon detectado" || success "Intel detectado"

# ── Homebrew ───────────────────────────────────────────────────────────────────
header "Verificando Homebrew"

if ! command -v brew &>/dev/null; then
    info "Instalando Homebrew (necesita tu contraseña de Mac)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    [ "$ARCH" = "arm64" ] && eval "$(/opt/homebrew/bin/brew shellenv)"
    [ "$ARCH" = "x86_64" ] && eval "$(/usr/local/bin/brew shellenv)"
fi

# Asegurar que brew está en el PATH
[ -f /opt/homebrew/bin/brew ]  && eval "$(/opt/homebrew/bin/brew shellenv)"
[ -f /usr/local/bin/brew ]     && eval "$(/usr/local/bin/brew shellenv)"

success "Homebrew: $(brew --version | head -1)"

# ── Python ─────────────────────────────────────────────────────────────────────
header "Verificando Python 3.11+"

PYTHON_BIN=""
for py in python3.13 python3.12 python3.11; do
    if command -v "$py" &>/dev/null; then
        VER="$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        MAJ="${VER%%.*}"; MIN="${VER##*.}"
        if [ "$MAJ" -ge 3 ] && [ "$MIN" -ge 11 ]; then
            PYTHON_BIN="$(command -v "$py")"; break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ] && command -v python3 &>/dev/null; then
    VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    MAJ="${VER%%.*}"; MIN="${VER##*.}"
    [ "$MAJ" -ge 3 ] && [ "$MIN" -ge 11 ] && PYTHON_BIN="$(command -v python3)"
fi

if [ -z "$PYTHON_BIN" ]; then
    info "Instalando Python 3.11 via Homebrew..."
    brew install python@3.11
    PYTHON_BIN="$(brew --prefix python@3.11)/bin/python3.11"
fi

success "Python: $("$PYTHON_BIN" --version)"

# ── ffmpeg ─────────────────────────────────────────────────────────────────────
header "Verificando ffmpeg"

if ! command -v ffmpeg &>/dev/null; then
    info "Instalando ffmpeg..."
    brew install ffmpeg
fi
success "ffmpeg: $(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f1-3)"

# ── Descargar VozMeet ──────────────────────────────────────────────────────────
header "Descargando VozMeet"

if [ -d "$INSTALL_DIR/.git" ]; then
    info "Actualizando VozMeet existente..."
    git -C "$INSTALL_DIR" pull origin claude/vozmeet-macos-app-EOB7u
elif [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/install.sh" ]; then
    success "VozMeet ya está descargado en $INSTALL_DIR"
else
    if [ -d "$INSTALL_DIR" ]; then
        warn "La carpeta $INSTALL_DIR existe pero está incompleta. Eliminando..."
        rm -rf "$INSTALL_DIR"
    fi
    info "Descargando desde GitHub..."
    git clone -b claude/vozmeet-macos-app-EOB7u \
        https://github.com/LuisDepo/VozMeet.git \
        "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
success "Código en: $INSTALL_DIR"

# ── Entorno virtual ────────────────────────────────────────────────────────────
header "Creando entorno virtual Python"

if [ ! -d ".venv" ]; then
    info "Creando entorno virtual..."
    "$PYTHON_BIN" -m venv .venv
fi

VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"
VENV_PIP="$INSTALL_DIR/.venv/bin/pip"
success "Entorno virtual listo"

# ── Dependencias ───────────────────────────────────────────────────────────────
header "Instalando dependencias de Python"
info "Esto puede tardar varios minutos..."

"$VENV_PIP" install --upgrade pip --quiet
"$VENV_PIP" install -r requirements.txt
success "Dependencias instaladas"

# ── Verificar pywebview ────────────────────────────────────────────────────────
header "Verificando pywebview"

if ! "$VENV_PYTHON" -c "import webview" 2>/dev/null; then
    info "Instalando componentes adicionales de PyObjC..."
    "$VENV_PIP" install --upgrade \
        "pyobjc-core>=10.0" \
        "pyobjc-framework-Cocoa>=10.0" \
        "pyobjc-framework-WebKit>=10.0" \
        "pywebview>=5.0.0"
fi

WEBVIEW_VER="$("$VENV_PYTHON" -c "import importlib.metadata; print(importlib.metadata.version('pywebview'))" 2>/dev/null || echo 'instalado')"
success "pywebview $WEBVIEW_VER verificado"

# ── Token HuggingFace ──────────────────────────────────────────────────────────
header "Token de HuggingFace"

EXISTING_TOKEN=""
[ -f ".env" ] && EXISTING_TOKEN="$(grep '^HF_TOKEN=' .env 2>/dev/null | cut -d'=' -f2 | tr -d ' ')"

if [ -n "$EXISTING_TOKEN" ] && [ "$EXISTING_TOKEN" != "tu_token_aqui" ]; then
    success "Token ya configurado"
else
    echo ""
    echo "  Necesitas un token GRATUITO de HuggingFace para identificar voces."
    echo ""
    echo "  Pasos (5 minutos):"
    echo "  1. Crea cuenta en:  https://huggingface.co/join"
    echo "  2. Obtén token en:  https://huggingface.co/settings/tokens  (tipo: Read)"
    echo "  3. Acepta términos en estos dos enlaces (con tu cuenta iniciada):"
    echo "       https://huggingface.co/pyannote/speaker-diarization-3.1"
    echo "       https://huggingface.co/pyannote/segmentation-3.0"
    echo ""
    echo -n "  Pega tu token aquí (hf_...): "
    read -r HF_TOKEN_INPUT
    HF_TOKEN_INPUT="${HF_TOKEN_INPUT// /}"

    if [ -n "$HF_TOKEN_INPUT" ] && [ "$HF_TOKEN_INPUT" != "tu_token_aqui" ]; then
        echo "HF_TOKEN=$HF_TOKEN_INPUT" > .env
        success "Token guardado"
    else
        cp .env.example .env 2>/dev/null || echo "HF_TOKEN=tu_token_aqui" > .env
        warn "Token no configurado. Edita ~/VozMeet/.env antes de usar la app."
    fi
fi

# ── Descargar modelos ──────────────────────────────────────────────────────────
header "Descarga de modelos de IA"

echo ""
warn "Los modelos ocupan ~6 GB. Solo se descargan una vez."
echo -n "  ¿Descargar ahora? (recomendado) [S/n]: "
read -r DL_CHOICE

if [[ ! "$DL_CHOICE" =~ ^[nN]$ ]]; then
    HF_TOKEN_VAL="$(grep '^HF_TOKEN=' .env 2>/dev/null | cut -d'=' -f2 | tr -d ' ')"

    info "Descargando Whisper large-v3 (~3 GB)..."
    "$VENV_PYTHON" -c "
from faster_whisper import WhisperModel
print('  Iniciando descarga...')
m = WhisperModel('large-v3', device='cpu', compute_type='int8')
print('  Whisper large-v3 listo.')
" || warn "Error descargando Whisper. Se intentará al primer uso."

    if [ -n "$HF_TOKEN_VAL" ] && [ "$HF_TOKEN_VAL" != "tu_token_aqui" ]; then
        info "Descargando pyannote (~1 GB)..."
        "$VENV_PYTHON" -c "
import os
os.environ['HF_TOKEN'] = '${HF_TOKEN_VAL}'
from pyannote.audio import Pipeline
print('  Iniciando descarga...')
p = Pipeline.from_pretrained('pyannote/speaker-diarization-3.1', token='${HF_TOKEN_VAL}')
print('  pyannote listo.')
" || warn "Error con pyannote. Verifica el token y que aceptaste los términos."
    else
        warn "Sin token — omitiendo pyannote. Configura HF_TOKEN en ~/VozMeet/.env"
    fi

    info "Descargando SpeechBrain ECAPA-TDNN (~100 MB)..."
    "$VENV_PYTHON" -c "
import os
from speechbrain.pretrained import EncoderClassifier
m = EncoderClassifier.from_hparams(
    source='speechbrain/spkrec-ecapa-voxceleb',
    savedir=os.path.expanduser('~/.cache/speechbrain/ecapa-tdnn'),
    run_opts={'device':'cpu'}
)
print('  SpeechBrain listo.')
" || warn "Error descargando SpeechBrain. Se intentará al primer uso."

    success "Modelos descargados"
else
    info "Se descargarán al primer uso."
fi

# ── Base de datos ──────────────────────────────────────────────────────────────
header "Inicializando base de datos"

mkdir -p data/uploads data/processed data/transcripts data/voice_samples

"$VENV_PYTHON" -c "
import sys; sys.path.insert(0, '.')
from app.database.db import init_db
init_db()
print('Base de datos lista.')
"
success "SQLite inicializada en data/vozmeet.db"

# ── Construir VozMeet.app ──────────────────────────────────────────────────────
header "Construyendo VozMeet.app"

APP_DIR="$INSTALL_DIR/VozMeet.app"
CONTENTS="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES_DIR="$CONTENTS/Resources"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

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
</dict>
</plist>
PLIST

cat > "$MACOS_DIR/VozMeet" << LAUNCHER
#!${VENV_PYTHON}
import sys, os
os.chdir("${INSTALL_DIR}")
sys.path.insert(0, "${INSTALL_DIR}")

env_file = os.path.join("${INSTALL_DIR}", ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

from app.launcher import main
main()
LAUNCHER

chmod +x "$MACOS_DIR/VozMeet"
xattr -dr com.apple.quarantine "$APP_DIR" 2>/dev/null || true
success "VozMeet.app construido"

# ── Instalar en /Applications ──────────────────────────────────────────────────
header "Instalación en /Applications"

echo -n "  ¿Instalar VozMeet en /Applications? [S/n]: "
read -r INST_APPS
if [[ ! "$INST_APPS" =~ ^[nN]$ ]]; then
    rm -rf "/Applications/VozMeet.app"
    cp -r "$APP_DIR" /Applications/
    xattr -dr com.apple.quarantine "/Applications/VozMeet.app" 2>/dev/null || true
    success "Instalado en /Applications/VozMeet.app"
fi

# ── Fin ────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║   ✅  VozMeet instalado correctamente     ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${RESET}"
echo "  Para abrir VozMeet:"
echo "  • Doble click en VozMeet.app en la carpeta ~/VozMeet/"
echo "  • O desde Launchpad / /Applications si lo instalaste ahí"
echo ""
[ -f .env ] && grep -q "tu_token_aqui" .env && \
    echo -e "  ${YELLOW}⚠ Recuerda configurar tu HF_TOKEN en ~/VozMeet/.env${RESET}\n"

echo "  Presiona ENTER para cerrar este instalador."
read -r
