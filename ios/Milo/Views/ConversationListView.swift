import MiloKit
import SwiftUI

struct ConversationListView: View {
    @Binding var selectedKey: String?
    @Binding var showRecap: Bool
    @Environment(Mailbox.self) private var mailbox
    @Environment(Notice.self) private var notice
    @State private var searchTask: Task<Void, Never>?

    private let categories: [(String?, String)] = [(nil, "Tutte"), ("people", "Persone"), ("updates", "Notifiche"), ("newsletters", "Newsletter")]

    var body: some View {
        @Bindable var mailbox = mailbox
        List(selection: $selectedKey) {
            if mailbox.view == .inbox && mailbox.search.isEmpty {
                Picker("Categoria", selection: Binding(get: { mailbox.category }, set: { value in
                    Task { await mailbox.show(.inbox, account: mailbox.account, category: value) }
                })) {
                    ForEach(categories, id: \.1) { category in Text(category.1).tag(category.0) }
                }
                .pickerStyle(.segmented)
                .listRowSeparator(.hidden)
            }
            if !mailbox.online {
                Label("Sei offline. Mostro la posta salvata su questo dispositivo.", systemImage: "wifi.slash")
                    .font(.footnote).foregroundStyle(Color.milo.muted)
            }
            ForEach(mailbox.conversations, id: \.key) { row in
                ConversationRow(row: row, color: Color(hex: mailbox.state?.accounts.first { $0.id == row.accountId }?.color),
                                delivery: row.sent.value ? mailbox.deliveries[row.id] : nil)
                    .tag(row.key)
                    .swipeActions(edge: .leading) {
                        Button {
                            Task { await mailbox.mutate(row, MailEdit.Patch(read: !row.read.value)) }
                        } label: {
                            Label(row.read.value ? "Da leggere" : "Letta", systemImage: row.read.value ? "envelope.badge" : "envelope.open")
                        }
                        .tint(Color.milo.accent)
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        Button(role: .destructive) {
                            Task { await mailbox.mutate(row, MailEdit.Patch(), deleted: true) }
                            notice.show("Conversazione nel cestino.")
                        } label: { Label("Elimina", systemImage: "trash") }
                        Button {
                            Task { await mailbox.mutate(row, MailEdit.Patch(archived: true)) }
                            notice.show("Archiviata. Milo sincronizza in background.")
                        } label: { Label("Archivia", systemImage: "archivebox") }
                        .tint(.indigo)
                    }
                    .contextMenu {
                        Button(row.starred.value ? "Rimuovi dai preferiti" : "Aggiungi ai preferiti", systemImage: "star") {
                            Task { await mailbox.mutate(row, MailEdit.Patch(starred: !row.starred.value)) }
                        }
                        Button(row.pinned.value ? "Rimuovi pin" : "Fissa in alto", systemImage: "pin") {
                            Task { await mailbox.mutate(row, MailEdit.Patch(pinned: !row.pinned.value)) }
                        }
                        Button("Rimanda a domani", systemImage: "clock") {
                            let tomorrow = Calendar.current.date(byAdding: .day, value: 1, to: Calendar.current.startOfDay(for: Date()))!
                                .addingTimeInterval(8 * 3600)
                            Task { await mailbox.mutate(row, MailEdit.Patch(snoozedUntil: tomorrow.timeIntervalSince1970)) }
                        }
                    }
            }
        }
        .listStyle(.plain)
        .overlay {
            if mailbox.conversations.isEmpty {
                ContentUnavailableView(mailbox.search.isEmpty ? "Nessuna conversazione." : "Nessun risultato.",
                                       systemImage: mailbox.search.isEmpty ? "tray" : "magnifyingglass")
            }
        }
        .navigationTitle(mailbox.view.title)
        .searchable(text: $mailbox.search, prompt: "Cerca nella tua posta")
        .onChange(of: mailbox.search) { _, _ in
            mailbox.applyFilter()
            searchTask?.cancel()
            searchTask = Task {
                try? await Task.sleep(nanoseconds: 400_000_000)
                if !Task.isCancelled { await mailbox.refresh() }
            }
        }
        .refreshable { await mailbox.downloadMail() }
        .toolbar {
            if mailbox.view == .inbox {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showRecap = true } label: { Label("Recap", systemImage: "sparkles") }
                }
            }
        }
    }
}

struct ConversationRow: View {
    var row: Conversation
    var color: Color?
    var delivery: Delivery? = nil

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            Avatar(name: row.sender, color: color, size: 34)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(row.sender ?? row.senderEmail ?? "")
                        .font(.subheadline.weight(row.read.value ? .regular : .semibold))
                        .foregroundStyle(row.read.value ? Color.milo.muted : .primary)
                        .lineLimit(1)
                    if (row.messageCount ?? 1) > 1 {
                        Text("\(row.messageCount ?? 1)")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 5)
                            .background(Color.milo.soft, in: RoundedRectangle(cornerRadius: 5))
                            .foregroundStyle(Color.milo.accent)
                    }
                    if !row.read.value { Circle().fill(Color.milo.accent).frame(width: 7, height: 7) }
                    Spacer(minLength: 4)
                    if row.pinned.value { Image(systemName: "pin.fill").font(.caption2).foregroundStyle(Color.milo.muted) }
                    if row.starred.value { Image(systemName: "star.fill").font(.caption2).foregroundStyle(Color.milo.accent) }
                    if let delivery { DeliveryTick(delivery: delivery) }
                    Text(Format.date(row.date)).font(.caption).foregroundStyle(Color.milo.muted)
                }
                Text(Mailbox.subjectCore(row.subject))
                    .font(.subheadline.weight(row.read.value ? .regular : .semibold))
                    .lineLimit(1)
                Text((row.sent.value ? "Tu: " : "") + (row.preview ?? ""))
                    .font(.footnote)
                    .foregroundStyle(Color.milo.muted)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("row-" + row.id)
    }
}

/// One muted check once the provider accepted Milo's submission, two accent checks once it was opened.
struct DeliveryTick: View {
    var delivery: Delivery

    private var opened: Bool { delivery.opened != nil }

    var label: String {
        if let opened = delivery.opened {
            return "Aperto il \(Format.date(opened, long: true))" + (delivery.opens > 1 ? " · \(delivery.opens) aperture" : "")
        }
        return delivery.tracked.value ? "Inviato e confermato dal server · non ancora aperto"
            : "Inviato e confermato dal server · apertura non tracciata"
    }

    var body: some View {
        ZStack(alignment: .leading) {
            Image(systemName: "checkmark")
            if opened { Image(systemName: "checkmark").offset(x: 5) }
        }
        .font(.caption2.weight(.bold))
        .padding(.trailing, opened ? 5 : 0)
        .foregroundStyle(opened ? Color.milo.accent : Color.milo.muted)
        .accessibilityElement()
        .accessibilityLabel(label)
        .accessibilityIdentifier(opened ? "delivery-opened" : "delivery-sent")
    }
}
