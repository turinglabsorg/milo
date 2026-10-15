# Milo for macOS — desktop client

The macOS counterpart of the Linux desktop client. The server and the
authoritative archive stay where they already run (the permanent Mac Pro
deployment); this app is only a client window onto that same service, with
the same configuration and the same web client. Linux (`install.py`,
`scripts/launch.py`, `scripts/notifier.py`) is untouched.

## What it is

A native SwiftUI/AppKit application (`MiloMac`, bundle
`io.meaningtech.milo.mac`, macOS 14+) that hosts the shared web client in a
`WKWebView`. The web view uses the persistent `WKWebsiteDataStore`, so the
client's encrypted IndexedDB device cache survives restarts exactly as it
does in the installed Chromium profile on Linux (see
[the client cache contract](../docs/CLIENT_CACHE.md)).

| Linux piece | macOS counterpart |
| --- | --- |
| `scripts/launch.py` Chromium `--app` window | `Milo` app window (`WebView.swift`) |
| `.data/server.json` lookup + `MILO_SERVER_URL` | `~/Library/Application Support/Milo/server.json` + `MILO_SERVER_URL` (`ServerConfig.swift`) |
| `owner_setup_url` first-start grant | Same rules in `ServerConfig.ownerInitialURL()`, including the `.ts.net` skip |
| `install.py` `.desktop` file | Bundled app installed to `~/Applications/Milo.app` |
| `xdg-mime default ... mailto` | `LSSetDefaultHandlerForURLScheme` (`Milo --register-mailto`, run by the installer) |
| `scripts/notifier.py` + systemd user unit | Same binary with `--notifier` under a LaunchAgent (`io.meaningtech.milo.notifier`) |
| `notify-send` banner, click opens the thread | `UNUserNotificationCenter` banner; clicking opens `milo://open/<id>` in the GUI |
| (no Linux equivalent) | Dock unread badge from `/api/state` `counts.unread`, refreshed on `/api/events` (`Badge.swift`) |
| Hyprland focus check | Frontmost-application check (`Notifier.miloFocused`) |
| `~/.local/state/milo/notifier.json` cursor | `~/Library/Application Support/Milo/notifier.json` |

Deep links keep the Linux fragment contract, which never reaches the
server: a `mailto:` link becomes `/#compose=<quoted mailto>`, a
notification click becomes `/#open=<message id>`, and the web app reads
and clears the fragment at boot.

## Install

Requires Xcode, plus XcodeGen (`brew install xcodegen`). From the
repository root:

```sh
uv run python macos/install.py
```

The installer builds Release, copies `Milo.app` into `~/Applications`,
mirrors an existing checkout pairing (`.data/server.json` and
`.data/setup.url`, mode 0600) into `~/Library/Application Support/Milo/`
without overwriting a different existing configuration, registers Milo
as the default `mailto:` handler, and loads the notifier LaunchAgent.
Remove the agent with
`launchctl bootout gui/$(id -u)/io.meaningtech.milo.notifier`.

To configure by hand, create
`~/Library/Application Support/Milo/server.json`:

```json
{"url": "https://<your-private-milo-origin>"}
```

The origin must be a bare HTTPS origin (no credentials, path, query, or
fragment), the same rule the Linux launcher enforces.

## Develop

The Xcode project is generated from `project.yml` (XcodeGen), like the
iOS app; never commit `MiloMac.xcodeproj`.

```sh
cd macos
xcodegen generate
xcodebuild -project MiloMac.xcodeproj -scheme MiloMac \
  -derivedDataPath /tmp/milo-mac-derived test
```

Process modes of the installed binary:
`Milo` (window), `Milo --notifier` (background banner agent),
`Milo --register-mailto` (set the default handler and exit),
`Milo --open=<message id>` and `Milo mailto:<...>` (compose/open actions,
also delivered to a running instance through the `milo:` URL scheme).
