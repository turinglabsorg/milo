#!/usr/bin/env python3
"""Keep the Docker server and its dedicated Grog relay available under launchd."""
import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME_DIR = Path.home()
ARCHIVE = HOME_DIR / 'Library/Application Support/Milo'
STOP = threading.Event()


def main():
    docker = shutil.which('docker')
    node = os.environ.get('MILO_NODE') or shutil.which('node')
    grog = HOME_DIR / '.claude/tools/grog/index.js'
    grog_cli = shutil.which('grog')
    if not docker or not node or not (grog_cli or grog.is_file()):
        raise SystemExit('Docker, Node and the existing owner Grog installation are required.')
    context = os.environ.get('MILO_DOCKER_CONTEXT', 'desktop-linux')
    base = [docker, '--context', context]
    environment = {**os.environ, 'MILO_ARCHIVE': str(ARCHIVE), 'MILO_UID': str(os.getuid()),
                   'MILO_GID': str(os.getgid()), 'GROG_SITES': str(ARCHIVE / 'grog-sites.json'),
                   'GROG_BOARD_DB': str(ARCHIVE / 'grog-board.sqlite')}
    compose = base + ['compose', '-f', str(ROOT / 'compose.yaml'), '-p', 'milo']
    backend = Path('/Applications/Docker.app/Contents/MacOS/com.docker.backend')
    engine = None
    relay = None
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: STOP.set())

    def run(command, capture=False):
        try:
            return subprocess.run(command, cwd=ROOT, env=environment, timeout=210,
                                  stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, text=True)
        except (OSError, subprocess.TimeoutExpired):
            return None

    print('Milo Docker supervisor started.', flush=True)
    try:
        while not STOP.is_set():
            ready = run(base + ['info', '--format', '{{.ServerVersion}}'])
            if not ready or ready.returncode:
                if backend.is_file() and (engine is None or engine.poll() is not None):
                    engine = subprocess.Popen([str(backend)], cwd=HOME_DIR, env=environment,
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                STOP.wait(10)
                continue
            ids = run(compose + ['ps', '-q', 'server'], capture=True)
            container = ids.stdout.strip() if ids and not ids.returncode else ''
            if not container:
                run(compose + ['up', '-d', '--no-build', '--wait'])
            else:
                health = run(base + ['inspect', '--format', '{{.State.Status}} {{.State.Health.Status}}', container],
                             capture=True)
                if not health or health.returncode or health.stdout.strip() == 'running unhealthy':
                    run(compose + ['restart', 'server'])
            if relay is None or relay.poll() is not None:
                relay = subprocess.Popen([node, grog_cli or str(grog), 'serve'], cwd=HOME_DIR, env=environment,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            STOP.wait(15)
    finally:
        if relay and relay.poll() is None:
            relay.terminate()
            try:
                relay.wait(timeout=10)
            except subprocess.TimeoutExpired:
                relay.kill()
        # Docker owns container restart policy. Do not stop other applications
        # or the engine when only this supervisor is being replaced.
        print('Milo Docker supervisor stopped.', flush=True)


if __name__ == '__main__':
    main()
