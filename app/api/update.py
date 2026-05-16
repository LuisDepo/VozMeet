import shutil
import tempfile
import zipfile
import urllib.request
from pathlib import Path
from fastapi import APIRouter
from app.logger import get_logger

router = APIRouter()
log = get_logger("update")

GITHUB_ZIP = "https://github.com/luisdepo/vozmeet/archive/refs/heads/main.zip"
from app.version import VERSION as CURRENT_VERSION


@router.get("/update/check")
def check_update():
    try:
        url = "https://raw.githubusercontent.com/luisdepo/vozmeet/main/app/launcher.py"
        req = urllib.request.Request(url, headers={"User-Agent": "VozMeet"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode()
        remote_version = CURRENT_VERSION
        for line in content.splitlines():
            if 'return "' in line and "get_version" not in line and "def " not in line:
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            zip_path.write_bytes(resp.read())

        log.info("Update: extracting zip...")
        with zipfile.ZipFile(str(zip_path), "r") as zf:
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

        shutil.rmtree(tmp, ignore_errors=True)
        log.info("Update: completed successfully")
        return {"ok": True, "message": "Actualización completada. Reinicia para aplicar los cambios."}

    except Exception as e:
        log.exception("Update install failed")
        return {"ok": False, "error": str(e)}
