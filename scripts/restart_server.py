#!/usr/bin/env python3
"""Gracefully restart only the verified Milo process supervised by Grog."""
import json
import os
import signal
import subprocess
import urllib.request
from pathlib import Path


def main():
    with urllib.request.urlopen('http://127.0.0.1:8025/api/status', timeout=5) as response:
        status = json.load(response)
    if status.get('service') != 'milo' or status.get('demo'):
        raise SystemExit('Port 8025 is not the production Milo service')
    pids = subprocess.check_output(['lsof', '-t', '-nP', '-iTCP:8025', '-sTCP:LISTEN'], text=True).split()
    if len(set(pids)) != 1:
        raise SystemExit('Milo listener is not unique')
    pid = int(pids[0])
    command = subprocess.check_output(['ps', '-p', str(pid), '-o', 'command='], text=True)
    root = Path(__file__).resolve().parent.parent
    if str(root / 'scripts/serve.py') not in command:
        raise SystemExit('Milo listener does not match this deployment')
    os.kill(pid, signal.SIGTERM)
    print('Milo restart requested; the existing Grog supervisor will relaunch it.')


if __name__ == '__main__':
    main()
