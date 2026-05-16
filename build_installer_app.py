#!/usr/bin/env python3
"""
Build VozMeet-Installer.app — real macOS .app installer. No Terminal required.
Fixes: no filter='data' (Python<3.12), full try/except with error dialog.
Output: /tmp/VozMeet-Installer.zip
"""
import base64, tarfile, io, os, stat, shutil, zipfile
from pathlib import Path

# ── 1. Build tar.gz of app files ──────────────────────────────────────────────
FILES = [
    "app/api/export.py",
    "app/api/recordings.py",
    "app/api/summary.py",
    "app/api/update.py",
    "app/core/pipeline.py",
    "app/core/summarizer.py",
    "app/core/transcriber.py",
    "app/launcher.py",
    "app/main.py",
    "app/version.py",
    "app/static/css/app.css",
    "app/static/css/apple.css",
    "app/static/img/cat-logo.svg",
    "app/static/index.html",
    "app/static/js/api.js",
    "app/static/js/app.js",
    "app/static/js/identify.js",
    "app/static/js/process.js",
    "app/static/js/transcript.js",
    "app/static/js/upload.js",
    "requirements.txt",
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

def _dialog(msg, title="VozMeet Installer"):
    subprocess.run(
        ["osascript", "-e",
         'display dialog "' + msg.replace('"', '\\"') +
         '" buttons {"OK"} default button "OK" with title "' + title + '"'],
        capture_output=True)

def _notify(msg):
    subprocess.run(
        ["osascript", "-e",
         'display notification "' + msg + '" with title "VozMeet Installer"'],
        capture_output=True)

def _extract(b64_data, dest):
    data = base64.b64decode(b64_data)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        # filter='data' only exists in Python 3.12+; fall back silently
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            tar.extractall(dest)

INSTALL_DIR = Path.home() / "AppsBMS/VozMeet/VozMeet-claude-vozmeet-macos-app-EOB7u"
VENV_PY = str(INSTALL_DIR / ".venv/bin/python")
VENV_PIP = str(INSTALL_DIR / ".venv/bin/pip")

try:
    # ── Pre-flight ────────────────────────────────────────────────────────────
    if not INSTALL_DIR.exists():
        _dialog(
            "No se encontro el directorio de instalacion:\n" + str(INSTALL_DIR) +
            "\n\nEjecuta primero el instalador original de VozMeet.",
            "VozMeet Installer - Error")
        sys.exit(1)

    if not Path(VENV_PY).exists():
        _dialog(
            "No se encontro el entorno Python (.venv):\n" + VENV_PY,
            "VozMeet Installer - Error")
        sys.exit(1)

    _notify("Instalando VozMeet v1.4...")
    os.chdir(str(INSTALL_DIR))

    # ── Kill port 8765 ────────────────────────────────────────────────────────
    try:
        r = subprocess.run(["lsof", "-ti", "tcp:8765"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            for pid in r.stdout.strip().split("\n"):
                if pid.strip():
                    subprocess.run(["kill", "-9", pid.strip()],
                                   capture_output=True)
            time.sleep(0.8)
    except Exception:
        pass

    # ── Extract app files ─────────────────────────────────────────────────────
    B64 = "TAR_B64_PLACEHOLDER"
    _extract(B64, str(INSTALL_DIR))

    # ── Install new Python dependencies ──────────────────────────────────────
    _notify("Instalando dependencias nuevas...")
    new_deps = ["python-docx>=1.1.0", "mlx-whisper>=0.4.0", "mlx-lm>=0.20.0"]
    for dep in new_deps:
        try:
            subprocess.run(
                [VENV_PIP, "install", "--quiet", "--upgrade", dep],
                capture_output=True, timeout=300
            )
        except Exception:
            pass  # non-fatal — mlx packages only work on Apple Silicon

    # ── Build .app bundle ─────────────────────────────────────────────────────
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

    # ── Copy to /Applications ─────────────────────────────────────────────────
    dest = Path("/Applications/VozMeet.app")
    if dest.exists():
        shutil.rmtree(str(dest))
    shutil.copytree(str(APP), str(dest))

    # ── Register & refresh Dock ───────────────────────────────────────────────
    lsreg = (
        "/System/Library/Frameworks/CoreServices.framework"
        "/Frameworks/LaunchServices.framework/Support/lsregister"
    )
    if os.path.exists(lsreg):
        subprocess.run([lsreg, "-f", str(dest)], capture_output=True)
    subprocess.run(["killall", "Dock"], capture_output=True)

    _dialog(
        "VozMeet v1.4 instalado correctamente.\n\n"
        "Novedades:\n"
        "- Modelo medium + mlx-whisper (mas rapido en M1/M2/M3)\n"
        "- Exportar a Word (.docx) ademas de TXT/MD/JSON\n"
        "- Dialogo para elegir donde guardar\n"
        "- Resumen de reunion con IA local (boton Resumen)\n"
        "- Logo actualizado\n\n"
        "Abre VozMeet desde la carpeta Aplicaciones.",
        "Instalacion completada")

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
    '  <key>NSHighResolutionCapable</key><true/>\n'
    '  <key>LSUIElement</key>           <true/>\n'
    '</dict></plist>\n'
)

# ── Verify key attributes ─────────────────────────────────────────────────────
content = exe.read_text()
assert content.startswith("#!/usr/bin/python3"), "bad shebang"
assert "TAR_B64_PLACEHOLDER" not in content, "placeholder not replaced"
assert "filter=" in content and "TypeError" in content, "no py<3.12 fallback"
assert "except Exception as e:" in content, "no error handler"
assert "mlx-whisper" in content, "missing mlx-whisper dep install"
assert "python-docx" in content, "missing python-docx dep install"
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
