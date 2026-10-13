#!/usr/bin/env python3
"""Install the tested server supervisor in the system boot domain."""
import argparse
import os
import plistlib
import pwd
import subprocess
from pathlib import Path

LABEL = 'space.grooooog.milo.server'
ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', required=True)
    parser.add_argument('--node', type=Path, required=True)
    args = parser.parse_args()
    if not args.node.is_file() or not os.access(args.node, os.X_OK):
        raise SystemExit('Supply the existing Node executable.')
    if os.getuid() != 0:
        raise SystemExit('Run with sudo to install the system boot service.')
    account = pwd.getpwnam(args.user)
    if not account.pw_uid or ROOT.stat().st_uid != account.pw_uid:
        raise SystemExit('The checkout must belong to the non-root server owner.')
    home = Path(account.pw_dir)
    archive = home / 'Library/Application Support/Milo'
    config = archive / 'private-server.json'
    if not config.is_file() or config.is_symlink() or config.stat().st_uid != account.pw_uid or config.stat().st_mode & 0o077:
        raise SystemExit('The existing protected owner archive is required.')
    for path in (ROOT / '.venv/bin/python', ROOT / 'scripts/mac_docker_watch.py', archive / 'grog-sites.json'):
        if not path.is_file():
            raise SystemExit('Prepare and verify the Docker deployment before installing autostart.')
    log = home / 'Library/Logs/Milo-server.log'
    log.touch(mode=0o600, exist_ok=True)
    os.chown(log, account.pw_uid, account.pw_gid)
    log.chmod(0o600)
    payload = {'Label': LABEL, 'UserName': args.user, 'RunAtLoad': True, 'KeepAlive': True,
               'ThrottleInterval': 20, 'WorkingDirectory': str(ROOT),
               'ProgramArguments': [str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/mac_docker_watch.py')],
               'EnvironmentVariables': {'HOME': str(home), 'PATH': f'{ROOT / ".venv/bin"}:{args.node.parent}:{home / ".local/bin"}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                                        'MILO_NODE': str(args.node),
                                        'MILO_DOCKER_CONTEXT': 'desktop-linux'},
               'StandardOutPath': str(log), 'StandardErrorPath': str(log)}
    target = Path('/Library/LaunchDaemons') / (LABEL + '.plist')
    data = plistlib.dumps(payload)
    if target.exists() and target.read_bytes() != data:
        current = plistlib.loads(target.read_bytes())
        if any(current.get(key) != payload[key] for key in ('Label', 'UserName', 'ProgramArguments')):
            raise SystemExit('An existing different Milo boot service will not be replaced.')
        subprocess.run(['launchctl', 'bootout', 'system/' + LABEL], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    if not target.exists() or target.read_bytes() != data:
        temporary = target.with_suffix('.tmp')
        temporary.write_bytes(data)
        temporary.chmod(0o644)
        os.replace(temporary, target)
    subprocess.run(['plutil', '-lint', str(target)], check=True)
    loaded = subprocess.run(['launchctl', 'print', 'system/' + LABEL], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL).returncode == 0
    if not loaded:
        subprocess.run(['launchctl', 'bootstrap', 'system', str(target)], check=True)
    print('Milo server boot service installed. Containers and archive remain independent of the client.')


if __name__ == '__main__':
    main()
