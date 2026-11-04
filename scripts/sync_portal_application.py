"""Interactively capture an approved data.go.kr API detail into local secrets.

The user signs in and opens the approved application detail in the browser.
This script reads the visible detail only; it does not submit applications.
"""

import argparse
import json

from yongin_collector.portal_application import (
    parse_approved_application, save_approved_application,
)
from yongin_collector.sources import SOURCES
from yongin_collector.store import ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("public_facilities",),
                        default="public_facilities")
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        parser.error("install the optional portal dependency: pip install -e '.[portal]'")
    source = SOURCES[args.source]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(source.application_url, wait_until="domcontentloaded")
        input("포털에서 로그인하고 해당 API의 승인된 활용신청 상세 화면을 연 뒤 Enter: ")
        page = context.pages[-1]
        # Only the visible page text is read. Credentials/cookies are not saved.
        application = parse_approved_application(
            args.source, page.locator("body").inner_text(), page.url
        )
        browser.close()
    status = save_approved_application(application, ROOT / ".runtime", source.url)
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
