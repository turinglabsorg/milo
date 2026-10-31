import XCTest

/// Drives the app on fictional demo data and saves screenshots for review (CI uploads them).
final class ScreenshotTests: XCTestCase {
    var app: XCUIApplication!

    override func setUp() {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-MiloDemo"]
        app.launch()
        // The demo asks once for the badge permission; accept it so it never covers the app.
        let allow = XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.buttons
            .matching(NSPredicate(format: "label IN {'Allow', 'Consenti'}")).firstMatch
        if allow.waitForExistence(timeout: 5) { allow.tap() }
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
        XCTAssertTrue(app.textFields["compose-to"].exists, "The header shows before writing")
        editor.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10), "Editing opens the keyboard on the rendered message")
        skipKeyboardTip()
        XCTAssertTrue(app.buttons["Grassetto"].waitForExistence(timeout: 5), "The formatting bar sits above the keyboard while writing")
        XCTAssertFalse(app.textFields["compose-to"].exists, "The header folds away while writing")
        XCTAssertFalse(app.buttons["Done"].exists, "WebKit's previous/next/done bar is gone")
        XCTAssertFalse(app.buttons["Fine"].exists)
        let window = app.windows.firstMatch.frame
        XCTAssertEqual(editor.frame.width, window.width, accuracy: 1, "The editor spans the whole width")
        XCTAssertGreaterThanOrEqual(editor.frame.minY, 0)
        for letter in "ragusa" {
            let key = app.keyboards.keys.matching(NSPredicate(format: "label ==[c] %@", String(letter))).firstMatch
            XCTAssertTrue(key.waitForExistence(timeout: 5))
            key.tap()
        }
        XCTAssertTrue(editor.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'ragusa'")).firstMatch.waitForExistence(timeout: 10),
                      "Typing edits the rendered message")
        sleep(1)
        save("06-compose-html-editing")
        app.buttons["compose-hide-keyboard"].tap()
        XCTAssertTrue(app.textFields["compose-to"].waitForExistence(timeout: 5), "The header comes back with the keyboard down")
        XCTAssertFalse(app.buttons["Grassetto"].exists)
        sleep(1)
        save("07-compose-html-rendered")
    }

    func testComposeTracksOpensAndSentMailShowsDeliveryTicks() {
        let row = app.descendants(matching: .any).matching(identifier: "row-m2").firstMatch
        if !row.waitForExistence(timeout: 10) {
            app.staticTexts["Smart inbox"].firstMatch.tap()
        }
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["compose"].waitForExistence(timeout: 5))
        app.buttons["compose"].tap()
        let editor = app.webViews["compose-rich-editor"]
        XCTAssertTrue(editor.waitForExistence(timeout: 10))
        XCTAssertTrue(editor.links["X"].waitForExistence(timeout: 10), "The composer shows the signature card with its links")
        XCTAssertFalse(editor.staticTexts["https://x.com/example"].exists, "The signature text is not shown as raw lines")
        save("08a-compose-signature-card")
        let to = app.textFields["compose-to"]
        to.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10))
        XCTAssertTrue(to.exists, "The header stays while a recipient is typed")
        XCTAssertGreaterThanOrEqual(to.frame.minY, app.navigationBars.firstMatch.frame.maxY - 1,
                                    "The recipient rows stay below the navigation bar while suggestions show")
        save("08b-compose-recipient-suggestions")
        to.typeText("\n")
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5), "Return closes the recipient keyboard")
        app.buttons["compose-options"].tap()
        let track = app.buttons["Traccia apertura"]
        XCTAssertTrue(track.waitForExistence(timeout: 5), "The compose options offer open tracking")
        XCTAssertTrue(app.buttons["Ricordamelo se non risponde"].exists, "The follow-up reminder lives in the same menu")
        save("08-compose-track-open")
        editor.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.85)).tap()
        XCTAssertTrue(track.waitForNonExistence(timeout: 5), "The options menu closes")
        app.buttons["Chiudi"].tap()
        XCTAssertTrue(app.buttons["Elimina bozza"].waitForExistence(timeout: 5))
        app.buttons["Elimina bozza"].tap()

        app.navigationBars.buttons.element(boundBy: 0).tap()
        let sent = app.staticTexts["Posta inviata"].firstMatch
        XCTAssertTrue(sent.waitForExistence(timeout: 10))
        sent.tap()
        let opened = app.descendants(matching: .any).matching(identifier: "row-m7").firstMatch
        XCTAssertTrue(opened.waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "delivery-opened").firstMatch.waitForExistence(timeout: 10),
                      "An opened mail shows two accent ticks")
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "delivery-sent").firstMatch.exists,
                      "A mail confirmed by the server but not yet opened shows one muted tick")
        save("09-sent-ticks")

        opened.tap()
        XCTAssertTrue(app.buttons["reply"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "delivery-opened").firstMatch.waitForExistence(timeout: 10),
                      "The thread shows the delivery ticks on the sent message")
        save("10-thread-ticks")
    }

    func testNewMessageWithASignatureCardAcceptsTyping() {
        let compose = app.buttons["compose"]
        if !compose.waitForExistence(timeout: 10) { app.staticTexts["Smart inbox"].firstMatch.tap() }
        XCTAssertTrue(compose.waitForExistence(timeout: 10))
        compose.tap()
        let editor = app.webViews["compose-rich-editor"]
        XCTAssertTrue(editor.waitForExistence(timeout: 10))
        XCTAssertTrue(editor.images.firstMatch.waitForExistence(timeout: 15), "The signature shows as its card")
        editor.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.05)).tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10))
        skipKeyboardTip()
        for letter in "ciao" {
            let key = app.keyboards.keys.matching(NSPredicate(format: "label ==[c] %@", String(letter))).firstMatch
            XCTAssertTrue(key.waitForExistence(timeout: 5))
            key.tap()
        }
        XCTAssertTrue(editor.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'ciao'")).firstMatch.waitForExistence(timeout: 10),
                      "Typing above the signature card writes the message")
        save("10-compose-new-typing")
    }

    /// A fresh simulator covers the keyboard with the slide-to-type tip the first time it opens.
    private func skipKeyboardTip() {
        let tip = app.buttons["Continue"]
        if tip.waitForExistence(timeout: 2) { tip.tap() }
    }

    func testHomeScreenIconShowsTheUnreadBadge() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        sleep(3)
        XCUIDevice.shared.press(.home)
        let icon = springboard.icons["Milo"]
        XCTAssertTrue(icon.waitForExistence(timeout: 10))
        let badged = NSPredicate(format: "value CONTAINS '2'")
        expectation(for: badged, evaluatedWith: icon)
        waitForExpectations(timeout: 15)
        save("09-home-badge")
    }
}
