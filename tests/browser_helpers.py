import time


def wait_for_async(page, predicate, arg=None, timeout=10000):
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        if page.evaluate(predicate, arg):
            return
        page.wait_for_timeout(25)
    raise AssertionError('Asynchronous browser condition did not become true')


def _rich_frame(page, scope):
    frame = page.locator(f'{scope} .rich-frame').first
    frame.wait_for(state='visible')
    wait_for_async(page, '(scope)=>{const f=document.querySelector(scope+" .rich-frame");const d=f&&f.contentDocument;'
                         'return Boolean(d&&d.readyState==="complete"&&d.querySelector("[data-milo-editor]"));}', scope)
    page.wait_for_timeout(50)
    return frame


def write_body(page, text, scope='#compose-form'):
    _rich_frame(page, scope).evaluate(
        '(frame,text)=>{const doc=frame.contentDocument;'
        'const esc=s=>s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");'
        'doc.body.innerHTML=text.split(/\\n{2,}/).map(b=>`<p>${esc(b).replace(/\\n/g,"<br>")||"<br>"}</p>`).join("");'
        'doc.dispatchEvent(new Event("input"));}', text)


def type_body(page, text, scope='#compose-form'):
    frame = _rich_frame(page, scope)
    frame.evaluate('(frame)=>{frame.focus();const doc=frame.contentDocument;if(doc.designMode!=="on")'
                   'frame.closest(".rich-editor").querySelector(".rich-edit").click();doc.body.focus();'
                   'const sel=doc.getSelection();sel.selectAllChildren(doc.body);sel.collapseToEnd();}')
    page.keyboard.type(text)
