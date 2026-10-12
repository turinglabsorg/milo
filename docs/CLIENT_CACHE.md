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
- Queue idempotent read/star/archive/trash operations durably on the device while
  disconnected. Synchronize these operations to the server outbox after reconnect.
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

## Native iOS implementation gate

The future native iOS client must implement this same behavior using a persistent
local database/file cache, with cache keys protected by Keychain and platform file
protection. It must support offline reading and drafts, device-local pending
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
