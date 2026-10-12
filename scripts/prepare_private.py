#!/usr/bin/env python3
"""Prepare owner-only access on this Mac. Does not enable Serve or Funnel."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from milo.private import private_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner-device', help='Exact Tailscale DNS name of another device owned by this user')
    parser.add_argument('--new-archive', action='store_true', help='Explicitly initialize a new host without an existing archive')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('Run this deployment helper on the Milo Mac server')
    status = json.loads(subprocess.check_output(['tailscale', 'status', '--json'], text=True))
    me = status['Self']
    users = status['User']
    owners = {users[str(me['UserID'])]['LoginName']}
    if args.owner_device:
        matches = [peer for peer in status.get('Peer', {}).values()
                   if peer.get('DNSName', '').rstrip('.') == args.owner_device.rstrip('.')]
        if len(matches) != 1 or matches[0].get('Tags'):
            raise SystemExit('The explicitly selected owner device was not found or is tagged')
        owners.add(users[str(matches[0]['UserID'])]['LoginName'])
    if not all(owners) or me.get('Tags'):
        raise SystemExit('Owner identity is unavailable; refusing to configure access')
    root = Path(__file__).resolve().parent.parent
    archive = Path(os.environ.get('MILO_DATA', str(Path.home() / 'Library/Application Support/Milo')))
    if (root / '.data/live/mail.sqlite').exists():
        archive = root / '.data/live'
    if not (archive / 'mail.sqlite').exists() and not args.new_archive:
        raise SystemExit('Existing Milo archive not found; refusing to create another archive')
    archive.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = archive / 'private-server.json'
    if path.exists():
        private_config(path)
        print('Existing private access configuration preserved.')
        return
    value = {'url': 'https://' + me['DNSName'].rstrip('.') + ':8443', 'owners': sorted(owners)}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream)
    private_config(path)
    print('Owner-only configuration prepared. Public port: 8025; protected loopback backend: 8029.')


if __name__ == '__main__':
    main()
