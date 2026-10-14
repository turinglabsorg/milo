import MiloKit
import SwiftUI
import UserNotifications

/// Bridges APNs callbacks into SwiftUI: the device token and notification taps.
@MainActor
@Observable
final class PushCenter {
    static let shared = PushCenter()
    var token: String?
    @ObservationIgnored weak var mailbox: Mailbox?
    /// Set when the user taps a notification; MainView opens that conversation.
    var openRequest: (messageId: String, accountId: String?, threadId: String?)?

    #if DEBUG
    static let environment = "sandbox"
    #else
    static let environment = "production"
    #endif

    func requestAuthorization() async {
        let center = UNUserNotificationCenter.current()
        guard (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) == true else { return }
        UIApplication.shared.registerForRemoteNotifications()
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { @MainActor in PushCenter.shared.token = token }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {}

    /// New-mail pushes carry content-available: download the conversation now, before it is tapped.
    func application(_ application: UIApplication, didReceiveRemoteNotification userInfo: [AnyHashable: Any]) async
        -> UIBackgroundFetchResult {
        guard let messageId = userInfo["message_id"] as? String,
              let mailbox = await MainActor.run(body: { PushCenter.shared.mailbox }) else { return .noData }
        await mailbox.prefetch(messageId: messageId, accountId: userInfo["account_id"] as? String,
                               threadId: userInfo["thread_id"] as? String)
        return .newData
    }

    /// Show new-mail banners even while Milo is open.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async
        -> UNNotificationPresentationOptions {
        [.banner, .sound, .list]
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        let info = response.notification.request.content.userInfo
        guard let messageId = info["message_id"] as? String else { return }
        let accountId = info["account_id"] as? String, threadId = info["thread_id"] as? String
        await MainActor.run { PushCenter.shared.openRequest = (messageId, accountId, threadId) }
    }
}
