#!/usr/bin/env python3
"""
Build VozMeet-Installer.app — handles BOTH fresh install AND update.
No Terminal required. Output: /tmp/VozMeet-Installer.zip
"""
import base64, tarfile, io, os, stat, shutil, zipfile
from pathlib import Path

# ── 1. Build tar.gz of app files ──────────────────────────────────────────────
FILES = [
    "app/__init__.py",
    "app/api/__init__.py",
    "app/api/export.py",
    "app/api/logs.py",
    "app/api/process.py",
    "app/api/recordings.py",
    "app/api/speakers.py",
    "app/api/summary.py",
    "app/api/update.py",
    "app/api/upload.py",
    "app/config.py",
    "app/core/__init__.py",
    "app/core/audio_extractor.py",
    "app/core/diarizer.py",
    "app/core/embedder.py",
    "app/core/merger.py",
    "app/core/pipeline.py",
    "app/core/summarizer.py",
    "app/core/transcriber.py",
    "app/database/__init__.py",
    "app/database/db.py",
    "app/database/models.py",
    "app/database/voice_store.py",
    "app/launcher.py",
    "app/logger.py",
    "app/main.py",
    "app/version.py",
    "app/static/css/app.css",
    "app/static/css/apple.css",
    "app/static/icons/VozMeet.icns",
    "app/static/img/cat-logo.svg",
    "app/static/index.html",
    "app/static/js/api.js",
    "app/static/js/app.js",
    "app/static/js/identify.js",
    "app/static/js/process.js",
    "app/static/js/transcript.js",
    "app/static/js/upload.js",
    "requirements.txt",
    ".env.example",
]
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for f in FILES:
        if Path(f).exists():
            tar.add(f)
        else:
            print(f"WARNING: {f} not found, skipping")
TAR_B64 = base64.b64encode(buf.getvalue()).decode()
print(f"tar.gz: {len(buf.getvalue())} bytes  b64: {len(TAR_B64)} chars")

# ── 2. Python installer script ────────────────────────────────────────────────
INSTALLER_PY = r'''#!/usr/bin/python3
import base64, tarfile, io, os, stat, shutil, subprocess, sys, time
from pathlib import Path

# ── UI helpers ────────────────────────────────────────────────────────────────
def _dialog(msg, title="VozMeet Installer", buttons=None):
    buttons = buttons or ["OK"]
    btn_list = "{" + ", ".join(f'"{b}"' for b in buttons) + "}"
    r = subprocess.run(
        ["osascript", "-e",
         f'button returned of (display dialog "{_esc(msg)}" '
         f'buttons {btn_list} default button "{buttons[-1]}" '
         f'with title "{title}")'],
        capture_output=True, text=True)
    return r.stdout.strip()

def _ask(prompt, default="", title="VozMeet Installer"):
    r = subprocess.run(
        ["osascript", "-e",
         f'text returned of (display dialog "{_esc(prompt)}" '
         f'default answer "{_esc(default)}" '
         f'buttons {{"Continuar"}} default button "Continuar" '
         f'with title "{title}")'],
        capture_output=True, text=True)
    return r.stdout.strip()

def _notify(msg):
    subprocess.run(
        ["osascript", "-e",
         f'display notification "{_esc(msg)}" with title "VozMeet Installer"'],
        capture_output=True)

def _esc(s):
    return s.replace('\\', '\\\\').replace('"', '\\"')

def _extract(b64_data, dest):
    data = base64.b64decode(b64_data)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            tar.extractall(dest)

def _run(cmd, timeout=600, check=False):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

# ── Constants ─────────────────────────────────────────────────────────────────
INSTALL_DIR = Path.home() / "AppsBMS/VozMeet/VozMeet-claude-vozmeet-macos-app-EOB7u"
VENV_PY  = str(INSTALL_DIR / ".venv/bin/python")
VENV_PIP = str(INSTALL_DIR / ".venv/bin/pip")
B64 = "TAR_B64_PLACEHOLDER"

# ── Fresh install ─────────────────────────────────────────────────────────────
def _do_fresh_install():
    btn = _dialog(
        "Bienvenido al instalador de VozMeet v1.4\n\n"
        "Esto instalara VozMeet en:\n" + str(INSTALL_DIR) + "\n\n"
        "Necesitaras:\n"
        "- Conexion a internet (descarga ~3-5 GB de modelos de IA)\n"
        "- Un token gratuito de HuggingFace\n"
        "- 20-40 minutos la primera vez\n\n"
        "El proceso es automatico. Solo espera.",
        "VozMeet Installer",
        ["Cancelar", "Instalar"])
    if btn == "Cancelar":
        sys.exit(0)

    # ── Buscar Python 3.11+ ───────────────────────────────────────────────────
    _notify("Buscando Python 3.11+...")
    python_bin = _find_python()
    if not python_bin:
        _dialog(
            "No se encontro Python 3.11 o superior.\n\n"
            "Instala Python desde:\n"
            "https://www.python.org/downloads/macos/\n\n"
            "O instala Homebrew (brew.sh) y luego:\n"
            "  brew install python@3.11",
            "VozMeet Installer - Error")
        sys.exit(1)

    # ── Verificar ffmpeg ──────────────────────────────────────────────────────
    _notify("Verificando ffmpeg...")
    if not _check_ffmpeg():
        _dialog(
            "ffmpeg no esta instalado.\n\n"
            "VozMeet necesita ffmpeg para convertir audio.\n\n"
            "Instala Homebrew desde brew.sh y luego:\n"
            "  brew install ffmpeg\n\n"
            "Luego vuelve a ejecutar el instalador.",
            "VozMeet Installer - Error")
        sys.exit(1)

    # ── Crear directorio y extraer archivos ──────────────────────────────────
    _notify("Creando directorio de instalacion...")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(str(INSTALL_DIR))
    _notify("Extrayendo archivos de VozMeet...")
    _extract(B64, str(INSTALL_DIR))

    # ── Crear entorno virtual ─────────────────────────────────────────────────
    _notify("Creando entorno virtual Python...")
    r = _run([python_bin, "-m", "venv", str(INSTALL_DIR / ".venv")])
    if r.returncode != 0:
        raise RuntimeError("No se pudo crear el entorno virtual:\n" + r.stderr)

    # ── Instalar dependencias ─────────────────────────────────────────────────
    _notify("Actualizando pip...")
    _run([VENV_PIP, "install", "--upgrade", "pip", "--quiet"])

    _notify("Instalando dependencias (puede tardar 20-40 min)...")
    reqs = str(INSTALL_DIR / "requirements.txt")
    r = _run([VENV_PIP, "install", "-r", reqs, "--quiet"], timeout=3600)
    if r.returncode != 0:
        raise RuntimeError("Error instalando dependencias:\n" + r.stderr[-1000:])

    # ── Token HuggingFace ─────────────────────────────────────────────────────
    _notify("Configurando HuggingFace...")
    token = _ask(
        "Ingresa tu token de HuggingFace (gratuito).\n\n"
        "Si no tienes uno:\n"
        "1. Crea cuenta en huggingface.co\n"
        "2. Ve a huggingface.co/settings/tokens\n"
        "3. Crea un token tipo 'Read'\n"
        "4. Acepta los terminos de pyannote/speaker-diarization-3.1\n\n"
        "Puedes dejarlo en blanco y configurarlo despues en:\n"
        + str(INSTALL_DIR / ".env"),
        default="",
        title="VozMeet - Token HuggingFace")
    env_path = INSTALL_DIR / ".env"
    if token and token != "tu_token_aqui":
        env_path.write_text(f"HF_TOKEN={token}\n")
    else:
        shutil.copy2(str(INSTALL_DIR / ".env.example"), str(env_path))

    # ── Inicializar base de datos ─────────────────────────────────────────────
    _notify("Inicializando base de datos...")
    for d in ["data/uploads", "data/processed", "data/transcripts", "data/voice_samples"]:
        (INSTALL_DIR / d).mkdir(parents=True, exist_ok=True)
    _run([VENV_PY, "-c",
          "import sys; sys.path.insert(0,'.'); from app.database.db import init_db; init_db()"],
         timeout=30)

    # ── Construir y copiar .app ───────────────────────────────────────────────
    _notify("Construyendo VozMeet.app...")
    _build_app()

    _dialog(
        "VozMeet v1.4 instalado correctamente.\n\n"
        + ("" if token else
           "PENDIENTE: Configura tu token HuggingFace\nen el archivo .env antes de usar.\n\n") +
        "Abre VozMeet desde la carpeta Aplicaciones.",
        "Instalacion completada")

# ── Update ────────────────────────────────────────────────────────────────────
def _do_update():
    _notify("Actualizando VozMeet a v1.4...")

    # Kill puerto 8765
    try:
        r = _run(["lsof", "-ti", "tcp:8765"])
        if r.returncode == 0 and r.stdout.strip():
            for pid in r.stdout.strip().split("\n"):
                if pid.strip():
                    _run(["kill", "-9", pid.strip()])
            time.sleep(0.8)
    except Exception:
        pass

    os.chdir(str(INSTALL_DIR))
    _extract(B64, str(INSTALL_DIR))

    _notify("Instalando dependencias nuevas...")
    for dep in ["python-docx>=1.1.0", "mlx-whisper>=0.4.0", "mlx-lm>=0.20.0"]:
        try:
            _run([VENV_PIP, "install", "--quiet", "--upgrade", dep], timeout=300)
        except Exception:
            pass

    _notify("Actualizando VozMeet.app...")
    _build_app()

    _dialog(
        "VozMeet v1.4 actualizado correctamente.\n\n"
        "Novedades:\n"
        "- Modelo medium + mlx-whisper (mas rapido en M1/M2/M3)\n"
        "- Exportar a Word (.docx)\n"
        "- Dialogo para elegir donde guardar\n"
        "- Resumen de reunion con IA local\n\n"
        "Abre VozMeet desde la carpeta Aplicaciones.",
        "Actualizacion completada")

# ── Shared: build VozMeet.app ─────────────────────────────────────────────────
def _build_app():
    APP = INSTALL_DIR / "VozMeet.app"
    (APP / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
    (APP / "Contents/Resources").mkdir(parents=True, exist_ok=True)

    launcher = APP / "Contents/MacOS/VozMeet"
    launcher.write_text(
        "#!" + VENV_PY + "\n"
        "import sys, os\n"
        "os.chdir(r'" + str(INSTALL_DIR) + "')\n"
        "sys.path.insert(0, r'" + str(INSTALL_DIR) + "')\n"
        "from app.launcher import main\n"
        "main()\n"
    )
    launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    (APP / "Contents/Info.plist").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
        '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '  <key>CFBundleName</key>          <string>VozMeet</string>\n'
        '  <key>CFBundleDisplayName</key>   <string>VozMeet</string>\n'
        '  <key>CFBundleIdentifier</key>    <string>com.bms.vozmeet</string>\n'
        '  <key>CFBundleVersion</key>       <string>1.4</string>\n'
        '  <key>CFBundleExecutable</key>    <string>VozMeet</string>\n'
        '  <key>CFBundleIconFile</key>      <string>VozMeet</string>\n'
        '  <key>NSHighResolutionCapable</key><true/>\n'
        '  <key>LSUIElement</key>           <false/>\n'
        '</dict></plist>\n'
    )

    icon_src = INSTALL_DIR / "app/static/icons/VozMeet.icns"
    if icon_src.exists():
        shutil.copy2(str(icon_src), str(APP / "Contents/Resources/VozMeet.icns"))

    dest = Path("/Applications/VozMeet.app")
    if dest.exists():
        shutil.rmtree(str(dest))
    shutil.copytree(str(APP), str(dest))

    lsreg = ("/System/Library/Frameworks/CoreServices.framework"
             "/Frameworks/LaunchServices.framework/Support/lsregister")
    if os.path.exists(lsreg):
        subprocess.run([lsreg, "-f", str(dest)], capture_output=True)
    subprocess.run(["killall", "Dock"], capture_output=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _find_python():
    candidates = [
        "/opt/homebrew/bin/python3.13",
        "/opt/homebrew/bin/python3.12",
        "/opt/homebrew/bin/python3.11",
        "/usr/local/bin/python3.13",
        "/usr/local/bin/python3.12",
        "/usr/local/bin/python3.11",
    ]
    for p in candidates:
        if Path(p).exists():
            r = subprocess.run([p, "--version"], capture_output=True, text=True)
            if r.returncode == 0:
                return p
    # Check system python3
    for py in ["python3.11", "python3.12", "python3.13", "python3"]:
        r = subprocess.run(["which", py], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            path = r.stdout.strip()
            ver = subprocess.run([path, "-c",
                "import sys; print(sys.version_info.minor)"],
                capture_output=True, text=True).stdout.strip()
            try:
                if int(ver) >= 11:
                    return path
            except ValueError:
                pass
    return None

def _check_ffmpeg():
    r = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
    return r.returncode == 0

# ── Entry point (after all defs) ──────────────────────────────────────────────
try:
    fresh = not INSTALL_DIR.exists() or not Path(VENV_PY).exists()
    if fresh:
        _do_fresh_install()
    else:
        _do_update()
except Exception as e:
    _dialog(
        "Error durante la instalacion:\n\n" + str(e) +
        "\n\nCaptura este mensaje y reportalo.",
        "VozMeet Installer - Error")
    sys.exit(1)
'''

installer_py = INSTALLER_PY.replace("TAR_B64_PLACEHOLDER", TAR_B64)

# ── Syntax check ──────────────────────────────────────────────────────────────
import tempfile, subprocess as sp
with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tf:
    tf.write(installer_py)
    tmp = tf.name
result = sp.run(["python3", "-m", "py_compile", tmp], capture_output=True, text=True)
if result.returncode != 0:
    print("SYNTAX ERROR:", result.stderr)
    raise SystemExit(1)
print("Syntax check: OK")
os.unlink(tmp)

# ── Build .app directory ──────────────────────────────────────────────────────
app_root = Path("/tmp/VozMeet-Installer.app")
if app_root.exists():
    shutil.rmtree(str(app_root))
macos = app_root / "Contents/MacOS"
macos.mkdir(parents=True)
resources = app_root / "Contents/Resources"
resources.mkdir(parents=True)

icon_src = Path("app/static/icons/VozMeet.icns")
if not icon_src.exists():
    raise SystemExit("Icon missing — run: python3 build_icon.py")
shutil.copy2(str(icon_src), str(resources / "VozMeet.icns"))

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
    '  <key>CFBundleVersion</key>       <string>1.4</string>\n'
    '  <key>CFBundleExecutable</key>    <string>VozMeet-Installer</string>\n'
    '  <key>CFBundleIconFile</key>      <string>VozMeet</string>\n'
    '  <key>CFBundleIconName</key>      <string>VozMeet</string>\n'
    '  <key>NSHighResolutionCapable</key><true/>\n'
    '  <key>LSUIElement</key>           <true/>\n'
    '</dict></plist>\n'
)

# ── Verify ────────────────────────────────────────────────────────────────────
content = exe.read_text()
assert content.startswith("#!/usr/bin/python3"), "bad shebang"
assert "TAR_B64_PLACEHOLDER" not in content, "placeholder not replaced"
assert "filter=" in content and "TypeError" in content, "no py<3.12 fallback"
assert "except Exception as e:" in content, "no error handler"
assert "_do_fresh_install" in content, "missing fresh install"
assert "_do_update" in content, "missing update path"
assert "mlx-whisper" in content, "missing mlx-whisper"
assert "python-docx" in content, "missing python-docx"
assert "1.4" in content, "version not updated"
print("Content checks: OK")

# ── Zip ───────────────────────────────────────────────────────────────────────
zip_path = Path("/tmp/VozMeet-Installer.zip")
with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
    for path in app_root.rglob("*"):
        arcname = str(path.relative_to(app_root.parent))
        zf.write(str(path), arcname)
        if path.is_file():
            zf.getinfo(arcname).external_attr = (path.stat().st_mode & 0xFFFF) << 16

print(f"ZIP: {zip_path}  ({zip_path.stat().st_size:,} bytes)")
print("DONE — ready to upload")
