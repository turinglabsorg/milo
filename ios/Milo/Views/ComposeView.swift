import MiloKit
import SwiftUI

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
    @FocusState private var bodyFocused: Bool
    @FocusState private var recipientSlot: RecipientSlot?
    @State private var suggestions: [Recipient] = []
    @State private var suggestTask: Task<Void, Never>?
    @State private var editingHTML = false
    @State private var remoteImages = false
    @State private var editorHeight: CGFloat = 240
    @State private var editor = HTMLEditorController()
    @State private var linkPrompt = false
    @State private var linkURL = "https://"

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
        TextField(title, text: text)
            .keyboardType(.emailAddress)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .focused($recipientSlot, equals: slot)
            .accessibilityIdentifier(identifier)
        if recipientSlot == slot {
            ForEach(suggestions) { person in
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

    private var formatBinding: Binding<Bool> {
        Binding(get: { hasHTML }, set: { formatted in
            guard formatted != hasHTML else { return }
            if formatted {
                draft.html = MailEditor.paragraphs(from: draft.body)
                editingHTML = true
            } else {
                let previous = draft.html
                draft.html = ""
                editingHTML = false
                notice.show("Formattazione rimossa: resta il testo semplice.", actionTitle: "Annulla", duration: 8) {
                    draft.html = previous
                }
            }
            draft.revision = max(Int(Date().timeIntervalSince1970 * 1000), draft.revision + 1)
        })
    }

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

    @ViewBuilder
    private var richEditor: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 4) {
                if editingHTML {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 2) {
                            ForEach(Self.tools) { tool in
                                Button {
                                    if tool.command == "createLink" { linkURL = "https://"; linkPrompt = true }
                                    else { editor.exec(tool.command) }
                                } label: {
                                    Image(systemName: tool.symbol).frame(width: 36, height: 36)
                                }
                                .buttonStyle(.borderless)
                                .accessibilityLabel(tool.title)
                            }
                        }
                    }
                }
                Spacer(minLength: 0)
                Button(editingHTML ? "Fine" : "Modifica") { editingHTML.toggle() }
                    .buttonStyle(.bordered)
                    .accessibilityIdentifier("compose-edit-html")
            }
            HTMLEditorView(html: draft.html ?? "", remoteImages: remoteImages, editing: editingHTML,
                           height: $editorHeight, controller: editor) { html, text in
                draft.html = html
                draft.body = text
                draft.revision = max(Int(Date().timeIntervalSince1970 * 1000), draft.revision + 1)
            }
            .frame(height: editorHeight)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(editingHTML ? Color.milo.accent : Color.milo.line, lineWidth: 1))
            if !remoteImages {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("Immagini esterne bloccate: aprire la bozza non attiva il pixel di tracciamento.")
                    Button("Carica immagini") { remoteImages = true }.buttonStyle(.borderless)
                }
                .font(.caption2)
                .foregroundStyle(Color.milo.muted)
            }
        }
        .padding(.vertical, 4)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    if (mailbox.state?.accounts.count ?? 0) > 1 {
                        Picker("Da", selection: $draft.accountId) {
                            ForEach(mailbox.state?.accounts ?? []) { account in
                                Text(account.email).tag(account.id)
                            }
                        }
                    }
                    recipientField("A", text: $draft.to, slot: .to, identifier: "compose-to")
                    recipientField("Cc", text: $draft.cc, slot: .cc, identifier: "compose-cc")
                    TextField("Oggetto", text: $draft.subject)
                        .accessibilityIdentifier("compose-subject")
                }
                Section {
                    Picker("Formato", selection: formatBinding) {
                        Text("Testo semplice").tag(false)
                        Text("Formattato").tag(true)
                    }
                    .pickerStyle(.segmented)
                    .accessibilityIdentifier("compose-format")
                    if hasHTML {
                        richEditor
                    } else {
                        TextEditor(text: $draft.body)
                            .frame(minHeight: 220)
                            .focused($bodyFocused)
                            .accessibilityIdentifier("compose-body")
                    }
                }
                Section {
                    if let templates = mailbox.state?.templates, !templates.isEmpty {
                        Menu {
                            ForEach(templates, id: \.name) { template in
                                Button(template.name) {
                                    if hasHTML {
                                        editingHTML = true
                                        editor.exec("insertHTML", MailEditor.paragraphs(from: template.body))
                                    } else {
                                        draft.body = template.body + draft.body
                                    }
                                }
                            }
                        } label: { Label("Risposte salvate", systemImage: "text.badge.plus") }
                    }
                    Picker("Ricordamelo se non risponde", selection: $followup) {
                        Text("Mai").tag(0)
                        Text("Entro 1 giorno").tag(1)
                        Text("Entro 3 giorni").tag(3)
                        Text("Entro una settimana").tag(7)
                    }
                }
                if let error {
                    Section { Text(error).foregroundStyle(Color.milo.danger) }
                }
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
            .onAppear { if draft.mode != .new && !hasHTML { bodyFocused = true } }
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
        sending = true
        error = nil
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
