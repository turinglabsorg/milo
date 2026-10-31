import MiloKit
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
}

/// The draft's HTML rendered as the recipient sees it; editable in place while `editing` is on.
/// Mail scripts are disabled; remote images stay blocked unless `remoteImages` is set.
struct HTMLEditorView: UIViewRepresentable {
    var html: String
    var remoteImages: Bool
    var editing: Bool
    var signature: MailEditor.SignaturePreview? = nil
    @Binding var height: CGFloat
    var controller: HTMLEditorController
    var onChange: (String, String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        configuration.userContentController.add(context.coordinator, contentWorld: .defaultClient, name: "miloEditor")
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.scrollView.isScrollEnabled = false
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
                if let height = try? await view.callAsyncJavaScript(script, arguments: arguments, contentWorld: .defaultClient) as? NSNumber {
                    resize(height.doubleValue)
                }
            }
        }

        func resize(_ value: Double) {
            let measured = max(160, CGFloat(value))
            if abs(parent.height - measured) > 1 { parent.height = measured }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard let state = message.body as? [String: Any], let html = state["html"] as? String,
                  let text = state["text"] as? String else { return }
            self.html = html
            if let height = state["height"] as? NSNumber { resize(height.doubleValue) }
            parent.onChange(html, text)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            Task { @MainActor in
                if let height = try? await webView.callAsyncJavaScript(MailEditor.script, contentWorld: .defaultClient) as? NSNumber {
                    resize(height.doubleValue)
                }
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
