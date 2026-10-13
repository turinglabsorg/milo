import json

import pytest

from scripts import launch


def test_shared_launcher_opens_owner_setup_without_printing_private_link(tmp_path, monkeypatch, capsys):
    data = tmp_path / ".data"
    data.mkdir()
    server = "https://milo.example"
    (data / "server.json").write_text(json.dumps({"url": server}))
    token = "x" * 32
    url = server + "#setup=" + token
    pairing = data / "setup.url"
    pairing.write_text(url)
    pairing.chmod(0o600)
    monkeypatch.setattr(launch, "ROOT", tmp_path)
    monkeypatch.setattr(launch, "DEMO", False)
    monkeypatch.delenv("MILO_SERVER_URL", raising=False)
    opened = []
    monkeypatch.setattr(launch, "open_window", opened.append)
    launch.main()
    assert opened == [url]
    assert token not in capsys.readouterr().out
    assert not (data / "live").exists()


@pytest.mark.parametrize("url", [
    "https://other.example#setup=" + "x" * 32,
    "https://milo.example?forward=elsewhere#setup=" + "x" * 32,
    "https://milo.example/another-path#setup=" + "x" * 32,
    "https://milo.example#setup=invalid",
])
def test_owner_authorization_is_bound_to_the_configured_service(tmp_path, monkeypatch, url):
    data = tmp_path / ".data"
    data.mkdir()
    pairing = data / "setup.url"
    pairing.write_text(url)
    pairing.chmod(0o600)
    monkeypatch.setattr(launch, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="non corrisponde"):
        launch.owner_setup_url("https://milo.example")


def test_owner_authorization_file_must_be_private(tmp_path, monkeypatch):
    data = tmp_path / ".data"
    data.mkdir()
    pairing = data / "setup.url"
    pairing.write_text("https://milo.example#setup=" + "x" * 32)
    monkeypatch.setattr(launch, "ROOT", tmp_path)
    pairing.chmod(0o644)
    with pytest.raises(RuntimeError, match="protetta"):
        launch.owner_setup_url("https://milo.example")
    pairing.chmod(0o600)
    private = data / "private.url"
    pairing.rename(private)
    pairing.symlink_to(private)
    with pytest.raises(RuntimeError, match="protetta"):
        launch.owner_setup_url("https://milo.example")


def test_private_device_access_ignores_old_public_setup_link(tmp_path, monkeypatch):
    data = tmp_path / '.data'
    data.mkdir()
    (data / 'setup.url').write_text('https://public.example#setup=' + 'x' * 32)
    monkeypatch.setattr(launch, 'ROOT', tmp_path)
    url = 'https://owner.example.ts.net:8443'
    assert launch.owner_setup_url(url) == url
