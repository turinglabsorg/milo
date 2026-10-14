import Foundation
import XCTest
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
@testable import MiloKit

@MainActor
final class MailboxTests: XCTestCase {
    var directory: URL!

    override func setUp() async throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("milo-tests-" + UUID().uuidString)
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: directory)
    }

    func make(_ transport: DemoTransport = DemoTransport()) -> (Mailbox, DemoTransport) {
        (Mailbox(api: APIClient(baseURL: URL(string: "https://milo.example")!, transport: transport),
                 cache: MailCache(root: directory)), transport)
    }

    func testDecodesServiceShapes() throws {
        let data = try JSONSerialization.data(withJSONObject: DemoTransport.rows[1])
        let row = try APIClient.decoder.decode(Conversation.self, from: data)
        XCTAssertEqual(row.key, "demo:t-m2")
        XCTAssertFalse(row.read.value)
        XCTAssertEqual(row.messageCount, 3)
        let message = try APIClient.decoder.decode(Message.self, from: JSONSerialization.data(
            withJSONObject: DemoTransport.message(DemoTransport.rows[1], body: true)))
        XCTAssertEqual(message.analysis?.actionItems, ["Rivedere il design", "Rispondere a Marco"])
        XCTAssertEqual(message.toAddresses?.first?.email, "sam@example.com")
    }

    func testInboxRendersFromCacheAfterRestart() async throws {
        let (mailbox, _) = make()
        await mailbox.start()
        XCTAssertEqual(mailbox.conversations.count, DemoTransport.rows.count)
        XCTAssertEqual(mailbox.conversations.first?.id, "m1")

        let offline = Mailbox(api: APIClient(baseURL: URL(string: "https://unreachable.invalid")!, transport: FailingTransport(), retryDelays: []),
                              cache: MailCache(root: directory))
        await offline.start()
        XCTAssertEqual(offline.conversations.count, DemoTransport.rows.count)
        XCTAssertTrue(offline.online, "One unreachable refresh is not an outage")
        await offline.refresh()
        XCTAssertFalse(offline.online)
    }

    func testViewsAndSearchFilterTheLocalCatalogue() async throws {
        let (mailbox, _) = make()
        await mailbox.start()
        mailbox.view = .starred
        mailbox.applyFilter()
        XCTAssertEqual(mailbox.conversations.map(\.id), ["m4"])
        mailbox.view = .inbox
        mailbox.category = "newsletters"
        mailbox.applyFilter()
        XCTAssertEqual(mailbox.conversations.map(\.id), ["m5"])
        mailbox.category = nil
        mailbox.search = "design"
        mailbox.applyFilter()
        XCTAssertEqual(mailbox.conversations.map(\.id), ["m2"])
    }

    func testOpeningDownloadsTheBodyOnceAndMarksRead() async throws {
        let (mailbox, transport) = make()
        await mailbox.start()
        let first = try XCTUnwrap(mailbox.conversations.first { $0.id == "m1" })
        await mailbox.open(first)
        XCTAssertEqual(mailbox.thread.first?.bodyLoaded, true)
        XCTAssertTrue(mailbox.thread.first?.html?.contains("programma") ?? false)
        XCTAssertTrue(transport.requests.contains("PATCH /api/messages/m1/thread"))
        XCTAssertEqual(mailbox.pendingCount, 0)
        let downloads = transport.requests.filter { $0 == "GET /api/messages/m1" }.count
        await mailbox.open(first)
        XCTAssertEqual(transport.requests.filter { $0 == "GET /api/messages/m1" }.count, downloads)
    }

    func testEditsAreJournaledAndSurviveOffline() async throws {
        let (mailbox, _) = make()
        await mailbox.start()
        let offline = Mailbox(api: APIClient(baseURL: URL(string: "https://unreachable.invalid")!, transport: FailingTransport(), retryDelays: []),
                              cache: MailCache(root: directory))
        await offline.start()
        let row = try XCTUnwrap(offline.conversations.first { $0.id == "m3" })
        await offline.mutate(row, MailEdit.Patch(archived: true))
        XCTAssertFalse(offline.conversations.contains { $0.id == "m3" })
        XCTAssertEqual(offline.pendingCount, 1)

        let (online, transport) = make()
        await online.start()
        XCTAssertEqual(online.pendingCount, 0)
        XCTAssertTrue(transport.requests.contains("PATCH /api/messages/m3/thread"))
    }

    func testSendIsScheduledForUndoAndUsesSignature() async throws {
        let (mailbox, transport) = make()
        await mailbox.start()
        var draft = try XCTUnwrap(mailbox.newDraft())
        XCTAssertEqual(draft.body, "\n\n-- \nSam Taylor")
        draft.to = "anna@example.com"
        draft.subject = "Ciao"
        try await mailbox.send(draft)
        XCTAssertTrue(transport.isScheduled(draft.id))
        try await mailbox.undoSend(draft)
        XCTAssertFalse(transport.isScheduled(draft.id))
        do {
            try await mailbox.undoSend(draft)
            XCTFail("A second undo must fail")
        } catch let error as APIError {
            XCTAssertEqual(error.status, 409)
        }
        var empty = draft
        empty.to = ""
        do { try await mailbox.send(empty); XCTFail("Recipients are required") } catch {}
    }

    func testReplyAddressesTheSenderWithoutOwnAddress() async throws {
        let (mailbox, _) = make()
        await mailbox.start()
        await mailbox.open(try XCTUnwrap(mailbox.conversations.first { $0.id == "m2" }))
        let reply = try XCTUnwrap(mailbox.replyDraft(all: true, body: "Ok"))
        XCTAssertEqual(reply.to, "marco@example.com")
        XCTAssertEqual(reply.subject, "Re: Il design è pronto per il tuo feedback")
        XCTAssertEqual(reply.body, "Ok\n\n-- \nSam Taylor")
        XCTAssertEqual(reply.mode, .replyAll)
        XCTAssertTrue(mailbox.isVIP("Marco@example.com"))
    }

    func testRefreshDropsConversationsDeletedElsewhere() async throws {
        let (mailbox, transport) = make()
        await mailbox.start()
        XCTAssertTrue(mailbox.conversations.contains { $0.id == "m3" })
        transport.remove("m3")
        await mailbox.refresh()
        XCTAssertFalse(mailbox.conversations.contains { $0.id == "m3" })
        XCTAssertEqual(mailbox.conversations.count, DemoTransport.rows.count - 1)
    }

    func testMailtoLinksBecomeDrafts() throws {
        let url = try XCTUnwrap(URL(string: "mailto:anna@example.com?subject=Ciao%20Anna&body=Ci%20vediamo&cc=marco@example.com"))
        let draft = try XCTUnwrap(Draft.mailto(url, accountId: "demo", signature: "\n\n-- \nSam"))
        XCTAssertEqual(draft.to, "anna@example.com")
        XCTAssertEqual(draft.cc, "marco@example.com")
        XCTAssertEqual(draft.subject, "Ciao Anna")
        XCTAssertEqual(draft.body, "Ci vediamo\n\n-- \nSam")
        XCTAssertNil(Draft.mailto(URL(string: "https://example.com")!, accountId: "demo", signature: nil))
    }

    func testReadsRetryWhileTheNetworkWakesUp() async throws {
        let transport = WakingTransport(failures: 3)
        let mailbox = Mailbox(api: APIClient(baseURL: URL(string: "https://milo.example")!, transport: transport,
                                             retryDelays: [0.01, 0.01, 0.01, 0.01]),
                              cache: MailCache(root: directory))
        await mailbox.start()
        XCTAssertTrue(mailbox.online)
        XCTAssertEqual(mailbox.conversations.count, DemoTransport.rows.count)
        transport.failures = 2
        await mailbox.open(try XCTUnwrap(mailbox.conversations.first { $0.id == "m2" }))
        XCTAssertNil(mailbox.threadError)
        XCTAssertEqual(mailbox.thread.first?.bodyLoaded, true)
    }

    func testRestartingServiceIsRetriedForReadsAndSuggestions() async throws {
        let transport = RestartingTransport(failures: 2)
        let api = APIClient(baseURL: URL(string: "https://milo.example")!, transport: transport, retryDelays: [0.01, 0.01, 0.01])
        let replies = try await api.suggestions(for: "m1")
        XCTAssertEqual(replies.count, 3)
        transport.failures = 2
        let todos = try await api.todos()
        XCTAssertEqual(todos.count, 2)
        transport.failures = 1
        do { try await api.setTodo("t1", done: true); XCTFail("Writes are not repeated") } catch let error as APIError {
            XCTAssertEqual(error.status, 502)
        }
    }

    func testSubjectCore() {
        XCTAssertEqual(Mailbox.subjectCore("Re: Fwd: RE: Progetto"), "Progetto")
        XCTAssertEqual(Mailbox.subjectCore(""), "Senza oggetto")
    }
}

/// Fails the first requests like a VPN that is still waking up, then answers.
final class WakingTransport: Transport, @unchecked Sendable {
    let demo = DemoTransport()
    var failures: Int
    init(failures: Int) { self.failures = failures }
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        if failures > 0 { failures -= 1; throw URLError(.networkConnectionLost) }
        return try await demo.send(request)
    }
}

/// Answers 502 like the Tailscale proxy while the service restarts.
final class RestartingTransport: Transport, @unchecked Sendable {
    let demo = DemoTransport()
    var failures: Int
    init(failures: Int) { self.failures = failures }
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        if failures > 0 {
            failures -= 1
            return (Data(), HTTPURLResponse(url: request.url!, statusCode: 502, httpVersion: nil, headerFields: nil)!)
        }
        return try await demo.send(request)
    }
}

struct FailingTransport: Transport {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        throw URLError(.notConnectedToInternet)
    }
}
