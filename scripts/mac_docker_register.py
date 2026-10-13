#!/usr/bin/env python3
"""Move only Milo from the shared process supervisor to its Docker-backed relay."""
import json
import os
import shlex
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = 'milo.grooooog.space'


def write(path, payload):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write((json.dumps(payload, indent=2) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)


def main():
    path = Path.home() / '.grog/sites.json'
    before = path.read_bytes()
    sites = json.loads(before)
    current = sites.get(HOST)
    expected = {'run': f'{shlex.quote(str(ROOT / ".venv/bin/python"))} {shlex.quote(str(ROOT / "scripts/serve.py"))}',
                'cwd': str(ROOT), 'port': 8025}
    if current is not None and current != expected:
        raise SystemExit('The existing Milo site does not match this deployment.')
    archive = Path.home() / 'Library/Application Support/Milo'
    if not (archive / 'private-server.json').is_file():
        raise SystemExit('The protected archive is missing.')
    write(archive / 'grog-sites.json', {HOST: {'port': 8025}})
    if path.read_bytes() != before:
        raise SystemExit('The shared site configuration changed; no shared entries were changed.')
    if current is not None:
        backup = path.with_name('sites.json.milo-docker-backup')
        if not backup.exists():
            backup.write_bytes(before)
            backup.chmod(0o600)
        del sites[HOST]
        write(path, sites)
    print('Only Milo moved to the dedicated persistent Docker relay; other site entries are preserved.')


if __name__ == '__main__':
    main()
