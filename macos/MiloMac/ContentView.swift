import SwiftUI

struct ContentView: View {
    @ObservedObject var model: AppModel
    @State private var loadError: String?

    var body: some View {
        Group {
            if let config = model.config, let initial = model.initialURL() {
                ZStack(alignment: .top) {
                    WebView(serverURL: config.serverURL, initialURL: initial, model: model) { message in
                        loadError = message
                    }
                    if let loadError {
                        banner(message: loadError)
                    }
                }
                .onChange(of: model.loadToken) { _, _ in loadError = nil }
            } else {
                setupView
            }
        }
        .frame(minWidth: 900, minHeight: 560)
    }

    private func banner(message: String) -> some View {
        HStack(spacing: 10) {
            Text("Milo is not reachable: \(message)")
                .lineLimit(2)
            Button("Reload") {
                loadError = nil
                model.reload()
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
        .padding(12)
    }

    private var setupView: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Milo")
                .font(.largeTitle.weight(.semibold))
            Text(model.configurationError ?? "No Milo server is configured on this Mac.")
            Text(
                "Create ~/Library/Application Support/Milo/server.json with "
                    + "{\"url\": \"https://<your-private-milo-origin>\"}, or run "
                    + "macos/install.py from a checkout that already has .data/server.json. "
                    + "The archive stays on the server; this app only connects to it."
            )
            .foregroundStyle(.secondary)
            Button("Retry") {
                model.reloadConfiguration()
            }
            .keyboardShortcut("r", modifiers: .command)
        }
        .padding(28)
        .frame(maxWidth: 560, alignment: .leading)
    }
}
