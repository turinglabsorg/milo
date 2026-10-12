# Private Mac service and public Grog landing

The public domain serves only the Milo presentation and a fixed Google OAuth
callback relay. It has no mailbox UI, password form, login API, or archive access.
The private email service listens on `127.0.0.1:8029`. Tailscale Serve provides
HTTPS on port 8443 and supplies the caller identity. The backend accepts only the
owner identities recorded in its host-local mode-0600 configuration; other
Tailscale users and anonymous requests receive 404, even with a valid Milo cookie.
Password and setup endpoints are unavailable in this deployment.

The authoritative Mac archive remains `~/Library/Application Support/Milo`,
outside the checkout. An existing `.data/live` archive is retained. Google tokens
and client credentials remain encrypted there; they never go to the landing or
Linux client. The app does not sign in to the macOS user account.

## Prepare and run

Install Python 3.11+, uv and the owner's Grog and Tailscale clients. Use a dedicated
checkout such as `~/Sites/milo`. Preserve existing Grog sites and Tailscale services.

```sh
uv sync --frozen
uv run python scripts/prepare_private.py
```

This prepares `private-server.json` in the existing archive with the server's
Tailscale HTTPS origin and exact owner identity. It does not enable Serve or
Funnel. `--owner-device <exact-device-DNS-name>` also includes the identity of an
explicitly selected second owner device. For a deliberately new host only,
`--new-archive` permits creation without an existing mailbox database.

Grog's permanent site command is `.venv/bin/python scripts/serve.py`, working in
this checkout on port 8025. `scripts/mac_server.py` registers only Milo and
preserves other sites and the existing Grog launch agent. `scripts/serve.py`
supervises both the public landing and private child; the child opens the same
archive. Missing private configuration leaves only the public landing available.
There is no fallback to public webmail. A failed private child causes the parent
to exit so Grog can restart both services.

Before enabling the proxy, confirm the loopback service is healthy and `/api/state`
without identity headers returns 404. Then configure **Serve**, with no Funnel:

```sh
tailscale serve --bg --https=8443 http://127.0.0.1:8029
```

Inspect existing Serve configuration first. Do not overwrite another handler or
enable Funnel. HTTPS certificates may require the owner's Tailscale consent.
The backend binds only loopback and disables forwarded-client-IP trust. Tailscale
Serve strips incoming identity headers before adding its attested caller identity;
see [the official identity-header documentation](https://tailscale.com/kb/1312/serve#identity-headers).

Set the Linux launcher's `.data/server.json` to the verified private HTTPS origin:
`{"url":"https://<Mac Tailscale DNS name>:8443"}`. The launcher opens the private
inbox using device identity, without an initialization code or password prompt.
The old public first-start link is ignored for Tailscale origins.

## Google and verification

Keep the registered Google redirect URI on the public static Grog domain:
`https://milo.grooooog.space/api/oauth/google/callback`. The public handler relays
only bounded state/code/error values to the fixed configured private callback.
It does not exchange codes or read the archive. PKCE, single-use state and the
browser nonce are checked by the private backend. Success/error returns to the
private client. Both services strip query strings from Uvicorn access logs.

Verify the deployed public landing and 404 responses for `/api/login`, `/api/state`,
`/api/messages` and `/static/app.js`. On the owner's actual Tailscale device,
verify the private inbox opens without a password and uses the existing accounts.
Check persistence after a service restart. `scripts/restart_server.py` requests
termination only after verifying the exact Grog-supervised Milo listener; Grog
relaunches it. Reboot/logout behavior depends on the owner's Grog launch agent.

The desktop client remains a dedicated Chromium window. Native iOS, push and
offline mailbox reading remain future work.
