import MiloKit
import SwiftUI

enum SidebarItem: Hashable {
    case view(MailView)
    case account(String?)
}

struct MainView: View {
    var onSignOut: () -> Void
    @Environment(Mailbox.self) private var mailbox
    @State private var sidebar: SidebarItem? = .view(.inbox)
    @State private var selectedKey: String?
    @State private var compose: Draft?
    @State private var showSettings = false
    @State private var showRecap = false

    var body: some View {
        NavigationSplitView {
            Sidebar(selection: $sidebar, onSettings: { showSettings = true })
        } content: {
            Group {
                switch mailbox.view {
                case .todo: TodoListView(selectedKey: $selectedKey)
                case .drafts: DraftListView(compose: $compose)
                default: ConversationListView(selectedKey: $selectedKey, showRecap: $showRecap)
                }
            }
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Task { await mailbox.downloadMail() }
                    } label: {
                        Label("Scarica posta ora", systemImage: "arrow.down.circle")
                    }
                    .disabled(mailbox.downloadingMail)
                    .accessibilityIdentifier("download-mail")
                }
                ToolbarItem(placement: .primaryAction) {
                    Button { compose = mailbox.newDraft() } label: { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("Nuovo messaggio")
                        .accessibilityIdentifier("compose")
                }
            }
        } detail: {
            if let selectedKey {
                ThreadView(key: selectedKey, compose: $compose, selectedKey: $selectedKey)
                    .id(selectedKey)
            } else {
                ContentUnavailableView("Spazio per una conversazione.", systemImage: "envelope",
                                       description: Text("Scegli un’email e prenditi il tempo per leggerla."))
            }
        }
        .tint(Color.milo.accent)
        .onChange(of: sidebar) { _, item in
            selectedKey = nil
            Task {
                switch item {
                case .view(let view): await mailbox.show(view, account: mailbox.account)
                case .account(let account): await mailbox.show(.inbox, account: account)
                case nil: break
                }
            }
        }
        .sheet(item: $compose) { draft in ComposeView(draft: draft) }
        .sheet(isPresented: $showSettings) { SettingsView(onSignOut: onSignOut) }
        .sheet(isPresented: $showRecap) { RecapView(selectedKey: $selectedKey) }
        .onOpenURL { url in
            // mailto: links open the composer (once Milo is the default mail app).
            if let account = mailbox.state?.accounts.first,
               let draft = Draft.mailto(url, accountId: account.id, signature: mailbox.signature(for: account.id)) {
                compose = draft
            }
        }
        .task {
            PushCenter.shared.mailbox = mailbox
            if !ProcessInfo.processInfo.arguments.contains("-MiloDemo") { await PushCenter.shared.requestAuthorization() }
        }
        .onChange(of: PushCenter.shared.token) { _, token in
            guard let token else { return }
            Task { try? await mailbox.api.registerDevice(token: token, environment: PushCenter.environment) }
        }
        .onChange(of: PushCenter.shared.openRequest?.messageId) { _, _ in
            guard let request = PushCenter.shared.openRequest else { return }
            PushCenter.shared.openRequest = nil
            Task {
                await mailbox.open(messageId: request.messageId, accountId: request.accountId, threadId: request.threadId)
                selectedKey = mailbox.selectedKey
            }
        }
        .task {
            // Refresh while the app is in the foreground; the service polls providers every minute.
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 15_000_000_000)
                await mailbox.refresh()
            }
        }
    }
}

struct Sidebar: View {
    @Binding var selection: SidebarItem?
    var onSettings: () -> Void
    @Environment(Mailbox.self) private var mailbox

    var body: some View {
        List(selection: $selection) {
            Section("La tua posta") {
                ForEach(MailView.allCases) { view in
                    Label(view.title, systemImage: view.symbol)
                        .badge(count(view))
                        .tag(SidebarItem.view(view))
                        .accessibilityIdentifier("view-" + view.rawValue)
                }
            }
            Section("Account") {
                Label("Tutti gli account", systemImage: "tray.2").tag(SidebarItem.account(nil))
                ForEach(mailbox.state?.accounts ?? []) { account in
                    Label {
                        Text(account.name)
                    } icon: {
                        Circle().fill(Color(hex: account.color) ?? Color.milo.accent).frame(width: 9, height: 9)
                    }
                    .tag(SidebarItem.account(account.id))
                }
            }
        }
        .navigationTitle("Milo")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(action: onSettings) { Image(systemName: "gearshape") }.accessibilityLabel("Impostazioni")
            }
        }
        .safeAreaInset(edge: .bottom) { SyncStatus().padding(.bottom, 8) }
    }

    private func count(_ view: MailView) -> Int {
        let counts = mailbox.state?.counts
        switch view {
        case .inbox: return counts?.inbox ?? 0
        case .unread: return counts?.unread ?? 0
        case .todo: return counts?.todo ?? 0
        case .starred: return counts?.starred ?? 0
        case .drafts: return counts?.drafts ?? 0
        case .snoozed: return counts?.snoozed ?? 0
        default: return 0
        }
    }
}

struct SyncStatus: View {
    @Environment(Mailbox.self) private var mailbox

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: mailbox.online ? (mailbox.syncing || mailbox.downloadingMail ? "arrow.triangle.2.circlepath" : "checkmark") : "wifi.slash")
            Text(text)
        }
        .font(.caption)
        .foregroundStyle(mailbox.online ? Color.milo.muted : Color.milo.danger)
        .accessibilityElement(children: .combine)
    }

    private var text: String {
        if !mailbox.online { return "Offline · mostro la posta salvata" }
        if mailbox.downloadingMail { return "Controllo la posta…" }
        if mailbox.pendingCount > 0 { return "\(mailbox.pendingCount) modifiche in sincronizzazione" }
        return mailbox.syncing ? "Aggiorno…" : "Posta aggiornata"
    }
}
