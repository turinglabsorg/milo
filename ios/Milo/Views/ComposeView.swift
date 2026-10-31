import Combine
import MiloKit
import SwiftUI
import UIKit

struct ComposeView: View {
    @State var draft: Draft
    @Environment(Mailbox.self) private var mailbox
    @Environment(Notice.self) private var notice
    @Environment(\.dismiss) private var dismiss
    @State private var followup = 0
    @State private var sending = false
    @State private var error: String?
    @State private var scheduling = false
    @State private var customDate = Date().addingTimeInterval(3600)
    @FocusState private var recipientSlot: RecipientSlot?
    @FocusState private var subjectFocused: Bool
    @State private var keyboardUp = false
    @State private var suggestions: [Recipient] = []
    @State private var suggestTask: Task<Void, Never>?
    @State private var editor = HTMLEditorController()
    @State private var linkPrompt = false
    @State private var linkURL = "https://"
    @State private var signatureCards: [String: Data] = [:]

    private enum RecipientSlot: Hashable { case to, cc }

    private var title: String {
        switch draft.mode {
        case .reply: "Rispondi"
        case .replyAll: "Rispondi a tutti"
        case .forward: "Inoltra"
        case .new: "Nuovo messaggio"
        }
    }

    @ViewBuilder
    private func recipientField(_ title: String, text: Binding<String>, slot: RecipientSlot, identifier: String) -> some View {
        HStack(spacing: 8) {
            Text(title).foregroundStyle(Color.milo.muted).frame(width: 34, alignment: .leading)
            TextField("", text: text)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($recipientSlot, equals: slot)
                .accessibilityLabel(title)
                .accessibilityIdentifier(identifier)
        }
        .composeRow()
        if recipientSlot == slot {
            ForEach(suggestions.prefix(5)) { person in
                Button {
                    text.wrappedValue = RecipientEdit.inserting(person.email, name: person.name, into: text.wrappedValue)
                } label: {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(person.name.isEmpty ? person.email : person.name)
                        if !person.name.isEmpty {
                            Text(person.email).font(.caption).foregroundStyle(Color.milo.muted)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .composeRow()
                .accessibilityIdentifier("recipient-\(person.email)")
            }
        }
    }

    private func refreshSuggestions() {
        guard let slot = recipientSlot else { suggestions = []; return }
        let value = slot == .to ? draft.to : draft.cc
        let token = RecipientEdit.token(value)
        if RecipientEdit.isAddress(token) { suggestions = []; return }
        suggestTask?.cancel()
        suggestTask = Task {
            try? await Task.sleep(nanoseconds: 150_000_000)
            guard !Task.isCancelled else { return }
            let found = (try? await mailbox.api.recipients(matching: token)) ?? []
            guard !Task.isCancelled, recipientSlot == slot else { return }
            let taken = RecipientEdit.addresses(in: value)
            suggestions = found.filter { !taken.contains($0.email.lowercased()) }
        }
    }

    private var hasHTML: Bool { !(draft.html ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    private struct RichTool: Identifiable {
        let command: String
        let symbol: String
        let title: String
        var id: String { command }
    }

    private static let tools = [
        RichTool(command: "bold", symbol: "bold", title: "Grassetto"),
        RichTool(command: "italic", symbol: "italic", title: "Corsivo"),
        RichTool(command: "underline", symbol: "underline", title: "Sottolineato"),
        RichTool(command: "h2", symbol: "textformat.size.larger", title: "Titolo"),
        RichTool(command: "p", symbol: "text.alignleft", title: "Paragrafo"),
        RichTool(command: "insertUnorderedList", symbol: "list.bullet", title: "Elenco puntato"),
        RichTool(command: "insertOrderedList", symbol: "list.number", title: "Elenco numerato"),
        RichTool(command: "createLink", symbol: "link", title: "Inserisci link"),
        RichTool(command: "removeFormat", symbol: "textformat", title: "Rimuovi formattazione"),
    ]

    /// The message is being written: the header folds away so the text gets the whole screen.
    private var writing: Bool { keyboardUp && recipientSlot == nil && !subjectFocused }

    private var formatBar: some View {
        HStack(spacing: 0) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 2) {
                    ForEach(Self.tools) { tool in
                        Button {
                            if tool.command == "createLink" { linkURL = "https://"; linkPrompt = true }
                            else { editor.exec(tool.command) }
                        } label: {
                            Image(systemName: tool.symbol).frame(width: 40, height: 40)
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel(tool.title)
                    }
                }
                .padding(.horizontal, 6)
            }
            Button { editor.blur() } label: {
                Image(systemName: "keyboard.chevron.compact.down").frame(width: 44, height: 40)
            }
            .buttonStyle(.borderless)
            .accessibilityLabel("Chiudi tastiera")
            .accessibilityIdentifier("compose-hide-keyboard")
        }
        .frame(height: 44)
        .background(.bar)
        .overlay(alignment: .top) { Divider() }
    }

    private var header: some View {
        VStack(spacing: 0) {
            if (mailbox.state?.accounts.count ?? 0) > 1 {
                HStack(spacing: 8) {
                    Text("Da").foregroundStyle(Color.milo.muted).frame(width: 34, alignment: .leading)
                    Picker("Da", selection: $draft.accountId) {
                        ForEach(mailbox.state?.accounts ?? []) { account in
                            Text(account.email).tag(account.id)
                        }
                    }
                    .labelsHidden()
                    .pickerStyle(.menu)
                    Spacer(minLength: 0)
                }
                .composeRow(vertical: 4)
                Divider()
            }
            recipientField("A", text: $draft.to, slot: .to, identifier: "compose-to")
            Divider()
            recipientField("Cc", text: $draft.cc, slot: .cc, identifier: "compose-cc")
            Divider()
            TextField("Oggetto", text: $draft.subject)
                .focused($subjectFocused)
                .accessibilityIdentifier("compose-subject")
                .composeRow()
            Divider()
            if let error {
                Text(error).foregroundStyle(Color.milo.danger).composeRow()
                Divider()
            }
        }
    }

    private var options: some View {
        Menu {
            if let templates = mailbox.state?.templates, !templates.isEmpty {
                Menu {
                    ForEach(templates, id: \.name) { template in
                        Button(template.name) { editor.exec("insertHTML", MailEditor.paragraphs(from: template.body)) }
                    }
                } label: { Label("Risposte salvate", systemImage: "text.badge.plus") }
            }
            Toggle("Traccia apertura", isOn: $draft.tracksOpen)
                .accessibilityIdentifier("compose-track")
            Picker("Ricordamelo se non risponde", selection: $followup) {
                Text("Mai").tag(0)
                Text("Entro 1 giorno").tag(1)
                Text("Entro 3 giorni").tag(3)
                Text("Entro una settimana").tag(7)
            }
            .pickerStyle(.menu)
        } label: { Image(systemName: "ellipsis.circle") }
        .accessibilityLabel("Opzioni")
        .accessibilityIdentifier("compose-options")
    }

    private var signaturePreview: MailEditor.SignaturePreview? {
        guard let text = mailbox.state?.signatures?[draft.accountId]?.trimmingCharacters(in: .whitespacesAndNewlines),
              !text.isEmpty, let png = signatureCards[draft.accountId] else { return nil }
        return MailEditor.SignaturePreview(text: text, png: png)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if !writing { header }
                HTMLEditorView(html: draft.html ?? "", remoteImages: false, editing: true, signature: signaturePreview,
                               controller: editor) { html, text in
                    draft.html = html
                    draft.body = text
                    draft.revision = max(Int(Date().timeIntervalSince1970 * 1000), draft.revision + 1)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .ignoresSafeArea(.container, edges: writing ? [] : .bottom)
                if writing { formatBar }
            }
            .frame(maxHeight: .infinity, alignment: .top)
            .animation(.easeOut(duration: 0.2), value: writing)
            .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in keyboardUp = true }
            .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in keyboardUp = false }
            .onChange(of: draft.accountId) { old, new in
                let signatures = mailbox.state?.signatures
                let html = MailEditor.swappingSignature(in: draft.html ?? "", from: signatures?[old], to: signatures?[new])
                guard html != (draft.html ?? "") else { return }
                draft.html = html
                if let before = signatures?[old], !before.isEmpty, draft.body.contains("-- \n" + before) {
                    let after = signatures?[new].flatMap { $0.isEmpty ? nil : "-- \n" + $0 } ?? ""
                    draft.body = draft.body.replacingOccurrences(of: "-- \n" + before, with: after)
                } else if let after = signatures?[new], !after.isEmpty, !draft.body.contains("-- \n" + after) {
                    draft.body += "\n\n-- \n" + after
                }
                draft.revision = max(Int(Date().timeIntervalSince1970 * 1000), draft.revision + 1)
            }
            .task(id: draft.accountId) {
                let account = draft.accountId
                guard signatureCards[account] == nil, mailbox.state?.signatures?[account]?.isEmpty == false,
                      let png = try? await mailbox.api.signatureCard(accountId: account) else { return }
                signatureCards[account] = png
            }
            .onChange(of: draft.to) { _, _ in if recipientSlot == .to { refreshSuggestions() } }
            .onChange(of: draft.cc) { _, _ in if recipientSlot == .cc { refreshSuggestions() } }
            .onChange(of: recipientSlot) { _, _ in refreshSuggestions() }
            .alert("Inserisci link", isPresented: $linkPrompt) {
                TextField("https://", text: $linkURL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Annulla", role: .cancel) {}
                Button("Inserisci") {
                    let url = linkURL.trimmingCharacters(in: .whitespacesAndNewlines)
                    if url.lowercased().hasPrefix("https://") || url.lowercased().hasPrefix("http://") || url.lowercased().hasPrefix("mailto:") {
                        editor.exec("createLink", url)
                    }
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Menu("Chiudi") {
                        Button("Salva bozza", systemImage: "tray.and.arrow.down") { saveAndClose() }
                        Button("Elimina bozza", systemImage: "trash", role: .destructive) {
                            Task { await mailbox.discard(draft) }
                            dismiss()
                        }
                    }
                }
                ToolbarItemGroup(placement: .confirmationAction) {
                    options
                    Button { scheduling = true } label: { Image(systemName: "clock") }
                        .accessibilityLabel("Programma l’invio")
                    Button { send() } label: {
                        if sending { ProgressView() } else { Image(systemName: "paperplane.fill") }
                    }
                    .accessibilityLabel("Invia")
                    .accessibilityIdentifier("compose-send")
                    .disabled(sending)
                }
            }
            .sheet(isPresented: $scheduling) { scheduleSheet.presentationDetents([.medium, .large]) }
            .onAppear {
                if !hasHTML { draft.html = MailEditor.paragraphs(from: draft.body) }
            }
            .interactiveDismissDisabled(sending)
        }
    }

    private var scheduleSheet: some View {
        NavigationStack {
            List {
                Section("Invia") {
                    ForEach(presets, id: \.1) { date, label in
                        Button { schedule(at: date) } label: {
                            VStack(alignment: .leading) {
                                Text(label)
                                Text(date.formatted(.dateTime.weekday(.wide).day().month().hour().minute()))
                                    .font(.caption).foregroundStyle(Color.milo.muted)
                            }
                        }
                    }
                }
                Section("Oppure scegli") {
                    DatePicker("Data e ora", selection: $customDate, in: Date()...)
                    Button("Programma") { schedule(at: customDate) }
                }
            }
            .navigationTitle("Quando lo invio?")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var presets: [(Date, String)] {
        let calendar = Calendar.current
        func at(_ days: Int, _ hour: Int) -> Date {
            calendar.date(bySettingHour: hour, minute: 0, second: 0, of: calendar.date(byAdding: .day, value: days, to: Date())!)!
        }
        var result = [(Date().addingTimeInterval(3600), "Tra un’ora")]
        if calendar.component(.hour, from: Date()) < 17 { result.append((at(0, 18), "Oggi alle 18")) }
        result.append((at(1, 8), "Domani alle 8"))
        let monday = calendar.nextDate(after: Date(), matching: DateComponents(hour: 8, weekday: 2), matchingPolicy: .nextTime)!
        result.append((monday, "Lunedì alle 8"))
        return result
    }

    private func send() {
        error = nil
        if draft.body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            error = "Il messaggio è vuoto: scrivi il testo prima di inviarlo."
            return
        }
        sending = true
        let draft = draft
        Task {
            defer { sending = false }
            do {
                try await mailbox.send(draft, followupDays: followup == 0 ? nil : followup)
                dismiss()
                notice.show("Messaggio in partenza…", actionTitle: "Annulla", duration: Mailbox.undoSeconds) {
                    do {
                        try await mailbox.undoSend(draft)
                        notice.show("Invio annullato: il messaggio è nelle bozze.")
                    } catch {
                        notice.show("Troppo tardi: il messaggio è già partito.")
                    }
                }
            } catch {
                self.error = (error as? APIError)?.message ?? error.localizedDescription
            }
        }
    }

    private func schedule(at date: Date) {
        scheduling = false
        let draft = draft
        Task {
            do {
                try await mailbox.schedule(draft, at: date, followupDays: followup == 0 ? nil : followup)
                dismiss()
                notice.show("Invio programmato per " + date.formatted(.dateTime.day().month().hour().minute()) + ".")
            } catch {
                self.error = (error as? APIError)?.message ?? error.localizedDescription
            }
        }
    }

    private func saveAndClose() {
        let draft = draft
        dismiss()
        Task {
            do { try await mailbox.save(draft); notice.show("Bozza salvata.") }
            catch { notice.show("Bozza salvata sul dispositivo: la sincronizzo appena possibile.") }
        }
    }
}

private extension View {
    func composeRow(vertical: CGFloat = 11) -> some View {
        padding(.horizontal, 16).padding(.vertical, vertical).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
    }
}
