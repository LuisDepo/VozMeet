"""
VozMeet launcher — entry point for the macOS .app bundle.
Starts FastAPI in a daemon thread, waits for health check, then opens
a native macOS window via pywebview.
"""
import sys
import time
import threading
import urllib.request
import urllib.error


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
            "Ejecuta: pip install pywebview pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-WebKit",
            file=sys.stderr,
        )
        sys.exit(1)

    window = webview.create_window(
        "VozMeet",
        "http://127.0.0.1:8765",
        width=1100,
        height=750,
        min_size=(900, 600),
        frameless=False,
    )

    webview.start()
    sys.exit(0)


if __name__ == "__main__":
    main()
