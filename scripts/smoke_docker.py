#!/usr/bin/env python3
"""Exercise the actual Docker service with a disposable, provider-disabled archive."""
import json
import os
import subprocess
import tempfile
import time
from email.message import EmailMessage
from pathlib import Path

import httpx

from milo.mail import parse_message
from milo.store import Store

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory(prefix='milo-docker-smoke-') as directory:
        archive = Path(directory) / 'archive'
        store = Store(archive)
        account = store.add_account({'name': 'Fixture', 'email': 'owner@example.com', 'username': 'owner@example.com',
                                     'password': 'isolated-fixture', 'imap_host': 'example.invalid', 'imap_port': 993,
                                     'smtp_host': 'example.invalid', 'smtp_port': 465, 'smtp_security': 'tls',
                                     'color': '#2563eb'})
        store.update_account(account, {'enabled': False})
        mail = EmailMessage()
        mail['From'] = 'Other <other@example.com>'
        mail['To'] = 'owner@example.com'
        mail['Subject'] = 'Persistent fixture'
        mail.set_content('An isolated message.')
        store.upsert_message(parse_message(mail.as_bytes(), account, 'INBOX', '1', 1))
        store.close()
        config = archive / 'private-server.json'
        config.write_text(json.dumps({'url': 'https://owner.example.ts.net:8443', 'owners': ['owner@example.com']}))
        config.chmod(0o600)
        override = Path(directory) / 'override.json'
        override.write_text(json.dumps({'services': {'server': {'image': 'milo-server:staging'}}}))
        environment = {**os.environ, 'MILO_ARCHIVE': str(archive), 'MILO_UID': str(os.getuid()),
                       'MILO_GID': str(os.getgid()), 'MILO_LANDING_PORT': '18025', 'MILO_PRIVATE_PORT': '18029'}
        command = ['docker', 'compose', '-p', 'milo-smoke', '-f', str(ROOT / 'compose.yaml'), '-f', str(override)]

        def compose(*args):
            subprocess.run(command + list(args), env=environment, check=True)

        try:
            compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '90')
            with httpx.Client(timeout=10) as client:
                public, private = 'http://127.0.0.1:18025', 'http://127.0.0.1:18029'
                assert client.get(public).headers.get('X-Milo-Surface') == 'public'
                for path in ('/api/state', '/api/login', '/static/app.js'):
                    assert client.get(public + path, headers={'Tailscale-User-Login': 'owner@example.com'}).status_code == 404
                assert client.get(private + '/api/state').status_code == 404
                assert client.get(private + '/api/state', headers={'Tailscale-User-Login': 'other@example.com'}).status_code == 404
                owner = {'Tailscale-User-Login': 'owner@example.com'}
                state = client.get(private + '/api/state', headers=owner)
                assert state.status_code == 200 and state.json()['counts']['inbox'] == 1
                profile = {'name': 'Test Owner', 'aliases': ['Owner'], 'context': '', 'reply_language': 'auto'}
                assert client.put(private + '/api/settings/identity', headers=owner, json=profile).status_code == 200
                compose('restart', 'server')
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    try:
                        state = client.get(private + '/api/state', headers=owner)
                        if state.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.25)
                assert state.status_code == 200 and state.json()['identity'] == profile
                assert state.json()['counts']['inbox'] == 1
                assert client.get(private + '/api/recap', headers=owner).status_code == 200
            print(json.dumps({'container_runtime': True, 'owner_guard': True, 'public_surface_private_404': True,
                              'archive_and_configuration_survive_restart': True}))
        finally:
            compose('down')


if __name__ == '__main__':
    main()
