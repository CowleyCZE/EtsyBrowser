"""Spuštění GUI jedním příkazem: python -m gui  ->  http://127.0.0.1:8080"""

import os
import sys
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def _find_available_port(preferred_port: int, host: str = "127.0.0.1") -> int:
    if not _is_port_in_use(preferred_port, host):
        return preferred_port
    # Pokud je výchozí port obsazen, zkusíme další volné porty
    for candidate in range(preferred_port + 1, preferred_port + 50):
        if not _is_port_in_use(candidate, host):
            return candidate
    return preferred_port


def main() -> None:
    try:
        import uvicorn
    except ImportError:
        print("Chybí závislosti GUI. Spusť: pip install -r requirements.txt")
        raise SystemExit(1)

    preferred_port = int(os.getenv("GUI_PORT", "8080"))
    port = _find_available_port(preferred_port, "127.0.0.1")
    if port != preferred_port:
        print(f"Upozornění: Port {preferred_port} je obsazen, používám port {port}.")
    url = f"http://127.0.0.1:{port}"
    print(f"EtsyBrowser GUI běží na {url} (ukončení: Ctrl+C)")
    if os.getenv("GUI_NO_BROWSER", "") != "1":
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    # Jen localhost: klíče a hesla nesmí být dostupné z jiných počítačů
    uvicorn.run("gui.app:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
