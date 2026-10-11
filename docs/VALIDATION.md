# Validation — 2026-10-11

Verified locally on the Linux development machine:

- `ruff check milo tests scripts install.py`: passed.
- `node --check web/app.js`: passed.
- Combined API, sync and Chromium suite: **60 tests passed**.
- Browser flows at 1440×1000, 900×900 and 390×844: reading, replying, saving and
  reopening drafts, deleting drafts, categories and search. No page errors or
  horizontal document overflow were observed.
- Real-service onboarding (without seeded mail) on the same three screen sizes:
  passphrase setup/login, OAuth client import, local Geist loading and
  Google authorization URL navigation. The outbound Google navigation was
  intercepted; these browser tests do not authorize a mailbox.
- Google protocol tests: real library code exchange against controlled HTTP
  responses, PKCE, one-time browser-bound state, revoked/expired sessions,
  encrypted client/refresh token storage and renewal persistence, reconnect
  identity, label outbox operations, interrupted backfill, history pagination
  and expired-cursor recovery, canonical Gmail send identity, and access-log
  stripping of OAuth query parameters.
- Account management: shared names/pause, encrypted IMAP credential rotation,
  unchanged account/message/draft identities and persistence after reopening.
  Invalid identity changes and Google password edits are rejected. Browser
  checks cover account editing at 1440×1000 and 390×844.
- Concurrency: Gmail read/star edits and account pause complete while a network
  sync lock is held; newer outbox edits survive older acknowledgements; flag
  reconciliation is atomic with user edits. Explicit Gmail sending does not
  wait for backfill and retains a newer shared draft saved during sending.
- Two clients with separate cookie jars authenticated to one service and
  observed the same account configuration, message changes, AI preferences and
  drafts. The saved archive and configuration survived reopening the store.
- A real Ollama daemon returned a validated summary, category, action list,
  source-linked recap and proposed reply from `mistral-large-4:cloud`, using only
  a fictional message. The initial native-schema request returned empty output;
  cloud prompting/validation was corrected and the live check then passed.
- Source and wheel distributions built successfully; the wheel contains the
  static UI, icon assets, Gmail adapter, Geist font and its OFL license. The distributions contain no `.data`, virtual
  environment or vault key.
- The installed user-local Linux launcher opens Milo in dedicated Chromium
  windows. The live service reports uninitialized/unauthenticated and denies
  private API access. The demo has been stopped in the normal user session; fictional fixtures
  remain only for isolated development tests.

Mac Pro deployment was activated through the owner's authorized desktop session
on 2026-10-11. The permanent Grog launch agent is loaded with `KeepAlive`; Milo's
archive exists at `~/Library/Application Support/Milo`, outside the checkout.
`https://milo.grooooog.space/api/status` reports the real service (`demo: false`)
and unauthenticated `/api/state` returns 401. The deployed JavaScript, CSS and
bundled Geist font match this checkout. The Linux launcher is configured to use
this same HTTPS origin. Initial passphrase setup is pending. No Google web-client
credentials or real mailbox authorization have been provided.

The tests do **not** prove:

- Live interoperability with Gmail, iCloud, Exchange or another real provider.
- Quality or safety of AI output across a real private mailbox.
- Offline mailbox reading, large mailbox performance or every IMAP extension.
- Authenticated mailbox use across two physical devices, or persistence of real
  email across a production service restart.
- A working native iOS build, background delivery or push notifications.

The overall product goal remains active. These are explicit future validation
gates, not claims established by the passing tests above.
