# Validation — updated 2026-10-12

## Current production result

The Mac Pro runs the real server in a healthy, non-root Docker container with
`unless-stopped` restart policy. Its existing archive remains mounted outside
the image; both published ports bind only to host loopback. The owner-only
archive is available through private Tailscale HTTPS. The public domain serves
the landing and fixed OAuth relay; private account/message/login/client routes
return 404. Both real Google accounts are available without account errors.
The installed Omarchy launcher opens the private client and keeps its device
cache on the laptop. The deployed JavaScript, cache module, stylesheet and
service worker match the tested source. No real test email was sent.

The system boot job is loaded and running as the archive owner, with explicit
Python/Node paths and a dedicated Grog relay for Milo. A real Milo-only container
restart preserved both accounts, identity/theme preferences, saved recap and
inbox. An isolated Docker smoke check also verified owner rejection and archive
persistence after restart. A full Mac power-cycle and pre-login Docker startup
have **not** been exercised; container restart evidence does not establish that
separate boot verification gate.

Identity is configurable and shared: name, aliases, context and reply-language
preference. No owner name or alias is hardcoded. Reply prompts identify connected
owner addresses and sent replies, use the incoming conversation's language in
automatic mode, and keep the reply in the owner's voice. The live configured
model was checked with a fictional English conversation and configurable owner
identity; this does not establish AI quality across the real mailbox.

New mail wakes a background recap worker. Integration tests verify one persisted
update for changed mail, unchanged-mail reuse, consent enforcement and retention
of the previous result after a generation error. Opening the recap reads the
saved result without generating it; the production snapshot is present and
reports ready. Desktop/mobile screenshots verify true black surfaces, compact
spacing, header account/analysis indicators, no sidebar AI promotion, editable
identity, readable recap priorities and matching full-width Google/IMAP buttons
with the Google icon.

The local suite passes **128 tests**; nine opt-in browser flows pass separately.
This includes lightweight recipient-header extraction without body
loading, Reply all owner-address exclusion, and encrypted inbox/body/inline-image
reuse through a temporary HTTP 503 and app reload. Local Docker-host Ollama
addresses retain local-model consent behavior; cloud models still require consent.

Keyboard regressions verify Backspace/Delete remove a selected conversation
before the HTTP response, P toggles favorites from rendered HTML, and typing,
open drafts/dialogs, modifier chords, composition and held-key repeats leave mail
unchanged. Account filtering restores the unified list through an explicit All
accounts control and clears the previous reader selection. Desktop/mobile
screenshots verify a title and compact Recap action replace the limited list
count and introductory copy, with account colors retained on avatar outlines
without duplicate account dots.

A read-only production check opened a conversation with a 100-message
thread index including sent replies, at desktop 1440×1000 and mobile 390×844
sizes. API writes were intercepted: draft saves were simulated and all other
mutations blocked. Reply all opened inline without waiting for the full incoming
body.

After the shortcuts/navigation update, a separate read-only production check
confirmed the current client assets, both error-free Google accounts, individual
mailbox filters, the unified All accounts list, compact headers, absence of
duplicate row dots and the saved recap. It observed no browser errors or API
mutations. The replacement container is healthy and retains the existing archive,
private port bindings and automatic restart policy.

| Visible behavior | Desktop | Mobile viewport |
| --- | ---: | ---: |
| First inbox load, empty device cache | 1,859 ms | 1,870 ms |
| First conversation body | 841 ms | 1,018 ms |
| Reopen downloaded conversation | 99 ms | 72 ms |
| Inbox after app reload with cache | 61 ms | 61 ms |
| Inbox after offline reload | 90 ms | 119 ms |
| Downloaded conversation while offline | 120 ms | 99 ms |
| Close long inline draft | 62 ms | 82 ms |

Repeated openings and offline reloads did not download the visible body again.
Downloaded API payloads persisted encrypted in IndexedDB with a non-extractable
key. Reply all appeared inline with To/Cc fields and excluded connected owner
addresses. No browser exceptions occurred. The lightweight thread index was
148,766 bytes before HTTP compression; list/index responses used gzip. Network
list requests had a 614 ms median and 842 ms maximum in this sample.

These are measured samples, not latency guarantees. First-time uncached content
still depends on the network. Native iOS, physical iPhone behavior, push delivery
and mailbox-wide AI quality remain future validation gates. The required native
cache behavior is documented in [CLIENT_CACHE.md](CLIENT_CACHE.md).

## Offline-first interactions — 2026-10-12

Isolated Chromium checks hold every API response while opening the cached inbox,
reading downloaded HTML, toggling favorites, archiving and switching folders.
The local journal and changes survive an offline restart. Separate checks verify
FIFO edits with delayed acknowledgements/stale metadata, cached-body word search
after offline restart, local draft save/delete and identity persistence followed
by reconnection. A rejected preference remains visible without blocking mail
edits; correcting it synchronizes successfully. Provider identity changes recover
through authenticated, account-scoped thread lookup. Metadata snapshot tests
verify 200-item chronological pagination remains stable when pins change.

Measured cached inbox/reader/favorites navigation in the held-server fixture was
approximately 40/81/70 ms. These are synthetic samples on the development laptop,
not a guarantee of network, storage or provider latency. Results and UI screenshots
are saved in the ignored `test-results` directory. Backend and browser regressions
also cover the existing responsive interface, editable identity, drafts and sends
using controlled transports. No real email was sent by these tests.

## Earlier checkpoints

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

On 2026-10-12, the owner authorized transferring the one-time initialization
link from the Mac Pro to the Linux client over Tailscale. The transfer completed
and Milo opened on Linux with its setup code prefilled; the code was not printed
in command output. A dedicated owner-controlled Google Cloud project named Milo
was created, and Gmail API activation was confirmed in the Console. OAuth
branding is prepared with an External audience. Completing its contact details,
creating/importing the web OAuth client and authorizing a real mailbox remain
pending. These configuration steps do not establish a successful mailbox sync.

The tests do **not** prove:

- Live interoperability with Gmail, iCloud, Exchange or another real provider.
- Quality or safety of AI output across a real private mailbox.
- Offline mailbox reading, large mailbox performance or every IMAP extension.
- Authenticated mailbox use across two physical devices, or persistence of real
  email across a production service restart.
- A working native iOS build, background delivery or push notifications.

The overall product goal is paused at the owner's request while scoped fixes
continue. These are explicit future validation
gates, not claims established by the passing tests above.

## Inbox improvements — 2026-10-12

The scoped update groups conversations, includes sent replies, supports shared
pin/theme/account-color preferences, renders sanitized HTML with CID images,
and removes conversations immediately while retaining a durable trash operation.
List responses contain metadata instead of MIME blobs and complete bodies.
Skeletons cover initial loading, navigation, reading and AI requests, and the
service reports active downloads separately from pending provider operations.

The isolated suite passes 86 tests (including two Chromium tests); the nine
existing browser flows pass separately on isolated demo and non-demo services.
These checks cover thread identity between accounts, sent replies, pin ordering,
HTML safety, dark-mode persistence, colors and removal before the DELETE response.
The owner-authorized live diagnostic confirms successful Gmail profile/list
responses and recovery of the previously reported account/outbox errors.
This does not identify the original transient rejection's precise cause.

## Private access, compose recovery and latency — 2026-10-12

The current local suite passes 97 tests (nine opt-in browser tests run separately
and also pass). An additional launcher regression verifies that Tailscale device
access ignores the old public setup link. Chromium tests on desktop and mobile
verify collapsed quoted HTML and its expanding/shrinking iframe, normalized reply
prefixes, intact forwarding beyond 100,000 characters, immediate draft closure
before a failing HTTP response, recovery after reload, and focus/caret retention
during synchronization. AI reply loading and its result stay inline; user edits
made during generation are preserved. A controlled mail transport verifies large
forward sending intact without contacting a real recipient.

Public-route checks verify that login, setup, account, message, attachment and
draft routes all return 404 even with forged cookies and identity headers. The
private backend accepts only the configured owner identity from a loopback proxy;
other identities and network-supplied identity headers are rejected. Actual local
production parent/child processes were launched against an isolated archive,
verified and stopped gracefully with both ports released.

A local 10,000-message archive exposed a missing expression index: list requests
initially exceeded five seconds. After adding the conversation index, measured
list latency was approximately 38 ms at the 95th percentile, visible inbox 138 ms,
slowest sampled conversation opening 66 ms, and 35 keystrokes in a 196,000-character
draft 443 ms. The list payload was 39,514 bytes. Measurements use synthetic test
messages and the local development machine; they are not a guarantee of network
or provider latency. Machine-readable measurements are written to the ignored
`test-results/performance.json`.

Production commit `ece2891` was activated on the Mac through the owner's saved
VNC session over Tailscale. Public HTTPS returned the landing with
`X-Milo-Surface: public`; `/api/login`, `/api/state`, `/api/messages` and
`/static/app.js` all returned 404. The private loopback service reports a real
initialized archive and Tailscale access; requests to its state API without an
owner identity return 404. The existing Grog supervisor is retained.

The owner subsequently enabled Tailscale Serve/HTTPS. The saved command completed
and the private HTTPS service returned authenticated, initialized, non-demo Milo
from Linux. Serve status shows only the private HTTPS handler to loopback 8029,
with no Funnel configuration. The installed Linux launcher now points to that
verified private origin. Both real Google accounts were available without errors,
and a real 17-message thread included sent replies and HTML with no browser
exceptions. No provider mutations or real sends were made by this check.

That earlier real-thread check also exposed a performance gap not covered by the small
fixtures: eagerly rendering/downloading every body took 8–14 seconds. The current
update introduces lightweight thread indices, body loading on expansion, compressed
responses and persistent client-local caching to address it. The production
measurements at the top of this document verify the resulting behavior.

## Client cache and Reply all — 2026-10-12

The local suite passes 104 tests; the nine opt-in browser flows pass separately.
New desktop/mobile tests verify downloaded HTML survives an offline reload,
opening cached content causes no extra body download, payloads are encrypted
in IndexedDB with a non-extractable key, inline images remain available offline,
and offline deletion survives reload and reconciles on reconnect without
resurrecting the row. Reply all includes Reply-To, To and Cc, removes the owner's
connected addresses and duplicates, and retains Cc in drafts. Controlled SMTP
and Gmail transports verify Cc delivery without sending to a real recipient.
Lazy thread indices exclude MIME and body data. On a synthetic 10,000-message
archive, list p95 remained around 41 ms and the sampled reader around 71 ms.

[The client-local cache contract](CLIENT_CACHE.md) is mandatory for every client,
including the future native iOS app. These browser tests do not establish an iOS
implementation or physical iPhone behavior.
