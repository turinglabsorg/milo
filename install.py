"""Install a user-local Linux launcher. No sudo, credentials or desktop settings."""
import os
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
Exec={desktop_quote(root / '.venv/bin/python')} {desktop_quote(root / 'scripts/launch.py')}
Icon={root / 'web/icon.svg'}
Terminal=false
Categories=Network;Email;
StartupWMClass=Milo
""")
print(f"Installed {launcher}\nOpen Milo from your application launcher.")
