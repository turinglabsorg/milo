import Foundation

/// Finds a confirmation (OTP) code in a message, mirroring the web client:
/// a digit group anchored to a code keyword, else a bare 6-digit group in a
/// message that talks about codes at all. Sent messages never carry one.
public enum ConfirmationCode {
    public static func detect(in messages: [Message]) -> String? {
        for message in messages.reversed() where !message.sent.value {
            let text = [message.subject, message.body].compactMap { $0 }.joined(separator: "\n")
            if let code = detect(in: text) { return code }
        }
        return nil
    }

    public static func detect(in text: String) -> String? {
        let range = NSRange(text.startIndex..., in: text)
        let hint = try? NSRegularExpression(
            pattern: "(codice|code|otp|verific|conferma|one[-\\s]?time|authentication|security|temporaneo|monouso)",
            options: .caseInsensitive)
        guard let hint, hint.firstMatch(in: text, range: range) != nil else { return nil }
        let anchored = try? NSRegularExpression(
            pattern: "(?:codice|code|otp|verifica(?:zione)?|conferma|verification|authentication|security"
                + "|one[-\\s]?time(?:\\s(?:password|code))?|temporaneo|monouso)[^0-9]{0,48}(\\d[\\d\\s-]{3,10}\\d)",
            options: .caseInsensitive)
        if let match = anchored?.firstMatch(in: text, range: range), let group = Range(match.range(at: 1), in: text) {
            let cleaned = text[group].filter { $0.isNumber }
            if (4...8).contains(cleaned.count) { return cleaned }
        }
        let plain = try? NSRegularExpression(pattern: "\\b(\\d{6})\\b")
        if let match = plain?.firstMatch(in: text, range: range), let group = Range(match.range(at: 1), in: text) {
            return String(text[group])
        }
        return nil
    }
}
