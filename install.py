"""Install a user-local Linux launcher and make Milo open mailto: links. No sudo or credentials."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def desktop_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`") + '"'


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
Exec={desktop_quote(root / '.venv/bin/python')} {desktop_quote(root / 'scripts/launch.py')} %u
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
