import AppKit
import Foundation
import UserNotifications

struct NotificationMessage: Decodable {
    let id: String?
    let sender: String?
    let sender_email: String?
    let subject: String?
}

struct NotificationsResponse: Decodable {
    let cursor: Int
    let messages: [NotificationMessage]
}

struct StatusResponse: Decodable {
    let authenticated: Bool?
}

/// Background mail banners for macOS, mirroring `scripts/notifier.py`:
/// follow `/api/events`, ask `/api/notifications` what is worth a banner,
/// remember the cursor, skip banners while Milo is in front, and open the
/// conversation when a banner is clicked. Runs in the `--notifier`
/// LaunchAgent mode so banners arrive while the window is closed.
final class Notifier: NSObject, UNUserNotificationCenterDelegate {
    /// Set by the app delegate: present the GUI (promotion included)
    /// instead of routing through LaunchServices.
    var onOpenMessage: ((String?) -> Void)?
    private let config: ServerConfig
    private let session: URLSession
    private var cursor: Int?
    private var stopped = false

    private static var stateFile: URL {
        ServerConfig.appSupportDirectory.appendingPathComponent("notifier.json")
    }

    init(config: ServerConfig) {
        self.config = config
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 70
        configuration.timeoutIntervalForResource = 120
        self.session = URLSession(configuration: configuration)
        self.cursor = Self.loadCursor()
        super.init()
    }

    // MARK: Cursor (~/Library/Application Support/Milo/notifier.json)

    private static func loadCursor() -> Int? {
        guard
            let data = try? Data(contentsOf: stateFile),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let cursor = object["cursor"] as? Int
        else { return nil }
        return cursor
    }

    private func saveCursor(_ newValue: Int) {
        let directory = Self.stateFile.deletingLastPathComponent()
        try? FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        let temporary = Self.stateFile.appendingPathExtension("tmp")
        if let data = try? JSONSerialization.data(withJSONObject: ["cursor": newValue]) {
            try? data.write(to: temporary, options: .atomic)
        }
    }

    // MARK: Focus (Hyprland check on Linux, frontmost app on macOS)

    private var miloFocused: Bool {
        NSWorkspace.shared.frontmostApplication?.bundleIdentifier == Bundle.main.bundleIdentifier
    }

    // MARK: Server

    private func check() async throws {
        var components = URLComponents(url: config.serverURL.appendingPathComponent("api/notifications"),
                                       resolvingAgainstBaseURL: false)!
        if let cursor {
            components.queryItems = [URLQueryItem(name: "after", value: String(cursor))]
        }
        let (data, response) = try await session.data(from: components.url!)
        try validate(response)
        let payload = try JSONDecoder().decode(NotificationsResponse.self, from: data)
        if !payload.messages.isEmpty, !miloFocused {
            announce(payload.messages)
        }
        if payload.cursor != cursor {
            cursor = payload.cursor
            saveCursor(payload.cursor)
        }
    }

    private func follow() async throws {
        var request = URLRequest(url: config.serverURL.appendingPathComponent("api/events"))
        request.timeoutInterval = 70
        let (bytes, response) = try await session.bytes(for: request)
        try validate(response)
        for try await line in bytes.lines {
            if line.hasPrefix("event: change") || line.hasPrefix("event: hello") {
                try await check()
            }
        }
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            throw NSError(
                domain: "MiloNotifier", code: http.statusCode,
                userInfo: [NSLocalizedDescriptionKey: "Server answered \(http.statusCode)"]
            )
        }
    }

    private func isOwner() async -> Bool {
        guard
            let (data, _) = try? await session.data(
                from: config.serverURL.appendingPathComponent("api/status")),
            let status = try? JSONDecoder().decode(StatusResponse.self, from: data)
        else { return true } // Unreachable: keep retrying rather than give up.
        return status.authenticated == true
    }

    // MARK: Banners

    private func announce(_ messages: [NotificationMessage]) {
        for message in messages.prefix(3) {
            let subject = (message.subject ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            banner(
                title: message.sender ?? message.sender_email ?? "Milo",
                body: subject.isEmpty ? "(Senza oggetto)" : subject,
                messageID: message.id
            )
        }
        if messages.count > 3 {
            banner(title: "Milo", body: "Altre \(messages.count - 3) email nuove", messageID: nil)
        }
    }

    private func banner(title: String, body: String, messageID: String?) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        if let messageID {
            content.userInfo = ["messageID": messageID]
        }
        let request = UNNotificationRequest(
            identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    // MARK: Run loop (exponential backoff, owner exit)

    func run() async {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        _ = try? await center.requestAuthorization(options: [.alert, .sound])
        var delay: UInt64 = 2
        while !stopped {
            do {
                try await check()
                try await follow()
                delay = 2
            } catch let error as NSError where [401, 403, 404].contains(error.code) {
                if await !isOwner() {
                    FileHandle.standardError.write(
                        Data("Milo refused the notifier: this device is not the owner's.\n".utf8))
                    return
                }
                try? await Task.sleep(nanoseconds: delay * 1_000_000_000)
                delay = min(delay * 2, 300)
            } catch {
                try? await Task.sleep(nanoseconds: delay * 1_000_000_000)
                delay = min(delay * 2, 300)
            }
        }
    }

    func stop() {
        stopped = true
    }

    // MARK: Banner click -> open the conversation in the GUI app

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        let messageID = response.notification.request.content.userInfo["messageID"] as? String
        if let onOpenMessage {
            onOpenMessage(messageID.flatMap { $0.isEmpty ? nil : $0 })
        } else if
            let messageID, !messageID.isEmpty,
            let url = URL(string: "milo://open/\(messageID)")
        {
            NSWorkspace.shared.open(url)
        } else {
            NSWorkspace.shared.open(Bundle.main.bundleURL)
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }
}
