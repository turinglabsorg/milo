from fastapi.testclient import TestClient

from milo.app import create_app


def test_client_shell_is_revalidated_by_embedded_webviews(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        for path in ('/', '/sw.js', '/static/app.js', '/static/style.css'):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-cache'
            assert response.headers['etag']
        sw = client.get('/sw.js').text
        assert "{cache: 'reload'}" in sw and "{cache:'no-cache'}" in sw
