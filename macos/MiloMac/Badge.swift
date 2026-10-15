import AppKit
import Foundation
import UserNotifications

struct StateResponse: Decodable {
    struct Counts: Decodable {
        let unread: Int
    }
    let counts: Counts
}

/// Dock badge with the unread inbox count (`/api/state` → `counts.unread`,
/// the server's own definition: unread, not sent/archived/snoozed).
/// Refreshes on `/api/events` changes and falls back to a 60-second poll.
/// Started in both the GUI and the `--notifier` agent process, so the
/// badge stays current while the window is closed.
final class DockBadge {
    private let config: ServerConfig
    private let session: URLSession
    private var task: Task<Void, Never>?

    static func label(unread: Int) -> String? {
        unread > 0 ? String(unread) : nil
    }

    init(config: ServerConfig) {
        self.config = config
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 70
        self.session = URLSession(configuration: configuration)
    }

    func start() {
        // macOS hides Dock badges for apps without the badge
        // notification permission, so ask for it up front (both modes).
        UNUserNotificationCenter.current().requestAuthorization(options: [.badge]) { _, _ in }
        task = Task { [weak self] in
            await self?.run()
        }
    }

    func stop() {
        task?.cancel()
    }

    private func refresh() async {
        guard
            let (data, response) = try? await session.data(
                from: config.serverURL.appendingPathComponent("api/state")),
            let http = response as? HTTPURLResponse,
            (200..<300).contains(http.statusCode),
            let state = try? JSONDecoder().decode(StateResponse.self, from: data)
        else { return }
        let unread = state.counts.unread
        let label = Self.label(unread: unread)
        await MainActor.run {
            NSApp.dockTile.badgeLabel = label
            NSApp.dockTile.display()
        }
        try? await UNUserNotificationCenter.current().setBadgeCount(unread)
    }

    private func follow() async throws {
        var request = URLRequest(url: config.serverURL.appendingPathComponent("api/events"))
        request.timeoutInterval = 70
        let (bytes, response) = try await session.bytes(for: request)
        guard
            let http = response as? HTTPURLResponse,
            (200..<300).contains(http.statusCode)
        else { return }
        for try await line in bytes.lines {
            if line.hasPrefix("event: change") || line.hasPrefix("event: hello") {
                await refresh()
            }
        }
    }

    private func run() async {
        while !Task.isCancelled {
            await refresh()
            do {
                try await follow()
            } catch {
                try? await Task.sleep(nanoseconds: 60 * 1_000_000_000)
            }
        }
    }
}
