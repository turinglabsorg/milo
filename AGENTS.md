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
- One-time data migrations use SQLite `PRAGMA user_version` in `Store.migrate`.
- Test unreleased frontend changes on the real archive with Playwright
  (`service_workers="block"`, route `/static/*.js|css` to local `web/`).
- Reads must never wait for mailbox sync: `Store.rows()` uses a per-thread
  read-only WAL connection unless the thread already holds `store.lock`.
  Parse mail before taking the writer lock and keep write transactions short.
- Never scan the archive at startup: the Docker health check restarts a slow
  container. One-time rewrites run in background batches and find candidates
  through the covering `messages_client_catalogue` index (body/raw are huge).
- Deploy: push `main`, fast-forward `~/Sites/milo` on the Mac, `docker compose
  build`, then bootout `system/space.grooooog.milo.server`, `compose up -d
  --no-build --wait`, bootstrap the plist again (docs/DEPLOYMENT.md).
