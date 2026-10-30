# Agent instructions

Read `~/.agents/AGENTS.md` at the start of each session and again before any
external action. That file is the single source of global agent instructions.

## Project notes

- The reading pane is patched in place (`morphChildren` in `web/app.js`), never
  rebuilt with `innerHTML`: recreating an email iframe reloads it and makes the
  reader flicker. Iframes are kept while their `srcdoc` is unchanged.
- Email frames are sandboxed without `allow-scripts`; never rely on scripts
  inside `srcdoc`. Height is fitted from the parent with a `ResizeObserver`.
- External images load by default; body cache keys therefore include
  `?load_images=true`, and background warming must use `bodyPath()`.
- Tests run against a real PostgreSQL: set `MILO_TEST_DATABASE_URL`; every
  archive directory gets its own throwaway database (`tests/conftest.py`).
- Test unreleased frontend changes on the real archive with Playwright
  (`service_workers="block"`, route `/static/*.js|css` to local `web/`).
- Storage is PostgreSQL (`MILO_DATABASE_URL`, password via
  `MILO_DATABASE_PASSWORD_FILE`). Reads must never wait for mailbox sync:
  `Store.rows()` borrows from a bounded reader pool (`READER_POOL`) unless the
  thread already holds `store.lock`; never keep per-thread connections (worker
  threads are retired and the connections leaked until Postgres refused
  clients). Queries use `?` placeholders (translated by `store.sql`), integer
  0/1 flags (cast boolean expressions with `::int` inside aggregates) and
  `ILIKE` for search. Never reintroduce SQLite.
  Parse mail before taking the writer lock and keep write transactions short.
- Never scan the archive at startup: the Docker health check restarts a slow
  container. One-time rewrites run in background batches.
- Deploy: push `main`, fast-forward `~/Sites/milo` on the Mac, `docker compose
  build`, verify image asset hashes, then SIGSTOP only the supervisor PID while
  replacing `server` (`compose up -d --no-deps --no-build`). SIGCONT it in an
  exit trap. Keep its launchd job loaded: bootout can kill its Docker backend
  child and restart the shared engine (docs/DEPLOYMENT.md).
- Original MIME lives in compressed files under `blobs/` (`Store.blobs`), read
  via `message(..., raw=True)`/`message_headers`. Write it only through
  `upsert_message`/`set_raw`; never store originals in the database.
- Replies get the quoted original appended server-side in `build_message`
  (`reply_quote`, times in `MILO_TIMEZONE`, default Europe/Rome) unless the
  body already quotes it; composers show only the new text.
- Linux: `install.py` registers `milo.desktop` as the `mailto:` handler;
  `scripts/launch.py` turns the link into `#compose=<mailto>`, which the web app
  opens once the accounts are known and then clears.
- Real time: `GET /api/events` (SSE) sends `change` when a write touches a
  table clients show (`VISIBLE_WRITE` in `store.py`, signalled after commit);
  the web app refreshes on it and polls only every 30 s while connected.
  Uvicorn uses `timeout_graceful_shutdown` so open streams never block restarts.
- To-dos: the web list and the iOS list can select every open item and mark
  that selection done (`PATCH /api/todos/{id}`). One row’s check still completes
  only that row. Ask Milo’s reply bubble is the answer text; citations render
  under it.
- Compose recipients: `GET /api/recipients?q=` suggests people you wrote to
  most recently, and searches name or address among correspondents (sent To/Cc
  plus incoming senders). Rows live in `correspondents`, filled as mail arrives
  and by `backfill_correspondents` for mail already archived. The web composer
  and the iOS composer both use it; a finished address does not open the list.
- Outgoing To/Cc headers pass through `recipient_headers` before MIME creation
  and scheduling: autocomplete's trailing comma is removed, malformed addresses
  are rejected before the composer closes, and SMTP uses the same normalized
  headers as Gmail. Moving between To and Cc must preserve the new field's
  pending suggestion lookup when the previous field loses focus.
- Drafts may carry an optional `html` field (API only): `build_message` then
  adds it as the `text/html` alternative of the plain `body` (docs/API.md).
  The web composer must round-trip it (`draftPayload` includes `html`); iOS
  still drops it.
- Outgoing attachments: `draft_attachments` rows + files in
  `draft-attachments/<draft_id>/` (raw-body `POST /api/drafts/{id}/attachments?name=`,
  18 MB total); added by `build_message`, removed when the draft is sent or
  deleted, orphans swept daily.
- Search keeps `ILIKE '%term%'`; trigram GIN indexes (`pg_trgm`,
  `messages_search_<column>`) make it indexed. They are built CONCURRENTLY on a
  dedicated connection after startup (`ensure_search_indexes`), invalid leftovers
  are rebuilt, and shutdown cancels a running build. Only one process builds
  (advisory try-lock 80251); `SCHEMA` DDL reruns only when its hash changes
  (setting `schema`), since rerunning it locks tables and deadlocked with CIC.
  Message and conversation searches include the stored `recipients` header,
  including sent To addresses and display names, with the same account/view
  filters. Keep `messages_search_recipients` in the background index set.
- `GET /api/messages` accepts explicit `limit` (1–500) and a paired finite
  `before_date`/`before_id` cursor for chronological conversation pagination.
  Its `next` query object retains filters and page size. Without pagination,
  preserve the pinned-first 100-row client list. Results are conversation
  metadata, not thread bodies; see `docs/API.md`. No new schema or index is
  needed: pagination reuses `Store.conversations` and its existing keyset path.
- Linux notifications: `scripts/notifier.py` (systemd user unit
  `milo-notifier.service`, written by `install.py` when `.data/server.json`
  exists) follows `/api/events` and asks `GET /api/notifications?after=<seq>`
  (arrival order, push rules from `Push.eligible`); clicking opens the thread
  (`launch.py --open=<id>` → `#open=<id>`); banners are skipped while
  the Milo window is focused (Hyprland). Cursor in `~/.local/state/milo/`.
- Heavy archive rewrites saturate Docker Desktop's bind-mount I/O and trip the
  health check. Back up with an APFS clone (`cp -c`, container stopped) and run
  bulk migrations natively on the Mac with the container stopped (the 10 GB
  raw move took ~6 minutes), then restart.

- Automatic AI analyzes only arrivals after activation: `ai_automatic_boundary`
  stores `since` and `after_seq`. `Store.set_setting("ai", ...)` resets it when
  automatic analysis is enabled (including configuration restore); `SyncEngine`
  initializes a missing boundary once, without scanning the archive. Automatic
  notification senders and Gmail Updates/Social labels classify as `updates`;
  Auto-Submitted/no-reply mail does too unless it has newsletter headers.
  Updates are excluded from automatic analysis and recap sources. Newsletters
  remain eligible; manual analysis remains available.
- AI action items are proposals until explicitly accepted. `todos.accepted` is
  a nullable timestamp; only accepted action items enter `/api/todos` and the
  navigation count. `POST /api/messages/{id}/todos` accepts `{text}` only from
  that message's current proposals and is idempotent. Message/body and thread
  responses include `todos` with acceptance/completion state. Accepted tasks
  survive reanalysis, replies and archiving; existing unaccepted rows remain
  proposals. Backup/restore and the iOS thread/body caches preserve acceptance.
  Web and iOS show **Accetta da fare**, then **Nei da fare** or **Fatto**.
- The offline web shell cache is `milo-shell-v30` (`web/sw.js`); bump its version
  when changing shell assets so installed clients fetch the new controls, and
  update the expected current cache in `tests/test_offline_first.py`.
- **Scarica posta ora**, app entry and foreground activation request the existing
  `POST /api/sync` immediately; periodic reads and folder navigation only refresh
  the archive. iOS pull-to-refresh uses `Mailbox.downloadMail()`, coalesces active
  requests and polls `ServiceState.sync` while providers work, preserving cached
  mail. macOS forwards activation through the `milo-download-mail` web event.
- The `macOS` workflow tests the desktop client and uploads `macos-client`, a
  `Milo-macOS.zip` containing a universal arm64/x86_64 app with ad-hoc signing.

## iOS app (`ios/`)

- Native SwiftUI app (iOS 17+). `ios/MiloKit` is a Foundation-only Swift
  package (API client, file-based device cache, edit journal, `Mailbox` model)
  that builds and tests on Linux: `. ~/.local/share/swiftly/env.sh && swift test
  --package-path ios/MiloKit` (Arch needs ncurses/libxml2 compat links inside
  the toolchain's `usr/lib/swift/linux`).
- The Xcode project is generated from `ios/project.yml` (XcodeGen); never
  commit `Milo.xcodeproj`. Linux cannot build iOS: the `iOS` GitHub Actions
  workflow builds on macOS, runs `ScreenshotTests` on a simulator with
  `-MiloDemo` (fictional `DemoTransport` data) and uploads the screenshots
  artifact (`gh run download -n ios-screenshots`).
- The device cache follows docs/CLIENT_CACHE.md with plain JSON files under
  Application Support protected by iOS Data Protection; sending always goes
  through a 10-second schedule so it can be undone, never auto-retried.
- TestFlight: run the `TestFlight` workflow (`gh workflow run TestFlight`).
  Bundle id `io.meaningtech.milo`, team `89J2AG5K92`; signing is automatic
  through the App Store Connect API key (repo secrets `ASC_KEY_P8`,
  `ASC_KEY_ID`, `ASC_ISSUER_ID`, `APPLE_TEAM_ID`). The build number is the
  workflow run number. Never read the `.p8` file yourself.
- Push notifications: `milo/push.py` sends through APNs with the key file
  `apns.p8` in the archive (mode 0600, `MILO_APNS_KEY_ID`/`MILO_APNS_TEAM_ID`
  in compose). Devices register via `POST /api/devices`. Only mail newer than
  an hour from people/VIP notifies; never blocked or unapproved senders.
  The iOS app registers its token (TestFlight = `production`) and opens the
  conversation from a tapped notification.
- `mailto:` links open the composer; becoming the default mail app also needs
  Apple's `com.apple.developer.mail-client` entitlement (requested by the owner).
- CI runs on every push: watch it in the background (`run_in_background`),
  never block the conversation waiting for it.
