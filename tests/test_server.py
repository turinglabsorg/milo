import json
import os
import plistlib
import shlex
import subprocess
import sys
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from milo import __main__ as cli
from scripts import mac_server


def test_register_preserves_existing_sites_and_private_backup(tmp_path):
    path = tmp_path / "sites.json"
    original = b'{"existing.example":{"port":4100,"custom":"keep this"}}\n'
    path.write_bytes(original)
    root = tmp_path / "A project with spaces"
    assert mac_server.register_site(path, root)
    sites = json.loads(path.read_bytes())
    assert sites["existing.example"] == {"port": 4100, "custom": "keep this"}
    assert shlex.split(sites[mac_server.HOST]["run"]) == [
        str(root / ".venv/bin/python"), str(root / "scripts/serve.py")]
    assert sites[mac_server.HOST]["cwd"] == str(root)
    backup = path.with_name("sites.json.milo-backup")
    assert backup.read_bytes() == original
    assert path.stat().st_mode & 0o777 == 0o600
    assert backup.stat().st_mode & 0o777 == 0o600
    installed = path.read_bytes()
    assert not mac_server.register_site(path, root)
    assert path.read_bytes() == installed
    assert backup.read_bytes() == original


@pytest.mark.parametrize("existing", [
    b'{"milo.grooooog.space":{"dir":"~/other-project"}}',
    b'{"another.example":{"port":"8025"}}',
    b'{"truncated":',
    b'["not a sites map"]',
])
def test_registration_refuses_conflicts_and_invalid_configuration(tmp_path, existing):
    path = tmp_path / "sites.json"
    path.write_bytes(existing)
    with pytest.raises((RuntimeError, ValueError)):
        mac_server.register_site(path, tmp_path / "milo")
    assert path.read_bytes() == existing
    assert not path.with_name("sites.json.milo-backup").exists()


def test_existing_grog_agent_is_reused_without_changes(tmp_path, monkeypatch):
    agent = tmp_path / "Library/LaunchAgents" / (mac_server.LABEL + ".plist")
    agent.parent.mkdir(parents=True)
    original = plistlib.dumps({"Label": mac_server.LABEL,
                              "ProgramArguments": ["/custom/node", "/custom/grog/index.js", "serve"],
                              "KeepAlive": True, "OtherSetting": "preserve"})
    agent.write_bytes(original)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(mac_server.subprocess, "run", run)
    assert mac_server.check_grog_agent(tmp_path) == (agent, True, None)
    assert agent.read_bytes() == original
    assert calls == [["launchctl", "print", f"gui/{os.getuid()}/{mac_server.LABEL}"]]


def test_custom_grog_sites_file_is_detected_before_registration(tmp_path, monkeypatch):
    agent = tmp_path / "Library/LaunchAgents" / (mac_server.LABEL + ".plist")
    agent.parent.mkdir(parents=True)
    agent.write_bytes(plistlib.dumps({"Label": mac_server.LABEL, "ProgramArguments": ["grog", "serve"],
                                     "EnvironmentVariables": {"GROG_SITES": "/custom/sites.json"}}))
    monkeypatch.setattr(mac_server.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    with pytest.raises(RuntimeError, match="personalizzato"):
        mac_server.check_grog_agent(tmp_path)
    assert not (tmp_path / ".grog/sites.json").exists()


def test_activation_requires_the_mac(monkeypatch):
    monkeypatch.setattr(mac_server.sys, "platform", "linux")
    with pytest.raises(SystemExit, match="Mac Pro"):
        mac_server.main()


def test_unrelated_running_service_is_not_published(tmp_path, monkeypatch):
    monkeypatch.setattr(mac_server.socket, "create_connection", lambda *args, **kwargs: BytesIO())
    path = tmp_path / "sites.json"
    path.write_bytes(b'{"other.example":{"port":4100}}')
    with pytest.raises(RuntimeError, match="occupata"):
        mac_server.check_port(path)
    assert json.loads(path.read_bytes()) == {"other.example": {"port": 4100}}


@pytest.mark.parametrize("state_status", [401, 200])
def test_ready_requires_https_and_unauthenticated_private_api(state_status, monkeypatch):
    calls = []

    def open_url(url, **kwargs):
        calls.append(url)
        if url.endswith("/api/status"):
            return BytesIO(b'{"service":"milo","demo":false,"initialized":false}')
        if state_status == 401:
            raise HTTPError(url, 401, "Private archive", {}, None)
        return BytesIO(b'{}')

    monkeypatch.setattr(mac_server, "urlopen", open_url)
    if state_status == 401:
        assert mac_server.verify_service()["service"] == "milo"
    else:
        with pytest.raises(RuntimeError, match="accesso privato"):
            mac_server.verify_service()
    assert calls == [mac_server.ORIGIN + "/api/status", mac_server.ORIGIN + "/api/state"]


@pytest.mark.parametrize("quiet", [True, False])
def test_service_bootstrap_code_is_kept_out_of_logs(tmp_path, monkeypatch, capsys, quiet):
    code = "private-first-start-code"
    monkeypatch.setattr(cli, "create_app", lambda *args: SimpleNamespace(
        state=SimpleNamespace(store=SimpleNamespace(bootstrap=code))))
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["milo", "--data", str(tmp_path), *(["--quiet-bootstrap"] if quiet else [])])
    cli.main()
    assert code not in capsys.readouterr().out
