import Foundation
import Observation

/// The app's model. Lists render from the local catalogue first, then refresh in background;
/// edits are journaled on the device before the UI shows them and synchronize afterwards.
@MainActor
@Observable
public final class Mailbox {
    public let api: APIClient
    let cache: MailCache

    public var authenticated = true
    public var online = true
    public var syncing = false
    public private(set) var downloadingMail = false
    public var lastError: String?
    public var state: ServiceState?
    public var view: MailView = .inbox
    public var category: String?
    public var account: String?
    public var search = ""
    public private(set) var conversations: [Conversation] = []
    public private(set) var todos: [Todo] = []
    public private(set) var drafts: [Draft] = []
    public private(set) var thread: [Message] = []
    public private(set) var selectedKey: String?
    public private(set) var loadingThread = false
    public private(set) var threadError: String?
    public private(set) var pendingCount = 0

    private var catalogue: [String: Conversation] = [:]
    private var serverSearch: [String: [String]] = [:]
    private var lastCatalogueRefresh = Date.distantPast
    private var flushing = false
    /// "Offline" is shown only after two refreshes in a row could not reach the service:
    /// one failed request while the VPN wakes up is not an outage.
    private var unreachableRefreshes = 0

    public static let undoSeconds: TimeInterval = 10

    public init(api: APIClient, cache: MailCache) {
        self.api = api
        self.cache = cache
    }

    // MARK: Loading

    /// Show the cached mailbox immediately, then refresh from the service.
    public func start() async {
        state = await cache.state()
        await reloadCatalogue()
        pendingCount = await cache.pending().count
        await downloadMail()
    }

    public func downloadMail() async {
        guard !downloadingMail else { return }
        downloadingMail = true
        defer { downloadingMail = false }
        do {
            try await api.downloadMail()
        } catch {
            await refresh()
            lastError = error.localizedDescription
            return
        }
        for attempt in 0..<60 {
            guard !Task.isCancelled else { return }
            await refresh()
            guard authenticated, online else { return }
            if attempt > 0 && !(state?.sync?.contains(where: \.working) ?? false) { return }
            do { try await Task.sleep(nanoseconds: 1_000_000_000) }
            catch { return }
        }
    }

    public func refresh() async {
        syncing = true
        defer { syncing = false }
        do {
            let status = try await api.status()
            authenticated = status.authenticated
            guard authenticated else { return }
            let fresh = try await api.state()
            state = fresh
            try? await cache.storeState(fresh)
            online = true
            unreachableRefreshes = 0
            lastError = nil
            await flush()
            switch view {
            case .todo: todos = try await api.todos()
            case .drafts: drafts = mergeDrafts(try await api.drafts(), await cache.pendingDrafts())
            default:
                let shown = conversations
                let rows = try await api.conversations(view: view, account: account, search: search)
                if !search.isEmpty { serverSearch[searchKey] = rows.map(\.key) }
                try await cache.merge(rows)
                if search.isEmpty { await reconcile(shown: shown, returned: rows) }
                await reloadCatalogue()
            }
            if Date().timeIntervalSince(lastCatalogueRefresh) > 120 {
                lastCatalogueRefresh = Date()
                Task { await self.refreshCatalogue() }
            }
        } catch let error as APIError {
            if error.status == 0 {
                unreachableRefreshes += 1
                online = unreachableRefreshes < 2
            }
            if error.status == 401 { authenticated = false }
            lastError = error.message
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// Rows this view showed but the service no longer lists (trashed, archived or moved on
    /// another device) are checked one by one: gone ones leave the device, moved ones update.
    private func reconcile(shown: [Conversation], returned: [Conversation]) async {
        let keys = Set(returned.map(\.key))
        let oldest = returned.count >= 100 ? (returned.map(\.date).min() ?? 0) : 0
        let pending = Set(await cache.pending().map(\.key))
        for row in shown where !keys.contains(row.key) && row.date >= oldest && !pending.contains(row.key) {
            do {
                try await cache.merge([try await api.conversation(account: row.accountId, thread: row.threadId ?? row.id)])
            } catch let error as APIError where error.status == 404 {
                try? await cache.remove(row.key)
            } catch {
                break
            }
        }
    }

    /// Page through the chronological catalogue so folders and search work offline.
    public func refreshCatalogue(maxPages: Int = 10) async {
        var cursor: Page.Cursor?
        for _ in 0..<maxPages {
            guard let page = try? await api.catalogue(after: cursor) else { return }
            try? await cache.merge(page.messages)
            guard let next = page.next else { break }
            cursor = next
            try? await Task.sleep(nanoseconds: 300_000_000)
        }
        await reloadCatalogue()
        await prefetchRecent()
    }

    private func reloadCatalogue() async {
        catalogue = Dictionary((await cache.conversations()).map { ($0.key, $0) }, uniquingKeysWith: { $1 })
        applyFilter()
    }

    private var searchKey: String { [view.rawValue, account ?? "", search].joined(separator: "|") }

    /// The same view rules as the web client's local replica.
    public func applyFilter() {
        let now = Date().timeIntervalSince1970
        let term = search.trimmingCharacters(in: .whitespaces).lowercased()
        let known = Set(serverSearch[searchKey] ?? [])
        conversations = catalogue.values.filter { row in
            if row.deleted == true { return false }
            if let account, row.accountId != account { return false }
            switch view {
            case .inbox:
                let snoozed = (row.snoozedUntil ?? 0) > now
                if !(row.hasInbox?.value ?? false) || snoozed { return false }
                if let category, row.category != category { return false }
            case .unread:
                if !(row.hasInbox?.value ?? false)
                    || (row.inboxUnreadCount ?? row.unreadCount ?? (row.read.value ? 0 : 1)) <= 0 { return false }
            case .starred: if !row.starred.value { return false }
            case .sent: if !(row.hasSent?.value ?? row.sent.value) { return false }
            case .archive: if !(row.hasArchive?.value ?? false) { return false }
            case .snoozed: if !((row.snoozedUntil ?? 0) > now) { return false }
            case .todo, .drafts: return false
            }
            if term.isEmpty || known.contains(row.key) { return true }
            return [row.sender, row.senderEmail, row.subject, row.preview].compactMap { $0 }
                .joined(separator: " ").lowercased().contains(term)
        }
        .sorted { ($0.pinned.value ? 1 : 0, $0.date) > ($1.pinned.value ? 1 : 0, $1.date) }
        .prefix(200).map { $0 }
    }

    public func show(_ view: MailView, account: String? = nil, category: String? = nil) async {
        self.view = view
        self.account = account
        self.category = view == .inbox ? category : nil
        applyFilter()
        await refresh()
    }

    // MARK: Reading

    /// Loads independently of the view that asked: a re-created screen must not cancel the download.
    public func open(_ conversation: Conversation) async {
        await Task { await self.load(conversation) }.value
    }

    /// Keeps "loading" and retries until the conversation arrives or another one is opened.
    /// Errors are not shown: a mailbox on Tailscale can need a few attempts after a pause.
    private func load(_ conversation: Conversation) async {
        selectedKey = conversation.key
        threadError = nil
        loadingThread = true
        defer { if selectedKey == conversation.key { loadingThread = false } }
        if let cached = await cache.thread(conversation.key) { thread = await withBodies(cached) }
        else { thread = [] }
        var pause: Double = 0.5
        while selectedKey == conversation.key {
            do {
                let fresh = try await api.thread(conversation.id)
                try? await cache.storeThread(conversation.key, fresh)
                guard selectedKey == conversation.key else { return }
                thread = await withBodies(fresh)
                if let latest = fresh.last { try? await loadBody(latest.id) }
                if !conversation.read.value && conversation.unreadCount ?? 1 > 0 {
                    await mutate(conversation, MailEdit.Patch(read: true))
                }
                return
            } catch is CancellationError {
                return
            } catch let error as APIError where error.status == 404 {
                if thread.isEmpty, selectedKey == conversation.key { threadError = "Questa conversazione non c’è più." }
                return
            } catch {
                // Cached content is already on screen: refresh it later instead of retrying now.
                if !thread.isEmpty { return }
                try? await Task.sleep(nanoseconds: UInt64(pause * 1_000_000_000))
                pause = min(pause * 2, 5)
            }
        }
    }

    private func withBodies(_ messages: [Message]) async -> [Message] {
        var result: [Message] = []
        for message in messages {
            if let body = await cache.body(message.id, version: message.contentVersion) {
                var merged = body
                merged.read = message.read
                merged.starred = message.starred
                merged.analysis = message.analysis ?? body.analysis
                merged.todos = message.todos ?? body.todos
                merged.toAddresses = message.toAddresses ?? body.toAddresses
                result.append(merged)
            } else {
                result.append(message)
            }
        }
        return result
    }

    /// Download one body unless this content version is already on the device.
    public func loadBody(_ id: String) async throws {
        let version = thread.first { $0.id == id }?.contentVersion
        if let cached = await cache.body(id, version: version) {
            replace(cached)
            return
        }
        let message = try await api.message(id)
        try? await cache.storeBody(message)
        replace(message)
    }

    private func replace(_ message: Message) {
        if let index = thread.firstIndex(where: { $0.id == message.id }) {
            var merged = message
            merged.todos = thread[index].todos ?? message.todos
            thread[index] = merged
        }
    }

    /// Open a thread from a message id (to-dos, recap priorities), using the catalogue row when known.
    public func open(messageId: String, accountId: String?, threadId: String?) async {
        let key = (accountId ?? "") + ":" + (threadId ?? messageId)
        let row = catalogue[key] ?? catalogue.values.first { $0.id == messageId }
            ?? Conversation(id: messageId, accountId: accountId ?? "", threadId: threadId, date: Date().timeIntervalSince1970)
        await open(row)
    }

    public func conversation(_ key: String) -> Conversation? { catalogue[key] }

    public func forwardDraft() -> Draft? {
        guard let message = thread.last else { return nil }
        let quoted = "\n\n---------- Messaggio inoltrato ----------\nDa: \(message.sender ?? "") <\(message.senderEmail ?? "")>\n" +
            "Oggetto: \(message.subject ?? "")\n\n\(message.body ?? message.preview ?? "")"
        var draft = Draft(accountId: message.accountId, subject: "Fwd: " + Mailbox.subjectCore(message.subject),
                          body: (signature(for: message.accountId) ?? "") + quoted, mode: .forward)
        draft.contextMessageId = message.id
        return draft
    }

    /// A push said new mail arrived: store its thread and latest body now, so it opens instantly.
    public func prefetch(messageId: String, accountId: String?, threadId: String?) async {
        guard let messages = try? await api.thread(messageId) else { return }
        let key = (accountId ?? messages.last?.accountId ?? "") + ":" + (threadId ?? messages.last?.threadId ?? messageId)
        try? await cache.storeThread(key, messages)
        if let latest = messages.last, await cache.body(latest.id, version: latest.contentVersion) == nil,
           let body = try? await api.message(latest.id) {
            try? await cache.storeBody(body)
        }
        if let rows = try? await api.conversations(view: .inbox) {
            try? await cache.merge(rows)
            await reloadCatalogue()
        }
    }

    /// The conversation to show after the current one leaves the list (trash, archive, snooze).
    public func neighbour(of key: String) -> String? {
        guard let index = conversations.firstIndex(where: { $0.key == key }) else { return nil }
        if index + 1 < conversations.count { return conversations[index + 1].key }
        return index > 0 ? conversations[index - 1].key : nil
    }

    /// Back in the foreground: a conversation left on an error is tried again.
    public func retryOpenThread() async {
        guard threadError != nil, let key = selectedKey, let row = catalogue[key] else { return }
        await open(row)
    }

    public func close() {
        selectedKey = nil
        thread = []
    }

    /// Low-concurrency background download of recent bodies so they open instantly and offline.
    public func prefetchRecent(limit: Int = 60) async {
        let recent = catalogue.values.filter { $0.deleted != true }.sorted { $0.date > $1.date }.prefix(limit)
        for row in recent {
            if await cache.body(row.id, version: row.contentVersion) != nil { continue }
            guard let message = try? await api.message(row.id) else { return }
            try? await cache.storeBody(message)
            try? await Task.sleep(nanoseconds: 150_000_000)
        }
    }

    // MARK: Editing

    public func mutate(_ conversation: Conversation, _ patch: MailEdit.Patch, deleted: Bool = false) async {
        let operation = MailEdit(key: conversation.key, messageId: conversation.id, patch: patch, deleted: deleted)
        do {
            try await cache.enqueue(operation)
        } catch {
            lastError = "Spazio sul dispositivo non disponibile: la modifica non è stata salvata."
            return
        }
        await reloadCatalogue()
        pendingCount = await cache.pending().count
        if deleted || patch.archived == true || patch.snoozedUntil != nil, selectedKey == conversation.key { close() }
        await flush()
    }

    /// Send the journal in order. Temporary failures wait for the next refresh; rejections stay visible.
    public func flush() async {
        guard !flushing else { return }
        flushing = true
        defer { flushing = false }
        for operation in await cache.pending() where operation.error == nil {
            do {
                try await api.apply(operation)
                try await cache.acknowledge(operation.id)
            } catch let error as APIError where error.isTemporary {
                break
            } catch let error as APIError where error.status == 404 {
                try? await cache.acknowledge(operation.id)
            } catch {
                try? await cache.fail(operation.id, error: (error as? APIError)?.message ?? error.localizedDescription)
            }
        }
        pendingCount = await cache.pending().count
    }

    // MARK: Composing

    public func signature(for accountId: String) -> String? {
        guard let text = state?.signatures?[accountId], !text.isEmpty else { return nil }
        return "\n\n-- \n" + text
    }

    public func replyDraft(all: Bool = false, body: String = "") -> Draft? {
        guard let source = thread.last(where: { !$0.sent.value }) ?? thread.last else { return nil }
        let mine = Set((state?.accounts ?? []).map { $0.email.lowercased() })
        var seen = mine
        func unique(_ addresses: [Address]) -> [String] {
            addresses.compactMap { address in
                let email = address.email.trimmingCharacters(in: .whitespaces)
                guard email.contains("@"), !seen.contains(email.lowercased()) else { return nil }
                seen.insert(email.lowercased())
                return email
            }
        }
        let primary: [Address] = source.sent.value ? (source.toAddresses ?? [])
            : (source.replyToAddresses?.isEmpty == false ? source.replyToAddresses! : [Address(name: nil, email: source.senderEmail ?? "")])
        let to = unique(all ? primary + (source.toAddresses ?? []) : primary)
        let cc = all ? unique(source.ccAddresses ?? []) : []
        let subject = "Re: " + Mailbox.subjectCore(source.subject)
        return Draft(accountId: source.accountId, to: to.joined(separator: ", "), cc: cc.joined(separator: ", "),
                     subject: subject, body: body + (signature(for: source.accountId) ?? ""), replyToId: source.id,
                     mode: all ? .replyAll : .reply)
    }

    public func newDraft() -> Draft? {
        guard let account = state?.accounts.first else { return nil }
        return Draft(accountId: account.id, body: signature(for: account.id) ?? "")
    }

    /// Save on the device first, then on the service.
    public func save(_ draft: Draft) async throws {
        var draft = draft
        draft.revision = max(draft.revision + 1, Int(Date().timeIntervalSince1970 * 1000))
        try await cache.keep(draft)
        _ = try await api.save(draft)
        try await cache.forget(draft: draft.id, revision: draft.revision)
    }

    /// Sending is always explicit: schedule a few seconds ahead so it can be undone.
    public func send(_ draft: Draft, followupDays: Int? = nil) async throws {
        guard !(draft.to + draft.cc).trimmingCharacters(in: .whitespaces).isEmpty else {
            throw APIError(status: 422, message: "Inserisci almeno un destinatario.")
        }
        try await save(draft)
        try await api.schedule(draft.id, at: Date().addingTimeInterval(Self.undoSeconds), followupDays: followupDays)
    }

    public func schedule(_ draft: Draft, at date: Date, followupDays: Int? = nil) async throws {
        try await save(draft)
        try await api.schedule(draft.id, at: date, followupDays: followupDays)
    }

    public func undoSend(_ draft: Draft) async throws {
        try await api.unschedule(draft.id)
    }

    public func discard(_ draft: Draft) async {
        try? await cache.forget(draft: draft.id)
        try? await api.deleteDraft(draft.id)
        drafts.removeAll { $0.id == draft.id }
    }

    private func mergeDrafts(_ remote: [Draft], _ local: [Draft]) -> [Draft] {
        var byId = Dictionary(remote.map { ($0.id, $0) }, uniquingKeysWith: { $1 })
        for draft in local where (byId[draft.id]?.revision ?? 0) < draft.revision { byId[draft.id] = draft }
        return byId.values.sorted { $0.revision > $1.revision }
    }

    // MARK: To-dos, senders, AI

    public func acceptAction(messageId: String, text: String) async throws {
        let accepted = try await api.acceptTodo(messageId: messageId, text: text)
        if let index = thread.firstIndex(where: { $0.id == messageId }) {
            thread[index].todos = (thread[index].todos ?? []).filter { $0.text != text } + [accepted]
            if let selectedKey { try? await cache.storeThread(selectedKey, thread) }
        }
        await refresh()
    }

    public func complete(_ todo: Todo) async {
        await complete([todo.id])
    }

    /// Marks every selected to-do done. The list drops them immediately; a failed write reloads.
    public func complete(_ ids: Set<String>) async {
        let pending = todos.filter { ids.contains($0.id) }
        guard !pending.isEmpty else { return }
        todos.removeAll { ids.contains($0.id) }
        for todo in pending {
            do { try await api.setTodo(todo.id, done: true) }
            catch { lastError = (error as? APIError)?.message; await refresh(); return }
        }
    }

    public func isVIP(_ email: String?) -> Bool {
        guard let email else { return false }
        return state?.vips?.contains(email.lowercased()) ?? false
    }

    public func toggleVIP(_ email: String) async {
        let vip = !isVIP(email)
        do {
            try await api.setVIP(email, vip)
            if vip { state?.vips = (state?.vips ?? []) + [email.lowercased()] }
            else { state?.vips?.removeAll { $0 == email.lowercased() } }
        } catch { lastError = (error as? APIError)?.message }
    }

    public static func subjectCore(_ subject: String?) -> String {
        let pattern = #"^\s*(?:(?:re|aw|sv|r|fw|fwd)(?:\[\d+\])?\s*:\s*)+"#
        let core = (subject ?? "").replacingOccurrences(of: pattern, with: "", options: [.regularExpression, .caseInsensitive])
            .trimmingCharacters(in: .whitespaces)
        return core.isEmpty ? "Senza oggetto" : core
    }

    /// Splits plain-text mail into the new text and the quoted history below it, like the web reader.
    public static func splitQuoted(_ body: String) -> (text: String, quoted: String?) {
        let pattern = #"^(?:On [^\n]{0,300}wrote:|Il giorno [^\n]{0,300}ha scritto:|Le [^\n]{0,300}[ée]crit\s*:|Am [^\n]{0,300}schrieb[^\n]*:|>\s)"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.anchorsMatchLines, .caseInsensitive]),
              let match = regex.firstMatch(in: body, range: NSRange(body.startIndex..., in: body)),
              match.range.location > 0, let range = Range(match.range, in: body) else { return (body, nil) }
        let text = String(body[..<range.lowerBound])
        return (text.replacingOccurrences(of: #"\s+$"#, with: "", options: .regularExpression), String(body[range.lowerBound...]))
    }
}
