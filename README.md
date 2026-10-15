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

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), PostgreSQL 16+ and, for
the dedicated app window, Chromium or Chrome. Point Milo at an empty database:

```sh
git clone https://github.com/turinglabsorg/milo.git
cd milo
uv sync
export MILO_DATABASE_URL=postgresql://milo@127.0.0.1:5432/milo
uv run python scripts/launch.py
```

## Run on macOS (client)

The native macOS client in [`macos/`](macos/README.md) connects to an
existing Milo service (for example the permanent Mac Pro deployment); it
does not run a second archive. With Xcode and XcodeGen installed:

```sh
uv run python macos/install.py
```

The Docker deployment (`compose.yaml`) runs PostgreSQL in its own container.
Tests need a server they can create databases on:
`MILO_TEST_DATABASE_URL=postgresql://user@127.0.0.1:5432/postgres uv run pytest`.

The launcher starts a local service at `http://127.0.0.1:8025` and opens Milo
directly on password setup. Choose your Milo password (at least 12 characters),
then add an account. There is no terminal code to enter. The installed app
handles its private first-start authorization automatically, including after
refreshing the page. To add Milo to the application launcher:

```sh
uv run python install.py
```

To run the service in the foreground:

```sh
uv run milo --data .data/live
```

## What works

- A responsive three-column inbox, search, categories and account filtering.
- Conversations group received mail and sent replies. Pin a conversation to the
  top, see which messages have AI analysis, and open formatted HTML email with
  authenticated inline images. External images load by default.
- Light, dark and system themes, shared account colors, loading skeletons and
  live download status. Lists load metadata; bodies load when opened.
- Google OAuth with PKCE, encrypted refresh tokens and native Gmail API sync.
  Read/unread, stars and archive changes use Gmail labels; expired history
  cursors trigger a fresh scan while retaining cached mail.
- IMAP over TLS: import inbox, sent and archive folders, with UIDVALIDITY-aware
  identities, bounded backfill, flag reconciliation and remote deletion detection.
- Durable queues for read/unread, stars, archive and trash operations. Pending operations
  survive a restart; failed operations remain visible and are retried. Archiving
  requires the provider to expose an Archive folder and support IMAP MOVE.
  Deleting a conversation removes it from the list immediately and queues a
  move to the provider's trash in the background. IMAP requires a Trash folder
  and MOVE; a failed move stays queued and the local conversation stays hidden.
- Inline replies, Reply all with deduplicated To/Cc recipients, and forwards.
  To and Cc suggest people you wrote to recently and search the rest of your
  contacts by name or address.
  Collapsed quoted history, normalized
  repeated reply prefixes, drafts up to one million characters, automatic saving
  and recovery after a failed save. Shared drafts and explicit SMTP sending over
  TLS/STARTTLS, reply headers and sent-mail caching. Ambiguous failures are never automatically resent.
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

## Ollama and DeepSeek V4.1 Flash

```sh
ollama pull deepseek-v4.1-flash:cloud
```

Milo defaults to `deepseek-v4.1-flash:cloud`, the
[published Ollama tag](https://ollama.com/library/deepseek-v4.1-flash), chosen for
its low usage.
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
client connecting to that service receives the stored accounts, mail, preferences
and drafts. The permanent Mac deployment uses owner-only Tailscale device access;
its public domain serves only a landing and OAuth relay, with no password endpoint.
Standalone local development retains password authentication. Received mail and
tokens stay on the server. Unsaved draft edits have a local recovery copy until
the server acknowledges them. The service polls providers every 60 seconds and
the UI refreshes every 2–10 seconds while visible. Downloaded message content and thread metadata are retained in the device cache
for offline reading. Folder/account navigation, cached-content search and ordinary
mailbox edits run locally; a durable journal synchronizes changes in background.
Saving/closing drafts and safe preferences do not wait for the server. Metadata
refreshes separately; already downloaded bodies are reused. Sending, AI and
uncached downloads still need the service. This cache is a requirement of every client, including the future iOS app;
see [the cache contract](docs/CLIENT_CACHE.md).

For access from iOS, the service needs a stable HTTPS address reachable by the
phone. Do not publish an unauthenticated demo or plain HTTP service to the
internet. A private HTTPS reverse proxy can route to the loopback service; run
Milo with `--secure-cookies` behind it. Native iOS, background sync, push and
device pairing are unfinished. [Architecture and deployment](docs/ARCHITECTURE.md).

## Data and backup

Mail metadata, bodies, settings and drafts live in PostgreSQL. The original
messages (with attachments) are compressed files under `blobs/` in the archive
directory, one per message; credentials are encrypted with Fernet using a
separate mode-0600 `vault.key`. Back up the database (`pg_dump`; the Docker
deployment keeps a nightly dump in `backups/postgres`), `blobs/` and `vault.key`.
Mail is not encrypted at rest; use disk encryption for the host. A passphrase authenticates
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

### Identity and automatic recap

Settings → Identity stores the owner's name, aliases, optional context and reply
language on the server. No personal identity is embedded in the application.
Connected mailbox addresses identify the owner automatically. AI reply drafts
use recent incoming and sent messages and follow the conversation's language by
default; an explicit language preference overrides that choice.

The inbox recap is computed and persisted in a background worker after new mail
arrives. Opening it reads an existing snapshot, without starting generation.
Previous results remain available during updates or temporary model errors.
Cloud processing still requires the configured consent. AI output remains a
draft to review, not a factual or delivery guarantee.

The production server runs in Docker on the Mac Pro with the existing archive
bind-mounted outside the image. Its boot supervisor and restart checks are in
[DEPLOYMENT.md](docs/DEPLOYMENT.md). The Omarchy client executes on the laptop and
retains its own device cache.

Keyboard shortcuts act on the selected conversation: **Backspace/Delete** moves
it to trash immediately while provider deletion runs in the background; **P**
adds or removes it from favorites. They also work when reading HTML mail and are
inactive in text fields, editable content, open drafts or dialogs. Modifier
chords, text composition and held-key repeats do not change the mailbox.
The account section offers an explicit **All accounts** filter for the unified
list. Account colors appear on avatar outlines without duplicate row dots;
folder headers retain the title and a compact Recap action.
