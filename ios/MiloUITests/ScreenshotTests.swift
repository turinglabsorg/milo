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
        let download = app.buttons["download-mail"]
        XCTAssertTrue(download.waitForExistence(timeout: 5))
        XCTAssertEqual(download.label, "Scarica posta ora")
        let enabled = NSPredicate(format: "enabled == true")
        expectation(for: enabled, evaluatedWith: download)
        waitForExpectations(timeout: 10)
        download.tap()
        save("01-inbox")

        row.tap()
        XCTAssertTrue(app.buttons["reply"].waitForExistence(timeout: 10))
        let body = app.webViews.staticTexts.containing(NSPredicate(format: "label CONTAINS 'design'")).firstMatch
        XCTAssertTrue(body.waitForExistence(timeout: 15), "The mail body must render in the web view")
        save("02-thread")

        // A fixed-width newsletter must fit the screen width.
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let wide = app.descendants(matching: .any).matching(identifier: "row-m6").firstMatch
        XCTAssertTrue(wide.waitForExistence(timeout: 10))
        wide.tap()
        let wideText = app.webViews.staticTexts.containing(NSPredicate(format: "label CONTAINS 'invited'")).firstMatch
        XCTAssertTrue(wideText.waitForExistence(timeout: 15))
        sleep(1)
        XCTAssertLessThanOrEqual(app.webViews.firstMatch.frame.maxX, app.windows.firstMatch.frame.maxX)
        save("02b-wide-newsletter")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        row.tap()
        XCTAssertTrue(app.buttons["reply"].waitForExistence(timeout: 10))
        app.buttons["reply"].tap()
        XCTAssertTrue(app.webViews["compose-rich-editor"].waitForExistence(timeout: 10))
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

    func testComposeEditsTheHTMLAlternativeWYSIWYG() {
        let row = app.descendants(matching: .any).matching(identifier: "row-m2").firstMatch
        if !row.waitForExistence(timeout: 10) {
            app.staticTexts["Smart inbox"].firstMatch.tap()
        }
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        row.tap()
        XCTAssertTrue(app.buttons["reply"].waitForExistence(timeout: 10))
        app.buttons["reply"].tap()
        let editor = app.webViews["compose-rich-editor"]
        XCTAssertTrue(editor.waitForExistence(timeout: 10), "Every message opens in the formatted editor")
        XCTAssertFalse(app.buttons["Testo semplice"].exists, "There is no plain-text mode")
        XCTAssertFalse(app.buttons["Formattato"].exists)
        XCTAssertFalse(app.textViews["compose-body"].exists)
        XCTAssertTrue(app.buttons["Grassetto"].waitForExistence(timeout: 5), "The formatting toolbar shows while editing")
        XCTAssertTrue(app.buttons["Fine"].exists)
        editor.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10), "Editing opens the keyboard on the rendered message")
        for letter in "ragusa" {
            let key = app.keyboards.keys.matching(NSPredicate(format: "label ==[c] %@", String(letter))).firstMatch
            XCTAssertTrue(key.waitForExistence(timeout: 5))
            key.tap()
        }
        XCTAssertTrue(editor.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'ragusa'")).firstMatch.waitForExistence(timeout: 10),
                      "Typing edits the rendered message")
        save("06-compose-html-editing")
        app.buttons["Fine"].tap()
        XCTAssertTrue(app.buttons["Modifica"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["Grassetto"].exists)
        sleep(1)
        save("07-compose-html-rendered")
    }
}
