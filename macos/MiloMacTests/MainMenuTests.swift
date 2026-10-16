import AppKit
import XCTest
@testable import Milo

final class MainMenuTests: XCTestCase {
    /// The web view answers copy:/paste: through the responder chain, but
    /// only when a main menu routes the shortcuts to it (Cmd+C in an email).
    func testEditMenuRoutesCopyAndPaste() throws {
        let edit = try XCTUnwrap(
            NSApp.mainMenu?.items.first { $0.submenu?.title == "Edit" }?.submenu)
        let copy = try XCTUnwrap(edit.items.first { $0.action == #selector(NSText.copy(_:)) })
        XCTAssertEqual(copy.keyEquivalent, "c")
        XCTAssertNotNil(edit.items.first { $0.action == #selector(NSText.paste(_:)) })
        XCTAssertNotNil(edit.items.first { $0.action == #selector(NSText.cut(_:)) })
        XCTAssertNotNil(edit.items.first { $0.action == #selector(NSText.selectAll(_:)) })
    }
}
