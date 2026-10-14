import MiloKit
import SwiftUI

/// First start: point the app at the Milo service. Access is the device's Tailscale identity.
struct SetupView: View {
    var initial: String
    var onConnect: (URL) -> Void
    @State private var address = ""
    @State private var checking = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("La tua posta.\nUn po’ più leggera.")
                            .font(.largeTitle.weight(.bold))
                        Text("Collega Milo al tuo servizio. Con Tailscale attivo su questo iPhone l’accesso è automatico: nessuna password da inserire.")
                            .foregroundStyle(Color.milo.muted)
                    }
                    .padding(.vertical, 8)
                    .listRowBackground(Color.clear)
                }
                Section("Indirizzo del servizio") {
                    TextField("https://milo.tailnet.ts.net:8443", text: $address)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textContentType(.URL)
                        .submitLabel(.go)
                        .onSubmit(connect)
                }
                if let error {
                    Section { Text(error).foregroundStyle(Color.milo.danger) }
                }
                Section {
                    Button(action: connect) {
                        HStack {
                            Text("Collega Milo")
                            Spacer()
                            if checking { ProgressView() } else { Image(systemName: "arrow.right") }
                        }
                    }
                    .disabled(checking || address.isEmpty)
                }
            }
            .navigationTitle("Benvenuto")
            .onAppear { address = initial }
        }
    }

    private func connect() {
        var text = address.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.contains("://") { text = "https://" + text }
        guard let url = URL(string: text), url.scheme == "https", url.host != nil else {
            error = "Inserisci un indirizzo HTTPS valido."
            return
        }
        checking = true
        error = nil
        Task {
            defer { checking = false }
            do {
                let status = try await APIClient(baseURL: url).status()
                guard status.service == "milo" else { error = "Questo indirizzo non è un servizio Milo."; return }
                guard status.authenticated else {
                    error = "Il servizio risponde ma non riconosce questo dispositivo. Verifica che sia autorizzato nella tua rete Tailscale."
                    return
                }
                onConnect(url)
            } catch {
                self.error = (error as? APIError)?.message ?? error.localizedDescription
            }
        }
    }
}
