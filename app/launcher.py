"""
VozMeet launcher — entry point for the macOS .app bundle.
"""
import sys
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path
from app.version import VERSION

_window = None          # pywebview window reference, set in main()
_server_error = [None]  # captures server thread exception so main() can report it


# ── Python API exposed to JavaScript via pywebview ────────────────────────────
class VozMeetApi:
    """Methods callable from JS as window.pywebview.api.<method>()"""

    def save_to_downloads(self, recording_id: int, fmt: str) -> dict:
        """Fetch export from FastAPI, show native save dialog, write to chosen path."""
        try:
            fmt = fmt.lower().strip()
            if fmt not in ("txt", "md", "json", "docx"):
                return {"ok": False, "error": "Formato no válido"}

            url = f"http://127.0.0.1:8765/api/export/{recording_id}?format={fmt}"
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
                content_disp = resp.headers.get("Content-Disposition", "")

            filename = f"transcripcion_{recording_id}.{fmt}"
            if "filename=" in content_disp:
                filename = content_disp.split("filename=")[-1].strip().strip('"')

            # Show native macOS save panel
            save_path = None
            if _window:
                try:
                    import webview
                    result = _window.create_file_dialog(
                        webview.SAVE_DIALOG,
                        directory=str(Path.home() / "Downloads"),
                        save_filename=filename,
                    )
                    save_path = result[0] if result else None
                except Exception:
                    pass

            # Fall back to ~/Downloads if dialog cancelled or unavailable
            if not save_path:
                save_path = str(Path.home() / "Downloads" / filename)

            dest = Path(save_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return {"ok": True, "path": str(dest), "filename": dest.name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def restart_app(self) -> dict:
        """Close the webview window so the user can relaunch the app."""
        def _close():
            time.sleep(0.6)
            try:
                import webview
                for w in webview.windows:
                    w.destroy()
            except Exception:
                import os, signal
                os.kill(os.getpid(), signal.SIGTERM)
        threading.Thread(target=_close, daemon=True).start()
        return {"ok": True}

    def get_version(self) -> str:
        return VERSION

    def generate_summary(self, recording_id: int) -> dict:
        """Trigger meeting summary generation. Returns {ok, summary} or {ok:False, error}."""
        try:
            url = f"http://127.0.0.1:8765/api/summary/{recording_id}"
            req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                import json
                result = json.loads(resp.read())
            return {"ok": True, "summary": result.get("summary", "")}
        except urllib.error.HTTPError as e:
            try:
                import json
                detail = json.loads(e.read()).get("detail", str(e))
            except Exception:
                detail = str(e)
            return {"ok": False, "error": detail}
        except Exception as e:
            return {"ok": False, "error": str(e)}


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
    try:
        import sys as _sys
        _base = str(Path(__file__).parent.parent)
        if _base not in _sys.path:
            _sys.path.insert(0, _base)
        import uvicorn
        from app.main import app as fastapi_app
        uvicorn.run(fastapi_app, host="127.0.0.1", port=8765, log_level="warning")
    except Exception as exc:
        _server_error[0] = exc


def wait_for_server(timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_error[0] is not None:
            return False
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def _show_error_dialog(msg: str):
    import subprocess
    safe = msg.replace("\\", "\\\\").replace('"', '\\"')
    # Truncate and put on one visual line for osascript safety
    safe = safe[:500].replace("\n", " | ")
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display dialog "VozMeet no pudo iniciarse:\\n\\n{safe}" '
             f'buttons {{"OK"}} default button "OK" '
             f'with title "VozMeet - Error" with icon stop'],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass


def _write_error_log(msg: str):
    try:
        import datetime
        log_dir = Path.home() / "Library" / "Logs" / "VozMeet"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(str(log_dir / "error.log"), "a") as f:
            f.write(f"\n[{datetime.datetime.now()}]\n{msg}\n")
    except Exception:
        pass


def _free_port():
    """Kill any process using port 8765 so we can bind fresh."""
    import subprocess
    try:
        r = subprocess.run(
            ["lsof", "-ti", "tcp:8765"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            for pid in r.stdout.strip().split("\n"):
                subprocess.run(["kill", "-9", pid.strip()], capture_output=True)
            time.sleep(0.5)
    except Exception:
        pass


def _trace(msg: str):
    """Write a timestamped line to the startup trace log (survives C-extension crashes)."""
    try:
        import datetime, os as _os
        log_dir = Path.home() / "Library" / "Logs" / "VozMeet"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(str(log_dir / "startup.log"), "a") as f:
            f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')}] {msg}\n")
            f.flush()
            _os.fsync(f.fileno())
    except Exception:
        pass


def _preload_whisper():
    """Warm up the Whisper model in the background so first transcription is instant.

    Wrapped in detailed tracing because a fatal C-extension abort here
    (e.g. OpenMP runtime conflict, Metal init) kills the whole process
    without a Python traceback."""
    _trace("preload: thread started")
    try:
        _trace("preload: importing transcriber")
        from app.core.transcriber import _get_model
        _trace("preload: calling _get_model()")
        _get_model()
        _trace("preload: model loaded OK")
    except Exception as e:
        _trace("preload: exception " + repr(e))


def main():
    global _window

    _trace("=== VozMeet starting ===")
    try:
        _trace("configure_macos_app")
        _configure_macos_app()

        _trace("free_port")
        _free_port()

        _trace("starting server thread")
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        _trace("wait_for_server")
        if not wait_for_server(timeout=60):
            err = _server_error[0]
            if err:
                import traceback
                tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
                _write_error_log(tb)
                raise RuntimeError(f"Error iniciando el servidor:\n{err}")
            else:
                raise RuntimeError(
                    "El servidor VozMeet no respondio en 60 segundos.\n"
                    "Log de error: ~/Library/Logs/VozMeet/error.log"
                )

        _trace("server is up")

        # Preload the Whisper model in the background so the first
        # transcription is fast. If this thread ever crashes the process,
        # ~/Library/Logs/VozMeet/startup.log shows exactly which step it
        # reached before dying.
        _trace("starting preload thread")
        preload_thread = threading.Thread(target=_preload_whisper, daemon=True)
        preload_thread.start()

        try:
            import webview
        except ImportError:
            raise RuntimeError(
                "pywebview no esta instalado.\n"
                "Reinstala VozMeet con el instalador oficial."
            )

        _trace("creating window")
        api = VozMeetApi()

        _LOADING_HTML = (
            "<html><head><style>"
            "body{margin:0;background:#1a1a1a;display:flex;align-items:center;"
            "justify-content:center;height:100vh;font-family:sans-serif;color:#888}"
            ".dot{animation:blink 1s infinite alternate}"
            "@keyframes blink{from{opacity:.2}to{opacity:1}}"
            "</style></head><body>"
            "<p style='font-size:18px'>Cargando VozMeet<span class=dot>...</span></p>"
            "</body></html>"
        )

        _window = webview.create_window(
            "VozMeet",
            html=_LOADING_HTML,
            width=1100,
            height=750,
            min_size=(900, 600),
            frameless=False,
            js_api=api,
        )
        _window.events.closing += _on_closing

        def _navigate():
            time.sleep(0.5)
            _trace("navigating to server")
            try:
                _window.load_url("http://127.0.0.1:8765")
                _trace("load_url called")
            except Exception as nav_exc:
                _trace("navigate error: " + str(nav_exc))

        _trace("webview.start")
        webview.start(func=_navigate)
        _trace("webview exited normally")
        sys.exit(0)

    except SystemExit:
        raise
    except Exception as exc:
        import traceback
        full = traceback.format_exc()
        _trace("EXCEPTION: " + str(exc))
        _write_error_log(full)
        _show_error_dialog(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
