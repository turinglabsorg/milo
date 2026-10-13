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
