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
import base64, tarfile, io, os, stat, shutil, subprocess, sys, time, platform
import urllib.request, threading, queue as _queue
from pathlib import Path

# ── Progress log (shared between threads) ────────────────────────────────────
_log_queue = _queue.Queue()
_install_error = [None]

def _log(msg):
    """Queue a progress message for the progress window."""
    _log_queue.put(("log", msg))

# ── UI helpers ────────────────────────────────────────────────────────────────
def _dialog(msg, title="VozMeet Installer", buttons=None):
    buttons = buttons or ["OK"]
    btn_list = "{" + ", ".join('"' + b + '"' for b in buttons) + "}"
    r = subprocess.run(
        ["osascript", "-e",
         'button returned of (display dialog "' + _esc(msg) + '" '
         'buttons ' + btn_list + ' default button "' + buttons[-1] + '" '
         'with title "' + title + '")'],
        capture_output=True, text=True)
    return r.stdout.strip()

def _ask(prompt, default="", title="VozMeet Installer"):
    r = subprocess.run(
        ["osascript", "-e",
         'text returned of (display dialog "' + _esc(prompt) + '" '
         'default answer "' + _esc(default) + '" '
         'buttons {"Continuar"} default button "Continuar" '
         'with title "' + title + '")'],
        capture_output=True, text=True)
    return r.stdout.strip()

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
        "El instalador descargara e instalara TODO lo necesario\n"
        "automaticamente (Python, ffmpeg, modelos de IA).\n\n"
        "Necesitaras:\n"
        "- Conexion a internet (descarga varios GB)\n"
        "- Un token gratuito de HuggingFace\n"
        "- 20-40 minutos la primera vez\n\n"
        "Es posible que te pida tu contrasena de Mac\n"
        "para instalar Python. Eso es normal.",
        "VozMeet Installer",
        ["Cancelar", "Instalar"])
    if btn == "Cancelar":
        sys.exit(0)

    _log("Buscando Python 3.11+...")
    python_bin = _find_python()
    if not python_bin:
        b = _dialog(
            "No se encontro Python 3.11 o superior.\n\n"
            "VozMeet puede instalarlo automaticamente desde\n"
            "el sitio oficial python.org (~45 MB).\n\n"
            "Te pedira tu contrasena de Mac para instalarlo.",
            "VozMeet - Instalar Python",
            ["Cancelar", "Instalar Python"])
        if b == "Cancelar":
            sys.exit(0)
        python_bin = _install_python()

    _log("Creando directorio de instalacion...")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(str(INSTALL_DIR))
    _log("Extrayendo archivos de VozMeet...")
    _extract(B64, str(INSTALL_DIR))

    _log("Verificando ffmpeg...")
    if not _find_ffmpeg_path():
        _log("Descargando ffmpeg (~45 MB)...")
        _install_ffmpeg(INSTALL_DIR)
        _log("ffmpeg instalado.")

    _log("Creando entorno virtual Python...")
    r = _run([python_bin, "-m", "venv", str(INSTALL_DIR / ".venv")])
    if r.returncode != 0:
        raise RuntimeError("No se pudo crear el entorno virtual:\n" + r.stderr)

    _log("Actualizando pip...")
    _run([VENV_PIP, "install", "--upgrade", "pip", "--quiet"])

    _log("Instalando dependencias (puede tardar 20-40 min)...")
    reqs_path = INSTALL_DIR / "requirements.txt"
    all_lines = [l for l in reqs_path.read_text().splitlines() if l.strip()]
    core_lines = [l for l in all_lines if "mlx" not in l.lower()]
    mlx_lines  = [l for l in all_lines if "mlx" in l.lower()]

    core_req = INSTALL_DIR / "_req_core.txt"
    core_req.write_text("\n".join(core_lines) + "\n")
    r = _run([VENV_PIP, "install", "-r", str(core_req), "--quiet"], timeout=3600)
    core_req.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError("Error instalando dependencias:\n" + r.stderr[-1000:])
    _log("Dependencias instaladas.")

    if platform.machine() == "arm64":
        _log("Instalando aceleracion Apple Silicon (mlx)...")
        for dep in mlx_lines:
            try:
                _log("  -> " + dep)
                _run([VENV_PIP, "install", "--quiet", dep], timeout=600)
            except Exception:
                pass
        _log("Aceleracion mlx lista.")

    _log("Configurando HuggingFace...")
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
        env_path.write_text("HF_TOKEN=" + token + "\n")
    else:
        shutil.copy2(str(INSTALL_DIR / ".env.example"), str(env_path))
    _log("Configuracion guardada.")

    _log("Inicializando base de datos...")
    for d in ["data/uploads", "data/processed", "data/transcripts", "data/voice_samples"]:
        (INSTALL_DIR / d).mkdir(parents=True, exist_ok=True)
    _run([VENV_PY, "-c",
          "import sys; sys.path.insert(0,'.'); from app.database.db import init_db; init_db()"],
         timeout=30)

    _log("Construyendo VozMeet.app...")
    _build_app()
    _log("VozMeet.app copiado a /Applications.")

    _dialog(
        "VozMeet v1.4 instalado correctamente.\n\n"
        + ("" if token else
           "PENDIENTE: Configura tu token HuggingFace\nen el archivo .env antes de usar.\n\n") +
        "Abre VozMeet desde la carpeta Aplicaciones.",
        "Instalacion completada")

# ── Update ────────────────────────────────────────────────────────────────────
def _do_update():
    _log("Actualizando VozMeet a v1.4...")

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
    _log("Extrayendo archivos actualizados...")
    _extract(B64, str(INSTALL_DIR))

    if not _find_ffmpeg_path():
        _log("Descargando ffmpeg...")
        try:
            _install_ffmpeg(INSTALL_DIR)
        except Exception:
            pass

    _log("Instalando dependencias nuevas...")
    deps = ["python-docx>=1.1.0"]
    if platform.machine() == "arm64":
        deps += ["mlx-whisper>=0.4.0", "mlx-lm>=0.20.0"]
    for dep in deps:
        try:
            _log("  -> " + dep)
            _run([VENV_PIP, "install", "--quiet", "--upgrade", dep], timeout=600)
        except Exception:
            pass

    _log("Actualizando VozMeet.app...")
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

def _find_ffmpeg_path():
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = [
        str(INSTALL_DIR / "bin" / "ffmpeg"),
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]
    for c in candidates:
        if Path(c).exists() and os.access(c, os.X_OK):
            return c
    return None

def _install_python():
    url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-macos11.pkg"
    pkg = "/tmp/vozmeet_python-3.11.9.pkg"
    _log("Descargando Python 3.11.9 (~45 MB)...")
    urllib.request.urlretrieve(url, pkg)

    shell_cmd = "/usr/sbin/installer -pkg '" + pkg + "' -target /"
    osa = 'do shell script "' + shell_cmd.replace('"', '\\"') + \
          '" with administrator privileges'
    _log("Instalando Python (solicita contrasena de Mac)...")
    r = subprocess.run(["osascript", "-e", osa], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            "No se pudo instalar Python.\n" +
            (r.stderr.strip() or "Instalacion cancelada o sin permisos."))

    try:
        os.remove(pkg)
    except Exception:
        pass

    py = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"
    if not Path(py).exists():
        py = _find_python()
    if not py or not Path(py).exists():
        raise RuntimeError("Python se instalo pero no se encontro el ejecutable.")
    _log("Python 3.11 instalado.")
    return py

def _install_ffmpeg(install_dir):
    machine = platform.machine()
    arch = "arm64" if machine == "arm64" else "x64"
    url = ("https://github.com/eugeneware/ffmpeg-static/releases/"
           "download/b6.0/ffmpeg-darwin-" + arch)
    bin_dir = Path(install_dir) / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "ffmpeg"

    urllib.request.urlretrieve(url, str(target))
    target.chmod(0o755)
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(target)],
                   capture_output=True)

    r = subprocess.run([str(target), "-version"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            "ffmpeg se descargo pero no se pudo ejecutar:\n" +
            (r.stderr or r.stdout)[:400] +
            "\n\nInstala ffmpeg manualmente con: brew install ffmpeg")
    return str(target)

# ── Background installer thread ───────────────────────────────────────────────
def _run_installer_bg():
    """All installation logic runs here so the progress window stays responsive."""
    try:
        fresh = not INSTALL_DIR.exists() or not Path(VENV_PY).exists()
        if fresh:
            _do_fresh_install()
        else:
            _do_update()
        _log_queue.put(("done", None))
    except SystemExit:
        _log_queue.put(("cancelled", None))
    except Exception as e:
        import traceback
        _install_error[0] = traceback.format_exc()
        _log_queue.put(("error", str(e)))

# ── Persistent progress window (main thread) ──────────────────────────────────
def _show_progress_window():
    """Show a tkinter progress window and run the installer in a background thread."""
    try:
        import tkinter as tk
        from tkinter.scrolledtext import ScrolledText
        _has_tk = True
    except ImportError:
        _has_tk = False

    if not _has_tk:
        # Fallback: no window, run directly
        _run_installer_bg()
        if _install_error[0]:
            _dialog("Error durante la instalacion:\n\n" +
                    (_install_error[0] or "")[:400] +
                    "\n\nCaptura este mensaje y reportalo.",
                    "VozMeet Installer - Error")
        return

    root = tk.Tk()
    root.title("VozMeet Installer")
    root.geometry("560x420")
    root.resizable(False, True)
    root.configure(bg="#1a1a1a")
    root.protocol("WM_DELETE_WINDOW", lambda: None)  # locked until done

    tk.Label(root,
             text="VozMeet Installer",
             font=("Helvetica Neue", 16, "bold"),
             fg="#ffffff", bg="#1a1a1a").pack(pady=(16, 2))

    status_var = tk.StringVar(value="Iniciando...")
    tk.Label(root,
             textvariable=status_var,
             font=("Helvetica Neue", 11),
             fg="#888888", bg="#1a1a1a").pack(pady=(0, 10))

    txt = ScrolledText(root,
                       wrap=tk.WORD,
                       font=("Menlo", 10),
                       bg="#2b2b2b", fg="#d4d4d4",
                       state=tk.DISABLED,
                       relief=tk.FLAT,
                       padx=8, pady=6)
    txt.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

    _state = {"done": False}

    def poll():
        while True:
            try:
                kind, msg = _log_queue.get_nowait()
                txt.configure(state=tk.NORMAL)
                if kind == "log":
                    txt.insert(tk.END, " -> " + msg + "\n")
                    status_var.set(msg[:70])
                elif kind == "done":
                    txt.insert(tk.END, "\n [OK] Instalacion completada exitosamente.\n")
                    status_var.set("Completado — puedes cerrar esta ventana")
                    root.protocol("WM_DELETE_WINDOW", root.destroy)
                    _state["done"] = True
                elif kind == "cancelled":
                    _state["done"] = True
                elif kind == "error":
                    txt.insert(tk.END, "\n [ERROR] " + (msg or "") + "\n")
                    status_var.set("Error durante la instalacion")
                    root.protocol("WM_DELETE_WINDOW", root.destroy)
                    _state["done"] = True
                txt.configure(state=tk.DISABLED)
                txt.see(tk.END)
            except Exception:
                break
        if not _state["done"]:
            root.after(200, poll)
        else:
            root.after(3000, root.destroy)

    root.after(300, poll)

    t = threading.Thread(target=_run_installer_bg, daemon=True)
    t.start()

    root.mainloop()

    if _install_error[0]:
        _dialog("Error durante la instalacion:\n\n" +
                (_install_error[0] or "")[:400] +
                "\n\nCaptura este mensaje y reportalo.",
                "VozMeet Installer - Error")

# ── Entry point ───────────────────────────────────────────────────────────────
_show_progress_window()
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
assert "_do_fresh_install" in content, "missing fresh install"
assert "_do_update" in content, "missing update path"
assert "_install_python" in content, "missing python auto-install"
assert "_install_ffmpeg" in content, "missing ffmpeg auto-install"
assert "ffmpeg-static" in content, "missing ffmpeg download url"
assert "administrator privileges" in content, "missing admin install"
assert "mlx-whisper" in content, "missing mlx-whisper"
assert "python-docx" in content, "missing python-docx"
assert "1.4" in content, "version not updated"
assert "_show_progress_window" in content, "missing progress window"
assert "tkinter" in content, "missing tkinter"
assert "_run_installer_bg" in content, "missing background thread"
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
