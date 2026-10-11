<p align="center"><img src="web/icon.svg" width="76" alt="Milo"></p>
<h1 align="center">Milo</h1>
<p align="center">Your inbox, with room to think.<br>Open source. Linux first. Built for an inbox that follows you.</p>

Milo is a new email client inspired by the calm, focused experience of
[Spark](https://sparkmailapp.com). A private service stores your accounts, email,
preferences and drafts once; clients connect to that same archive. The first
client runs on Linux in a dedicated Chromium window. Native iOS comes next.

**Early development:** this is a working foundation, not a finished replacement
for an established email client. A real mailbox and a physical iPhone still need
end-to-end validation. See [the roadmap](docs/ROADMAP.md).

## Run on Linux

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/) and, for the dedicated
app window, Chromium or Chrome.

```sh
git clone https://github.com/turinglabsorg/milo.git
cd milo
uv sync
uv run python scripts/launch.py
```

The launcher starts a local service at `http://127.0.0.1:8025`, opens Milo and
fills the one-time setup code. Choose a passphrase of at least 12 characters,
then add an account. To add Milo to the application launcher:

```sh
uv run python install.py
```

To run the service in the foreground:

```sh
uv run milo --data .data/live
```

## What works

- A responsive three-column inbox, search, categories and account filtering.
- Google OAuth with PKCE, encrypted refresh tokens and native Gmail API sync.
  Read/unread, stars and archive changes use Gmail labels; expired history
  cursors trigger a fresh scan while retaining cached mail.
- IMAP over TLS: import inbox, sent and archive folders, with UIDVALIDITY-aware
  identities, bounded backfill, flag reconciliation and remote deletion detection.
- Durable queues for read/unread, stars and archive operations. Pending operations
  survive a restart; failed operations remain visible and are retried. Archiving
  requires the provider to expose an Archive folder and support IMAP MOVE.
- Shared drafts and explicit SMTP sending over TLS/STARTTLS, reply headers and
  sent-mail caching. Ambiguous failures are never automatically resent.
- Shared account names, pause/resume and encrypted IMAP credential updates.
  Google reconnection checks that the chosen mailbox matches the original one.
- Gmail local edits and explicit sending stay responsive during mailbox sync;
  later queued edits and concurrently updated drafts are preserved.
- Snooze, deterministic category filters and safe attachment downloads.
- Ollama: structured email analysis, automatic categorization, inbox recap with
  links to source messages and proposed replies that stay drafts.
- Persistent sessions and settings, encrypted account credentials, a protected
  data directory and an installable web app shell.

Google accounts use **Continue with Google**, not an app password. Create a
Google web OAuth client once for your Milo service, then authorize each mailbox.
See [Google setup](docs/GOOGLE.md). Other accounts use IMAP/SMTP; iCloud requires
an Apple app-specific password. Microsoft OAuth/Graph remains unfinished.

The interface bundles [Geist](https://vercel.com/font), with readable type sizes
and no external font requests. Its license is included in `web/fonts/OFL.txt`.

## Ollama and Mistral Large 4

```sh
ollama pull mistral-large-4:cloud
```

Milo defaults to `mistral-large-4:cloud`, the
[published Ollama tag](https://ollama.com/library/mistral-large-4).
**This tag runs in Ollama Cloud.** Start Ollama and sign in to its cloud service,
then enable cloud processing in Milo → Settings → Milo AI. Automatic analysis is
off until enabled. Selected email content is sent to the chosen model. You can
instead select an installed local model. A remote Ollama endpoint can be set
with `MILO_OLLAMA_URL`; its processing also requires cloud consent.

Email content is treated as untrusted input. AI has no tools to send, delete or
archive mail. Generated results need human review; JSON validation does not
guarantee factual accuracy.

## One configuration across devices

Use **one running Milo service**, not separate archives on each device. Another
browser connecting to the same service and signing in with the same passphrase
receives the stored accounts, mail, preferences and drafts. Messages never live
in browser localStorage. The service polls providers every 60 seconds and the
UI refreshes every 30 seconds while visible. Only the web app shell is cached
offline; offline mailbox reading is still on the roadmap.

For access from iOS, the service needs a stable HTTPS address reachable by the
phone. Do not publish an unauthenticated demo or plain HTTP service to the
internet. A private HTTPS reverse proxy can route to the loopback service; run
Milo with `--secure-cookies` behind it. Native iOS, background sync, push and
device pairing are unfinished. [Architecture and deployment](docs/ARCHITECTURE.md).

## Data and backup

The Linux launcher stores data in `.data/live` under this checkout, with mode
0700; credentials are encrypted with Fernet using a separate mode-0600 key.
Back up **both** `mail.sqlite` and `vault.key` while the service is stopped. The
database also contains message bodies and raw attachments, which are not
encrypted at rest; use disk encryption for the host. A passphrase authenticates
access to the service, it does not encrypt the mailbox. There is no automatic
passphrase recovery yet. Do not commit or share `.data`, logs, backups or keys.

For the permanent Mac Pro service with a static Grog domain, see
[deployment](docs/DEPLOYMENT.md).

The CLI without `--data` uses `$XDG_DATA_HOME/milo` (normally
`~/.local/share/milo`). The launcher always passes `.data/live` explicitly.

## Development and validation

```sh
uv sync --extra dev
uv run ruff check milo tests scripts install.py
uv run pytest -q
```

Browser tests use two isolated temporary services (never your real archive):

```sh
uv run playwright install chromium
uv run milo --demo --data /tmp/milo-browser-demo --port 8026
uv run milo --data /tmp/milo-browser-live --port 8027
# Run each service in a separate terminal, then:
MILO_TEST_URL=http://127.0.0.1:8026 MILO_LIVE_TEST_URL=http://127.0.0.1:8027 \
MILO_LIVE_TEST_DATA=/tmp/milo-browser-live uv run pytest tests/test_browser.py -q
```

For an explicit live model check with **only fictional email content**:

```sh
uv run python scripts/check_ollama.py
```

Ollama Cloud currently does not enforce JSON schemas via `format`; Milo includes
the schema in its prompt and validates the returned JSON locally. Local models
also receive the native schema parameter. See [Ollama's structured output documentation](https://docs.ollama.com/capabilities/structured-outputs).

Tests cover authentication, credential secrecy, multiple clients, persistence,
MIME parsing, attachments, rule precedence, cloud consent, AI result validation,
SMTP TLS, IMAP flags, UIDVALIDITY resets, remote deletions, archive moves,
OAuth state/PKCE/callback binding, token renewal persistence, Gmail labels,
history pagination/reset, interrupted backfill, send identity, responsive layout,
Google onboarding, account maintenance, concurrent edits/sending, font loading,
search and drafts. Provider tests use deterministic doubles;
they do not establish successful interoperability with a real mailbox.

MIT · [turinglabs](https://github.com/turinglabsorg)
