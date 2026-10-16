import MiloKit
import SwiftUI

/// DESIGN.md tokens: blue accent, quiet borders, black surfaces in dark mode.
extension Color {
    static let milo = MiloPalette()
}

struct MiloPalette {
    let accent = Color.accentColor
    let line = Color(light: 0xDFE7F2, dark: 0x272727)
    let soft = Color(light: 0xEAF2FF, dark: 0x171717)
    let surfaceAlt = Color(light: 0xF4F7FC, dark: 0x0D0D0D)
    let muted = Color(light: 0x617189, dark: 0xA5A5A5)
    let danger = Color(light: 0xC0262D, dark: 0xF87171)
}

extension Color {
    init(light: UInt32, dark: UInt32) {
        self.init(uiColor: UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                           blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
        })
    }

    init?(hex: String?) {
        guard let hex, hex.count == 7, hex.hasPrefix("#"), let value = UInt32(hex.dropFirst(), radix: 16) else { return nil }
        self.init(red: Double((value >> 16) & 0xFF) / 255, green: Double((value >> 8) & 0xFF) / 255,
                  blue: Double(value & 0xFF) / 255)
    }
}

enum Format {
    static func initials(_ name: String?) -> String {
        let words = (name ?? "?").split { " @.".contains($0) }.prefix(2)
        return words.compactMap { $0.first.map(String.init) }.joined().uppercased()
    }

    /// Time for today, short date otherwise, like the web list.
    static func date(_ timestamp: Double, long: Bool = false) -> String {
        let date = Date(timeIntervalSince1970: timestamp)
        if !long && Calendar.current.isDateInToday(date) { return date.formatted(date: .omitted, time: .shortened) }
        return long ? date.formatted(.dateTime.day().month(.abbreviated).hour().minute())
            : date.formatted(.dateTime.day().month(.abbreviated))
    }
}

struct Avatar: View {
    var name: String?
    var color: Color?
    var size: CGFloat = 36

    var body: some View {
        Text(Format.initials(name))
            .font(.system(size: size * 0.34, weight: .semibold))
            .foregroundStyle(Color.milo.muted)
            .frame(width: size, height: size)
            .background(Color.milo.soft, in: RoundedRectangle(cornerRadius: size * 0.28))
            .overlay(RoundedRectangle(cornerRadius: size * 0.28).strokeBorder(color ?? Color.milo.line, lineWidth: 1.5))
            .accessibilityHidden(true)
    }
}

extension MailView {
    var title: String {
        switch self {
        case .inbox: "Smart inbox"
        case .unread: "Da leggere"
        case .todo: "Da fare"
        case .starred: "Preferiti"
        case .drafts: "Bozze"
        case .sent: "Posta inviata"
        case .snoozed: "Per dopo"
        case .archive: "Archivio"
        }
    }

    var symbol: String {
        switch self {
        case .inbox: "tray"
        case .unread: "envelope.badge"
        case .todo: "checklist"
        case .starred: "star"
        case .drafts: "square.and.pencil"
        case .sent: "paperplane"
        case .snoozed: "clock"
        case .archive: "archivebox"
        }
    }
}
