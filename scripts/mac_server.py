#!/usr/bin/env python3
"""Activate this Milo checkout on the Mac's existing permanent Grog service."""
import json
import os
import plistlib
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ORIGIN = "https://milo.grooooog.space"
HOST = "milo.grooooog.space"
LABEL = "space.grooooog.serve"
PORT = 8025


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def register_site(path, root):
    previous = path.read_bytes() if path.exists() else None
    sites = json.loads(previous) if previous else {}
    if not isinstance(sites, dict):
        raise RuntimeError("sites.json non contiene una mappa di siti; non lo modifico.")
    spec = {"run": f"{shlex.quote(str(root / '.venv/bin/python'))} "
                   f"{shlex.quote(str(root / 'scripts/serve.py'))}",
            "cwd": str(root), "port": PORT}
    current = sites.get(HOST)
    if current is not None and current != spec:
        legacy = {"run": ".venv/bin/python scripts/serve.py", "cwd": "~/Sites/milo", "port": PORT}
        if current != legacy or root != Path.home() / "Sites/milo":
            raise RuntimeError("Il dominio Milo ha già una configurazione diversa; non la sostituisco.")
    for host, entry in sites.items():
        if host != HOST and isinstance(entry, dict) and str(entry.get("port")) == str(PORT):
            raise RuntimeError("La porta 8025 è già assegnata a un altro sito Grog.")
    if current == spec:
        return False
    sites[HOST] = spec
    if (path.read_bytes() if path.exists() else None) != previous:
        raise RuntimeError("sites.json è cambiato durante la preparazione; riprova.")
    if previous is not None:
        backup = path.with_name(path.name + ".milo-backup")
        if not backup.exists():
            atomic_write(backup, previous)
    atomic_write(path, (json.dumps(sites, indent=2) + "\n").encode())
    return True


def check_grog_agent(home):
    agent = home / "Library/LaunchAgents" / (LABEL + ".plist")
    loaded = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    payload = None
    if agent.exists():
        data = plistlib.loads(agent.read_bytes())
        if data.get("Label") != LABEL or "serve" not in data.get("ProgramArguments", []):
            raise RuntimeError("Il launch agent esistente non identifica grog serve.")
        override = data.get("EnvironmentVariables", {}).get("GROG_SITES")
        if override and Path(override).expanduser() != home / ".grog/sites.json":
            raise RuntimeError("Grog usa un file siti personalizzato; non modifico quello sbagliato.")
    elif not loaded:
        node = shutil.which("node")
        grog = home / ".claude/tools/grog/index.js"
        if not node or not grog.is_file():
            raise RuntimeError("Serve il Grog del proprietario già installato su questo Mac, con Node disponibile.")
        running = subprocess.run(["pgrep", "-f", r"(^|[ /])(grog|index[.]js)[[:space:]]+serve([[:space:]]|$)"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if running:
            raise RuntimeError("Grog serve è già avviato fuori da launchd; non apro un secondo processo.")
        log = home / "Library/Logs/grog-serve.log"
        payload = plistlib.dumps({
            "Label": LABEL, "ProgramArguments": [node, str(grog), "serve"],
            "RunAtLoad": True, "KeepAlive": True,
            "WorkingDirectory": str(home),
            "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            "StandardOutPath": str(log), "StandardErrorPath": str(log),
        })
    return agent, loaded, payload


def check_port(sites_path):
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            pass
    except OSError:
        return
    sites = json.loads(sites_path.read_bytes()) if sites_path.exists() else {}
    if not isinstance(sites, dict) or HOST not in sites:
        raise RuntimeError("La porta 8025 è occupata; non pubblico il servizio che la sta usando.")
    try:
        with urlopen(f"http://127.0.0.1:{PORT}/api/status", timeout=3) as response:
            status = json.load(response)
        if status.get("service") == "milo" and status.get("demo") is False:
            return
    except (URLError, ValueError):
        pass
    raise RuntimeError("La porta 8025 non risponde come Milo; non pubblico quel servizio.")


def verify_service():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urlopen(ORIGIN + "/api/status", timeout=5) as response:
                status = json.load(response)
            if status.get("service") == "milo" and status.get("demo") is False:
                try:
                    urlopen(ORIGIN + "/api/state", timeout=5).close()
                except HTTPError as error:
                    if error.code == 401:
                        return status
                raise RuntimeError("La verifica dell'accesso privato non è riuscita.")
        except (URLError, json.JSONDecodeError):
            time.sleep(2)
    raise RuntimeError("Il dominio non risponde ancora come Milo. La configurazione è salvata, "
                       "ma il server non è verificato; controlla Grog sul Mac.")


def main():
    if sys.platform != "darwin":
        raise SystemExit("Esegui questo comando sul Mac Pro: qui deve vivere l'archivio email.")
    root = Path(__file__).resolve().parent.parent
    home = Path.home()
    if not (root / ".venv/bin/python").is_file():
        raise SystemExit("Prima esegui uv sync --frozen in questo checkout.")
    try:
        agent, loaded, payload = check_grog_agent(home)
        check_port(home / ".grog/sites.json")
        register_site(home / ".grog/sites.json", root)
        if not loaded:
            if payload:
                if agent.exists():
                    raise RuntimeError("Il launch agent è cambiato durante la preparazione; riprova.")
                log = home / "Library/Logs/grog-serve.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                log.touch(mode=0o600, exist_ok=True)
                log.chmod(0o600)
                atomic_write(agent, payload)
            subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(agent)], check=True)
        print("Milo registrato nel servizio permanente Grog. Verifico HTTPS…", flush=True)
        status = verify_service()
        url = ORIGIN
        if not status.get("initialized"):
            legacy = root / ".data/live"
            archive = legacy if (legacy / "mail.sqlite").exists() else home / "Library/Application Support/Milo"
            with sqlite3.connect(f"{(archive / 'mail.sqlite').as_uri()}?mode=ro", uri=True) as database:
                row = database.execute("SELECT value FROM settings WHERE key='bootstrap'").fetchone()
            if row and json.loads(row[0]):
                url += "#setup=" + json.loads(row[0])
        subprocess.run(["open", url], check=True)
        print(ORIGIN + " è attivo. Nel browser scegli la passphrase, poi collega Google.")
        print("Questo avvio non autorizza ancora una casella Google: serve Continua con Google.")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, sqlite3.Error) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
