import MiloKit
import SwiftUI
import WebKit

struct ThreadView: View {
    var key: String
    @Binding var compose: Draft?
    @Binding var selectedKey: String?
    @Environment(Mailbox.self) private var mailbox
    @Environment(Notice.self) private var notice
    @Environment(\.dismiss) private var dismiss
    @State private var expanded: Set<String> = []
    @State private var replies: [String]?
    @State private var loadingReplies = false

    private var conversation: Conversation? { mailbox.conversation(key) }
    private var peer: Message? { mailbox.thread.last { !$0.sent.value } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text(Mailbox.subjectCore(mailbox.thread.last?.subject ?? conversation?.subject))
                    .font(.title2.weight(.semibold))
                    .padding(.top, 4)
                if let analysis = mailbox.thread.last(where: { $0.analysis != nil })?.analysis {
                    AnalysisCard(analysis: analysis)
                }
                if mailbox.thread.isEmpty && mailbox.loadingThread {
                    ProgressView("Carico la conversazione…").frame(maxWidth: .infinity).padding(.top, 40)
                } else if mailbox.thread.isEmpty {
                    VStack(spacing: 12) {
                        Text(mailbox.threadError ?? "Questa conversazione non è ancora sul dispositivo.")
                            .foregroundStyle(Color.milo.muted)
                            .multilineTextAlignment(.center)
                        Button("Riprova") { Task { if let conversation { await mailbox.open(conversation) } } }
                            .buttonStyle(.bordered)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 40)
                    .accessibilityIdentifier("thread-error")
                }
                ForEach(mailbox.thread) { message in
                    MessageCard(message: message, expanded: isExpanded(message)) {
                        toggle(message)
                    }
                }
                if !mailbox.thread.isEmpty { actions }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 80)
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { toolbar }
        .task(id: key) {
            if let conversation { await mailbox.open(conversation) }
        }
    }

    private func isExpanded(_ message: Message) -> Bool {
        message.id == mailbox.thread.last?.id || expanded.contains(message.id)
    }

    private func toggle(_ message: Message) {
        if expanded.contains(message.id) { expanded.remove(message.id) } else {
            expanded.insert(message.id)
            if message.bodyLoaded != true { Task { try? await mailbox.loadBody(message.id) } }
        }
    }

    private var actions: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Button { compose = mailbox.replyDraft() } label: { Label("Rispondi", systemImage: "arrowshape.turn.up.left") }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("reply")
                Button { compose = mailbox.replyDraft(all: true) } label: { Label("Tutti", systemImage: "arrowshape.turn.up.left.2") }
                    .buttonStyle(.bordered)
                Button { compose = mailbox.forwardDraft() } label: { Label("Inoltra", systemImage: "arrowshape.turn.up.right") }
                    .buttonStyle(.bordered)
            }
            .labelStyle(.titleAndIcon)
            .font(.subheadline)
            if let peer {
                if let replies {
                    ForEach(replies, id: \.self) { reply in
                        Button { compose = mailbox.replyDraft(body: reply) } label: {
                            Text(reply).font(.subheadline).multilineTextAlignment(.leading)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 16).padding(.vertical, 12)
                                .background(Color.milo.surfaceAlt, in: RoundedRectangle(cornerRadius: 14))
                                .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color.milo.line))
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Apre una risposta con questo testo")
                    }
                } else {
                    Button {
                        loadingReplies = true
                        Task {
                            defer { loadingReplies = false }
                            do { replies = try await mailbox.api.suggestions(for: peer.id) }
                            catch { notice.show((error as? APIError)?.message ?? "Suggerimenti non disponibili.") }
                        }
                    } label: {
                        Label(loadingReplies ? "Milo prepara le risposte…" : "Suggerisci risposte rapide", systemImage: "sparkles")
                            .font(.subheadline)
                    }
                    .disabled(loadingReplies)
                }
            }
        }
        .padding(.top, 6)
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        if let conversation {
            ToolbarItemGroup(placement: .bottomBar) {
                Button { act(conversation, MailEdit.Patch(archived: true), "Archiviata.") } label: { Image(systemName: "archivebox") }
                    .accessibilityLabel("Archivia")
                Spacer()
                Button { act(conversation, MailEdit.Patch(), "Nel cestino.", deleted: true) } label: { Image(systemName: "trash") }
                    .accessibilityLabel("Elimina")
                Spacer()
                Button { act(conversation, MailEdit.Patch(starred: !conversation.starred.value)) } label: {
                    Image(systemName: conversation.starred.value ? "star.fill" : "star")
                }
                .accessibilityLabel(conversation.starred.value ? "Rimuovi dai preferiti" : "Aggiungi ai preferiti")
                Spacer()
                Button { act(conversation, MailEdit.Patch(read: !conversation.read.value)) } label: {
                    Image(systemName: conversation.read.value ? "envelope.badge" : "envelope.open")
                }
                .accessibilityLabel(conversation.read.value ? "Segna da leggere" : "Segna come letta")
                Spacer()
                Menu {
                    if let email = peer?.senderEmail {
                        Button(mailbox.isVIP(email) ? "Rimuovi dai VIP" : "Mittente VIP", systemImage: "crown") {
                            Task { await mailbox.toggleVIP(email) }
                        }
                        Button("Blocca il mittente", systemImage: "nosign", role: .destructive) {
                            Task {
                                do { try await mailbox.api.block(email); notice.show("Mittente bloccato: le sue email vanno in archivio.") }
                                catch { notice.show((error as? APIError)?.message ?? "Operazione non riuscita.") }
                                await mailbox.refresh()
                            }
                        }
                    }
                    if let peer, peer.unsubscribe != nil {
                        Button("Disiscriviti", systemImage: "envelope.badge.shield.half.filled") { unsubscribe(peer) }
                    }
                    Button("Rimanda a domani", systemImage: "clock") {
                        let tomorrow = Calendar.current.date(byAdding: .day, value: 1, to: Calendar.current.startOfDay(for: Date()))!
                            .addingTimeInterval(8 * 3600)
                        act(conversation, MailEdit.Patch(snoozedUntil: tomorrow.timeIntervalSince1970), "Rimandata a domani.")
                    }
                } label: { Image(systemName: "ellipsis.circle") }
            }
        }
    }

    private func act(_ conversation: Conversation, _ patch: MailEdit.Patch, _ message: String? = nil, deleted: Bool = false) {
        // Leaving the list moves on to the next conversation, like the desktop client.
        if deleted || patch.archived == true || patch.snoozedUntil != nil {
            selectedKey = mailbox.neighbour(of: conversation.key)
        }
        Task { await mailbox.mutate(conversation, patch, deleted: deleted) }
        if let message { notice.show(message) }
    }

    private func unsubscribe(_ message: Message) {
        Task {
            do {
                let result = try await mailbox.api.unsubscribe(message.id)
                if result.method == "link", let url = result.url.flatMap(URL.init(string:)) {
                    await UIApplication.shared.open(url)
                    notice.show("Ho aperto la pagina di disiscrizione del mittente.")
                } else {
                    notice.show(result.method == "email" ? "Richiesta di disiscrizione inviata." : "Disiscrizione completata.")
                }
            } catch {
                notice.show((error as? APIError)?.message ?? "Disiscrizione non riuscita.")
            }
        }
    }
}

struct AnalysisCard: View {
    var analysis: Analysis

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Il punto, secondo Milo", systemImage: "sparkles")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Color.milo.accent)
            if let summary = analysis.summary { Text(summary).font(.subheadline) }
            ForEach(analysis.actionItems ?? [], id: \.self) { item in
                Label(item, systemImage: "circle").font(.footnote).foregroundStyle(Color.milo.muted)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.milo.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.milo.line))
    }
}

struct MessageCard: View {
    var message: Message
    var expanded: Bool
    var onToggle: () -> Void
    @Environment(Mailbox.self) private var mailbox
    @State private var height: CGFloat = 120

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button(action: onToggle) {
                HStack(alignment: .top, spacing: 10) {
                    Avatar(name: message.sent.value ? "Tu" : message.sender, size: expanded ? 34 : 28)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(message.sent.value ? "Tu" : (message.sender ?? message.senderEmail ?? ""))
                            .font(.subheadline.weight(.semibold)).foregroundStyle(.primary)
                        Text(expanded ? (message.senderEmail ?? "") : (message.preview ?? ""))
                            .font(.caption).foregroundStyle(Color.milo.muted).lineLimit(1)
                    }
                    Spacer()
                    Text(Format.date(message.date, long: true)).font(.caption).foregroundStyle(Color.milo.muted)
                }
            }
            .buttonStyle(.plain)
            if expanded {
                if message.bodyLoaded == true {
                    if let html = message.html, !html.isEmpty {
                        MailWebView(html: MailHTML.document(html), height: $height)
                            .frame(height: height)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                    } else {
                        Text(linked(message.body ?? ""))
                            .font(.body)
                            .textSelection(.enabled)
                    }
                    if let attachments = message.attachments, !attachments.isEmpty {
                        ForEach(attachments, id: \.index) { attachment in
                            Link(destination: mailbox.api.attachmentURL(messageId: message.id, index: attachment.index,
                                                                        preview: attachment.type == "application/pdf")) {
                                Label(attachment.name ?? "Allegato", systemImage: "paperclip").font(.footnote)
                            }
                        }
                    }
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding()
                        .task { try? await mailbox.loadBody(message.id) }
                }
            }
        }
        .padding(expanded ? 12 : 10)
        .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 10))
        .overlay(alignment: .leading) {
            if message.sent.value { Rectangle().fill(Color.milo.accent).frame(width: 3).clipShape(RoundedRectangle(cornerRadius: 2)) }
        }
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.milo.line))
    }

    /// Plain-text mail: detect links so they open in Safari.
    private func linked(_ text: String) -> AttributedString {
        var result = AttributedString(text)
        guard let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue) else { return result }
        for match in detector.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            guard let url = match.url, let range = Range(match.range, in: text),
                  let lower = AttributedString.Index(range.lowerBound, within: result),
                  let upper = AttributedString.Index(range.upperBound, within: result) else { continue }
            result[lower..<upper].link = url
        }
        return result
    }
}

/// Sanitized mail HTML in a WebView with JavaScript off for the content. The app's own script
/// (linkify, quoted history, height) runs in the client world; links open in Safari.
struct MailWebView: UIViewRepresentable {
    var html: String
    @Binding var height: CGFloat

    func makeCoordinator() -> Coordinator { Coordinator(height: $height) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        configuration.dataDetectorTypes = [.phoneNumber]
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.scrollView.isScrollEnabled = false
        view.isOpaque = false
        view.backgroundColor = .white
        view.loadHTMLString(html, baseURL: nil)
        context.coordinator.html = html
        // Images arriving later and opened quotes change the size: follow the content.
        let coordinator = context.coordinator
        coordinator.observation = view.scrollView.observe(\.contentSize, options: [.new]) { [weak coordinator, weak view] _, _ in
            // The scroll size never shrinks below the frame: measure the document itself.
            Task { @MainActor in
                guard let coordinator, let view, coordinator.ready else { return }
                await coordinator.measure(view)
            }
        }
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        if context.coordinator.html != html {
            context.coordinator.html = html
            view.loadHTMLString(html, baseURL: nil)
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var height: Binding<CGFloat>
        var html = ""
        var observation: NSKeyValueObservation?

        init(height: Binding<CGFloat>) { self.height = height }

        var ready = false

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            Task { @MainActor in
                _ = try? await webView.callAsyncJavaScript(MailHTML.enhanceScript, contentWorld: .defaultClient)
                ready = true
                await measure(webView)
            }
        }

        @MainActor
        func measure(_ webView: WKWebView) async {
            // Fixed-width newsletters (600px tables) shrink to the screen like in Mail, instead of
            // overflowing a view that cannot scroll sideways.
            let script = """
            const c = document.querySelector('.milo-email-document');
            if (!c.dataset.fitted) {
              c.dataset.fitted = '1';
              const natural = c.scrollWidth, available = document.documentElement.clientWidth;
              if (natural > available + 2) c.style.zoom = String(available / natural);
            }
            return Math.ceil(c.getBoundingClientRect().height);
            """
            guard let value = try? await webView.callAsyncJavaScript(script, contentWorld: .defaultClient) as? NSNumber else { return }
            let measured = max(80, CGFloat(value.doubleValue))
            if abs(height.wrappedValue - measured) > 1 { height.wrappedValue = measured }
        }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction) async -> WKNavigationActionPolicy {
            if action.navigationType == .linkActivated, let url = action.request.url {
                await UIApplication.shared.open(url)
                return .cancel
            }
            return action.navigationType == .other ? .allow : .cancel
        }
    }
}
