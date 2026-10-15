import SwiftUI

/// Window content root. The process entry point lives in `main.swift`
/// (plain AppKit) so `--notifier` and `--register-mailto` modes can run
/// without creating a window.
struct RootView: View {
    var body: some View {
        ContentView(model: AppModel.shared)
    }
}
