# Validation — 2026-10-11

Verified locally on the Linux development machine:

- `ruff check milo tests scripts install.py`: passed.
- `node --check web/app.js`: passed.
- Combined API, sync and Chromium suite: **22 tests passed**.
- Browser flows at 1440×1000, 900×900 and 390×844: reading, replying, saving and
  reopening drafts, deleting drafts, categories and search. No page errors or
  horizontal document overflow were observed.
- Two clients with separate cookie jars authenticated to one service and
  observed the same account configuration, message changes, AI preferences and
  drafts. The saved archive and configuration survived reopening the store.
- A real Ollama daemon returned a validated summary, category, action list,
  source-linked recap and proposed reply from `mistral-large-4:cloud`, using only
  a fictional message. The initial native-schema request returned empty output;
  cloud prompting/validation was corrected and the live check then passed.
- Source and wheel distributions built successfully; the wheel contains the
  static UI and icon assets. The distributions contain no `.data`, virtual
  environment or vault key.
- The installed user-local Linux launcher opens Milo in dedicated Chromium
  windows. The live service reports uninitialized/unauthenticated and denies
  private API access. The separate demo serves only fictional messages.

The tests do **not** prove:

- Live interoperability with Gmail, iCloud, Exchange or another real provider.
- Quality or safety of AI output across a real private mailbox.
- Offline mailbox reading, large mailbox performance or every IMAP extension.
- Access through a deployed HTTPS service or two physical devices.
- A working native iOS build, background delivery or push notifications.

The overall product goal remains active. These are explicit future validation
gates, not claims established by the passing tests above.
