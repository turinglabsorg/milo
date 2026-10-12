# Docker Mac server and Omarchy client

The Mac Pro runs the server and authoritative archive. The Omarchy client runs
on the laptop and keeps its own persistent cache. The public domain serves only
the landing and fixed Google OAuth relay. Private mail uses Tailscale Serve
HTTPS; other identities, anonymous requests and password/setup routes get 404.

## Persistent archive and access

Keep `~/Library/Application Support/Milo` outside the source checkout and image.
Its existing mode-0600 `private-server.json` contains the fixed Tailscale HTTPS
origin and exact owner identities. Provider credentials remain encrypted in this
archive. Never bake the archive, client cache, credential files or `.data` into
an image; the Docker context uses an explicit allowlist.

For a deliberately new deployment, `scripts/prepare_private.py` prepares owner
configuration from Tailscale metadata. It does not enable Serve/Funnel or replace
an existing handler. The configured private handler stays:

```sh
tailscale serve --bg --https=8443 http://127.0.0.1:8029
```

The owner must be authorized on the tailnet. Tailscale strips supplied identity
headers and adds its attested caller identity; see [the identity-header docs](https://tailscale.com/kb/1312/serve#identity-headers).

## Build and verify

Use the existing Docker Desktop runtime on the Mac, the owner's Grog installation,
Python and uv for host supervision. SSH over Tailscale is the deployment transport.
Use the `desktop-linux` context explicitly, preserving other runtimes/projects.

```sh
uv sync --frozen
MILO_ARCHIVE="$HOME/Library/Application Support/Milo" docker compose build
docker tag milo-server:current milo-server:staging
uv run python scripts/smoke_docker.py
```

The smoke check starts an isolated container on temporary loopback ports with a
provider-disabled fixture archive. It verifies public/private separation, owner
rejection, configuration and message persistence through a container restart,
then removes only its own container/network.

Production publishes **only** `127.0.0.1:8025` and `127.0.0.1:8029`. Do not change
these to `0.0.0.0`. The dedicated bridge uses `10.241.84.0/24`, gateway
`10.241.84.1`; check existing network ranges before creation. That exact gateway
is supplied as a trusted proxy peer; arbitrary network callers remain rejected.
The application disables forwarded-client-IP processing. The container runs as
the archive owner, with a read-only image, limited temporary storage, dropped
capabilities and a health check for both surfaces.

## Production activation and boot

After verifying the image, `scripts/mac_docker_register.py` moves **only Milo**
from the shared Grog site map to an archive-local `grog-sites.json` containing the
landing port. It preserves all other sites and a protected backup. Wait for the
old Python listeners to stop before starting Docker against the same archive.

```sh
MILO_ARCHIVE="$HOME/Library/Application Support/Milo" docker compose up -d --no-build --wait
sudo .venv/bin/python scripts/mac_docker_install.py --user "$(id -un)"
```

The system LaunchDaemon `space.grooooog.milo.server` runs as the non-root archive
owner, independently of the Omarchy window and GUI login. Its supervisor checks
Docker, starts the installed backend if absent, activates the Compose service,
and keeps a dedicated **Grog serve** relay for Milo. Docker's
[`unless-stopped` restart policy](https://docs.docker.com/reference/compose-file/services/#restart)
retains the service after runtime restarts. The supervisor restarts an unhealthy
Milo container without stopping other applications or the Docker engine.

Docker Desktop's normal [startup setting](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
starts at sign-in. The system boot supervisor supplies the additional headless
startup path; a full machine power-cycle is a separate verification gate from a
container restart. FileVault may require a human disk unlock before any server can
start; do not disable disk protection to hide that constraint.

Verify the boot job is loaded in the **system** domain, container health/restart
policy, loopback port bindings, unchanged archive mount, private owner access and
public 404 responses. Verify message/account/configuration persistence after a
controlled **Milo-only** restart. Do not reboot the Mac or restart shared services
merely to test a single application.

## Client and OAuth

The laptop launcher's `.data/server.json` points to the verified private HTTPS
origin. Device identity replaces a password/code. Downloaded client data persists
on that device and can be read offline, as required by [CLIENT_CACHE.md](CLIENT_CACHE.md).

Keep Google's registered redirect URI on the static public domain:
`https://milo.grooooog.space/api/oauth/google/callback`. The public handler relays
only bounded state/code/error values to the fixed private callback. PKCE,
one-time state and browser nonce are checked by the private backend. Both
surfaces exclude OAuth query parameters from access logs.
