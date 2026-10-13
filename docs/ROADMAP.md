# Roadmap — the full product

The product is an open-source email client with a private owner archive for Linux and iOS, with one
configuration and synchronized stored mail. This first foundation does not
complete that goal.

| Requirement | Current evidence | Remaining work |
| --- | --- | --- |
| New project and dedicated folder | Public [turinglabsorg/milo](https://github.com/turinglabsorg/milo) repository in its own folder | Ongoing releases |
| Spark-inspired daily client | Responsive inbox, reading pane, compose, snooze, search, filters | Real daily-mail validation, accessibility review, keyboard navigation, richer reading/composition |
| Linux availability | App launcher and running local service | Packaging, startup supervision, notifications and desktop integration |
| Durable mail and configuration | SQLite archive, vault, shared settings/drafts and account maintenance | Backup/recovery UX, account removal, full folder/pagination support |
| Sync between devices | Independent API clients share mail, drafts and account edits; concurrent Google edits/send tested | Always-on HTTPS deployment; physical-device test; offline cache/change feed and conflict handling |
| Ollama + Mistral Large 4 | Real analysis, recap and proposed reply verified against `mistral-large-4:cloud` with fictional mail | Operational error handling and real-mail quality validation |
| Automatic mail analysis | Structured summary/priority/actions and automatic worker | Real-mail quality assessment, throughput and retry validation |
| Recaps | Cited inbox recap API and UI | Quality checks on a real multi-thread inbox |
| Automatic filtering | Deterministic rules and AI categories | Rule suggestions, VIPs, custom labels and explainability |
| Actual provider interoperability | Generic IMAP/SMTP and controlled protocol doubles | Connect a user-approved test mailbox; verify live receipt, reply, sent folder and remote edits |
| Gmail / Outlook | Google OAuth/PKCE and Gmail labels/history adapter; protocol tests | Live Google account authorization and round trip; Microsoft Graph/Exchange adapter |
| iOS availability | Responsive portable client and PWA shell | Physical Safari/PWA check; native iOS client, Keychain, local cache, APNs, build/signing on macOS |

## Mandatory client-local cache

Every client, including the future native iOS app, must persist downloaded email locally and support offline reading. Server-only caching does not satisfy this requirement. Follow [the client cache contract](CLIENT_CACHE.md).

## Next milestones

1. Connect a real mailbox and complete a round trip with controlled test mail.
2. Add account removal and Microsoft OAuth; fix provider behavior from evidence.
3. Package and supervise the Linux service, with notifications and recovery.
4. Deploy the shared service behind private HTTPS and verify two physical devices.
5. Build the native iOS client against the same persistent archive.
6. Introduce encrypted offline replicas and background synchronization; then
   release reviewed Linux and iOS builds.

No green unit test, screenshot or manifest alone establishes completion of a
provider integration, cross-device sync or an iOS release.
