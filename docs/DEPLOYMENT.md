# Permanent service on the Mac Pro with Grog

The requested host is the owner's Mac Pro, reachable over Tailscale. Deployment
requires an authorized SSH session; at the time of this change, Tailscale's
interactive SSH check has prevented access. **This is prepared configuration,
not evidence of a completed deployment or reserved domain.**

## Prepare the host

Use a dedicated checkout, for example `~/Sites/milo`, and Python 3.11+ with uv:

```sh
git clone https://github.com/turinglabsorg/milo.git ~/Sites/milo
cd ~/Sites/milo
uv sync --frozen
```

Keep one authoritative archive on this host. Do not run another process against
that same SQLite database. Configure Ollama on this host, or set
`MILO_OLLAMA_URL` to an explicitly selected reachable Ollama service; cloud
processing and automatic analysis are enabled by the owner in Milo settings.

## Add the static Grog site

Merge this entry into `~/.grog/sites.json`, preserving every existing site:

```json
{
  "milo.grooooog.space": {
    "run": ".venv/bin/python scripts/serve.py",
    "cwd": "~/Sites/milo",
    "port": 8025
  }
}
```

`scripts/serve.py` launches the production Uvicorn service on loopback with
secure cookies, the fixed HTTPS origin and a host-local persistent archive.
Grog's existing `serve` launch agent supervises and restarts the site command.
Use the owner's Grog CLI, not the unrelated GNU groff `grog` binary installed on
some Linux systems. Inspect the existing Grog installation and launch agent
before starting a second `grog serve` process. Grog hot-reloads its sites map.

Default origin is `https://milo.grooooog.space`; change `MILO_PUBLIC_URL` if a
registered static domain is selected instead. The OAuth callback must match
that origin exactly. Uvicorn removes query strings from its access logs. Inspect
the relay's request inspection/logging too; OAuth authorization codes must not
be retained there.

## Initialize and verify

Read the first-start bootstrap code locally from the service host's private
archive. Open the HTTPS origin, enter that one-time code and choose the owner's
passphrase; never publish a bootstrap-bearing URL or a demo archive. Configure
the Google web client using [Google setup](GOOGLE.md).

Before treating deployment as ready:

- Check HTTPS and confirm unauthenticated `/api/state` returns 401.
- Confirm setup is one-time and cookies are Secure/HttpOnly.
- Authorize a real mailbox; verify sync and persistence across a service restart.
- Open the same origin on Linux and iPhone and confirm they share settings,
  account identities and message changes.
- Check the Grog launch agent survives logout/reboot as configured on this Mac.

The Linux launcher can point to the shared service by setting `MILO_SERVER_URL`
or by writing its origin to `.data/server.json` as `{"url":"https://milo.grooooog.space"}`.
