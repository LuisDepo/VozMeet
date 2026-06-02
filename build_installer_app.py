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
    "app/core/heavy_worker.py",
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
        "Bienvenido al instalador de VozMeet v1.5\n\n"
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

    _create_venv_and_install(python_bin)

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
        "VozMeet v1.5 instalado correctamente.\n\n"
        + ("" if token else
           "PENDIENTE: Configura tu token HuggingFace\nen el archivo .env antes de usar.\n\n") +
        "Abre VozMeet desde la carpeta Aplicaciones.",
        "Instalacion completada")

# ── Update ────────────────────────────────────────────────────────────────────
def _do_update():
    _log("Actualizando VozMeet a v1.5...")

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

    # ── Reparacion: entorno Intel (x86_64) en un Mac Apple Silicon ───────────
    # Un .venv creado con un Python Intel (o cuyos paquetes son wheels x86_64
    # instalados bajo Rosetta) no carga las extensiones C en arm64: numpy/torch
    # fallan con 'incompatible architecture' y el procesamiento se cae (rc=-11).
    # Detectamos esto de dos formas — el python del venv no es arm64, O los
    # paquetes nativos no se pueden importar — y reconstruimos el entorno con un
    # Python nativo arm64. Los datos (data/, .env) NO se tocan.
    #
    # Usamos _host_is_apple_silicon() (sysctl hw.optional.arm64) en vez de
    # platform.machine(), porque si el instalador corre bajo Rosetta este ultimo
    # mentiria devolviendo 'x86_64' y la reparacion nunca se dispararia.
    venv_arm64 = _venv_is_arm64()
    venv_ok = _venv_imports_ok()
    if _host_is_apple_silicon() and (not venv_arm64 or not venv_ok):
        reason = ("Python Intel (Rosetta)" if not venv_arm64
                  else "paquetes compilados para Intel (x86_64)")
        _log("Detectado entorno incompatible: " + reason + ". Reconstruyendo arm64...")
        b = _dialog(
            "VozMeet detecto que la instalacion actual usa componentes para\n"
            "Intel (x86_64) que no funcionan en tu Mac con Apple Silicon.\n"
            "Por eso el procesamiento de archivos se cae.\n\n"
            "El instalador reconstruira el entorno con la version nativa\n"
            "(Apple Silicon, arm64). Tus voces y grabaciones NO se borraran.\n\n"
            "Puede tardar 20-40 minutos y pedir tu contrasena de Mac.",
            "VozMeet - Reparar instalacion",
            ["Cancelar", "Reparar"])
        if b == "Cancelar":
            sys.exit(0)

        python_bin = _find_python()
        if not python_bin:
            python_bin = _install_python()

        venv_dir = INSTALL_DIR / ".venv"
        if venv_dir.exists():
            _log("Eliminando entorno Intel anterior...")
            shutil.rmtree(str(venv_dir))

        if not _find_ffmpeg_path():
            _log("Descargando ffmpeg...")
            try:
                _install_ffmpeg(INSTALL_DIR)
            except Exception:
                pass

        _create_venv_and_install(python_bin)

        _log("Construyendo VozMeet.app (Apple Silicon)...")
        _build_app()

        _dialog(
            "VozMeet se reparo y ahora usa Python nativo Apple Silicon.\n\n"
            "Tus voces y grabaciones se conservaron.\n\n"
            "Abre VozMeet desde la carpeta Aplicaciones.",
            "Reparacion completada")
        return

    if not _find_ffmpeg_path():
        _log("Descargando ffmpeg...")
        try:
            _install_ffmpeg(INSTALL_DIR)
        except Exception:
            pass

    _log("Instalando dependencias nuevas...")
    # Pin numpy<2 FIRST — torch's C API is incompatible with numpy 2.x and
    # SIGSEGVs on import (rc=-11) even on CPU.  An existing install may already
    # have numpy 2.x, and the mlx --upgrade below can pull it back in, so force
    # the downgrade here and verify it actually took.
    _log("Fijando numpy<2 (requerido por torch)...")
    _run([VENV_PIP, "install", "--quiet", "numpy>=1.24.0,<2.0.0"], timeout=300)

    deps = ["python-docx>=1.1.0"]
    if _host_is_apple_silicon():
        deps += ["mlx-whisper>=0.4.0", "mlx-lm>=0.20.0"]
    for dep in deps:
        try:
            _log("  -> " + dep)
            _run([VENV_PIP, "install", "--quiet", "--upgrade", dep], timeout=600)
        except Exception:
            pass

    # mlx/--upgrade may have dragged numpy 2.x back in. Re-pin and confirm the
    # installed numpy is <2 so torch can import.
    _log("Verificando numpy<2...")
    _run([VENV_PIP, "install", "--quiet", "numpy>=1.24.0,<2.0.0"], timeout=300)
    nv = _run([VENV_PY, "-c", "import numpy,sys;sys.exit(0 if numpy.__version__[0]=='1' else 1)"])
    if nv.returncode != 0:
        _log("numpy 2.x persiste — forzando reinstalacion limpia de numpy<2...")
        _run([VENV_PIP, "install", "--quiet", "--force-reinstall",
              "numpy>=1.24.0,<2.0.0"], timeout=300)

    # Re-test Metal compatibility every update — mlx may have been fixed upstream
    _test_and_configure_mlx()

    _log("Actualizando VozMeet.app...")
    _build_app()

    _dialog(
        "VozMeet v1.5 actualizado correctamente.\n\n"
        "Novedades:\n"
        "- Procesamiento aislado: la app ya no se cierra durante el analisis\n"
        "- Aceleracion automatica segun tu Mac (M1/M2/M3/M4/Intel)\n"
        "- Correccion del error 'ffmpeg' al transcribir con mlx\n"
        "- Transcripcion mas rapida (sin re-decodificar el audio)\n\n"
        "Abre VozMeet desde la carpeta Aplicaciones.",
        "Actualizacion completada")

# ── Shared: create venv + install all dependencies ───────────────────────────
def _create_venv_and_install(python_bin):
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

    # Pin numpy<2 first — torch's C API is incompatible with numpy 2.x and
    # will SIGSEGV on import even on CPU.  Install it alone so pip can't
    # back-solve a 2.x version to satisfy another package's loose bound.
    _log("Fijando numpy<2 (requerido por torch)...")
    _run([VENV_PIP, "install", "--quiet", "numpy>=1.24.0,<2.0.0"], timeout=300)

    core_req = INSTALL_DIR / "_req_core.txt"
    core_req.write_text("\n".join(core_lines) + "\n")
    r = _run([VENV_PIP, "install", "-r", str(core_req), "--quiet"], timeout=3600)
    core_req.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError("Error instalando dependencias:\n" + r.stderr[-1000:])
    _log("Dependencias instaladas.")

    # mlx (aceleracion Apple Silicon) — solo en arm64, no fatal si falla
    if _host_is_apple_silicon():
        _log("Instalando aceleracion Apple Silicon (mlx)...")
        for dep in mlx_lines:
            try:
                _log("  -> " + dep)
                _run([VENV_PIP, "install", "--quiet", dep], timeout=600)
            except Exception:
                pass
        _log("Aceleracion mlx lista.")
        _test_and_configure_mlx()

# ── Shared: test Metal / mlx + torch MPS compatibility ───────────────────────
def _test_and_configure_mlx():
    """Probe the Metal accelerators with REAL compute (not just import) in
    isolated subprocesses, then write/clear .mlx_disabled and .mps_disabled.

    Some M1 configs import mlx.core fine but abort() (SIGABRT) on the first
    Metal kernel — and a SIGABRT in any thread kills the whole app silently.
    Running an actual matmul in a subprocess catches that here, at install time,
    so the app picks the fastest backend that is STABLE on this exact machine:
      - working Metal  -> mlx (Neural Engine) for transcription, MPS for diarization
      - broken Metal   -> faster-whisper + CPU diarization (reliable everywhere)."""
    if not _host_is_apple_silicon():
        return  # Intel: no mlx / MPS

    _log("Verificando aceleracion Metal en este Mac (mlx + MPS)...")
    mlx_flag = INSTALL_DIR / ".mlx_disabled"
    mps_flag = INSTALL_DIR / ".mps_disabled"

    def _probe(code):
        r = _run([VENV_PY, "-c", code], timeout=60)
        return r.returncode == 0 and "OK" in r.stdout, r.returncode

    mlx_ok, mlx_rc = _probe(
        "import mlx.core as mx; x=mx.ones((64,64)); mx.eval(x@x); print('OK')")
    if mlx_ok:
        _log("mlx (Neural Engine) compatible — transcripcion acelerada activa.")
        mlx_flag.unlink(missing_ok=True)
    else:
        _log("mlx no estable aqui (rc=" + str(mlx_rc) +
             "). Usando faster-whisper (igual de preciso).")
        mlx_flag.write_text("mlx Metal compute test failed rc=" + str(mlx_rc) + "\n")

    mps_ok, mps_rc = _probe(
        "import torch; x=torch.ones(64,64,device='mps'); _=(x@x).cpu(); print('OK')")
    if mps_ok:
        _log("torch MPS compatible — diarizacion acelerada activa.")
        mps_flag.unlink(missing_ok=True)
    else:
        _log("MPS no estable aqui (rc=" + str(mps_rc) + "). Diarizacion en CPU.")
        mps_flag.write_text("torch MPS compute test failed rc=" + str(mps_rc) + "\n")

# ── Shared: build VozMeet.app ─────────────────────────────────────────────────
def _build_app():
    APP = INSTALL_DIR / "VozMeet.app"
    (APP / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
    (APP / "Contents/Resources").mkdir(parents=True, exist_ok=True)

    launcher = APP / "Contents/MacOS/VozMeet"
    launcher.write_text(
        "#!" + VENV_PY + "\n"
        "import sys, os\n"
        "# OpenMP duplicate-runtime guard — must be set before torch/ctranslate2\n"
        "# load, or OpenMP calls abort() (SIGABRT) and the app closes silently.\n"
        "os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')\n"
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
        '  <key>CFBundleVersion</key>       <string>1.5</string>\n'
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
def _host_is_apple_silicon():
    """True if the physical CPU is Apple Silicon — reliable even when this
    installer process itself is running under Rosetta (where platform.machine()
    and uname -m both lie and report 'x86_64'). hw.optional.arm64 reflects the
    real hardware, not the translated process."""
    try:
        r = subprocess.run(["sysctl", "-n", "hw.optional.arm64"],
                           capture_output=True, text=True, timeout=10)
        if r.stdout.strip() == "1":
            return True
    except Exception:
        pass
    return platform.machine() == "arm64"

def _python_arch(py):
    """Return the architecture a given python runs as ('arm64', 'x86_64', '')."""
    try:
        r = subprocess.run(
            [py, "-c", "import platform;print(platform.machine())"],
            capture_output=True, text=True, timeout=30)
        return r.stdout.strip()
    except Exception:
        return ""

def _venv_is_arm64():
    """True if the installed venv python runs natively as arm64."""
    return _python_arch(VENV_PY) == "arm64"

def _venv_imports_ok():
    """Smoke-test the venv: can it actually import the native C-extensions?
    A venv whose python is arm64 can still hold x86_64 wheels (installed long
    ago under Rosetta), so checking the python arch alone is not enough — the
    .so files fail to dlopen with 'incompatible architecture'. We import the
    heaviest native deps and require success."""
    if not Path(VENV_PY).exists():
        return False
    r = subprocess.run(
        [VENV_PY, "-c", "import numpy, ctranslate2; print('OK')"],
        capture_output=True, text=True)
    return r.returncode == 0 and "OK" in r.stdout

def _find_python():
    """Find a Python 3.11+. On Apple Silicon, only accept a NATIVE arm64 build
    (an Intel build runs under Rosetta and breaks WKWebView + mlx)."""
    host_arm = _host_is_apple_silicon()
    candidates = [
        "/opt/homebrew/bin/python3.13",
        "/opt/homebrew/bin/python3.12",
        "/opt/homebrew/bin/python3.11",
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13",
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
        "/usr/local/bin/python3.13",
        "/usr/local/bin/python3.12",
        "/usr/local/bin/python3.11",
    ]
    for py in ["python3.11", "python3.12", "python3.13", "python3"]:
        r = subprocess.run(["which", py], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            candidates.append(r.stdout.strip())

    for p in candidates:
        if not Path(p).exists():
            continue
        ver = subprocess.run(
            [p, "-c", "import sys; print(sys.version_info.minor)"],
            capture_output=True, text=True).stdout.strip()
        try:
            if int(ver) < 11:
                continue
        except ValueError:
            continue
        # On Apple Silicon, skip Intel/Rosetta pythons.
        if host_arm and _python_arch(p) != "arm64":
            continue
        return p
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
    # python.org "macos11" build is a universal2 package: it provides a native
    # arm64 binary on Apple Silicon, which is exactly what we need.
    url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-macos11.pkg"
    pkg = "/tmp/vozmeet_python-3.11.9.pkg"
    _log("Descargando Python 3.11.9 universal (~45 MB)...")
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
    if _host_is_apple_silicon() and _python_arch(py) != "arm64":
        raise RuntimeError(
            "Se instalo Python pero no es la version Apple Silicon (arm64).")
    _log("Python 3.11 (Apple Silicon) instalado.")
    return py

def _install_ffmpeg(install_dir):
    arch = "arm64" if _host_is_apple_silicon() else "x64"
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

# The CFBundleExecutable must be a /bin/sh script — macOS refuses to launch
# a Python script directly as a .app on some machines ("No se encuentra el
# archivo").  The shell launcher finds python3 wherever it lives and execs
# the actual installer (installer.py in the same MacOS directory).
SHELL_LAUNCHER = r'''#!/bin/sh
# VozMeet Installer launcher — finds python3 and runs the real installer.
DIR="$(cd "$(dirname "$0")" && pwd)"
PY=""
for candidate in \
    /usr/bin/python3 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
    python3; do
    if [ -x "$candidate" ] 2>/dev/null || command -v "$candidate" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    osascript -e 'display dialog "Python 3 no encontrado.\n\nInstala Python desde python.org y vuelve a abrir el instalador." buttons {"OK"} default button "OK" with icon stop with title "VozMeet Installer"'
    exit 1
fi
exec "$PY" "$DIR/installer.py" "$@"
'''

exe = macos / "VozMeet-Installer"
exe.write_text(SHELL_LAUNCHER)
exe.chmod(0o755)

py_installer = macos / "installer.py"
py_installer.write_text(installer_py)
py_installer.chmod(0o644)

(app_root / "Contents/Info.plist").write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
    '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0"><dict>\n'
    '  <key>CFBundleName</key>          <string>VozMeet Installer</string>\n'
    '  <key>CFBundleDisplayName</key>   <string>VozMeet Installer</string>\n'
    '  <key>CFBundleIdentifier</key>    <string>com.bms.vozmeet.installer</string>\n'
    '  <key>CFBundleVersion</key>       <string>1.5.2</string>\n'
    '  <key>CFBundleExecutable</key>    <string>VozMeet-Installer</string>\n'
    '  <key>CFBundleIconFile</key>      <string>VozMeet</string>\n'
    '  <key>CFBundleIconName</key>      <string>VozMeet</string>\n'
    '  <key>NSHighResolutionCapable</key><true/>\n'
    '  <key>LSUIElement</key>           <true/>\n'
    '</dict></plist>\n'
)

# ── Verify ────────────────────────────────────────────────────────────────────
content = py_installer.read_text()
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
assert "_test_and_configure_mlx" in content, "missing mlx Metal compatibility test"
assert "mx.eval" in content, "mlx test must run real compute, not just import"
assert "device='mps'" in content, "missing torch MPS compatibility test"
assert ".mlx_disabled" in content, "missing mlx_disabled flag"
assert ".mps_disabled" in content, "missing mps_disabled flag"
assert "1.5" in content, "version not updated"
assert "_show_progress_window" in content, "missing progress window"
assert "tkinter" in content, "missing tkinter"
assert "_run_installer_bg" in content, "missing background thread"
assert "_python_arch" in content, "missing arch detection"
assert "_venv_is_arm64" in content, "missing venv arch check"
assert "_create_venv_and_install" in content, "missing shared venv builder"
assert "Rosetta" in content, "missing Intel/Rosetta repair"
assert "hw.optional.arm64" in content, "missing reliable Apple Silicon detection"
assert "_venv_imports_ok" in content, "missing venv import smoke-test"
assert "_host_is_apple_silicon" in content, "missing host arch helper"
# Verify shell launcher
shell_content = exe.read_text()
assert shell_content.startswith("#!/bin/sh"), "launcher must be a sh script"
assert "installer.py" in shell_content, "launcher must call installer.py"
assert "python3" in shell_content, "launcher must find python3"
print("Content checks: OK")

# ── Zip ───────────────────────────────────────────────────────────────────────
# Use zipfile.ZipInfo to set permissions explicitly so macOS Archive Utility
# honours the execute bit on the shell launcher after extraction.
zip_path = Path("/tmp/VozMeet-Installer.zip")
with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(app_root.rglob("*")):
        arcname = str(path.relative_to(app_root.parent))
        if path.is_dir():
            zi = zipfile.ZipInfo(arcname + "/")
            zi.external_attr = (0o40755 & 0xFFFF) << 16
            zf.writestr(zi, "")
        else:
            mode = path.stat().st_mode
            zi = zipfile.ZipInfo(arcname)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (mode & 0xFFFF) << 16
            zi.create_system = 3  # Unix
            zf.writestr(zi, path.read_bytes())

print(f"ZIP: {zip_path}  ({zip_path.stat().st_size:,} bytes)")
print("DONE — ready to upload")
