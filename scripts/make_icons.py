"""Render the project's vector icon as app-manifest PNG assets."""
from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
svg = (root / "web/icon.svg").read_text()
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for size in (180, 192, 512):
        page = browser.new_page(viewport={"width": size, "height": size})
        page.set_content('<html><body style="margin:0">' + svg + '</body></html>')
        page.locator("svg").evaluate("(element,size) => {element.style.width=size+'px';element.style.height=size+'px'}", size)
        page.locator("svg").screenshot(path=str(root / f"web/icon-{size}.png"), omit_background=True)
        page.close()
    browser.close()
