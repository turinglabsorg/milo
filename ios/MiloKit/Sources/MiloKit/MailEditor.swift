import Foundation

/// WYSIWYG editing of a draft's HTML alternative: the document loaded in the editor web view,
/// the client-world script that edits it and serializes it back, and plain-text conversions.
public enum MailEditor {
    public static func document(_ html: String, remoteImages: Bool = false) -> String {
        let images = remoteImages ? "data: https:" : "data:"
        let head = """
        <meta data-milo-editor charset="utf-8"><meta data-milo-editor name="viewport" content="width=device-width, initial-scale=1">\
        <meta data-milo-editor name="referrer" content="no-referrer">\
        <meta data-milo-editor http-equiv="Content-Security-Policy" content="default-src 'none'; img-src \(images); style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">\
        <style data-milo-editor>html{color-scheme:light;-webkit-text-size-adjust:100%;height:100%}body{margin:0;padding:12px 16px 24px;min-height:100%;box-sizing:border-box;font:16px/1.55 -apple-system,system-ui,sans-serif;color:#172033;background:#fff;overflow-wrap:anywhere}body:focus{outline:none}img,table{max-width:100%!important}img{height:auto}[data-milo-signature-source]{display:none!important}[data-milo-signature-preview]{margin:16px 0 0;-webkit-user-modify:read-only;user-select:none}[data-milo-signature-preview] img{display:block;border-radius:12px}[data-milo-signature-preview] span{display:block;margin:8px 0 0 4px;font:13px/18px -apple-system,system-ui,sans-serif;color:#617189}[data-milo-signature-preview] a{color:#2f5bd3;text-decoration:none}</style>
        """
        if html.range(of: "<html[\\s>]", options: [.regularExpression, .caseInsensitive]) != nil {
            var copy = html
            if let open = html.range(of: "<head[^>]*>", options: [.regularExpression, .caseInsensitive]) {
                copy.insert(contentsOf: head, at: open.upperBound)
                return copy
            }
            if let root = html.range(of: "<html[^>]*>", options: [.regularExpression, .caseInsensitive]) {
                copy.insert(contentsOf: "<head>" + head + "</head>", at: root.upperBound)
                return copy
            }
        }
        return "<!doctype html><html data-milo-fragment><head>\(head)</head><body>\(html)</body></html>"
    }

    /// Plain text as HTML paragraphs, used when a draft switches to the formatted editor.
    public static func paragraphs(from text: String) -> String {
        func escape(_ value: String) -> String {
            value.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
                .replacingOccurrences(of: ">", with: "&gt;").replacingOccurrences(of: "\"", with: "&quot;")
        }
        let blocks = text.replacingOccurrences(of: "\r\n", with: "\n")
            .components(separatedBy: "\n\n").filter { !$0.isEmpty }
        if blocks.isEmpty { return "<p><br></p>" }
        return blocks.map { "<p>" + escape($0).replacingOccurrences(of: "\n", with: "<br>") + "</p>" }.joined()
    }

    /// The draft's HTML with the previous sender account's signature replaced by the new one's.
    /// Complete HTML documents are templates that carry their own signature and stay untouched.
    public static func swappingSignature(in html: String, from old: String?, to new: String?) -> String {
        if html.range(of: "<html[\\s>]", options: [.regularExpression, .caseInsensitive]) != nil { return html }
        let block = { (text: String?) -> String? in
            guard let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return nil }
            return paragraphs(from: "-- \n" + text)
        }
        let before = block(old), after = block(new)
        if before == after { return html }
        if let before, let range = html.range(of: before, options: .backwards) {
            return html.replacingCharacters(in: range, with: after ?? "")
        }
        if let after, !html.contains(after) { return html + after }
        return html
    }

    /// The sender's signature as the recipient sees it: the server-rendered card and the link lines
    /// under it. The editor shows it in place of the signature text, which stays in the saved draft.
    public struct SignaturePreview: Equatable, Sendable {
        public var text: String
        public var card: String
        public var links: [[String: String]]

        public init(text: String, png: Data) {
            self.text = text
            card = "data:image/png;base64," + png.base64EncodedString()
            links = MailEditor.signatureLinks(text).map { ["url": $0, "label": MailEditor.linkLabel($0)] }
        }

        var script: [String: Any] { ["text": text, "card": card, "links": links] }
    }

    static let linkLabels = ["linkedin.com": "LinkedIn", "x.com": "X", "twitter.com": "X", "github.com": "GitHub",
                             "instagram.com": "Instagram", "facebook.com": "Facebook"]

    /// Signature lines made only of a URL: they become clickable links under the card.
    public static func signatureLinks(_ text: String) -> [String] {
        text.components(separatedBy: .newlines).map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { $0.range(of: "^https?://\\S+$", options: .regularExpression) != nil }
    }

    public static func linkLabel(_ url: String) -> String {
        var host = url.replacingOccurrences(of: "^https?://", with: "", options: .regularExpression)
        host = String(host.split(whereSeparator: { $0 == "/" || $0 == "?" }).first ?? "").lowercased()
        if host.hasPrefix("www.") { host.removeFirst(4) }
        return linkLabels[host] ?? host
    }

    /// Shows `preview` in place of its signature text, or restores the text when it is nil.
    public static func decorateScript(_ preview: SignaturePreview?) -> (String, [String: Any]) {
        ("window.miloEditor && window.miloEditor.decorate(signature)", ["signature": preview?.script ?? NSNull()])
    }

    /// Installed once per load in the app's content world. Mail scripts never run; this script
    /// edits the body as `contentEditable` (so the keyboard keeps autocorrection and predictions) and reports `{html, text, height}` to the `miloEditor` handler.
    public static let script = #"""
    if (!window.miloEditor) {
      const ed = window.miloEditor = {range: null, editing: false};
      ed.clean = root => {
        root.querySelectorAll('[data-milo-signature-preview]').forEach(node => node.remove());
        root.querySelectorAll('[data-milo-signature-source]').forEach(node => node.removeAttribute('data-milo-signature-source'));
        const body = root.nodeName === 'BODY' ? root : root.querySelector('body');
        if (body) ['contenteditable', 'autocorrect', 'autocapitalize', 'spellcheck'].forEach(name => body.removeAttribute(name));
        return root;
      };
      ed.serialize = () => {
        if (document.documentElement.hasAttribute('data-milo-fragment')) return ed.clean(document.body.cloneNode(true)).innerHTML;
        const root = ed.clean(document.documentElement.cloneNode(true));
        root.querySelectorAll('[data-milo-editor]').forEach(node => node.remove());
        return '<!doctype html>\n' + root.outerHTML;
      };
      ed.lines = node => {
        const clone = node.cloneNode(true);
        clone.querySelectorAll('br').forEach(br => br.replaceWith('\n'));
        return clone.textContent.replace(/\u00a0/g, ' ').split('\n').map(line => line.trim()).filter(Boolean).join('\n');
      };
      ed.decorate = signature => {
        document.querySelectorAll('[data-milo-signature-preview]').forEach(node => node.remove());
        document.querySelectorAll('[data-milo-signature-source]').forEach(node => node.removeAttribute('data-milo-signature-source'));
        if (!signature || !signature.card) return ed.height();
        const wanted = ['--', ...signature.text.split('\n').map(line => line.trim()).filter(Boolean)].join('\n');
        const source = [...document.body.querySelectorAll('p')].reverse().find(node => ed.lines(node) === wanted);
        if (!source) return ed.height();
        const preview = document.createElement('div');
        preview.setAttribute('data-milo-signature-preview', '');
        preview.contentEditable = 'false';
        const card = document.createElement('img');
        card.alt = signature.text.split('\n').filter(line => !/^https?:\/\/\S+$/.test(line.trim())).join(' · ');
        card.addEventListener('load', () => { card.style.width = Math.round(card.naturalWidth / 2) + 'px'; ed.post(); });
        card.src = signature.card;
        preview.append(card);
        if (signature.links.length) {
          const row = document.createElement('span');
          signature.links.forEach((link, index) => {
            if (index) row.append(' · ');
            const anchor = document.createElement('a');
            anchor.href = link.url;
            anchor.textContent = link.label;
            row.append(anchor);
          });
          preview.append(row);
        }
        source.setAttribute('data-milo-signature-source', '');
        source.after(preview);
        // The hidden signature text must never be the only place the caret can go.
        if (!source.previousElementSibling) {
          const line = document.createElement('p');
          line.append(document.createElement('br'));
          source.before(line);
        }
        if (ed.editing) ed.caret(true);
        return ed.height();
      };
      ed.writable = node => !!node && !(node.closest && node.closest('[data-milo-signature-source],[data-milo-signature-preview]'));
      ed.caret = force => {
        const selection = getSelection();
        const at = selection.rangeCount ? selection.getRangeAt(0).startContainer : null;
        const anchor = at && (at.nodeType === 1 ? at : at.parentElement);
        const source = document.querySelector('[data-milo-signature-source]');
        if (anchor && document.body.contains(anchor) && ed.writable(anchor) && !(force && source)) return;
        const target = source ? source.previousElementSibling : document.body;
        if (!target) return;
        const range = document.createRange();
        range.selectNodeContents(target);
        range.collapse(!source);
        if (source && target.lastChild && target.lastChild.nodeName === 'BR' && target.childNodes.length === 1) range.setStartBefore(target.lastChild);
        selection.removeAllRanges();
        selection.addRange(range);
        ed.range = range.cloneRange();
      };
      ed.prune = () => {
        document.querySelectorAll('[data-milo-signature-source]').forEach(source => {
          const next = source.nextElementSibling;
          if (!next || !next.hasAttribute('data-milo-signature-preview')) source.remove();
        });
      };
      ed.text = () => {
        const clone = ed.clean(document.body.cloneNode(true));
        clone.querySelectorAll('style,script,head').forEach(node => node.remove());
        clone.querySelectorAll('br').forEach(node => node.replaceWith('\n'));
        clone.querySelectorAll('div,li,tr').forEach(node => node.append('\n'));
        clone.querySelectorAll('p,h1,h2,h3,h4,table,blockquote,ul,ol').forEach(node => node.append('\n\n'));
        clone.querySelectorAll('li').forEach(node => node.prepend('• '));
        clone.querySelectorAll('a[href]').forEach(node => {
          const href = node.getAttribute('href');
          if (/^https?:/i.test(href) && !node.textContent.includes(href)) node.append(' (' + href + ')');
        });
        return clone.textContent.replace(/[ \t\u00a0]+\n/g, '\n').replace(/^--$/gm, '-- ').replace(/\n{3,}/g, '\n\n').trim();
      };
      ed.height = () => Math.ceil(document.documentElement.scrollHeight);
      ed.state = () => ({html: ed.serialize(), text: ed.text(), height: ed.height()});
      ed.post = () => { ed.prune(); window.webkit.messageHandlers.miloEditor.postMessage(ed.state()); };
      ed.restore = () => {
        if (!ed.range) return;
        const selection = getSelection();
        selection.removeAllRanges();
        selection.addRange(ed.range);
      };
      ed.exec = (command, value) => {
        ed.restore();
        if (command === 'h2' || command === 'p') document.execCommand('formatBlock', false, command);
        else document.execCommand(command, false, value || null);
        ed.post();
      };
      ed.setEditing = on => {
        ed.editing = on;
        const body = document.body;
        if (on) {
          body.contentEditable = 'true';
          body.setAttribute('autocorrect', 'on');
          body.setAttribute('autocapitalize', 'sentences');
          body.setAttribute('spellcheck', 'true');
          ed.caret(true);
        } else {
          body.removeAttribute('contenteditable');
          ['autocorrect', 'autocapitalize', 'spellcheck'].forEach(name => body.removeAttribute(name));
        }
      };
      ed.blur = () => { if (document.activeElement) document.activeElement.blur(); };
      document.addEventListener('input', ed.post);
      new MutationObserver(ed.post).observe(document.documentElement, {subtree: true, childList: true, characterData: true});
      document.addEventListener('selectionchange', () => {
        const selection = getSelection();
        if (!selection.rangeCount || !document.body.contains(selection.anchorNode)) return;
        if (ed.editing && !ed.writable(selection.anchorNode.nodeType === 1 ? selection.anchorNode : selection.anchorNode.parentElement)) return ed.caret();
        ed.range = selection.getRangeAt(0).cloneRange();
      });
      document.addEventListener('click', event => {
        if (!ed.editing && event.target.closest && event.target.closest('a')) event.preventDefault();
      }, true);
    }
    return window.miloEditor.height();
    """#
}
