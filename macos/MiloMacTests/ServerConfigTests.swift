import XCTest
@testable import Milo

final class ServerConfigTests: XCTestCase {
    func testRejectsNonHTTPSAndDecoratedOrigins() {
        XCTAssertThrowsError(try ServerConfig.validate("http://milo.example"))
        XCTAssertThrowsError(try ServerConfig.validate("https://user:pass@milo.example"))
        XCTAssertThrowsError(try ServerConfig.validate("https://milo.example/path"))
        XCTAssertThrowsError(try ServerConfig.validate("https://milo.example/?next=1"))
        XCTAssertThrowsError(try ServerConfig.validate("https://milo.example/#setup=x"))
    }

    func testAcceptsBareHTTPSOrigin() throws {
        let url = try ServerConfig.validate("https://milo.example.ts.net:8443/")
        XCTAssertEqual(url.absoluteString, "https://milo.example.ts.net:8443")
    }

    func testFragmentEncodingMatchesLinuxQuote() {
        // scripts/launch.py: quote(mailto, safe="")
        XCTAssertEqual(
            ServerConfig.percentEncode("mailto:anna@example.com?subject=Ciao Anna&body=A+B"),
            "mailto%3Aanna%40example.com%3Fsubject%3DCiao%20Anna%26body%3DA%2BB"
        )
    }

    func testComposeAndOpenURLs() throws {
        let config = ServerConfig(
            serverURL: try ServerConfig.validate("https://milo.example"),
            configDirectory: URL(fileURLWithPath: "/tmp")
        )
        XCTAssertEqual(
            try config.composeURL(mailto: "mailto:anna@example.com").absoluteString,
            "https://milo.example/#compose=mailto%3Aanna%40example.com"
        )
        XCTAssertEqual(
            try config.openURL(messageID: "abc-123_X").absoluteString,
            "https://milo.example/#open=abc-123_X"
        )
        XCTAssertThrowsError(try config.openURL(messageID: "bad id!"))
        XCTAssertThrowsError(try config.openURL(messageID: ""))
        XCTAssertThrowsError(try config.composeURL(mailto: "https://example.com"))
    }

    func testTailscaleHostSkipsSetupGrant() throws {
        let config = ServerConfig(
            serverURL: try ServerConfig.validate("https://milo.example.ts.net"),
            configDirectory: URL(fileURLWithPath: "/nonexistent")
        )
        XCTAssertEqual(try config.ownerInitialURL().absoluteString, "https://milo.example.ts.net")
    }

    func testPendingParsing() {
        XCTAssertEqual(
            PendingAction.parse(arguments: ["Milo", "mailto:anna@example.com?subject=Ciao"]),
            .compose(mailto: "mailto:anna@example.com?subject=Ciao")
        )
        XCTAssertEqual(
            PendingAction.parse(arguments: ["Milo", "--open=msg_1-2"]),
            .open(messageID: "msg_1-2")
        )
        XCTAssertNil(PendingAction.parse(arguments: ["Milo", "--open=bad id"]))
        XCTAssertEqual(
            PendingAction.parse(url: URL(string: "milo://open/msg_1-2")!),
            .open(messageID: "msg_1-2")
        )
        XCTAssertNil(PendingAction.parse(url: URL(string: "milo://open/bad%20id")!))
        XCTAssertEqual(
            PendingAction.parse(url: URL(string: "mailto:anna@example.com")!),
            .compose(mailto: "mailto:anna@example.com")
        )
    }
}
