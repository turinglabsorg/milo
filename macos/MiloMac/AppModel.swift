import Foundation
import SwiftUI

/// Shared state between the AppDelegate (mailto / notification entry
/// points) and the SwiftUI window hosting the web client.
@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()
    @Published private(set) var config: ServerConfig?
    @Published private(set) var configurationError: String?
    /// Incremented to ask the web view to (re)load `pending`.
    @Published private(set) var loadToken = 0
    @Published private(set) var mailRequestToken = 0
    private(set) var pending: PendingAction?

    init() {
        reloadConfiguration()
    }

    func reloadConfiguration() {
        do {
            config = try ServerConfig.load()
            configurationError = nil
        } catch let error as ServerConfigError {
            config = nil
            configurationError = error.description
        } catch {
            config = nil
            configurationError = error.localizedDescription
        }
    }

    /// First URL for a fresh web view; attaches the private grant.
    func initialURL() -> URL? {
        guard let config else { return nil }
        do {
            return try config.initialURL(pending: pending)
        } catch {
            configurationError = error.localizedDescription
            return nil
        }
    }

    /// A mailto link or notification click while the app already runs:
    /// ask the existing web view to navigate (it reloads so the web app
    /// picks the fragment up in `boot()`, like a new Linux window).
    func handle(_ action: PendingAction) {
        pending = action
        loadToken += 1
        NSApp.activate(ignoringOtherApps: true)
    }

    func consumePending() -> PendingAction? {
        defer { pending = nil }
        return pending
    }

    /// Ask the web view to reload its current page (error banner retry).
    func reload() {
        loadToken += 1
    }

    func downloadMail() {
        mailRequestToken += 1
    }
}
