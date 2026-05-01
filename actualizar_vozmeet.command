#!/bin/bash
# VozMeet — script de actualización
# Double-click este archivo para actualizar VozMeet desde GitHub.

set -e
cd "$(dirname "$0")"

REPO_ZIP="https://github.com/luisdepo/vozmeet/archive/refs/heads/main.zip"
TMP_DIR=$(mktemp -d)

echo "========================================"
echo "  Actualizando VozMeet..."
echo "========================================"
echo ""

# Download latest zip from GitHub
echo "→ Descargando última versión..."
curl -L --fail --silent --show-error "$REPO_ZIP" -o "$TMP_DIR/vozmeet.zip"

echo "→ Descomprimiendo..."
unzip -q "$TMP_DIR/vozmeet.zip" -d "$TMP_DIR"

SRC="$TMP_DIR/vozmeet-main"

echo "→ Instalando archivos..."
# Sync app source — preserve data/ and .env
rsync -a --exclude='data/' --exclude='.env' --exclude='__pycache__' \
    "$SRC/app/" app/

# Sync other top-level files if they exist in the repo
for f in requirements.txt; do
    [ -f "$SRC/$f" ] && cp "$SRC/$f" .
done

# Install/update Python dependencies
echo "→ Actualizando dependencias Python..."
VENV_DIR="$HOME/Library/Application Support/VozMeet/venv"
if [ -d "$VENV_DIR" ]; then
    "$VENV_DIR/bin/pip" install -q --upgrade -r requirements.txt
else
    echo "⚠️  Entorno virtual no encontrado en $VENV_DIR"
    echo "   Si estás en modo desarrollo, activa tu venv manualmente."
fi

# Clean up
rm -rf "$TMP_DIR"

echo ""
echo "✅ VozMeet actualizado correctamente."
echo "   Reinicia la app para aplicar los cambios."
echo ""
read -p "Presiona Enter para cerrar esta ventana..."
