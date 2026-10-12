# Client-local cache — required for every Milo client

This is a product requirement for **all clients**, including Linux and the future
native iOS app. A client must retain downloaded message content locally. Opening
an already downloaded message must not require downloading it again from the Mac.
The Mac remains the authoritative server for accounts, provider credentials and
the complete archive; a server-side archive alone does not satisfy this requirement.

## Behavior

- Show the locally cached inbox immediately, then refresh metadata in the background.
- Retain downloaded thread metadata, plain text, sanitized HTML and downloaded
  attachments/inline images across app restarts. Read cached content offline.
- Fetch thread metadata separately from bodies. Download the visible message first,
  render collapsed messages only on opening, and fill the thread cache in background.
- Reuse immutable content by message ID and `content_version`; mutable flags,
  classification, analysis and thread membership come from metadata refreshes.
- A body change invalidates only that content version. A trash tombstone must stay
  hidden locally while offline and after reconnect. Do not resurrect queued deletes.
- Keep draft edits locally until server acknowledgement, with revision checks.
- Commit read/star/pin/category/archive/snooze/trash changes to a durable local
  journal before confirming them in the UI, whether online or disconnected.
  Render folder/account filters and favorites from the normalized local catalogue.
  Synchronize the journal in background, preserving the latest intent when old
  HTTP responses arrive. Retain queued identity/theme/AI/account-display preferences
  locally; provider credentials remain server-only.
- **Never automatically send a draft or retry SMTP/Gmail sending after reconnect.**
  Sending is always an explicit user action and ambiguous outcomes require review.
- Explain when content has never been downloaded or local storage is unavailable.
  Do not imply that an uncached body or attachment is available offline.

## Current client

The shared client uses an origin-isolated IndexedDB database with AES-GCM payloads
and a persisted non-extractable CryptoKey. Its private service worker retains the
app shell. API data is managed explicitly; OAuth/provider credentials are never
cached. Browser profile and device access remain the local trust boundary. Cache
storage encryption is not a separate owner password or an end-to-end encryption
claim. Revoked online authorization and explicit logout clear cached API state.

Thread metadata uses `/api/messages/{id}/thread?lazy=true`; content uses the
existing authenticated message/attachment routes. `content_version` is a hash of
stored MIME content. Cached content remains reusable when only flags change.

The normalized conversation catalogue is refreshed in background through the
authenticated, chronological `/api/client/messages` metadata feed. Pages contain
200 conversations, without MIME or bodies. A partial SQLite index selects each
page before aggregating its thread details, so pagination does not repeatedly
materialize the complete archive. The client defers this background backfill
behind initial reading and spaces page requests; catalogue refreshes are bounded
to once per two minutes. Folder membership includes both
incoming messages and sent replies. Missing rows are verified through
`/api/client/thread` before removal; the same lookup recovers queued edits when
an IMAP message identity changes while its conversation survives. The visible
list remains limited to 100 conversations; the local catalogue can contain more.

Search filters local sender/address/subject/preview metadata immediately and
matches words in downloaded bodies. A dedicated worker tokenizes cached text
without blocking the editor; its index is encrypted with the catalogue and
invalidated by content version. Server SQLite substring search refines results
for bodies not downloaded on this device. The local word index is not an
archive-wide full-text database or an exact-phrase search engine. Cached body
search survives offline restart; uncached content still requires connectivity.

Transient failures retain the journal for automatic retry. A permanent rejection
is retained with a visible synchronization error and does not block unrelated
operations. Correcting the rejected setting replaces that failed intent; the
Sync action can explicitly retry retained failures. AI requests wait for pending
identity/preferences to reach the server and explain synchronization failures.

Draft saving and closing depend only on local storage; server persistence runs
in background. Draft deletions survive reload and wait for an in-flight save
before reaching the server. Explicit sending first persists the chosen revision
on the server and then sends it. Sending, AI and first-time content downloads
still require a reachable service. No send is queued for automatic replay.

The in-memory cache uses a 16 MiB LRU, independent of persistent IndexedDB.
Per-key revisions prevent a delayed disk read or encryption write from replacing
newer cached values. Journal enqueue/acknowledgement is serialized, and local
catalogue persistence precedes removing an acknowledged journal operation.

## Native iOS implementation gate

The future native iOS client must implement this same behavior using a persistent
local database/file cache, with cache keys protected by Keychain and platform file
protection. It must support local catalogue/search, immediate offline edits and drafts, device-local pending
operations, version-aware refresh, authenticated attachment caching and deliberate
cache removal without silently losing unsynchronized edits. Downloading each body
again whenever a conversation is opened is not an acceptable native implementation.
Physical iPhone tests must prove persistence after app termination, airplane-mode
reading, reconnection, queued changes, storage-pressure handling and no duplicate
send. Responsive Chromium tests do not establish native iOS completion.

The current shared browser client caches downloaded binary assets up to 16 MiB
per item. Larger explicit attachment downloads remain ordinary device files,
rather than being silently duplicated in IndexedDB. Native iOS must implement
its own cache budget and storage-pressure UX under the same retention contract.

Temporary server/gateway failures (including 5xx during a restart) retain cached
API data and binary assets. They are connectivity failures, not authorization
revocations. Pending idempotent metadata operations remain durable; sending still
requires explicit action. Only an actual authorization rejection clears access
state automatically.
