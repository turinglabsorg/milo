import AppKit
import SwiftUI
import WebKit

/// WKWebView host for the shared web client.
///
/// The persistent website data store is what makes the client's
/// IndexedDB device cache (docs/CLIENT_CACHE.md) survive restarts on
/// macOS, exactly as the installed Chromium profile does on Linux.
/// Never switch this to a non-persistent store.
struct WebView: NSViewRepresentable {
    let serverURL: URL
    let initialURL: URL
    @ObservedObject var model: AppModel
    var onLoadError: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(serverURL: serverURL, onLoadError: onLoadError)
    }

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.preferences.isElementFullscreenEnabled = true
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        context.coordinator.webView = webView
        webView.load(URLRequest(url: initialURL))
        context.coordinator.loadedToken = model.loadToken
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        guard context.coordinator.loadedToken != model.loadToken else { return }
        context.coordinator.loadedToken = model.loadToken
        guard let action = model.consumePending() else {
            webView.reload()
            return
        }
        context.coordinator.navigate(to: action, in: webView)
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
        let serverURL: URL
        let onLoadError: (String) -> Void
        weak var webView: WKWebView?
        var loadedToken = -1

        init(serverURL: URL, onLoadError: @escaping (String) -> Void) {
            self.serverURL = serverURL
            self.onLoadError = onLoadError
        }

        private func isSameOrigin(_ url: URL) -> Bool {
            url.scheme == serverURL.scheme && url.host == serverURL.host && url.port == serverURL.port
        }

        func navigate(to action: PendingAction, in webView: WKWebView) {
            guard let config = try? ServerConfig.load() else { return }
            let target: URL?
            switch action {
            case .compose(let mailto): target = try? config.composeURL(mailto: mailto)
            case .open(let id): target = try? config.openURL(messageID: id)
            }
            guard let target else { return }
            // A fragment-only change does not reload the page and the web
            // app reads the fragment once in boot(); force the reload.
            if let current = webView.url, isSameOrigin(current) {
                let fragment = target.fragment.map { "#\($0)" } ?? ""
                let script = "window.location.hash = \(jsonString(fragment)); window.location.reload();"
                webView.evaluateJavaScript(script)
            } else {
                webView.load(URLRequest(url: target))
            }
        }

        private func jsonString(_ value: String) -> String {
            let data = (try? JSONSerialization.data(withJSONObject: [value])) ?? Data("[]".utf8)
            let array = String(decoding: data, as: UTF8.self)
            return String(array.dropFirst().dropLast())
        }

        // MARK: Navigation policy

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }
            if navigationAction.shouldPerformDownload {
                decisionHandler(.download)
                return
            }
            switch url.scheme?.lowercased() {
            case "mailto":
                // Handled by the web composer, not by a new default handler loop.
                navigate(to: .compose(mailto: url.absoluteString), in: webView)
                decisionHandler(.cancel)
            case "tel":
                NSWorkspace.shared.open(url)
                decisionHandler(.cancel)
            case "http", "https":
                if isSameOrigin(url) {
                    decisionHandler(.allow)
                } else if navigationAction.navigationType == .linkActivated {
                    NSWorkspace.shared.open(url)
                    decisionHandler(.cancel)
                } else {
                    decisionHandler(.allow)
                }
            case "about", "blob", "data":
                decisionHandler(.allow)
            default:
                decisionHandler(.cancel)
            }
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationResponse: WKNavigationResponse,
            decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
        ) {
            if !navigationResponse.canShowMIMEType {
                decisionHandler(.download)
            } else {
                decisionHandler(.allow)
            }
        }

        func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
            download.delegate = self
        }

        func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
            download.delegate = self
        }

        // MARK: Downloads (safe attachment downloads, Linux parity)

        func download(
            _ download: WKDownload,
            decideDestinationUsing response: URLResponse,
            suggestedFilename: String,
            completionHandler: @escaping (URL?) -> Void
        ) {
            let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
            var destination = downloads.appendingPathComponent(suggestedFilename)
            var counter = 1
            while FileManager.default.fileExists(atPath: destination.path) {
                let name = destination.deletingPathExtension().lastPathComponent
                let base = counter == 1 ? name : name.replacingOccurrences(
                    of: " (\\d+)$", with: "", options: .regularExpression)
                destination = downloads
                    .appendingPathComponent("\(base) (\(counter))")
                    .appendingPathExtension(destination.pathExtension)
                counter += 1
            }
            completionHandler(destination)
        }

        func downloadDidFinish(_ download: WKDownload) {}

        func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
            onLoadError("Download failed: \(error.localizedDescription)")
        }

        // MARK: New windows (target=_blank)

        func webView(
            _ webView: WKWebView,
            createWebViewWith configuration: WKWebViewConfiguration,
            for navigationAction: WKNavigationAction,
            windowFeatures: WKWindowFeatures
        ) -> WKWebView? {
            guard let url = navigationAction.request.url else { return nil }
            if isSameOrigin(url) {
                webView.load(URLRequest(url: url))
            } else if url.scheme == "http" || url.scheme == "https" {
                NSWorkspace.shared.open(url)
            }
            return nil
        }

        // MARK: Failures

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            onLoadError(error.localizedDescription)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            onLoadError(error.localizedDescription)
        }
    }
}
