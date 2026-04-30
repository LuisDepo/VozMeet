"""
VozMeet launcher — entry point for the macOS .app bundle.
"""
import sys
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path


# ── Python API exposed to JavaScript via pywebview ────────────────────────────
class VozMeetApi:
    """Methods callable from JS as window.pywebview.api.<method>()"""

    def save_to_downloads(self, recording_id: int, fmt: str) -> dict:
        """Fetch export from FastAPI and save to ~/Downloads. Returns {ok, path, error}."""
        try:
            fmt = fmt.lower().strip()
            if fmt not in ("txt", "md", "json"):
                return {"ok": False, "error": "Formato no válido"}

            url = f"http://127.0.0.1:8765/api/export/{recording_id}?format={fmt}"
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read()
                content_disp = resp.headers.get("Content-Disposition", "")

            filename = f"transcripcion_{recording_id}.{fmt}"
            if "filename=" in content_disp:
                filename = content_disp.split("filename=")[-1].strip().strip('"')

            dest = Path.home() / "Downloads" / filename
            dest.write_bytes(data)
            return {"ok": True, "path": str(dest), "filename": filename}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_version(self) -> str:
        return "1.1"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _configure_macos_app():
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is not None:
            info["CFBundleName"] = "VozMeet"
            info["CFBundleDisplayName"] = "VozMeet"
    except Exception:
        pass

    icon_path = Path(__file__).parent / "static" / "icons" / "VozMeet.icns"
    try:
        from AppKit import NSApplication, NSImage
        ns_app = NSApplication.sharedApplication()
        if icon_path.exists():
            icon = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
            if icon:
                ns_app.setApplicationIconImage_(icon)
    except Exception:
        pass


def _is_processing() -> bool:
    try:
        from app.database.db import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM recordings WHERE status='processing'"
            ).fetchone()
        return row and row["n"] > 0
    except Exception:
        return False


def _on_closing():
    if _is_processing():
        import subprocess
        result = subprocess.run(
            ["osascript", "-e",
             "button returned of (display dialog "
             "\"VozMeet está procesando una grabación.\\n\\n"
             "Si cierras ahora el proceso se interrumpirá.\\n"
             "Podrás reanudarlo desde el Historial.\" "
             "buttons {\"Cancelar\", \"Cerrar\"} "
             "default button \"Cancelar\" "
             "with title \"VozMeet\" with icon caution)"],
            capture_output=True, text=True, timeout=30,
        )
        if result.stdout.strip() != "Cerrar":
            return False
    return True


def start_server():
    import uvicorn
    from app.main import app as fastapi_app
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8765, log_level="warning")


def wait_for_server(timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    _configure_macos_app()

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    if not wait_for_server(timeout=30):
        print("Error: El servidor VozMeet no respondió a tiempo.", file=sys.stderr)
        sys.exit(1)

    try:
        import webview
    except ImportError:
        print(
            "Error: pywebview no está instalado.\n"
            "Ejecuta: pip install pywebview pyobjc-core pyobjc-framework-Cocoa",
            file=sys.stderr,
        )
        sys.exit(1)

    api = VozMeetApi()
    window = webview.create_window(
        "VozMeet",
        "http://127.0.0.1:8765",
        width=1100,
        height=750,
        min_size=(900, 600),
        frameless=False,
        js_api=api,
    )
    window.events.closing += _on_closing

    webview.start()
    sys.exit(0)


if __name__ == "__main__":
    main()
