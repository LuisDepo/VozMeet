import ssl
import shutil
import tempfile
import zipfile
import urllib.request
from pathlib import Path
from fastapi import APIRouter
from app.logger import get_logger

router = APIRouter()
log = get_logger("update")


def _ssl_context():
    """An SSL context that works even on a Python whose CA certs were never
    installed (python.org's known 'Install Certificates' gap). Prefer certifi,
    then the system store, then unverified for these trusted GitHub URLs."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()

# The working build lives on this branch; the in-app updater pulls from it so
# the Update button delivers the same code as the installer .zip.
UPDATE_BRANCH = "claude/vozmeet-macos-app-EOB7u"
GITHUB_ZIP = f"https://github.com/luisdepo/vozmeet/archive/refs/heads/{UPDATE_BRANCH}.zip"
from app.version import VERSION as CURRENT_VERSION


@router.get("/update/check")
def check_update():
    try:
        url = ("https://raw.githubusercontent.com/luisdepo/vozmeet/"
               f"{UPDATE_BRANCH}/app/version.py")
        req = urllib.request.Request(url, headers={"User-Agent": "VozMeet"})
        with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as resp:
            content = resp.read().decode()
        remote_version = CURRENT_VERSION
        for line in content.splitlines():
            if line.strip().startswith("VERSION") and '"' in line:
                parts = line.split('"')
                if len(parts) >= 2:
                    remote_version = parts[1]
                    break
        return {
            "current_version": CURRENT_VERSION,
            "remote_version": remote_version,
            "update_available": remote_version != CURRENT_VERSION,
        }
    except Exception as e:
        log.warning("Update check failed (repo privado o sin red): %s", e)
        # Private repo or no network — assume up to date rather than showing error
        return {
            "current_version": CURRENT_VERSION,
            "remote_version": CURRENT_VERSION,
            "update_available": False,
        }


@router.post("/update/install")
def install_update():
    try:
        project_root = Path(__file__).parent.parent.parent
        log.info("Update: project root = %s", project_root)

        tmp = tempfile.mkdtemp(prefix="vozmeet_update_")
        zip_path = Path(tmp) / "vozmeet.zip"

        log.info("Update: downloading from GitHub...")
        req = urllib.request.Request(GITHUB_ZIP, headers={"User-Agent": "VozMeet"})
        with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as resp:
            zip_path.write_bytes(resp.read())

        log.info("Update: extracting zip...")
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                return {"ok": False, "error": "Descarga corrupta: " + bad}
            zf.extractall(tmp)

        # GitHub zips extract to <repo>-<branch>/ folder
        extracted = [d for d in Path(tmp).iterdir() if d.is_dir() and d.name != "__MACOSX"]
        if not extracted:
            return {"ok": False, "error": "No se encontró el directorio extraído"}
        src_root = extracted[0]
        app_src = src_root / "app"
        if not app_src.exists():
            return {"ok": False, "error": "Estructura del zip inesperada"}

        log.info("Update: copying files from %s to %s...", app_src, project_root / "app")
        # Copy all app/ files, skipping __pycache__ and data/
        for item in app_src.rglob("*"):
            if "__pycache__" in str(item):
                continue
            rel = item.relative_to(app_src)
            dst = project_root / "app" / rel
            if item.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(dst))

        # Keep requirements.txt in sync (used by the installer / future repairs).
        src_reqs = src_root / "requirements.txt"
        if src_reqs.exists():
            shutil.copy2(str(src_reqs), str(project_root / "requirements.txt"))

        # Enforce numpy<2 — torch's C API is incompatible with numpy 2.x and
        # will SIGSEGV on import.  Run this before _reconfigure_accelerators so
        # the probe subprocesses see the correct numpy.
        _fix_numpy(project_root)

        # Re-evaluate Metal/mlx + MPS compatibility for THIS machine and persist
        # the disable-flags. Runs in subprocesses so a Metal crash can't take down
        # the running app, and so the freshly-copied code path is exercised.
        _reconfigure_accelerators(project_root)

        shutil.rmtree(tmp, ignore_errors=True)
        log.info("Update: completed successfully")
        return {"ok": True, "message": "Actualización completada. Reinicia para aplicar los cambios."}

    except Exception as e:
        log.exception("Update install failed")
        return {"ok": False, "error": str(e)}


def _fix_numpy(project_root: Path):
    """Downgrade numpy to <2 if needed. torch's C API (tensor_numpy.cpp) is
    incompatible with numpy 2.x — importing torch SIGSEGVs on every machine."""
    import sys
    import subprocess
    venv_pip = project_root / ".venv" / "bin" / "pip"
    if not venv_pip.exists():
        venv_pip = project_root / ".venv" / "bin" / "pip3"
    if not venv_pip.exists():
        log.warning("Update: pip not found, skipping numpy fix")
        return
    try:
        r = subprocess.run(
            [str(venv_pip), "install", "--quiet", "numpy>=1.24.0,<2.0.0"],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode == 0:
            log.info("Update: numpy pinned to <2")
        else:
            log.warning("Update: numpy pin failed: %s", r.stderr[-500:])
    except Exception as e:
        log.warning("Update: numpy pin error: %s", e)


def _reconfigure_accelerators(project_root: Path):
    """Probe mlx (Metal) and torch MPS in throwaway subprocesses and write/clear
    the .mlx_disabled / .mps_disabled flags accordingly. A subprocess SIGABRT is
    confined to the child, so this is safe to run inside the live app."""
    import sys
    import platform
    import subprocess

    if platform.machine() != "arm64":
        return  # Intel: no Metal/mlx/MPS to probe

    def _probe(code: str) -> bool:
        try:
            r = subprocess.run([sys.executable, "-c", code],
                               capture_output=True, text=True, timeout=60)
            return r.returncode == 0 and "OK" in r.stdout
        except Exception:
            return False

    mlx_flag = project_root / ".mlx_disabled"
    mps_flag = project_root / ".mps_disabled"

    # Real compute, not just import — catches configs that import fine but abort
    # on the first Metal kernel.
    mlx_ok = _probe("import mlx.core as mx; "
                    "x=mx.ones((64,64)); mx.eval(x@x); print('OK')")
    mps_ok = _probe("import torch; "
                    "x=torch.ones(64,64,device='mps'); _=(x@x).cpu(); print('OK')")

    try:
        if mlx_ok:
            mlx_flag.unlink(missing_ok=True)
        else:
            mlx_flag.write_text("mlx Metal compute test failed\n")
        if mps_ok:
            mps_flag.unlink(missing_ok=True)
        else:
            mps_flag.write_text("torch MPS compute test failed\n")
        log.info("Update: accelerator probe — mlx_ok=%s mps_ok=%s", mlx_ok, mps_ok)
    except Exception:
        log.warning("Update: could not write accelerator flags")
