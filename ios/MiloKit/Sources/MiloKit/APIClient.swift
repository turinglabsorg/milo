import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public struct APIError: Error, LocalizedError, Sendable {
    public var status: Int
    public var message: String
    public var errorDescription: String? { message }
    /// Network failures, timeouts and 5xx/408/429 are retried; other answers are final.
    public var isTemporary: Bool { status == 0 || status >= 500 || status == 408 || status == 429 }
}

public protocol Transport: Sendable {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionTransport: Transport {
    let session: URLSession

    public init(session: URLSession = URLSessionTransport.patient) { self.session = session }

    /// Waits for the network (a VPN like Tailscale may take a moment to wake) instead of failing at once.
    public static let patient: URLSession = {
        let configuration = URLSessionConfiguration.default
        #if os(iOS) || os(macOS)
        configuration.waitsForConnectivity = true
        #endif
        configuration.timeoutIntervalForRequest = 20
        configuration.timeoutIntervalForResource = 60
        return URLSession(configuration: configuration)
    }()

    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError(status: 0, message: "Risposta non valida") }
        return (data, http)
    }
}

public final class APIClient: Sendable {
    public let baseURL: URL
    let transport: Transport
    /// Pauses before retrying a read that never reached the service.
    let retryDelays: [Double]

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()
    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    public init(baseURL: URL, transport: Transport = URLSessionTransport(), retryDelays: [Double] = [0.4, 1.2, 2.5, 4]) {
        self.baseURL = baseURL
        self.transport = transport
        self.retryDelays = retryDelays
    }

    func url(_ path: String, _ query: [String: String] = [:]) -> URL {
        var components = URLComponents(url: baseURL.appendingPathComponent("api" + path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        return components.url!
    }

    func data(_ method: String, _ path: String, query: [String: String] = [:], body: Data? = nil,
              timeout: TimeInterval = 15, idempotent: Bool? = nil, attempt start: Int = 0) async throws -> Data {
        // Reads and side-effect-free AI requests are retried; writes are never sent twice.
        let repeatable = idempotent ?? (method == "GET")
        var request = URLRequest(url: url(path, query), timeoutInterval: timeout)
        request.httpMethod = method
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        var attempt = start
        var result: (Data, HTTPURLResponse)?
        while result == nil {
            do {
                result = try await transport.send(request)
            } catch let error as APIError {
                throw error
            } catch {
                // A cancelled request is not a network failure: let the caller ignore it.
                if error is CancellationError || (error as? URLError)?.code == .cancelled || Task.isCancelled {
                    throw CancellationError()
                }
                guard repeatable, attempt < retryDelays.count else {
                    let code = (error as? URLError).map { " (rete \($0.code.rawValue))" } ?? ""
                    throw APIError(status: 0, message: "Milo non è raggiungibile\(code). Controlla che Tailscale sia attivo.")
                }
                try? await Task.sleep(nanoseconds: UInt64(retryDelays[attempt] * 1_000_000_000))
                attempt += 1
            }
        }
        let (data, response) = result!
        // A restarting service answers 502/503/504 through the Tailscale proxy for a moment.
        if repeatable, [502, 503, 504].contains(response.statusCode), attempt < retryDelays.count, !Task.isCancelled {
            try? await Task.sleep(nanoseconds: UInt64(retryDelays[attempt] * 1_000_000_000))
            return try await self.data(method, path, query: query, body: body, timeout: timeout,
                                  idempotent: repeatable, attempt: attempt + 1)
        }
        guard (200..<300).contains(response.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw APIError(status: response.statusCode, message: detail ?? "Operazione non riuscita (\(response.statusCode))")
        }
        return data
    }

    func get<T: Decodable>(_ type: T.Type, _ path: String, query: [String: String] = [:]) async throws -> T {
        try Self.decoder.decode(T.self, from: try await data("GET", path, query: query))
    }

    func send<T: Decodable>(_ type: T.Type, _ method: String, _ path: String, body: some Encodable) async throws -> T {
        try Self.decoder.decode(T.self, from: try await data(method, path, body: try Self.encoder.encode(body), timeout: 60))
    }

    @discardableResult
    func call(_ method: String, _ path: String, body: [String: Any]? = nil, idempotent: Bool? = nil) async throws -> Data {
        try await data(method, path, body: try body.map { try JSONSerialization.data(withJSONObject: $0) }, timeout: 90,
                       idempotent: idempotent)
    }

    static func encode(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? id
    }

    // MARK: Endpoints

    public func status() async throws -> ServiceStatus { try await get(ServiceStatus.self, "/status") }
    public func state() async throws -> ServiceState { try await get(ServiceState.self, "/state") }

    public func downloadMail() async throws { _ = try await data("POST", "/sync", idempotent: true) }

    public func conversations(view: MailView, account: String? = nil, search: String = "") async throws -> [Conversation] {
        struct List: Decodable { var messages: [Conversation] }
        var query = ["view": view.rawValue, "search": search]
        if let account { query["account"] = account }
        return try await get(List.self, "/messages", query: query).messages
    }

    public func catalogue(after cursor: Page.Cursor? = nil) async throws -> Page {
        var query: [String: String] = [:]
        if let cursor {
            query = ["before_date": String(cursor.beforeDate), "before_id": cursor.beforeId]
        }
        return try await get(Page.self, "/client/messages", query: query)
    }

    /// Current catalogue row of one conversation; 404 when it no longer exists on the service.
    public func conversation(account: String, thread: String) async throws -> Conversation {
        struct One: Decodable { var message: Conversation }
        return try await get(One.self, "/client/thread", query: ["account": account, "thread": thread]).message
    }

    public func thread(_ messageId: String) async throws -> [Message] {
        try await get(Thread.self, "/messages/\(Self.encode(messageId))/thread", query: ["lazy": "true"]).messages
    }

    public func message(_ id: String) async throws -> Message {
        try await get(Message.self, "/messages/\(Self.encode(id))", query: ["load_images": "true"])
    }

    public func attachmentURL(messageId: String, index: Int, preview: Bool = false) -> URL {
        url("/messages/\(Self.encode(messageId))/attachments/\(index)", preview ? ["preview": "true"] : [:])
    }

    public func apply(_ operation: MailEdit) async throws {
        let path = "/messages/\(Self.encode(operation.messageId))/thread"
        if operation.deleted {
            try await call("DELETE", path)
        } else {
            _ = try await data("PATCH", path, body: try Self.encoder.encode(operation.patch), timeout: 60)
        }
    }

    public func drafts() async throws -> [Draft] {
        struct List: Decodable { var drafts: [Draft] }
        return try await get(List.self, "/drafts").drafts
    }

    public func save(_ draft: Draft) async throws -> String {
        struct Saved: Decodable { var id: String }
        return try await send(Saved.self, "PUT", "/drafts", body: draft).id
    }

    public func deleteDraft(_ id: String) async throws { try await call("DELETE", "/drafts/\(Self.encode(id))") }

    public func schedule(_ id: String, at date: Date, followupDays: Int? = nil) async throws {
        var body: [String: Any] = ["send_at": date.timeIntervalSince1970]
        if let followupDays { body["followup_days"] = followupDays }
        try await call("PUT", "/drafts/\(Self.encode(id))/schedule", body: body)
    }

    public func unschedule(_ id: String) async throws { try await call("DELETE", "/drafts/\(Self.encode(id))/schedule") }

    /// Register this device's APNs token so the service can notify it about new mail.
    public func registerDevice(token: String, environment: String) async throws {
        try await call("POST", "/devices", body: ["token": token, "environment": environment])
    }

    public func deliveries() async throws -> [Delivery] {
        struct List: Decodable { var deliveries: [Delivery] }
        return try await get(List.self, "/deliveries").deliveries
    }

    public func todos() async throws -> [Todo] {
        struct List: Decodable { var todos: [Todo] }
        return try await get(List.self, "/todos").todos
    }

    public func setTodo(_ id: String, done: Bool) async throws {
        try await call("PATCH", "/todos/\(Self.encode(id))", body: ["done": done])
    }

    public func acceptTodo(messageId: String, text: String) async throws -> TodoProposal {
        try await send(TodoProposal.self, "POST", "/messages/\(Self.encode(messageId))/todos", body: ["text": text])
    }

    public func recap() async throws -> Recap { try await get(Recap.self, "/recap") }

    public func recipients(matching query: String) async throws -> [Recipient] {
        struct List: Decodable { var recipients: [Recipient] }
        return try await get(List.self, "/recipients", query: query.isEmpty ? [:] : ["q": query]).recipients
    }

    public func suggestions(for messageId: String) async throws -> [String] {
        struct Replies: Decodable { var replies: [String] }
        let data = try await call("POST", "/messages/\(Self.encode(messageId))/suggestions", idempotent: true)
        return try Self.decoder.decode(Replies.self, from: data).replies
    }

    public func ask(_ question: String) async throws -> Answer {
        try Self.decoder.decode(Answer.self, from: try await call("POST", "/ask", body: ["question": question], idempotent: true))
    }

    public func setVIP(_ email: String, _ vip: Bool) async throws {
        try await call("PATCH", "/senders/\(Self.encode(email))", body: ["vip": vip])
    }

    public func block(_ email: String) async throws {
        try await call("PATCH", "/senders/\(Self.encode(email))", body: ["status": "blocked"])
    }

    public struct UnsubscribeResult: Decodable, Sendable { public var method: String; public var url: String? }

    public func unsubscribe(_ messageId: String) async throws -> UnsubscribeResult {
        try Self.decoder.decode(UnsubscribeResult.self, from: try await call("POST", "/messages/\(Self.encode(messageId))/unsubscribe"))
    }
}
