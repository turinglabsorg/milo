#!/usr/bin/env python3
"""Desktop notifications for new mail while the Milo window is closed.

Runs as a systemd user service (installed by install.py). It follows the
server's change stream and asks `/api/notifications` what is worth a banner,
with the same rules as phone pushes. Clicking a banner opens Milo.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.launch import shared_server  # noqa: E402

STATE = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "milo" / "notifier.json"
ICON = ROOT / "web" / "icon-192.png"
FALLBACK_POLL = 60


def load_cursor():
    try:
        return int(json.loads(STATE.read_text())["cursor"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_cursor(cursor):
    STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"cursor": cursor}))
    temporary.replace(STATE)


def milo_focused(server):
    """Skip banners while the owner is looking at Milo itself."""
    if not shutil.which("hyprctl"):
        return False
    try:
        window = json.loads(subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True,
                                           timeout=2).stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    host = urlsplit(server).hostname or ""
    label = f"{window.get('class', '')} {window.get('initialClass', '')}"
    return "Milo" in label or bool(host and host in label)


def open_milo(message_id=None):
    extra = [f"--open={message_id}"] if message_id else []
    subprocess.Popen([sys.executable, str(ROOT / "scripts/launch.py"), *extra], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def banner(title, body, message_id=None):
    command = ["notify-send", "--app-name=Milo", "--action=open=Apri Milo", "--wait", title, body]
    if ICON.exists():
        command[1:1] = ["--icon", str(ICON)]

    def show():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
        except (OSError, subprocess.SubprocessError):
            return
        if result.stdout.strip() == "open":
            open_milo(message_id)
    threading.Thread(target=show, daemon=True).start()


def announce(messages):
    for message in messages[:3]:
        subject = (message.get("subject") or "").strip() or "(Senza oggetto)"
        banner(message.get("sender") or message.get("sender_email") or "Milo", subject, message.get("id"))
    if len(messages) > 3:
        banner("Milo", f"Altre {len(messages) - 3} email nuove")


class Notifier:
    def __init__(self, server, client):
        self.server, self.client = server, client
        self.cursor = load_cursor()

    def check(self):
        params = {} if self.cursor is None else {"after": self.cursor}
        response = self.client.get(self.server + "/api/notifications", params=params)
        response.raise_for_status()
        data = response.json()
        if data["messages"] and not milo_focused(self.server):
            announce(data["messages"])
        if data["cursor"] != self.cursor:
            self.cursor = data["cursor"]
            save_cursor(self.cursor)

    def follow(self):
        """One stream session; returns when it ends so the caller reconnects."""
        with self.client.stream("GET", self.server + "/api/events",
                                timeout=httpx.Timeout(10, read=FALLBACK_POLL)) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("event: change") or line.startswith("event: hello"):
                    self.check()


def owner(server, client):
    try:
        return client.get(server + "/api/status").json().get("authenticated") is True
    except (httpx.HTTPError, ValueError):
        return True  # unreachable: keep retrying rather than give up


def main():
    server = shared_server()
    if not server:
        sys.exit("Milo notifier needs a shared Milo server (.data/server.json).")
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        notifier = Notifier(server, client)
        delay = 2
        while True:
            try:
                notifier.check()
                notifier.follow()
                delay = 2
            except httpx.HTTPStatusError as exc:
                # Non-owners get 404 everywhere; an older server only lacks the endpoint.
                if exc.response.status_code in {401, 403, 404} and not owner(server, client):
                    sys.exit("Milo refused the notifier: this device is not the owner's.")
                delay = min(delay * 2, 300)
            except (httpx.HTTPError, ValueError, KeyError):
                delay = min(delay * 2, 300)
            time.sleep(delay)


if __name__ == "__main__":
    main()
