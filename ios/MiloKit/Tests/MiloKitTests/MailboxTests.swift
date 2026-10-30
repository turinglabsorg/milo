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

    func testDraftKeepsItsHTMLAlternative() throws {
        let html = "<p>Ciao <b>Comune</b></p>"
        let data = try JSONSerialization.data(withJSONObject: ["id": "d1", "account_id": "a1", "to": "c@example.com", "cc": "",
                                                               "subject": "HTML", "body": "Ciao", "html": html, "mode": "new", "revision": 1])
        var draft = try APIClient.decoder.decode(Draft.self, from: data)
        XCTAssertEqual(draft.html, html)
        draft.body = "Ciao, aggiornato"
        let encoded = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(draft)) as? [String: Any]
        XCTAssertEqual(encoded?["html"] as? String, html)
        XCTAssertEqual(encoded?["body"] as? String, "Ciao, aggiornato")
        let plain = try APIClient.decoder.decode(Draft.self, from: JSONSerialization.data(withJSONObject: [
            "id": "d2", "account_id": "a1", "to": "", "cc": "", "subject": "", "body": "x", "mode": "new", "revision": 1]))
        XCTAssertNil(plain.html)
    }

    func testDraftsAreTrackedUnlessTheOwnerTurnsItOff() throws {
        var draft = Draft(accountId: "a1", to: "c@example.com", body: "Ciao")
        XCTAssertTrue(draft.tracksOpen)
        var encoded = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(draft)) as? [String: Any]
        XCTAssertNil(encoded?["track"])
        draft.tracksOpen = false
        encoded = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(draft)) as? [String: Any]
        XCTAssertEqual(encoded?["track"] as? Bool, false)
        let stored = try APIClient.decoder.decode(Draft.self, from: APIClient.encoder.encode(draft))
        XCTAssertFalse(stored.tracksOpen)
    }

    func testRefreshLoadsDeliveryTicks() async throws {
        let (mailbox, transport) = make()
        await mailbox.refresh()
        XCTAssertTrue(transport.requests.contains("GET /api/deliveries"))
        let opened = try XCTUnwrap(mailbox.deliveries["m1"])
        XCTAssertNotNil(opened.opened)
        XCTAssertEqual(opened.opens, 2)
        XCTAssertTrue(opened.tracked.value)
        let waiting = try XCTUnwrap(mailbox.deliveries["m4"])
        XCTAssertNil(waiting.opened)
    }

    func testEditorDocumentBlocksRemoteImagesAndKeepsTheSenderDocument() {
        let fragment = MailEditor.document("<p>Ciao</p>")
        XCTAssertTrue(fragment.contains("data-milo-fragment"))
        XCTAssertTrue(fragment.contains("img-src data:;"))
        XCTAssertTrue(fragment.contains("<body><p>Ciao</p></body>"))
        let full = MailEditor.document("<html><head><style>p{color:red}</style></head><body><p>Ciao</p></body></html>", remoteImages: true)
        XCTAssertFalse(full.contains("data-milo-fragment"))
        XCTAssertTrue(full.contains("img-src data: https:;"))
        XCTAssertTrue(full.contains("<style>p{color:red}</style>"))
        XCTAssertEqual(MailEditor.paragraphs(from: "Ciao <Comune>\nriga\n\nSeconda"), "<p>Ciao &lt;Comune&gt;<br>riga</p><p>Seconda</p>")
        XCTAssertEqual(MailEditor.paragraphs(from: ""), "<p><br></p>")
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

    func testDownloadMailChecksProvidersAndShowsNewMailBeforePeriodicRefresh() async throws {
        let transport = DownloadTransport()
        let mailbox = Mailbox(api: APIClient(baseURL: URL(string: "https://milo.example")!, transport: transport,
                                             retryDelays: []), cache: MailCache(root: directory))
        await mailbox.start()
        let initialRequests = await transport.syncRequests
        XCTAssertEqual(initialRequests, 1)
        XCTAssertFalse(mailbox.conversations.contains { $0.id == "new-mail" })
        await mailbox.show(.inbox)
        await mailbox.refresh()
        let afterNavigation = await transport.syncRequests
        XCTAssertEqual(afterNavigation, 1, "Navigation and background reads do not check providers")
        await mailbox.downloadMail()
        let afterDownload = await transport.syncRequests
        XCTAssertEqual(afterDownload, 2)
        XCTAssertTrue(mailbox.conversations.contains { $0.id == "new-mail" })
        XCTAssertFalse(mailbox.downloadingMail)
    }

    func testSlowDownloadKeepsCachedMailVisibleAndCoalescesRequests() async throws {
        let (initial, _) = make()
        await initial.start()
        let transport = DownloadTransport(hold: true)
        let mailbox = Mailbox(api: APIClient(baseURL: URL(string: "https://milo.example")!, transport: transport),
                              cache: MailCache(root: directory))
        let starting = Task { await mailbox.start() }
        for _ in 0..<100 {
            if await transport.syncRequests > 0 { break }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertEqual(mailbox.conversations.count, DemoTransport.rows.count)
        XCTAssertTrue(mailbox.downloadingMail)
        await mailbox.downloadMail()
        let requests = await transport.syncRequests
        XCTAssertEqual(requests, 1)
        await transport.release()
        await starting.value
        XCTAssertFalse(mailbox.downloadingMail)
    }

    func testFailedDownloadStillRefreshesArchivedMail() async throws {
        let transport = DownloadTransport(fail: true)
        let mailbox = Mailbox(api: APIClient(baseURL: URL(string: "https://milo.example")!, transport: transport,
                                             retryDelays: []), cache: MailCache(root: directory))
        await mailbox.downloadMail()
        XCTAssertEqual(mailbox.conversations.count, DemoTransport.rows.count)
        XCTAssertNotNil(mailbox.lastError)
        XCTAssertFalse(mailbox.downloadingMail)
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

    func testUnreadViewListsOnlyUnreadInboxConversations() async throws {
        let (mailbox, _) = make()
        await mailbox.start()
        mailbox.view = .unread
        mailbox.applyFilter()
        XCTAssertEqual(mailbox.conversations.map(\.id), ["m1", "m2"])
    }

    func testConfirmationCodeDetection() {
        XCTAssertEqual(ConfirmationCode.detect(in: "Il tuo codice di conferma è 482916. Non condividerlo."), "482916")
        XCTAssertEqual(ConfirmationCode.detect(in: "Your verification code is 731 204, valid for 10 minutes."), "731204")
        XCTAssertNil(ConfirmationCode.detect(in: "Parliamone domani, il pacco arriva nel 2026."))
        XCTAssertNil(ConfirmationCode.detect(in: "Totale ordine 482916 euro, grazie."))
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

    func testCompletingASelectionClearsThoseTodos() async throws {
        let (mailbox, _) = make()
        await mailbox.show(.todo)
        XCTAssertEqual(Set(mailbox.todos.map(\.id)), ["t1", "t2"])
        await mailbox.complete(["t1", "t2"])
        XCTAssertTrue(mailbox.todos.isEmpty)
    }

    func testAcceptingAnActionPersistsItsStateInTheThreadCache() async throws {
        let (mailbox, transport) = make()
        await mailbox.start()
        await mailbox.open(try XCTUnwrap(mailbox.conversations.first { $0.id == "m2" }))
        XCTAssertEqual(mailbox.thread.first?.analysis?.proposedActions, ["Rivedere il design", "Rispondere a Marco"])
        try await mailbox.acceptAction(messageId: "m2", text: "Rispondere a Marco")
        let accepted = try XCTUnwrap(mailbox.thread.first?.todos?.first { $0.text == "Rispondere a Marco" })
        XCTAssertNotNil(accepted.accepted)
        XCTAssertTrue(transport.requests.contains("POST /api/messages/m2/todos"))
        let todos = try await mailbox.api.todos()
        XCTAssertTrue(todos.contains { $0.text == "Rispondere a Marco" })
        XCTAssertEqual(mailbox.state?.counts.todo, 3)
        try await mailbox.loadBody("m2")
        XCTAssertNotNil(mailbox.thread.first?.todos?.first { $0.text == "Rispondere a Marco" }?.accepted)
        let cached = await mailbox.cache.thread("demo:t-m2")
        XCTAssertNotNil(cached?.first?.todos?.first { $0.text == "Rispondere a Marco" }?.accepted)
    }

    func testRecipientEditKeepsEarlierAddresses() {
        XCTAssertEqual(RecipientEdit.token("Anna <anna@example.com>, mar"), "mar")
        XCTAssertEqual(RecipientEdit.token("Anna <anna@example.com>, "), "")
        XCTAssertTrue(RecipientEdit.isAddress("anna@example.com"))
        XCTAssertFalse(RecipientEdit.isAddress("mar"))
        XCTAssertEqual(
            RecipientEdit.inserting("marco@example.com", name: "Marco Bianchi", into: "Anna <anna@example.com>, mar"),
            "Anna <anna@example.com>, Marco Bianchi <marco@example.com>, ")
        XCTAssertEqual(RecipientEdit.inserting("anna@example.com", name: "", into: ""), "anna@example.com, ")
        XCTAssertEqual(
            RecipientEdit.inserting("bob@example.com", name: "Bob", into: "Anna <anna@example.com>, "),
            "Anna <anna@example.com>, Bob <bob@example.com>, ")
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

    func testConversationKeepsLoadingUntilItArrives() async throws {
        let transport = WakingTransport(failures: 0)
        let mailbox = Mailbox(api: APIClient(baseURL: URL(string: "https://milo.example")!, transport: transport,
                                             retryDelays: [0.01]),
                              cache: MailCache(root: directory))
        await mailbox.start()
        transport.failures = 5
        await mailbox.open(try XCTUnwrap(mailbox.conversations.first { $0.id == "m4" }))
        XCTAssertNil(mailbox.threadError)
        XCTAssertFalse(mailbox.loadingThread)
        XCTAssertEqual(mailbox.thread.first?.id, "m4")
    }

    func testSubjectCore() {
        XCTAssertEqual(Mailbox.subjectCore("Re: Fwd: RE: Progetto"), "Progetto")
        XCTAssertEqual(Mailbox.subjectCore(""), "Senza oggetto")
        let split = Mailbox.splitQuoted("Va bene.\n\nIl giorno mer 14 ott 2026 alle 10:00 Anna <anna@example.com> ha scritto:\n> Ci vediamo?")
        XCTAssertEqual(split.text, "Va bene.")
        XCTAssertEqual(split.quoted, "Il giorno mer 14 ott 2026 alle 10:00 Anna <anna@example.com> ha scritto:\n> Ci vediamo?")
        XCTAssertNil(Mailbox.splitQuoted("Solo testo").quoted)
        XCTAssertNil(Mailbox.splitQuoted("> tutto citato").quoted)
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

actor DownloadTransport: Transport {
    let demo = DemoTransport()
    private(set) var syncRequests = 0
    private var busyReads = 0
    private var arrived = false
    private var hold: Bool
    private let fail: Bool

    init(hold: Bool = false, fail: Bool = false) {
        self.hold = hold
        self.fail = fail
    }

    func release() { hold = false }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let path = request.url!.path
        if path == "/api/sync" {
            syncRequests += 1
            while hold { try await Task.sleep(nanoseconds: 10_000_000) }
            if fail {
                return (Data(), HTTPURLResponse(url: request.url!, statusCode: 503, httpVersion: nil, headerFields: nil)!)
            }
            busyReads = 1
        }
        let (data, response) = try await demo.send(request)
        var payload = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        if path == "/api/state" {
            payload["sync"] = [["account_id": "demo", "phase": busyReads > 0 ? "downloading" : "ready"]]
            if busyReads == 0 && syncRequests >= 2 { arrived = true }
            busyReads = max(0, busyReads - 1)
        }
        if path == "/api/messages" && arrived {
            var rows = payload["messages"] as! [[String: Any]]
            rows.append(DemoTransport.row("new-mail", "Anna", "anna@example.com", "Just arrived", "New mail", 0))
            payload["messages"] = rows
        }
        return (try JSONSerialization.data(withJSONObject: payload), response)
    }
}
