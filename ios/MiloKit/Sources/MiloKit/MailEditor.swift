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
        <style data-milo-editor>html{color-scheme:light;-webkit-text-size-adjust:100%}body{margin:0;padding:14px;min-height:120px;font:16px/1.55 -apple-system,system-ui,sans-serif;color:#172033;background:#fff;overflow-wrap:anywhere}body:focus{outline:none}img,table{max-width:100%!important}img{height:auto}</style>
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

    /// Installed once per load in the app's content world. Mail scripts never run; this script
    /// edits through `designMode` and reports `{html, text, height}` to the `miloEditor` handler.
    public static let script = #"""
    if (!window.miloEditor) {
      const ed = window.miloEditor = {range: null};
      ed.serialize = () => {
        if (document.documentElement.hasAttribute('data-milo-fragment')) return document.body.innerHTML;
        const root = document.documentElement.cloneNode(true);
        root.querySelectorAll('[data-milo-editor]').forEach(node => node.remove());
        return '<!doctype html>\n' + root.outerHTML;
      };
      ed.text = () => {
        const clone = document.body.cloneNode(true);
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
      ed.post = () => window.webkit.messageHandlers.miloEditor.postMessage(ed.state());
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
        document.designMode = on ? 'on' : 'off';
        if (on) document.body.focus();
      };
      document.addEventListener('input', ed.post);
      new MutationObserver(ed.post).observe(document.documentElement, {subtree: true, childList: true, characterData: true});
      document.addEventListener('selectionchange', () => {
        const selection = getSelection();
        if (selection.rangeCount && document.body.contains(selection.anchorNode)) ed.range = selection.getRangeAt(0).cloneRange();
      });
      document.addEventListener('click', event => {
        if (document.designMode !== 'on' && event.target.closest && event.target.closest('a')) event.preventDefault();
      }, true);
    }
    return window.miloEditor.height();
    """#
}
