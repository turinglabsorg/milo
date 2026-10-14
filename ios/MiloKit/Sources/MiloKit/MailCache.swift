import Foundation

/// Device cache required by docs/CLIENT_CACHE.md: catalogue, thread metadata, downloaded bodies,
/// the edit journal and unsent drafts survive restarts and are readable offline.
/// Plain files written atomically; on iOS they are protected by Data Protection.
public actor MailCache {
    let root: URL
    private var catalogue: [String: Conversation] = [:]
    private var journal: [MailEdit] = []
    private var drafts: [String: Draft] = [:]
    private var loaded = false

    public init(root: URL) {
        self.root = root
    }

    public static func standard() -> MailCache {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return MailCache(root: base.appendingPathComponent("MiloCache", isDirectory: true))
    }

    private func file(_ name: String) -> URL { root.appendingPathComponent(name) }

    private func ensureLoaded() {
        guard !loaded else { return }
        loaded = true
        try? FileManager.default.createDirectory(at: root.appendingPathComponent("bodies"), withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: root.appendingPathComponent("threads"), withIntermediateDirectories: true)
        if let rows: [Conversation] = read("catalogue.json") {
            catalogue = Dictionary(rows.map { ($0.key, $0) }, uniquingKeysWith: { $1 })
        }
        journal = read("journal.json") ?? []
        drafts = Dictionary(((read("drafts.json") as [Draft]?) ?? []).map { ($0.id, $0) }, uniquingKeysWith: { $1 })
    }

    private func read<T: Decodable>(_ name: String) -> T? {
        guard let data = try? Data(contentsOf: file(name)) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    private func write<T: Encodable>(_ value: T, _ name: String) throws {
        let data = try JSONEncoder().encode(value)
        #if os(iOS)
        try data.write(to: file(name), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        #else
        try data.write(to: file(name), options: .atomic)
        #endif
    }

    // MARK: Catalogue

    public func conversations() -> [Conversation] {
        ensureLoaded()
        return Array(catalogue.values)
    }

    public func conversation(_ key: String) -> Conversation? {
        ensureLoaded()
        return catalogue[key]
    }

    /// Merge fresh rows. Rows with a queued local edit keep the local intent until it is acknowledged.
    public func merge(_ rows: [Conversation]) throws {
        ensureLoaded()
        let pending = Set(journal.map(\.key))
        for row in rows where !pending.contains(row.key) {
            catalogue[row.key] = row
        }
        try write(Array(catalogue.values), "catalogue.json")
    }

    public func remove(_ key: String) throws {
        ensureLoaded()
        catalogue[key] = nil
        try write(Array(catalogue.values), "catalogue.json")
    }

    // MARK: Threads and bodies

    private static func safe(_ name: String) -> String {
        String(name.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) ? Character($0) : "_" })
    }

    public func thread(_ key: String) -> [Message]? {
        ensureLoaded()
        return read("threads/\(Self.safe(key)).json")
    }

    public func storeThread(_ key: String, _ messages: [Message]) throws {
        ensureLoaded()
        try write(messages, "threads/\(Self.safe(key)).json")
    }

    /// A body is reusable while its content version is unchanged; flags come from metadata.
    public func body(_ id: String, version: String?) -> Message? {
        ensureLoaded()
        guard let message: Message = read("bodies/\(Self.safe(id)).json") else { return nil }
        if let version, message.contentVersion != version { return nil }
        return message
    }

    public func storeBody(_ message: Message) throws {
        ensureLoaded()
        try write(message, "bodies/\(Self.safe(message.id)).json")
    }

    // MARK: Journal

    /// Commit a local edit before the UI confirms it; apply it to the catalogue optimistically.
    public func enqueue(_ operation: MailEdit) throws {
        ensureLoaded()
        journal.append(operation)
        try write(journal, "journal.json")
        if var row = catalogue[operation.key] {
            if operation.deleted { row.deleted = true }
            if let read = operation.patch.read { row.read = Flag(read); row.unreadCount = read ? 0 : max(1, row.receivedCount ?? 1) }
            if let starred = operation.patch.starred { row.starred = Flag(starred) }
            if let pinned = operation.patch.pinned { row.pinned = Flag(pinned) }
            if let archived = operation.patch.archived {
                row.archived = Flag(archived)
                row.hasInbox = Flag(!archived && (row.receivedCount ?? 1) > 0)
                row.hasArchive = Flag(archived)
            }
            if let snoozed = operation.patch.snoozedUntil { row.snoozedUntil = snoozed }
            catalogue[operation.key] = row
            try write(Array(catalogue.values), "catalogue.json")
        }
    }

    public func pending() -> [MailEdit] {
        ensureLoaded()
        return journal
    }

    public func acknowledge(_ id: String) throws {
        ensureLoaded()
        journal.removeAll { $0.id == id }
        try write(journal, "journal.json")
    }

    public func fail(_ id: String, error: String) throws {
        ensureLoaded()
        if let index = journal.firstIndex(where: { $0.id == id }) { journal[index].error = error }
        try write(journal, "journal.json")
    }

    // MARK: Drafts kept until the service acknowledges them

    public func pendingDrafts() -> [Draft] {
        ensureLoaded()
        return Array(drafts.values)
    }

    public func keep(_ draft: Draft) throws {
        ensureLoaded()
        if let current = drafts[draft.id], current.revision > draft.revision { return }
        drafts[draft.id] = draft
        try write(Array(drafts.values), "drafts.json")
    }

    public func forget(draft id: String, revision: Int? = nil) throws {
        ensureLoaded()
        if let revision, let current = drafts[id], current.revision > revision { return }
        drafts[id] = nil
        try write(Array(drafts.values), "drafts.json")
    }

    // MARK: Service state

    public func state() -> ServiceState? { read("state.json") }
    public func storeState(_ state: ServiceState) throws { try write(state, "state.json") }

    /// Logout or lost authorization: only this device copy goes; the server archive stays.
    public func clear() throws {
        catalogue = [:]
        journal = []
        drafts = [:]
        loaded = false
        try? FileManager.default.removeItem(at: root)
    }
}
