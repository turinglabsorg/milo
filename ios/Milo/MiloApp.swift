import MiloKit
import SwiftUI

@main
struct MiloApp: App {
    @AppStorage("serverURL") private var serverURL = ""
    @State private var mailbox: Mailbox?
    @State private var notice = Notice()
    @Environment(\.scenePhase) private var phase

    private static let demo = ProcessInfo.processInfo.arguments.contains("-MiloDemo")

    var body: some Scene {
        WindowGroup {
            Group {
                if let mailbox {
                    MainView(onSignOut: signOut)
                        .environment(mailbox)
                } else {
                    SetupView(initial: serverURL) { url in
                        serverURL = url.absoluteString
                        connect(url)
                    }
                }
            }
            .environment(notice)
            .overlay(alignment: .bottom) { NoticeBanner().environment(notice) }
            .task { if mailbox == nil { start() } }
        }
        .onChange(of: phase) { _, phase in
            if phase == .active { Task { await mailbox?.refresh() } }
        }
    }

    private func start() {
        if Self.demo {
            let cache = MailCache(root: FileManager.default.temporaryDirectory.appendingPathComponent("milo-demo-\(UUID())"))
            let box = Mailbox(api: APIClient(baseURL: URL(string: "https://milo.demo")!, transport: DemoTransport()), cache: cache)
            mailbox = box
            Task { await box.start() }
        } else if let url = URL(string: serverURL), !serverURL.isEmpty {
            connect(url)
        }
    }

    private func connect(_ url: URL) {
        let box = Mailbox(api: APIClient(baseURL: url), cache: MailCache.standard())
        mailbox = box
        Task { await box.start() }
    }

    private func signOut() {
        Task {
            try? await MailCache.standard().clear()
            serverURL = ""
            mailbox = nil
        }
    }
}

/// One transient message at the bottom of the screen, optionally with an action such as Undo.
@MainActor
@Observable
final class Notice {
    var text: String?
    var actionTitle: String?
    private var action: (() async -> Void)?
    private var generation = 0

    func show(_ text: String, actionTitle: String? = nil, duration: TimeInterval = 4, action: (() async -> Void)? = nil) {
        generation += 1
        let current = generation
        self.text = text
        self.actionTitle = actionTitle
        self.action = action
        Task {
            try? await Task.sleep(nanoseconds: UInt64(duration * 1_000_000_000))
            if current == generation { dismiss() }
        }
    }

    func run() {
        let action = action
        dismiss()
        Task { await action?() }
    }

    func dismiss() {
        text = nil
        actionTitle = nil
        action = nil
    }
}

struct NoticeBanner: View {
    @Environment(Notice.self) private var notice

    var body: some View {
        if let text = notice.text {
            HStack(spacing: 14) {
                Text(text).font(.subheadline).foregroundStyle(.primary)
                Spacer(minLength: 0)
                if let title = notice.actionTitle {
                    Button(title) { notice.run() }
                        .font(.subheadline.weight(.semibold))
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Color.milo.line))
            .padding(.horizontal, 16)
            .padding(.bottom, 12)
            .transition(.move(edge: .bottom).combined(with: .opacity))
            .animation(.spring(duration: 0.3), value: notice.text)
            .accessibilityElement(children: .combine)
        }
    }
}
