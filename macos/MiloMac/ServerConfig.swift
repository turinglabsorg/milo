import Foundation

/// Pure-Foundation mirror of the Linux client's server resolution
/// (`scripts/launch.py`): same validation, same first-start grant rules,
/// so a Mac and a Linux laptop paired to the same archive behave alike.
enum ServerConfigError: Error, CustomStringConvertible {
    case notConfigured
    case invalid(String)

    var description: String {
        switch self {
        case .notConfigured:
            return "No Milo server is configured on this Mac."
        case .invalid(let message):
            return message
        }
    }
}

struct ServerConfig {
    let serverURL: URL
    /// Directory holding `server.json` / `setup.url` for this client.
    let configDirectory: URL

    static var appSupportDirectory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Milo", isDirectory: true)
    }

    /// Resolution order: `MILO_SERVER_URL`, then the macOS Application
    /// Support copy, then a checkout `.data/server.json` (development).
    static func load(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default
    ) throws -> ServerConfig {
        if let raw = environment["MILO_SERVER_URL"], !raw.isEmpty {
            return ServerConfig(serverURL: try validate(raw), configDirectory: appSupportDirectory)
        }
        let candidates: [URL] = [
            appSupportDirectory.appendingPathComponent("server.json"),
            checkoutDataDirectory(fileManager: fileManager)?.appendingPathComponent("server.json"),
        ].compactMap { $0 }
        for candidate in candidates where fileManager.fileExists(atPath: candidate.path) {
            let data: Data
            do {
                data = try Data(contentsOf: candidate)
            } catch {
                throw ServerConfigError.invalid("The shared server configuration is invalid.")
            }
            guard
                let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                let raw = object["url"] as? String
            else {
                throw ServerConfigError.invalid("The shared server configuration is invalid.")
            }
            return ServerConfig(
                serverURL: try validate(raw),
                configDirectory: candidate.deletingLastPathComponent()
            )
        }
        throw ServerConfigError.notConfigured
    }

    /// A checkout two levels above the bundle (`macos/build/.../Milo.app`)
    /// or above this source tree during development; nil once installed.
    static func checkoutDataDirectory(fileManager: FileManager = .default) -> URL? {
        var url = Bundle.main.bundleURL
        for _ in 0..<6 {
            url.deleteLastPathComponent()
            let candidate = url.appendingPathComponent(".data", isDirectory: true)
            if fileManager.fileExists(atPath: candidate.appendingPathComponent("server.json").path) {
                return candidate
            }
        }
        return nil
    }

    /// The shared Milo server must use an HTTPS origin (Linux parity).
    static func validate(_ raw: String) throws -> URL {
        guard
            let url = URL(string: raw),
            url.scheme == "https",
            let host = url.host, !host.isEmpty,
            url.user == nil, url.password == nil,
            url.query == nil, url.fragment == nil,
            url.path.isEmpty || url.path == "/"
        else {
            throw ServerConfigError.invalid("The shared Milo server must use an HTTPS origin.")
        }
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        components?.path = ""
        guard let origin = components?.url else {
            throw ServerConfigError.invalid("The shared Milo server must use an HTTPS origin.")
        }
        return origin
    }

    /// Attach this client's private first-start authorization, never log it.
    /// Tailscale device identity replaces first-start and password grants.
    func ownerInitialURL(fileManager: FileManager = .default) throws -> URL {
        if (serverURL.host ?? "").hasSuffix(".ts.net") {
            return serverURL
        }
        let pairing = configDirectory.appendingPathComponent("setup.url")
        var isDirectory: ObjCBool = false
        guard fileManager.fileExists(atPath: pairing.path, isDirectory: &isDirectory), !isDirectory.boolValue else {
            return serverURL
        }
        let values = try fileManager.attributesOfItem(atPath: pairing.path)
        let permissions = (values[.posixPermissions] as? NSNumber)?.intValue ?? 0
        let isSymlink = (try? fileManager.destinationOfSymbolicLink(atPath: pairing.path)) != nil
        guard !isSymlink, permissions & 0o077 == 0 else {
            throw ServerConfigError.invalid(
                "La configurazione privata di Milo deve appartenere a questo utente ed essere protetta."
            )
        }
        let raw = try String(contentsOf: pairing, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard
            let url = URL(string: raw),
            url.scheme == serverURL.scheme,
            url.host == serverURL.host,
            url.port == serverURL.port,
            url.query == nil,
            url.path.isEmpty || url.path == "/",
            let fragment = url.fragment,
            fragment.range(of: #"^setup=[A-Za-z0-9_-]{32}$"#, options: .regularExpression) != nil
        else {
            throw ServerConfigError.invalid(
                "Il collegamento privato di Milo non corrisponde al server configurato."
            )
        }
        return url
    }

    /// The fragment never reaches the server; the web app reads it and clears it.
    func initialURL(pending: PendingAction?) throws -> URL {
        switch pending {
        case .compose(let mailto):
            return try composeURL(mailto: mailto)
        case .open(let id):
            return try openURL(messageID: id)
        case nil:
            return try ownerInitialURL()
        }
    }

    func composeURL(mailto: String) throws -> URL {
        guard mailto.lowercased().hasPrefix("mailto:") else {
            throw ServerConfigError.invalid("Invalid mailto link.")
        }
        return URL(string: "/#compose=\(Self.percentEncode(mailto))", relativeTo: serverURL)!
            .absoluteURL
    }

    func openURL(messageID: String) throws -> URL {
        guard messageID.range(of: #"^[A-Za-z0-9_-]{1,80}$"#, options: .regularExpression) != nil else {
            throw ServerConfigError.invalid("Invalid message identifier.")
        }
        return URL(string: "/#open=\(messageID)", relativeTo: serverURL)!.absoluteURL
    }

    /// `quote(value, safe="")` equivalent: keep only RFC 3986 unreserved.
    static func percentEncode(_ value: String) -> String {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
    }
}

enum PendingAction: Equatable {
    case compose(mailto: String)
    case open(messageID: String)

    /// Command-line parity with `scripts/launch.py`: a `mailto:` argument
    /// or `--open=<message id>`.
    static func parse(arguments: [String]) -> PendingAction? {
        if let mailto = arguments.first(where: { $0.lowercased().hasPrefix("mailto:") }) {
            return .compose(mailto: mailto)
        }
        for argument in arguments where argument.hasPrefix("--open=") {
            let id = String(argument.dropFirst("--open=".count))
            if id.range(of: #"^[A-Za-z0-9_-]{1,80}$"#, options: .regularExpression) != nil {
                return .open(messageID: id)
            }
        }
        return nil
    }

    static func parse(url: URL) -> PendingAction? {
        switch url.scheme?.lowercased() {
        case "mailto":
            return .compose(mailto: url.absoluteString)
        case "milo":
            // milo://open/<message id> and milo://compose?url=<mailto:...>
            // hand actions from the notifier agent to the GUI instance.
            if url.host == "open" {
                let id = url.lastPathComponent
                if id.range(of: #"^[A-Za-z0-9_-]{1,80}$"#, options: .regularExpression) != nil {
                    return .open(messageID: id)
                }
            }
            if url.host == "compose",
               let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
               let mailto = components.queryItems?.first(where: { $0.name == "url" })?.value,
               mailto.lowercased().hasPrefix("mailto:") {
                return .compose(mailto: mailto)
            }
            return nil
        default:
            return nil
        }
    }
}
