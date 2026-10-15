"""Install the macOS Milo client: build the WKWebView app, place it in
~/Applications, register it as the mailto: handler, and load the
background notifier LaunchAgent. No sudo. The archive stays on the
server; this only installs the client (Linux parity: install.py)."""
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHECKOUT = ROOT.parent
LABEL = "io.meaningtech.milo.notifier"
BUNDLE_ID = "io.meaningtech.milo.mac"


def run(*args, check=True):
    return subprocess.run([str(arg) for arg in args], check=check)


def bundle_id(app):
    plist = app / "Contents/Info.plist"
    if not plist.is_file():
        return None
    try:
        return plistlib.loads(plist.read_bytes()).get("CFBundleIdentifier")
    except (ValueError, OSError):
        return None


def mirror_config():
    """Copy a checkout pairing (.data/server.json, setup.url) into the
    macOS Application Support folder, never overwriting a different
    existing configuration."""
    source = CHECKOUT / ".data"
    target = Path.home() / "Library/Application Support/Milo"
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.chmod(0o700)
    for name in ("server.json", "setup.url"):
        origin, destination = source / name, target / name
        if not origin.is_file():
            continue
        if destination.exists():
            if destination.read_bytes() != origin.read_bytes():
                print(f"Keeps the existing {destination} (it differs from the checkout copy).")
            continue
        shutil.copyfile(origin, destination)
        destination.chmod(0o600)
        print(f"Configured the Milo server from {origin}.")


def install_notifier(app):
    binary = app / "Contents/MacOS/Milo"
    agents = Path.home() / "Library/LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    log_directory = Path.home() / "Library/Logs/Milo"
    log_directory.mkdir(parents=True, exist_ok=True)
    target = agents / f"{LABEL}.plist"
    payload = {
        "Label": LABEL,
        "ProgramArguments": [str(binary), "--notifier"],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 20,
        "StandardOutPath": str(log_directory / "notifier.log"),
        "StandardErrorPath": str(log_directory / "notifier.log"),
    }
    data = plistlib.dumps(payload)
    domain = f"gui/{os.getuid()}"
    loaded = subprocess.run(["launchctl", "print", f"{domain}/{LABEL}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if target.exists() and target.read_bytes() == data:
        if loaded:
            print("Milo notifications already run in the background.")
            return
    else:
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.chmod(0o600)
        os.replace(temporary, target)
    if loaded:
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], check=False)
    run("launchctl", "bootstrap", domain, target)
    print("Milo notifications run in the background (launchctl print gui/$(id -u)/" + LABEL + ").")


def main():
    if sys.platform != "darwin":
        sys.exit("Run this installer on macOS; the Linux client uses install.py at the repository root.")
    for tool in ("xcodegen", "xcodebuild"):
        if not shutil.which(tool):
            sys.exit(f"{tool} is required (xcodegen: brew install xcodegen).")
    mirror_config()
    derived = ROOT / "build/DerivedData"
    run("xcodegen", "generate", "--spec", ROOT / "project.yml")
    run("xcodebuild", "-project", ROOT / "MiloMac.xcodeproj", "-scheme", "MiloMac",
        "-configuration", "Release", "-derivedDataPath", derived,
        "CODE_SIGN_IDENTITY=-", "CODE_SIGNING_REQUIRED=NO", "build")
    built = derived / "Build/Products/Release/Milo.app"
    if not built.is_dir():
        sys.exit("The build did not produce Milo.app.")
    applications = Path.home() / "Applications"
    applications.mkdir(parents=True, exist_ok=True)
    destination = applications / "Milo.app"
    if destination.exists() and bundle_id(destination) != BUNDLE_ID:
        sys.exit(f"{destination} belongs to a different application; not replacing it.")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(built, destination, symlinks=True)
    run(destination / "Contents/MacOS/Milo", "--register-mailto")
    install_notifier(destination)
    print(f"Installed {destination}\nOpen Milo from Launchpad or Spotlight; mailto: links now open in Milo.")


if __name__ == "__main__":
    main()
