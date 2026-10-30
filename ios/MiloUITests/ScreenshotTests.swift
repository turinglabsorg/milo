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

    func testComposeEditsAndPreviewsTheHTMLAlternative() {
        let row = app.descendants(matching: .any).matching(identifier: "row-m2").firstMatch
        if !row.waitForExistence(timeout: 10) {
            app.staticTexts["Smart inbox"].firstMatch.tap()
        }
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        row.tap()
        XCTAssertTrue(app.buttons["reply"].waitForExistence(timeout: 10))
        app.buttons["reply"].tap()
        XCTAssertTrue(app.textViews["compose-body"].waitForExistence(timeout: 10))
        let section = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Versione HTML'")).firstMatch
        for _ in 0..<4 where !section.isHittable { app.swipeUp() }
        XCTAssertTrue(section.waitForExistence(timeout: 5))
        section.tap()
        let editor = app.textViews["compose-html"]
        XCTAssertTrue(editor.waitForExistence(timeout: 5))
        editor.tap()
        editor.typeText("<h1>LetzGo Guide</h1><p>Gentile <b>Comune</b></p>")
        let preview = app.webViews.staticTexts.containing(NSPredicate(format: "label CONTAINS 'LetzGo Guide'")).firstMatch
        XCTAssertTrue(preview.waitForExistence(timeout: 10), "The HTML preview must render what was typed")
        XCTAssertTrue(app.staticTexts["Inviata insieme al testo semplice"].exists)
        save("06-compose-html")
        for _ in 0..<3 where !preview.isHittable { app.swipeUp() }
        save("07-compose-html-preview")
    }
}
