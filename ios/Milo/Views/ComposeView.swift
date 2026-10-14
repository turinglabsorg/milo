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

    private var title: String {
        switch draft.mode {
        case .reply: "Rispondi"
        case .replyAll: "Rispondi a tutti"
        case .forward: "Inoltra"
        case .new: "Nuovo messaggio"
        }
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
                    TextField("A", text: $draft.to)
                        .keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityIdentifier("compose-to")
                    TextField("Cc", text: $draft.cc)
                        .keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("Oggetto", text: $draft.subject)
                        .accessibilityIdentifier("compose-subject")
                }
                Section {
                    TextEditor(text: $draft.body)
                        .frame(minHeight: 220)
                        .focused($bodyFocused)
                        .accessibilityIdentifier("compose-body")
                }
                Section {
                    if let templates = mailbox.state?.templates, !templates.isEmpty {
                        Menu {
                            ForEach(templates, id: \.name) { template in
                                Button(template.name) { draft.body = template.body + draft.body }
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
            .onAppear { if draft.mode != .new { bodyFocused = true } }
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
