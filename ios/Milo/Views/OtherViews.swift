import MiloKit
import SwiftUI

struct TodoListView: View {
    @Binding var selectedKey: String?
    @Environment(Mailbox.self) private var mailbox
    @Environment(Notice.self) private var notice

    var body: some View {
        List {
            ForEach(mailbox.todos) { todo in
                HStack(alignment: .top, spacing: 12) {
                    Button {
                        Task { await mailbox.complete(todo) }
                        notice.show("Fatto.")
                    } label: {
                        Image(systemName: "circle").font(.title3).foregroundStyle(Color.milo.muted)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Segna come fatto")
                    Button {
                        Task {
                            await mailbox.open(messageId: todo.messageId, accountId: todo.accountId, threadId: todo.threadId)
                            selectedKey = mailbox.selectedKey
                        }
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(todo.text).font(.subheadline).foregroundStyle(.primary)
                            HStack(spacing: 6) {
                                if todo.kind == "followup" {
                                    Tag(text: "Da seguire", color: Color.milo.danger)
                                } else if todo.priority == "high" {
                                    Tag(text: "Priorità alta", color: Color.milo.accent)
                                }
                                Text([todo.sender, Mailbox.subjectCore(todo.subject)].compactMap { $0 }.joined(separator: " · "))
                                    .font(.caption).foregroundStyle(Color.milo.muted).lineLimit(1)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
                .padding(.vertical, 2)
            }
        }
        .listStyle(.plain)
        .overlay {
            if mailbox.todos.isEmpty {
                ContentUnavailableView("Niente in sospeso.", systemImage: "checklist",
                                       description: Text("Le cose da fare che Milo trova nelle email arrivano qui."))
            }
        }
        .navigationTitle("Da fare")
        .refreshable { await mailbox.refresh() }
    }
}

struct Tag: View {
    var text: String
    var color: Color

    var body: some View {
        Text(text).font(.caption2.weight(.semibold)).foregroundStyle(color)
            .padding(.horizontal, 6).padding(.vertical, 1)
            .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 5))
    }
}

struct DraftListView: View {
    @Binding var compose: Draft?
    @Environment(Mailbox.self) private var mailbox

    var body: some View {
        List(mailbox.drafts) { draft in
            Button { compose = draft } label: {
                VStack(alignment: .leading, spacing: 3) {
                    if let scheduled = draft.scheduled {
                        Text(scheduled.error.map { "Invio non riuscito: " + $0 }
                             ?? "Invio " + Format.date(scheduled.sendAt, long: true))
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(scheduled.error == nil ? Color.milo.accent : Color.milo.danger)
                    }
                    Text(draft.to.isEmpty ? "Nessun destinatario" : draft.to).font(.caption).foregroundStyle(Color.milo.muted)
                    Text(draft.subject.isEmpty ? "Senza oggetto" : draft.subject).font(.subheadline.weight(.semibold))
                    Text(draft.body).font(.footnote).foregroundStyle(Color.milo.muted).lineLimit(1)
                }
            }
            .buttonStyle(.plain)
        }
        .listStyle(.plain)
        .overlay {
            if mailbox.drafts.isEmpty {
                ContentUnavailableView("Un pensiero da scrivere.", systemImage: "square.and.pencil",
                                       description: Text("Le bozze salvate appaiono qui, anche sugli altri dispositivi."))
            }
        }
        .navigationTitle("Bozze")
        .refreshable { await mailbox.refresh() }
    }
}

struct RecapView: View {
    @Binding var selectedKey: String?
    @Environment(Mailbox.self) private var mailbox
    @Environment(\.dismiss) private var dismiss
    @State private var recap: Recap?
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                if let recap {
                    if let overview = recap.overview {
                        Section { Text(overview).font(.body) }
                    }
                    if let priorities = recap.priorities, !priorities.isEmpty {
                        Section("Da tenere d’occhio") {
                            ForEach(Array(priorities.enumerated()), id: \.offset) { index, priority in
                                Button {
                                    Task {
                                        await mailbox.open(messageId: priority.messageId, accountId: nil, threadId: nil)
                                        selectedKey = mailbox.selectedKey
                                        dismiss()
                                    }
                                } label: {
                                    HStack(alignment: .top, spacing: 10) {
                                        Text("\(index + 1)").font(.caption.weight(.semibold)).foregroundStyle(Color.milo.accent)
                                            .frame(width: 22, height: 22)
                                            .background(Color.milo.soft, in: RoundedRectangle(cornerRadius: 6))
                                        Text(priority.action).foregroundStyle(.primary)
                                    }
                                }
                            }
                        }
                    }
                    if let generated = recap.generatedAt {
                        Section { Text("Aggiornato " + Format.date(generated, long: true)).font(.caption).foregroundStyle(Color.milo.muted) }
                    }
                } else if let error {
                    Text(error).foregroundStyle(Color.milo.danger)
                } else {
                    ProgressView("Carico il recap…")
                }
            }
            .navigationTitle("Il punto della tua inbox")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Chiudi") { dismiss() } } }
            .task {
                do { recap = try await mailbox.api.recap() }
                catch { self.error = (error as? APIError)?.message ?? error.localizedDescription }
            }
        }
    }
}

struct SettingsView: View {
    var onSignOut: () -> Void
    @Environment(Mailbox.self) private var mailbox
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("Servizio") {
                    LabeledContent("Indirizzo", value: mailbox.api.baseURL.host ?? "")
                    LabeledContent("Stato", value: mailbox.online ? "Connesso" : "Non raggiungibile")
                }
                Section("Account") {
                    ForEach(mailbox.state?.accounts ?? []) { account in
                        HStack {
                            Circle().fill(Color(hex: account.color) ?? Color.milo.accent).frame(width: 9, height: 9)
                            VStack(alignment: .leading) {
                                Text(account.name)
                                Text(account.email).font(.caption).foregroundStyle(Color.milo.muted)
                            }
                            Spacer()
                            if let error = account.error {
                                Image(systemName: "exclamationmark.triangle").foregroundStyle(Color.milo.danger)
                                    .accessibilityLabel(error)
                            }
                        }
                    }
                    Text("Collega e gestisci gli account dall’app Milo sul computer: valgono per tutti i dispositivi.")
                        .font(.footnote).foregroundStyle(Color.milo.muted)
                }
                Section {
                    Button("Scollega questo iPhone", role: .destructive) {
                        dismiss()
                        onSignOut()
                    }
                } footer: {
                    Text("Cancella solo la copia della posta su questo iPhone. L’archivio resta sul tuo servizio Milo.")
                }
            }
            .navigationTitle("Impostazioni")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Chiudi") { dismiss() } } }
        }
    }
}
