from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from milo.app import create_app
from milo.public import create_public_app

PRIVATE = 'https://owner.example.ts.net:8443'
OWNER = {'Tailscale-User-Login': 'owner@example.com'}


def test_public_surface_has_no_archive_login_or_application():
    with TestClient(create_public_app(PRIVATE)) as client:
        root = client.get('/')
        assert root.status_code == 200 and 'La tua posta.' in root.text
        assert not any(value in root.text for value in ('password', 'app.js', PRIVATE, '<form'))
        for path in ('/api/login', '/api/setup', '/api/status', '/api/state', '/api/accounts', '/api/messages',
                     '/api/client/messages', '/api/client/thread?account=a&thread=t', '/static/replica.js', '/static/search-worker.js', '/api/messages/one/attachments/0', '/api/drafts', '/static/app.js', '/docs', '/openapi.json'):
            for method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
                response = client.request(method, path, headers={**OWNER, 'Cookie': 'milo_session=forged'},
                                          json={'password': 'attempt'})
                assert response.status_code == 404, (method, path)
                assert 'set-cookie' not in response.headers
        assert 'unregister' in client.get('/sw.js').text


def test_public_oauth_relay_has_fixed_destination_and_no_credentials():
    with TestClient(create_public_app(PRIVATE)) as client:
        response = client.get('/api/oauth/google/callback', params={'state': 'state', 'code': 'code',
                              'redirect_uri': 'https://evil.example', 'next': 'https://evil.example'}, follow_redirects=False)
        target = urlsplit(response.headers['location'])
        assert response.status_code == 303 and target.netloc == urlsplit(PRIVATE).netloc
        assert parse_qs(target.query) == {'state': ['state'], 'code': ['code']}
        assert 'set-cookie' not in response.headers
        assert client.get('/api/oauth/google/callback', follow_redirects=False).headers['location'] == '/'
    with TestClient(create_public_app()) as client:
        assert client.get('/api/oauth/google/callback?state=x&code=y', follow_redirects=False).headers['location'] == '/'


def test_private_owner_access_never_checks_password_and_rejects_other_devices(tmp_path, monkeypatch):
    app = create_app(tmp_path, private_url=PRIVATE, tailscale_owners=['owner@example.com'], secure_cookies=True,
                     public_url='https://public.example')
    monkeypatch.setattr(app.state.engine, 'sync_all', lambda: [])
    monkeypatch.setattr(app.state.store, 'login', lambda value: pytest.fail('Password login must be unreachable'))
    with TestClient(app, base_url=PRIVATE, client=('127.0.0.1', 40000)) as client:
        for path in ('/', '/api/status', '/api/state', '/static/app.js'):
            assert client.get(path).status_code == 404
        status = client.get('/api/status', headers=OWNER)
        assert status.json()['authenticated'] and status.json()['access'] == 'tailscale'
        cookie = status.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
        assert app.state.store.valid_session(client.cookies.get('milo_session'))
        assert client.get('/api/state', headers=OWNER).status_code == 200
        assert client.get('/api/state').status_code == 404  # Even with an actual valid session.
        assert client.get('/api/state', headers={'Tailscale-User-Login': 'other@example.com'}).status_code == 404
        for path in ('/api/login', '/api/setup', '/api/setup/authorize', '/api/setup/status', '/api/logout'):
            for method in ('GET', 'POST'):
                assert client.request(method, path, headers=OWNER, json={'password': 'guess'}).status_code == 404
        assert client.put('/api/settings/appearance', headers={**OWNER, 'Origin': 'https://public.example'},
                          json={'theme': 'dark'}).status_code == 403
        assert client.put('/api/settings/appearance', headers={**OWNER, 'Origin': PRIVATE},
                          json={'theme': 'dark'}).status_code == 200
        callback = client.get('/api/oauth/google/callback?state=bad&error=access_denied', headers=OWNER,
                              follow_redirects=False)
        assert callback.headers['location'].startswith(PRIVATE + '/#google_error=')
        assert app.state.google.redirect_uri == 'https://public.example/api/oauth/google/callback'


def test_identity_header_from_network_connection_is_untrusted(tmp_path):
    app = create_app(tmp_path, private_url=PRIVATE, tailscale_owners=['owner@example.com'], secure_cookies=True)
    app.state.engine.sync_all = lambda: []
    with TestClient(app, base_url=PRIVATE, client=('100.100.1.2', 40000)) as client:
        assert client.get('/api/state', headers=OWNER).status_code == 404


def test_container_trusts_only_explicit_published_gateway(tmp_path):
    from ipaddress import AddressValueError

    gateway = '172.29.184.1'
    app = create_app(tmp_path / 'container', private_url=PRIVATE, tailscale_owners=['owner@example.com'],
                     secure_cookies=True, proxy_peers=[gateway])
    app.state.engine.sync_all = lambda: []
    with TestClient(app, client=(gateway, 43210)) as client:
        assert client.get('/api/state').status_code == 404
        assert client.get('/api/state', headers=OWNER).status_code == 200
        assert client.get('/api/state', headers={'Tailscale-User-Login': 'other@example.com'}).status_code == 404
        assert client.post('/api/login', headers=OWNER, json={'password': 'guess'}).status_code == 404
    app = create_app(tmp_path / 'other', private_url=PRIVATE, tailscale_owners=['owner@example.com'],
                     secure_cookies=True, proxy_peers=[gateway])
    app.state.engine.sync_all = lambda: []
    with TestClient(app, client=('172.29.184.2', 43210)) as client:
        assert client.get('/api/state', headers=OWNER).status_code == 404
    for invalid in ('0.0.0.0', '8.8.8.8', '172.29.184.0/24'):
        with pytest.raises((ValueError, AddressValueError)):
            create_app(tmp_path / invalid.replace('/', '_'), proxy_peers=[invalid])


def test_only_the_local_landing_can_report_pixel_opens(tmp_path, monkeypatch):
    app = create_app(tmp_path, private_url=PRIVATE, tailscale_owners=['owner@example.com'], secure_cookies=True,
                     public_url='https://public.example')
    monkeypatch.setattr(app.state.engine, 'sync_all', lambda: [])
    token = 'A' * 24
    with TestClient(app, base_url='http://127.0.0.1:8029', client=('127.0.0.1', 40000)) as local:
        assert local.post(f'/internal/opened/{token}').status_code == 204
        assert local.get(f'/internal/opened/{token}').status_code == 404
        assert local.get('/api/deliveries').status_code == 404
    with TestClient(app, base_url=PRIVATE, client=('127.0.0.1', 40000)) as proxied:
        assert proxied.post(f'/internal/opened/{token}').status_code == 404
    with TestClient(app, base_url='http://127.0.0.1:8029', client=('172.29.184.1', 40000)) as gateway:
        assert gateway.post(f'/internal/opened/{token}').status_code == 404
