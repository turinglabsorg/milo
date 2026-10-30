import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// A fictional in-memory service for tests and simulator screenshots. Never touches real mail.
public final class DemoTransport: Transport, @unchecked Sendable {
    private let lock = NSLock()
    private var drafts: [String: [String: Any]] = [:]
    private var scheduled: [String: Double] = [:]
    private var acceptedActions: [String: [[String: Any]]] = [:]
    public private(set) var requests: [String] = []
    private var removed: Set<String> = []

    private var approvedActions: [[String: Any]] {
        lock.lock(); defer { lock.unlock() }
        return acceptedActions.values.flatMap { $0 }
    }

    /// Simulate a conversation deleted on another device.
    public func remove(_ id: String) {
        lock.lock(); removed.insert(id); lock.unlock()
    }

    private var visibleRows: [[String: Any]] {
        lock.lock(); defer { lock.unlock() }
        return Self.allRows.filter { !removed.contains($0["id"] as? String ?? "") }
    }

    public init() {}

    static let now = Date().timeIntervalSince1970
    static let account = ["id": "demo", "name": "Personale", "email": "sam@example.com", "provider": "imap",
                          "color": "#2563eb", "enabled": 1] as [String: Any]
    static let rows: [[String: Any]] = [
        row("m1", "Giulia Rossi", "giulia@example.com", "Un caffè e due idee per lunedì",
            "Ciao! Ho messo insieme qualche idea per la presentazione di lunedì.", 600, read: 0),
        row("m2", "Marco Bianchi", "marco@example.com", "Il design è pronto per il tuo feedback",
            "La prima versione del design è pronta: dimmi cosa ne pensi.", 5400, read: 0, count: 3),
        row("m3", "Linear", "updates@linear.app", "Il tuo workspace, questa settimana",
            "Il team ha completato 12 attività questa settimana.", 9000, category: "updates"),
        row("m4", "Sara Conti", "sara@example.com", "Weekend fuori porta?",
            "Stavo pensando di andare al mare sabato, ti va?", 86400, starred: 1),
        row("m5", "The Pragmatic Engineer", "news@pragmatic.example", "Building software that people love",
            "This week: why the best software starts with a clear problem.", 90000, category: "newsletters"),
        row("m6", "TestFlight", "testflight@example.com", "Milo is now available to test",
            "You've been invited to test Milo.", 120000, category: "updates"),
    ]
    /// Mail Sam sent: one already opened by the recipient, one only confirmed by the server.
    static let sentRows: [[String: Any]] = [
        row("m7", "Sam Taylor", "sam@example.com", "Proposta per lunedì",
            "Ti mando la proposta: dimmi se i numeri ti tornano.", 900, sent: true),
        row("m8", "Sam Taylor", "sam@example.com", "Preventivo aggiornato",
            "In allegato il preventivo con le modifiche di ieri.", 7200, sent: true),
    ]
    static var allRows: [[String: Any]] { rows + sentRows }
    /// A fixed-width newsletter layout, wider than a phone.
    static let wideHTML = "<table width=\"600\" style=\"width:600px\"><tr><td style=\"width:600px;padding:20px\">" +
        "<div style=\"width:560px;height:180px;background:#2563eb;border-radius:24px\"></div>" +
        "<p style=\"font-size:28px;text-align:right\">Milo AI Mail by Sebastiano</p>" +
        "<p style=\"font-size:17px\">You've been invited to test Milo. This line is long on purpose so it must wrap inside six hundred pixels.</p>" +
        "</td></tr></table>"

    static func row(_ id: String, _ sender: String, _ email: String, _ subject: String, _ preview: String,
                    _ age: Double, read: Int = 1, starred: Int = 0, category: String = "people", count: Int = 1,
                    sent: Bool = false) -> [String: Any] {
        ["id": id, "account_id": "demo", "thread_id": "t-" + id, "sender": sender, "sender_email": email,
         "subject": subject, "preview": preview, "date": now - age, "read": read, "content_version": "v-" + id,
         "starred": starred, "archived": 0, "sent": sent ? 1 : 0, "category": category, "has_inbox": sent ? 0 : 1,
         "has_archive": 0, "has_sent": sent ? 1 : 0, "received_count": count, "unread_count": read == 0 ? 1 : 0, "pinned": 0,
         "message_count": count, "analyzed_count": 0, "replied": false]
    }

    static func message(_ row: [String: Any], body: Bool) -> [String: Any] {
        var message = row
        message["recipients"] = "sam@example.com"
        message["to_addresses"] = [["name": "Sam", "email": "sam@example.com"]]
        message["cc_addresses"] = [[String: Any]]()
        message["reply_to_addresses"] = [[String: Any]]()
        message["body_loaded"] = body
        if (row["sent"] as? Int) == 1 {
            message["recipients"] = "giulia@example.com"
            message["to_addresses"] = [["name": "Giulia Rossi", "email": "giulia@example.com"]]
        }
        if body {
            let text = (row["preview"] as? String ?? "") + "\n\nA presto,\n" + (row["sender"] as? String ?? "")
            message["body"] = text
            message["html"] = "<p>" + (row["preview"] as? String ?? "") +
                "</p><p>Il programma è su https://example.com/programma, dimmi se ti torna.</p><p>A presto,<br>" +
                (row["sender"] as? String ?? "") + "</p>"
            message["attachments"] = [[String: Any]]()
            if row["id"] as? String == "m6" { message["html"] = wideHTML }
        }
        if row["id"] as? String == "m2" {
            message["analysis"] = ["summary": "Marco chiede un feedback sul primo design entro giovedì.",
                                   "priority": "high", "action_items": ["Rivedere il design", "Rispondere a Marco"]]
            message["todos"] = [["id": "t1", "text": "Rivedere il design", "accepted": now]]
        }
        return message
    }

    func reply(_ request: URLRequest) -> (Int, Any) {
        let path = request.url!.path
        let method = request.httpMethod ?? "GET"
        lock.lock(); requests.append(method + " " + path); lock.unlock()
        switch (method, path) {
        case ("POST", "/api/sync"):
            return (202, ["accepted": true, "demo": true])
        case ("GET", "/api/status"):
            return (200, ["service": "milo", "authenticated": true, "access": "tailscale", "demo": true])
        case ("GET", "/api/state"):
            return (200, ["accounts": [Self.account], "counts": ["inbox": 5, "unread": 2, "starred": 1, "todo": 2 + approvedActions.count],
                          "identity": ["name": "Sam Taylor"], "signatures": ["demo": "Sam Taylor"],
                          "templates": [["name": "Grazie", "body": "Grazie mille, ti aggiorno a breve."]],
                          "vips": ["marco@example.com"]])
        case ("GET", "/api/messages"), ("GET", "/api/client/messages"):
            return (200, ["messages": visibleRows, "next": NSNull()])
        case ("GET", "/api/client/thread"):
            let thread = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?
                .queryItems?.first { $0.name == "thread" }?.value ?? ""
            guard let row = visibleRows.first(where: { $0["thread_id"] as? String == thread }) else {
                return (404, ["detail": "Conversazione non trovata"])
            }
            return (200, ["message": row])
        case ("GET", "/api/todos"):
            let todos: [[String: Any]] = [
                ["id": "t1", "message_id": "m2", "text": "Rivedere il design", "priority": "high", "kind": "action",
                 "sender": "Marco Bianchi", "subject": "Il design è pronto per il tuo feedback", "date": Self.now - 5400],
                ["id": "t2", "message_id": "m1", "text": "Nessuna risposta: Proposta", "priority": "high", "kind": "followup",
                 "sender": "Giulia Rossi", "subject": "Proposta", "date": Self.now - 600]]
            return (200, ["todos": todos + approvedActions])
        case ("GET", "/api/recipients"):
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?
                .queryItems?.first { $0.name == "q" }?.value?.lowercased() ?? ""
            let people: [[String: String]] = [
                ["name": "Giulia Rossi", "email": "giulia@example.com"],
                ["name": "Marco Bianchi", "email": "marco@example.com"],
            ]
            let matched = query.isEmpty ? people : people.filter {
                $0["name"]!.lowercased().contains(query) || $0["email"]!.contains(query)
            }
            return (200, ["recipients": matched])
        case ("GET", "/api/deliveries"):
            return (200, ["deliveries": [["id": "m7", "sent": Self.now - 900, "opened": Self.now - 300, "opens": 2, "tracked": 1],
                                         ["id": "m8", "sent": Self.now - 7200, "opened": NSNull(), "opens": 0, "tracked": 1]]])
        case ("GET", "/api/drafts"):
            lock.lock(); defer { lock.unlock() }
            return (200, ["drafts": Array(drafts.values)])
        case ("GET", "/api/recap"):
            return (200, ["overview": "Due conversazioni aspettano te: Marco vuole un feedback sul design.",
                          "priorities": [["message_id": "m2", "action": "Rispondi a Marco sul design"]],
                          "generated_at": Self.now - 300])
        case ("PUT", "/api/drafts"):
            let body = (try? JSONSerialization.jsonObject(with: request.httpBody ?? Data())) as? [String: Any] ?? [:]
            let id = body["id"] as? String ?? UUID().uuidString
            lock.lock(); drafts[id] = body; lock.unlock()
            return (200, ["id": id])
        default:
            break
        }
        let parts = path.split(separator: "/").map(String.init)
        if parts.count >= 3, parts[1] == "messages" {
            let id = parts[2]
            guard let row = Self.allRows.first(where: { $0["id"] as? String == id }) else { return (404, ["detail": "Email non trovata"]) }
            if parts.count == 4, parts[3] == "todos", method == "POST" {
                let body = (try? JSONSerialization.jsonObject(with: request.httpBody ?? Data())) as? [String: String] ?? [:]
                let text = body["text"] ?? ""
                lock.lock(); defer { lock.unlock() }
                if let existing = acceptedActions[id]?.first(where: { $0["text"] as? String == text }) { return (200, existing) }
                let todo: [String: Any] = ["id": UUID().uuidString, "message_id": id, "text": text,
                                         "accepted": Self.now, "kind": "action"]
                acceptedActions[id, default: []].append(todo)
                return (200, todo)
            }
            var message = Self.message(row, body: parts.count == 3)
            lock.lock(); let accepted = acceptedActions[id] ?? []; lock.unlock()
            message["todos"] = (message["todos"] as? [[String: Any]] ?? []) + accepted
            if parts.count == 4, parts[3] == "thread" {
                if method == "GET" { return (200, ["messages": [message], "sync": [String: Any]()]) }
                return (200, ["ok": true])
            }
            if parts.count == 4, parts[3] == "suggestions" {
                return (200, ["replies": ["Perfetto, ci vediamo lunedì.", "Mi serve un giorno in più.", "Ne parliamo a voce?"]])
            }
            return (200, message)
        }
        if parts.count == 4, parts[1] == "drafts", parts[3] == "schedule" {
            lock.lock(); defer { lock.unlock() }
            if method == "DELETE" {
                guard scheduled.removeValue(forKey: parts[2]) != nil else { return (409, ["detail": "Troppo tardi"]) }
                return (200, ["ok": true])
            }
            let body = (try? JSONSerialization.jsonObject(with: request.httpBody ?? Data())) as? [String: Any] ?? [:]
            scheduled[parts[2]] = body["send_at"] as? Double
            return (200, ["draft_id": parts[2]])
        }
        if parts.count >= 3, parts[1] == "todos" || parts[1] == "senders" { return (200, ["ok": true]) }
        return (404, ["detail": "Non trovato"])
    }

    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (status, body) = reply(request)
        let data = try JSONSerialization.data(withJSONObject: body)
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": "application/json"])!
        return (data, response)
    }

    public func isScheduled(_ draftId: String) -> Bool {
        lock.lock(); defer { lock.unlock() }
        return scheduled[draftId] != nil
    }
}
