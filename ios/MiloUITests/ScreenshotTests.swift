import XCTest

/// Drives the app on fictional demo data and saves screenshots for review (CI uploads them).
final class ScreenshotTests: XCTestCase {
    var app: XCUIApplication!

    override func setUp() {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-MiloDemo"]
        app.launch()
    }

    func save(_ name: String) {
        let screenshot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        if let directory = ProcessInfo.processInfo.environment["MILO_SCREENSHOTS"] {
            try? FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
            try? screenshot.pngRepresentation.write(to: URL(fileURLWithPath: directory).appendingPathComponent(name + ".png"))
        }
    }

    func testInboxThreadComposeAndTodo() {
        let row = app.descendants(matching: .any).matching(identifier: "row-m2").firstMatch
        if !row.waitForExistence(timeout: 10) {
            // iPhone starts on the sidebar: open the inbox first.
            app.staticTexts["Smart inbox"].firstMatch.tap()
        }
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        save("01-inbox")

        row.tap()
        XCTAssertTrue(app.buttons["reply"].waitForExistence(timeout: 10))
        sleep(2)
        save("02-thread")

        app.buttons["reply"].tap()
        XCTAssertTrue(app.textViews["compose-body"].waitForExistence(timeout: 10))
        save("03-reply")
        app.buttons["compose-send"].tap()
        XCTAssertTrue(app.staticTexts["Messaggio in partenza…"].waitForExistence(timeout: 10))
        save("04-undo")
        app.buttons["Annulla"].tap()

        app.navigationBars.buttons.element(boundBy: 0).tap()
        if app.navigationBars.buttons.element(boundBy: 0).exists { app.navigationBars.buttons.element(boundBy: 0).tap() }
        let todo = app.staticTexts["Da fare"].firstMatch
        if todo.waitForExistence(timeout: 5) {
            todo.tap()
            XCTAssertTrue(app.staticTexts["Rivedere il design"].waitForExistence(timeout: 10))
            save("05-todo")
        }
    }
}
