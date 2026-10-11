#!/usr/bin/env python3
"""Launch the local service and open Milo in a dedicated Chromium window."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DEMO = "--demo" in sys.argv
PORT = 8026 if DEMO else 8025
URL = f"http://127.0.0.1:{PORT}"
DATA = ROOT / ".data" / ("demo" if DEMO else "live")


def running():
    try:
        with urllib.request.urlopen(URL + "/api/status", timeout=1) as response:
            status = json.load(response)
        if status.get("service") != "milo" or status.get("demo") != DEMO:
            raise RuntimeError(f"Port {PORT} belongs to another service. Run Milo on a different port.")
        return True
    except (urllib.error.URLError, TimeoutError):
        return False


def shared_server():
    if DEMO:
        return None
    url = os.environ.get("MILO_SERVER_URL")
    config = ROOT / ".data/server.json"
    if not url and config.exists():
        try:
            url = json.loads(config.read_text())["url"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("The shared server configuration is invalid.") from exc
    if not url:
        return None
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise RuntimeError("The shared Milo server must use an HTTPS origin.")
    return url.rstrip("/")


def open_window(url):
    browser = next((shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome")
                    if shutil.which(name)), None)
    if browser:
        subprocess.Popen([browser, "--app=" + url, "--class=Milo", "--new-window"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        subprocess.Popen(["xdg-open", url], start_new_session=True)


def main():
    server = shared_server()
    if server:
        open_window(server)
        print(f"Milo is connected to {server}")
        return
    python = ROOT / ".venv/bin/python"
    if not python.exists():
        raise RuntimeError("Run 'uv sync' in the Milo folder first.")
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    DATA.chmod(0o700)
    if not running():
        log = DATA / "service.log"
        descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "ab") as output:
            process = subprocess.Popen([str(python), "-m", "milo", "--data", str(DATA), "--port", str(PORT),
                                        *(["--demo"] if DEMO else [])], cwd=ROOT, stdout=output, stderr=output,
                                       start_new_session=True)
        for _ in range(80):
            if running():
                break
            if process.poll() is not None:
                raise RuntimeError(f"Milo exited. Check {log}")
            time.sleep(0.1)
        else:
            raise RuntimeError(f"Milo did not start. Check {log}")
    # A fragment is never sent to the HTTP server or access logs. The UI removes it immediately.
    connection = sqlite3.connect(DATA / "mail.sqlite")
    bootstrap = connection.execute("SELECT value FROM settings WHERE key='bootstrap'").fetchone()
    connection.close()
    url = URL
    if bootstrap and json.loads(bootstrap[0]) and not DEMO:
        url += "#setup=" + json.loads(bootstrap[0])
    open_window(url)
    print(f"Milo is running at {URL}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
