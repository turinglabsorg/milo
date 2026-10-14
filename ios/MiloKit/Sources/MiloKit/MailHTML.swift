import Foundation

/// Sanitized email HTML (the service runs it through nh3) wrapped like the web client's frames:
/// a strict Content-Security-Policy, no scripts from the mail, sender formatting preserved.
public enum MailHTML {
    public static func document(_ html: String, remoteImages: Bool = true) -> String {
        let images = remoteImages ? "'self' https: data:" : "'self' data:"
        return """
        <!doctype html><html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="referrer" content="no-referrer">
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src \(images); style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
        <style>
        html{color-scheme:light;-webkit-text-size-adjust:100%}
        body{margin:0;font:16px/1.55 -apple-system,system-ui,sans-serif;color:#172033;overflow-wrap:anywhere;background:#fff}
        .milo-email-document{display:flow-root;padding:14px;box-sizing:border-box}
        img,table{max-width:100%!important}img{height:auto}pre{white-space:pre-wrap}a{color:#2563eb}
        table{border-collapse:collapse}
        .milo-quoted-history{margin:16px 0;border-top:1px solid #dfe7f2;padding-top:10px}
        .milo-quoted-history>summary{color:#64748b;font-size:14px}
        .milo-quoted-history:not([open])>*:not(summary){display:none!important}
        </style></head><body><div class="milo-email-document">\(html)</div></body></html>
        """
    }

    /// Run by the app (not by the mail) after loading: link bare URLs, unwrap Google redirect links,
    /// collapse quoted history and report the content height.
    public static let enhanceScript = #"""
    const pattern=/\bhttps?:\/\/[^\s<>"'()\[\]]+/gi;
    const real=url=>{try{const u=new URL(url);if(/(^|\.)google\.[a-z.]+$/i.test(u.hostname)&&u.pathname==='/url'){const t=u.searchParams.get('q')||u.searchParams.get('url');if(t&&/^https?:\/\//i.test(t))return t;}}catch(e){}return url;};
    const label=url=>{try{const u=new URL(url);for(const k of [...u.searchParams.keys()])if(/^utm_/i.test(k))u.searchParams.delete(k);return (u.host+u.pathname+u.search).replace(/\/$/,'');}catch(e){return url;}};
    for(const a of document.querySelectorAll('a[href]')){const h=a.getAttribute('href'),t=real(h);if(t!==h){a.setAttribute('href',t);if(a.textContent.trim()===h)a.textContent=label(t);}}
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT),nodes=[];
    while(walker.nextNode()){const n=walker.currentNode;pattern.lastIndex=0;if(!n.parentElement.closest('a,style')&&pattern.test(n.nodeValue))nodes.push(n);}
    for(const n of nodes){const f=document.createDocumentFragment();let last=0;pattern.lastIndex=0;
      for(const m of n.nodeValue.matchAll(pattern)){let url=m[0];const trail=(/[.,;:!?]+$/.exec(url)||[''])[0];url=url.slice(0,url.length-trail.length);
        f.append(n.nodeValue.slice(last,m.index));const a=document.createElement('a');const t=real(url);a.href=t;a.textContent=label(t);f.append(a);last=m.index+url.length;}
      f.append(n.nodeValue.slice(last));n.replaceWith(f);}
    const selectors='.gmail_quote,.gmail_quote_container,.yahoo_quoted,.protonmail_quote,blockquote[type="cite"],blockquote';
    for(const node of [...document.querySelectorAll(selectors)].filter(x=>!x.parentElement.closest(selectors))){
      const d=document.createElement('details'),s=document.createElement('summary');d.className='milo-quoted-history';s.textContent='Mostra il testo citato';node.replaceWith(d);d.append(s,node);}
    return Math.ceil(document.querySelector('.milo-email-document').scrollHeight);
    """#
}
