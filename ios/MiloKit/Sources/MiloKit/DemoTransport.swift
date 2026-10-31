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

    public static let signature = "Sam Taylor\nPersonale · sam@example.com\nhttps://x.com/example"
    /// The demo signature card as the service renders it (`milo.signature.render_signature`).
    static let signatureCard = Data(base64Encoded: "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")!
    static let cardToken = "demo-card-token-00000000"

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
            if row["id"] as? String == "m7" {
                message["html"] = "<p>Ti mando la proposta: dimmi se i numeri ti tornano.</p>" +
                    "<div style=\"margin:16px 0 0\"><img src=\"/api/signature/\(cardToken).png\" width=\"211\" height=\"69\" " +
                    "alt=\"Sam Taylor\" style=\"display:block;border:0;border-radius:12px\"><span style=\"display:block;margin:8px 0 0 4px\">" +
                    "<a href=\"https://x.com/example\">X</a></span></div>"
            }
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
                          "identity": ["name": "Sam Taylor"], "signatures": ["demo": Self.signature],
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
        let path = request.url!.path
        if path == "/api/signatures/demo/card.png" || path == "/api/signature/\(Self.cardToken).png" {
            lock.lock(); requests.append("GET " + path); lock.unlock()
            return (Self.signatureCard, HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                                                        headerFields: ["Content-Type": "image/png"])!)
        }
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
