# Permanent service on the Mac Pro with Grog

Milo is a server on the owner's Mac Pro. It stores email, accounts, preferences
and drafts there; Linux and iPhone connect to the same HTTPS service. Tailscale
can be used to reach the Mac for administration.

The owner's deployment was activated on 2026-10-11 at
`https://milo.grooooog.space`. HTTPS returned the real, non-demo Milo status,
and unauthenticated `/api/state` returned 401. The Mac's Grog launch agent is
loaded with `KeepAlive`; the archive exists at
`~/Library/Application Support/Milo`. The served JavaScript, CSS and Geist font
match this checkout. Initial passphrase setup and real Google authorization
remain pending; see [validation](VALIDATION.md) for the limits of these checks.

## Prepare the host

Use a dedicated checkout, for example `~/Sites/milo`, and Python 3.11+ with uv:

```sh
git clone https://github.com/turinglabsorg/milo.git ~/Sites/milo
cd ~/Sites/milo
uv sync --frozen
uv run --frozen python scripts/mac_server.py
```

Run these commands on the Mac. The activation script adds only Milo to Grog's
sites file, preserves other sites, and reuses `space.grooooog.serve`. If that
launch agent is absent, it creates one using the owner's installed Grog. It
refuses conflicting domain/port settings and a custom Grog sites-file override.
After HTTPS responds and the unauthenticated private API returns 401, it opens
Milo in the Mac browser with private first-start authorization. The interface
asks only for the owner's Milo password; authorization happens automatically
and survives a page reload. Then configure Google and authorize each mailbox.

The server's default Mac archive is `~/Library/Application Support/Milo`, outside
the checkout. A previously existing `.data/live` archive is retained. Keep one
authoritative archive on this host. Configure Ollama on this host, or set
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
The activation script uses absolute paths for the command and working directory.
Use the owner's Grog CLI, not the unrelated GNU groff `grog` binary installed on
some Linux systems. Inspect the existing Grog installation and launch agent
before starting a second `grog serve` process. Grog hot-reloads its sites map.
The service keeps bootstrap codes out of shared Grog logs; initialization codes
remain in the owner's private archive.

Default origin is `https://milo.grooooog.space`; change `MILO_PUBLIC_URL` if a
registered static domain is selected instead. The OAuth callback must match
that origin exactly. Uvicorn removes query strings from its access logs. Inspect
the deployed Grog version's logging too; OAuth authorization codes must not be
retained there. The currently published Grog counting proxy retains the path
without the query string and preserves the incoming Host header.

## Initialize and verify

Open Milo through the activation script or the paired Linux app and choose the
owner's Milo password. There is no user-facing initialization code. A private
owner link is exchanged for a short-lived Secure/HttpOnly cookie; a public
visitor without that authorization cannot initialize or claim the server.
Configure the Google web client using [Google setup](GOOGLE.md).

For the owner's Linux installation, keep its first-start link in
`.data/setup.url` with mode 0600. The launcher checks that the link belongs to
the configured HTTPS origin and opens it automatically. The UI immediately
removes the private fragment from the address and never places it in a form.
Never publish this file or an owner link. After password setup, the authorization
is consumed and the same installed app opens the normal login or inbox.

Before treating deployment as ready:

- Check HTTPS and confirm unauthenticated `/api/state` returns 401.
- Confirm setup is one-time and cookies are Secure/HttpOnly.
- Authorize a real mailbox; verify sync and persistence across a service restart.
- Open the same origin on Linux and iPhone and confirm they share settings,
  account identities and message changes.
- Check the Grog launch agent survives logout/reboot as configured on this Mac.

The Linux launcher can point to the shared service by setting `MILO_SERVER_URL`
or by writing its origin to `.data/server.json` as `{"url":"https://milo.grooooog.space"}`.
