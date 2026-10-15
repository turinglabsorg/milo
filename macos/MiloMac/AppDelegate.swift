import AppKit
import CoreServices
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private var window: NSWindow?
    private var notifier: Notifier?
    private var notifierTask: Task<Void, Never>?
    private var badge: DockBadge?
    /// The LaunchAgent and the GUI share one bundle, so LaunchServices
    /// delivers reopen/URL events to the agent process. The agent then
    /// promotes itself to a regular app and shows the window; closing
    /// the window demotes it back to a background agent.
    private var promotedToGUI = false

    var isNotifierMode: Bool {
        CommandLine.arguments.contains("--notifier")
    }

    func applicationWillFinishLaunching(_ notification: Notification) {
        if CommandLine.arguments.contains("--register-mailto") {
            registerMailtoHandler()
            return
        }
        // The agent stays a regular app (no window at launch) so its
        // Dock icon can carry the unread badge, like Mail.
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if CommandLine.arguments.contains("--register-mailto") {
            NSApp.terminate(nil)
            return
        }
        startBadge()
        if isNotifierMode {
            startNotifier()
            return
        }
        if let action = PendingAction.parse(arguments: CommandLine.arguments) {
            AppModel.shared.handle(action)
        }
        showWindow()
    }

    func applicationWillTerminate(_ notification: Notification) {
        notifier?.stop()
        notifierTask?.cancel()
        badge?.stop()
    }

    private func startBadge() {
        guard let config = try? ServerConfig.load() else { return }
        let badge = DockBadge(config: config)
        badge.start()
        self.badge = badge
    }

    // MARK: Window

    private func showWindow() {
        if isNotifierMode, !promotedToGUI {
            promotedToGUI = true
            NSApp.setActivationPolicy(.regular)
        }
        if let window {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let hosting = NSHostingController(rootView: ContentView(model: AppModel.shared))
        let window = NSWindow(contentViewController: hosting)
        window.title = "Milo"
        window.delegate = self
        window.styleMask = [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView]
        window.setContentSize(NSSize(width: 1280, height: 820))
        window.minSize = NSSize(width: 900, height: 560)
        // No frame restoration: a frame saved on another display can
        // strand the window off-screen. Always start centered.
        window.center()
        window.makeKeyAndOrderFront(nil)
        self.window = window
        NSApp.activate(ignoringOtherApps: true)
    }

    func windowWillClose(_ notification: Notification) {
        window = nil
        promotedToGUI = false
    }

    private func presentGUI(_ action: PendingAction?) {
        // AppKit delivers these events on the main thread.
        MainActor.assumeIsolated {
            showWindow()
            if let action {
                AppModel.shared.handle(action)
            }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        !isNotifierMode
    }

    // MARK: URL entry points (mailto handler, milo://open/<id>)

    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls {
            if let action = PendingAction.parse(url: url) {
                presentGUI(action)
            }
        }
    }

    // MARK: mailto registration

    /// `LSSetDefaultHandlerForURLScheme` is the macOS counterpart of the
    /// Linux installer's `xdg-mime default ... x-scheme-handler/mailto`.
    private func registerMailtoHandler() {
        guard let bundleID = Bundle.main.bundleIdentifier else { return }
        let status = LSSetDefaultHandlerForURLScheme("mailto" as CFString, bundleID as CFString)
        if status != noErr {
            FileHandle.standardError.write(Data("Could not register Milo as the mailto handler (\(status)).\n".utf8))
            exit(1)
        }
        print("Milo is now the default handler for mailto: links.")
    }

    // MARK: Background notifier (LaunchAgent mode)

    private func startNotifier() {
        do {
            let config = try ServerConfig.load()
            let notifier = Notifier(config: config)
            notifier.onOpenMessage = { [weak self] messageID in
                Task { @MainActor in
                    self?.presentGUI(messageID.map { .open(messageID: $0) })
                }
            }
            self.notifier = notifier
            notifierTask = Task { await notifier.run() }
        } catch {
            FileHandle.standardError.write(Data("Milo notifier: \(error)\n".utf8))
            NSApp.terminate(nil)
        }
    }
}
