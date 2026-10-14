import Foundation

/// The service stores flags as 0/1 integers and a few as JSON booleans; accept both.
public struct Flag: Codable, Hashable, Sendable, ExpressibleByBooleanLiteral {
    public var value: Bool

    public init(_ value: Bool) { self.value = value }
    public init(booleanLiteral value: Bool) { self.value = value }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { value = false }
        else if let bool = try? container.decode(Bool.self) { value = bool }
        else { value = (try container.decode(Int.self)) != 0 }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(value ? 1 : 0)
    }
}

/// One row of the conversation list: the latest message of a thread plus thread-wide aggregates.
public struct Conversation: Codable, Hashable, Identifiable, Sendable {
    public var id: String
    public var accountId: String
    public var threadId: String?
    public var sender: String?
    public var senderEmail: String?
    public var subject: String?
    public var preview: String?
    public var date: Double
    public var read: Flag
    public var contentVersion: String?
    public var starred: Flag
    public var archived: Flag
    public var sent: Flag
    public var category: String?
    public var snoozedUntil: Double?
    public var hasInbox: Flag?
    public var hasArchive: Flag?
    public var hasSent: Flag?
    public var receivedCount: Int?
    public var unreadCount: Int?
    public var pinned: Flag
    public var messageCount: Int?
    public var analyzedCount: Int?
    public var replied: Flag?
    /// Local tombstone for a queued trash operation; never sent by the server.
    public var deleted: Bool?

    /// Conversations are keyed by account and thread, like the web client's catalogue.
    public var key: String { accountId + ":" + (threadId ?? id) }

    public init(id: String, accountId: String, threadId: String? = nil, sender: String? = nil,
                senderEmail: String? = nil, subject: String? = nil, preview: String? = nil, date: Double,
                read: Bool = true, starred: Bool = false, archived: Bool = false, sent: Bool = false,
                category: String? = "people", pinned: Bool = false, messageCount: Int? = 1) {
        self.id = id
        self.accountId = accountId
        self.threadId = threadId
        self.sender = sender
        self.senderEmail = senderEmail
        self.subject = subject
        self.preview = preview
        self.date = date
        self.read = Flag(read)
        self.starred = Flag(starred)
        self.archived = Flag(archived)
        self.sent = Flag(sent)
        self.category = category
        self.pinned = Flag(pinned)
        self.messageCount = messageCount
        self.hasInbox = Flag(!archived && !sent)
        self.hasArchive = Flag(archived && !sent)
        self.hasSent = Flag(sent)
    }
}

public struct Address: Codable, Hashable, Sendable {
    public var name: String?
    public var email: String
}

public struct Attachment: Codable, Hashable, Sendable {
    public var index: Int
    public var name: String?
    public var type: String?
}

public struct Unsubscribe: Codable, Hashable, Sendable {
    public var oneClick: Bool
    public var url: String?
    public var mailto: String?
}

public struct Analysis: Codable, Hashable, Sendable {
    public var summary: String?
    public var priority: String?
    public var actionItems: [String]?
    public var category: String?
}

/// A message in a thread. Bodies (`body`, `html`, attachments) are present only once downloaded.
public struct Message: Codable, Hashable, Identifiable, Sendable {
    public var id: String
    public var accountId: String
    public var threadId: String?
    public var messageId: String?
    public var sender: String?
    public var senderEmail: String?
    public var recipients: String?
    public var subject: String?
    public var preview: String?
    public var date: Double
    public var read: Flag
    public var starred: Flag
    public var archived: Flag
    public var sent: Flag
    public var category: String?
    public var snoozedUntil: Double?
    public var analysis: Analysis?
    public var pinned: Flag
    public var contentVersion: String?
    public var toAddresses: [Address]?
    public var ccAddresses: [Address]?
    public var replyToAddresses: [Address]?
    public var bodyLoaded: Bool?
    public var body: String?
    public var html: String?
    public var remoteImages: Bool?
    public var attachments: [Attachment]?
    public var unsubscribe: Unsubscribe?
}

public struct Thread: Codable, Sendable {
    public var messages: [Message]
}

public struct Account: Codable, Hashable, Identifiable, Sendable {
    public var id: String
    public var name: String
    public var email: String
    public var provider: String?
    public var color: String?
    public var enabled: Flag?
    public var error: String?
    public var lastSync: Double?
}

public struct Counts: Codable, Hashable, Sendable {
    public var inbox: Int?
    public var unread: Int?
    public var starred: Int?
    public var snoozed: Int?
    public var drafts: Int?
    public var todo: Int?
    public var screener: Int?
}

public struct Identity: Codable, Hashable, Sendable {
    public var name: String?
}

public struct Template: Codable, Hashable, Sendable {
    public var name: String
    public var body: String
}

public struct ServiceState: Codable, Sendable {
    public var accounts: [Account]
    public var counts: Counts
    public var identity: Identity?
    public var signatures: [String: String]?
    public var templates: [Template]?
    public var vips: [String]?
}

public struct ServiceStatus: Codable, Sendable {
    public var service: String
    public var authenticated: Bool
    public var access: String?
    public var demo: Bool?
}

public struct Page: Codable, Sendable {
    public struct Cursor: Codable, Hashable, Sendable {
        public var beforeDate: Double
        public var beforeId: String
    }
    public var messages: [Conversation]
    public var next: Cursor?
}

public struct Schedule: Codable, Hashable, Sendable {
    public var sendAt: Double
    public var error: String?
}

public struct Draft: Codable, Hashable, Identifiable, Sendable {
    public enum Mode: String, Codable, Sendable { case new, reply, replyAll = "reply_all", forward }
    public var id: String
    public var accountId: String
    public var to: String
    public var cc: String
    public var subject: String
    public var body: String
    public var replyToId: String?
    public var contextMessageId: String?
    public var mode: Mode
    public var revision: Int
    public var scheduled: Schedule?

    public init(id: String = UUID().uuidString.lowercased(), accountId: String, to: String = "", cc: String = "",
                subject: String = "", body: String = "", replyToId: String? = nil, mode: Mode = .new,
                revision: Int = Int(Date().timeIntervalSince1970 * 1000)) {
        self.id = id
        self.accountId = accountId
        self.to = to
        self.cc = cc
        self.subject = subject
        self.body = body
        self.replyToId = replyToId
        self.contextMessageId = replyToId
        self.mode = mode
        self.revision = revision
    }
}

public struct Todo: Codable, Hashable, Identifiable, Sendable {
    public var id: String
    public var messageId: String
    public var text: String
    public var priority: String?
    public var kind: String
    public var sender: String?
    public var senderEmail: String?
    public var subject: String?
    public var date: Double?
    public var accountId: String?
    public var threadId: String?
}

public struct Recap: Codable, Sendable {
    public struct Priority: Codable, Hashable, Sendable {
        public var messageId: String
        public var action: String
    }
    public var overview: String?
    public var priorities: [Priority]?
    public var generatedAt: Double?
}

public struct Answer: Codable, Sendable {
    public struct Source: Codable, Hashable, Identifiable, Sendable {
        public var id: String
        public var sender: String?
        public var subject: String?
        public var date: Double?
    }
    public var answer: String
    public var sources: [Source]
}

public enum MailView: String, CaseIterable, Codable, Sendable, Identifiable {
    case inbox, todo, starred, drafts, sent, snoozed, archive
    public var id: String { rawValue }
}

/// A local edit waiting to reach the service. Committed to disk before the UI confirms it.
public struct Operation: Codable, Hashable, Identifiable, Sendable {
    public struct Patch: Codable, Hashable, Sendable {
        public var read: Bool?
        public var starred: Bool?
        public var archived: Bool?
        public var pinned: Bool?
        public var snoozedUntil: Double?
        public init(read: Bool? = nil, starred: Bool? = nil, archived: Bool? = nil, pinned: Bool? = nil,
                    snoozedUntil: Double? = nil) {
            self.read = read
            self.starred = starred
            self.archived = archived
            self.pinned = pinned
            self.snoozedUntil = snoozedUntil
        }
    }
    public var id: String
    public var key: String
    public var messageId: String
    public var patch: Patch
    public var deleted: Bool
    public var error: String?

    public init(key: String, messageId: String, patch: Patch = Patch(), deleted: Bool = false) {
        id = UUID().uuidString.lowercased()
        self.key = key
        self.messageId = messageId
        self.patch = patch
        self.deleted = deleted
    }
}
