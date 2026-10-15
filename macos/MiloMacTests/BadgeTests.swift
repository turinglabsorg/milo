import XCTest
@testable import Milo

final class BadgeTests: XCTestCase {
    func testBadgeLabel() {
        XCTAssertNil(DockBadge.label(unread: 0))
        XCTAssertEqual(DockBadge.label(unread: 1), "1")
        XCTAssertEqual(DockBadge.label(unread: 42), "42")
    }

    func testStateDecoding() throws {
        let data = Data(#"{"counts": {"inbox": 461, "unread": 2, "starred": 48}}"#.utf8)
        let state = try JSONDecoder().decode(StateResponse.self, from: data)
        XCTAssertEqual(state.counts.unread, 2)
    }
}
