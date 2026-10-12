"""Sanitize email HTML while retaining tables, inline typography and CID images."""
from urllib.parse import quote, urlsplit

import nh3


def render_html(mail, message_id, load_images=False):
    part = mail.get_body(preferencelist=("html",))
    if not part:
        return {"html": None, "remote_images": False}
    try:
        source = part.get_content()
    except (LookupError, UnicodeError):
        source = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
    images = {}
    for index, attachment in enumerate(mail.walk()):
        if attachment.get("Content-ID") and attachment.get_content_type().startswith("image/"):
            images[attachment["Content-ID"].strip("<>")] = f"/api/messages/{quote(message_id, safe='')}/attachments/{index}"
    blocked = False

    def attribute(tag, name, value):
        nonlocal blocked
        if name == "src":
            if value.startswith("cid:"):
                return images.get(value[4:])
            parsed = urlsplit(value)
            if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username:
                blocked = True
                return value if load_images and parsed.scheme == "https" else None
            return None
        if name == "href":
            parsed = urlsplit(value)
            return value if parsed.scheme in {"https", "http", "mailto"} and not parsed.username else None
        return value

    html = nh3.clean(source[:2_000_000],
        tags={"a", "abbr", "b", "blockquote", "br", "caption", "center", "code", "col", "colgroup",
              "dd", "del", "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6",
              "hr", "i", "img", "li", "ol", "p", "pre", "s", "small", "span", "strong", "sub", "sup",
              "table", "tbody", "td", "th", "thead", "tfoot", "tr", "u", "ul"},
        clean_content_tags={"script", "style", "iframe", "object", "svg", "math", "form", "button", "textarea"},
        attributes={"*": {"style", "title", "dir", "lang", "class", "id"}, "a": {"href"},
                    "img": {"src", "alt", "width", "height"}, "table": {"width", "cellpadding", "cellspacing", "border", "align", "bgcolor"},
                    "td": {"width", "height", "colspan", "rowspan", "align", "valign", "bgcolor"},
                    "th": {"colspan", "rowspan", "align"}, "font": {"color", "face", "size"},
                    "blockquote": {"type"}},
        attribute_filter=attribute, set_tag_attribute_values={"a": {"target": "_blank"}},
        url_schemes={"http", "https", "mailto", "cid"},
        filter_style_properties={"color", "background-color", "font", "font-family", "font-size", "font-weight",
                                 "font-style", "line-height", "text-align", "text-decoration", "letter-spacing",
                                 "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
                                 "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
                                 "border", "border-top", "border-bottom", "border-left", "border-right",
                                 "border-color", "border-width", "border-style", "border-radius", "border-collapse",
                                 "width", "height", "max-width", "min-width", "vertical-align", "display"})
    return {"html": html, "remote_images": blocked}
