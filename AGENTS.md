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
  `Store.rows()` uses a per-thread connection unless the thread already holds
  `store.lock`. Queries use `?` placeholders (translated by `store.sql`), integer
  0/1 flags (cast boolean expressions with `::int` inside aggregates) and
  `ILIKE` for search. Never reintroduce SQLite.
  Parse mail before taking the writer lock and keep write transactions short.
- Never scan the archive at startup: the Docker health check restarts a slow
  container. One-time rewrites run in background batches.
- Deploy: push `main`, fast-forward `~/Sites/milo` on the Mac, `docker compose
  build`, then bootout `system/space.grooooog.milo.server`, `compose up -d
  --no-build --wait`, bootstrap the plist again (docs/DEPLOYMENT.md).
- Original MIME lives in compressed files under `blobs/` (`Store.blobs`), read
  via `message(..., raw=True)`/`message_headers`. Write it only through
  `upsert_message`/`set_raw`; never store originals in the database.
- Heavy archive rewrites saturate Docker Desktop's bind-mount I/O and trip the
  health check. Back up with an APFS clone (`cp -c`, container stopped) and run
  bulk migrations natively on the Mac with the container stopped (the 10 GB
  raw move took ~6 minutes), then restart.

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
