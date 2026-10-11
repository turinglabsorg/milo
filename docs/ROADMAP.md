# Roadmap — the full product

The goal remains a public, intelligent email client for Linux and iOS, with one
configuration and synchronized stored mail. This first foundation does not
complete that goal.

| Requirement | Current evidence | Remaining work |
| --- | --- | --- |
| New project and dedicated folder | Standalone `milo` repository | Public publication and ongoing releases |
| Spark-inspired daily client | Responsive inbox, reading pane, compose, snooze, search, filters | Real daily-mail validation, accessibility contrast, keyboard navigation, richer reading/composition |
| Linux availability | App launcher and running local service | Packaging, startup supervision, notifications and desktop integration |
| Durable mail and configuration | SQLite archive; credentials vault; shared settings and drafts | Backup/recovery UX, account editing/removal, full folder/pagination support |
| Sync between devices | Two independent API clients share persistent state in tests | Always-on HTTPS deployment; physical-device test; offline cache/change feed and conflict handling |
| Ollama + Mistral Large 4 | Real analysis, recap and proposed reply verified against `mistral-large-4:cloud` with fictional mail | Operational error handling and real-mail quality validation |
| Automatic mail analysis | Structured summary/priority/actions and automatic worker | Real-mail quality assessment, throughput and retry validation |
| Recaps | Cited inbox recap API and UI | Quality checks on a real multi-thread inbox |
| Automatic filtering | Deterministic rules and AI categories | Rule suggestions, VIPs, custom labels and explainability |
| Actual provider interoperability | Generic IMAP/SMTP and controlled protocol doubles | Connect a user-approved test mailbox; verify live receipt, reply, sent folder and remote edits |
| Gmail / Outlook | Gmail app-password preset; TLS support | OAuth, Gmail labels/All Mail and Microsoft Graph/Exchange adapters |
| iOS availability | Responsive portable client and PWA shell | Physical Safari/PWA check; native iOS client, Keychain, local cache, APNs, build/signing on macOS |

## Next milestones

1. Connect a real mailbox and complete a round trip with controlled test mail.
2. Add account maintenance and native OAuth; fix provider behavior from evidence.
3. Package and supervise the Linux service, with notifications and recovery.
4. Deploy the shared service behind private HTTPS and verify two physical devices.
5. Build the native iOS client against the same persistent archive.
6. Introduce encrypted offline replicas and background synchronization; then
   release reviewed Linux and iOS builds.

No green unit test, screenshot or manifest alone establishes completion of a
provider integration, cross-device sync or an iOS release.
