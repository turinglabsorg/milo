import MiloKit
import SwiftUI

@main
struct MiloApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var delegate
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
            .overlay(alignment: .top) { NoticeBanner().environment(notice) }
            .task { if mailbox == nil { start() } }
        }
        .onChange(of: phase) { _, phase in
            if phase == .active {
                Task {
                    await mailbox?.refresh()
                    await mailbox?.retryOpenThread()
                }
            }
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
    @State private var drag: CGFloat = 0

    var body: some View {
        if let text = notice.text {
            HStack(spacing: 12) {
                Text(text).font(.subheadline).foregroundStyle(.primary)
                Spacer(minLength: 0)
                if let title = notice.actionTitle {
                    Button(title) { notice.run() }
                        .font(.subheadline.weight(.semibold))
                }
                Button { notice.dismiss() } label: {
                    Image(systemName: "xmark").font(.footnote.weight(.semibold)).foregroundStyle(Color.milo.muted)
                        .frame(width: 28, height: 28)
                }
                .accessibilityLabel("Chiudi avviso")
            }
            .padding(.leading, 16)
            .padding(.trailing, 8)
            .padding(.vertical, 8)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color.milo.line))
            .shadow(color: .black.opacity(0.18), radius: 12, y: 4)
            .padding(.horizontal, 16)
            .padding(.top, 6)
            .offset(y: min(0, drag))
            // Tap or swipe up to dismiss; the banner sits at the top so it never covers the toolbar.
            .onTapGesture { notice.dismiss() }
            .gesture(DragGesture().onChanged { drag = $0.translation.height }.onEnded { value in
                if value.translation.height < -20 { notice.dismiss() }
                drag = 0
            })
            .transition(.move(edge: .top).combined(with: .opacity))
            .animation(.spring(duration: 0.3), value: notice.text)
            .accessibilityElement(children: .contain)
        }
    }
}
