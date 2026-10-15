"""Install a user-local Linux launcher and make Milo open mailto: links. No sudo or credentials."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def desktop_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`") + '"'


def desktop_arg(value):
    """Quote only when needed: xdg-mime cannot resolve a quoted Exec program."""
    return str(value) if re.fullmatch(r"[\w/.+-]+", str(value)) else desktop_quote(value)


root = Path(__file__).resolve().parent
if not (root / ".venv/bin/python").exists():
    sys.exit("Run 'uv sync' first.")
data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
applications = data_home / "applications"
applications.mkdir(parents=True, exist_ok=True)
launcher = applications / "milo.desktop"
launcher.write_text(f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Milo
Comment=La tua posta, con spazio per pensare
Exec={desktop_arg(root / '.venv/bin/python')} {desktop_arg(root / 'scripts/launch.py')} %u
Icon={root / 'web/icon.svg'}
Terminal=false
Categories=Network;Email;
MimeType=x-scheme-handler/mailto;
StartupWMClass=Milo
""")
if shutil.which("update-desktop-database"):
    subprocess.run(["update-desktop-database", str(applications)], check=False)
if shutil.which("xdg-mime"):
    subprocess.run(["xdg-mime", "default", "milo.desktop", "x-scheme-handler/mailto"], check=False)
print(f"Installed {launcher}\nOpen Milo from your application launcher; mailto: links now open in Milo.")

# Desktop notifications while the window is closed (shared server only).
if (root / ".data/server.json").exists() and shutil.which("systemctl") and shutil.which("notify-send"):
    units = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "systemd/user"
    units.mkdir(parents=True, exist_ok=True)
    (units / "milo-notifier.service").write_text(f"""[Unit]
Description=Milo desktop notifications
After=graphical-session.target network-online.target
PartOf=graphical-session.target

[Service]
ExecStart={desktop_quote(root / '.venv/bin/python')} {desktop_quote(root / 'scripts/notifier.py')}
Restart=on-failure
RestartSec=60

[Install]
WantedBy=graphical-session.target
""")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", "milo-notifier.service"], check=False)
    subprocess.run(["systemctl", "--user", "restart", "milo-notifier.service"], check=False)
    print("Milo notifications run in the background (systemctl --user status milo-notifier).")
