import MiloKit
import ObjectiveC
import SwiftUI
import UIKit
import WebKit

/// Sends formatting commands to the editor web view of the open composer.
@MainActor
final class HTMLEditorController {
    weak var webView: WKWebView?

    func exec(_ command: String, _ value: String = "") {
        guard let webView else { return }
        Task {
            _ = try? await webView.callAsyncJavaScript("window.miloEditor && window.miloEditor.exec(command, value)",
                                                       arguments: ["command": command, "value": value],
                                                       contentWorld: .defaultClient)
        }
    }

    func blur() {
        guard let webView else { return }
        Task { _ = try? await webView.callAsyncJavaScript("window.miloEditor && window.miloEditor.blur()", contentWorld: .defaultClient) }
        webView.endEditing(true)
    }
}

/// The draft's HTML rendered as the recipient sees it; editable in place while `editing` is on.
/// It fills the space it is given and scrolls by itself. Mail scripts are disabled; remote images
/// stay blocked unless `remoteImages` is set.
struct HTMLEditorView: UIViewRepresentable {
    var html: String
    var remoteImages: Bool
    var editing: Bool
    var signature: MailEditor.SignaturePreview? = nil
    var controller: HTMLEditorController
    var onChange: (String, String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        configuration.userContentController.add(context.coordinator, contentWorld: .defaultClient, name: "miloEditor")
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.scrollView.keyboardDismissMode = .interactive
        view.scrollView.alwaysBounceVertical = true
        Self.hideFormAccessory(view)
        view.isOpaque = false
        view.backgroundColor = .white
        view.accessibilityIdentifier = "compose-rich-editor"
        context.coordinator.load(view, html: html, remoteImages: remoteImages)
        context.coordinator.editing = editing
        controller.webView = view
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        let coordinator = context.coordinator
        coordinator.parent = self
        controller.webView = view
        if html != coordinator.html || remoteImages != coordinator.remoteImages {
            coordinator.load(view, html: html, remoteImages: remoteImages)
        }
        if editing != coordinator.editing {
            coordinator.editing = editing
            if coordinator.ready { coordinator.applyEditing(view) }
        }
        if coordinator.ready, signature != coordinator.signature { coordinator.decorate(view) }
    }

    /// Removes the previous/next/done bar WebKit puts above the keyboard: the composer shows its
    /// own formatting bar there.
    static func hideFormAccessory(_ view: WKWebView) {
        guard let content = view.scrollView.subviews.first(where: { NSStringFromClass(type(of: $0)).hasPrefix("WKContent") }) else { return }
        let base: AnyClass = type(of: content)
        let name = "MiloEditorContent_" + NSStringFromClass(base)
        var subclass: AnyClass? = NSClassFromString(name)
        if subclass == nil, let made = objc_allocateClassPair(base, name, 0) {
            let selector = #selector(getter: UIResponder.inputAccessoryView)
            let none: @convention(block) (AnyObject) -> AnyObject? = { _ in nil }
            if let method = class_getInstanceMethod(UIResponder.self, selector) {
                class_addMethod(made, selector, imp_implementationWithBlock(none), method_getTypeEncoding(method))
            }
            objc_registerClassPair(made)
            subclass = made
        }
        if let subclass { object_setClass(content, subclass) }
    }

    static func dismantleUIView(_ view: WKWebView, coordinator: Coordinator) {
        view.configuration.userContentController.removeScriptMessageHandler(forName: "miloEditor", contentWorld: .defaultClient)
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var parent: HTMLEditorView
        var html = ""
        var remoteImages = false
        var editing = false
        var ready = false
        var signature: MailEditor.SignaturePreview?

        init(_ parent: HTMLEditorView) { self.parent = parent }

        func load(_ view: WKWebView, html: String, remoteImages: Bool) {
            self.html = html
            self.remoteImages = remoteImages
            ready = false
            signature = nil
            view.loadHTMLString(MailEditor.document(html, remoteImages: remoteImages), baseURL: nil)
        }

        func applyEditing(_ view: WKWebView) {
            let on = editing
            Task { @MainActor in
                _ = try? await view.callAsyncJavaScript("window.miloEditor && window.miloEditor.setEditing(on)",
                                                        arguments: ["on": on], contentWorld: .defaultClient)
            }
        }

        /// Shows the sender's signature card in place of its text; the saved HTML keeps the text.
        func decorate(_ view: WKWebView) {
            let preview = parent.signature
            signature = preview
            Task { @MainActor in
                let (script, arguments) = MailEditor.decorateScript(preview)
                _ = try? await view.callAsyncJavaScript(script, arguments: arguments, contentWorld: .defaultClient)
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard let state = message.body as? [String: Any], let html = state["html"] as? String,
                  let text = state["text"] as? String else { return }
            self.html = html
            parent.onChange(html, text)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            Task { @MainActor in
                _ = try? await webView.callAsyncJavaScript(MailEditor.script, contentWorld: .defaultClient)
                ready = true
                applyEditing(webView)
                decorate(webView)
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction) async -> WKNavigationActionPolicy {
            if action.navigationType == .linkActivated, let url = action.request.url {
                await UIApplication.shared.open(url)
                return .cancel
            }
            return action.navigationType == .other ? .allow : .cancel
        }
    }
}
