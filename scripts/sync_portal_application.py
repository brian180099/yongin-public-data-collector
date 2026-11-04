"""After manual login, find and verify an approved API key automatically."""

import argparse
import json
import time

import httpx

from yongin_collector.portal_application import (
    APPLICATION_TITLES, parse_approved_application, save_approved_application,
    verify_approved_application,
)
from yongin_collector.sources import SOURCES
from yongin_collector.store import ROOT


APPLICATION_LIST_URL = "https://www.data.go.kr/iim/api/selectAcounList.do"
APPLICATION_DETAIL_PATH = "/selectAPIAcountView.do"


def wait_for_login(context, timeout_seconds: int = 600):
    """Let the user handle login and any portal authentication challenge."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for page in context.pages:
            if (not page.is_closed() and
                    page.get_by_text("로그아웃", exact=True).count() and
                    page.get_by_text("로그아웃", exact=True).first.is_visible()):
                return page
        if not context.pages:
            break
        context.pages[-1].wait_for_timeout(500)
    raise ValueError("portal login was not detected before timeout")


def open_approved_detail(context, page, title: str):
    page.goto(APPLICATION_LIST_URL, wait_until="domcontentloaded")
    match = page.get_by_text(title, exact=False)
    if not match.count():
        search = page.locator("input[placeholder*='검색어']")
        if search.count():
            search.first.fill(title)
            search.first.press("Enter")
    try:
        match.first.wait_for(state="visible", timeout=15000)
    except Exception:
        raise ValueError("approved application was not found in the account list") from None
    match.first.click()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        for candidate in context.pages:
            if not candidate.is_closed() and candidate.url.split("?", 1)[0].endswith(
                    APPLICATION_DETAIL_PATH):
                return candidate
        page.wait_for_timeout(250)
    raise ValueError("application detail did not open")


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
        browser = playwright.chromium.launch(channel="chrome", headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(source.application_url, wait_until="domcontentloaded")
            print("열린 브라우저에서 공공데이터포털에 로그인하세요. 이후 단계는 자동 진행됩니다.")
            page = wait_for_login(context)
            page = open_approved_detail(
                context, page, APPLICATION_TITLES[args.source]
            )
            # Visible text is kept in memory only. No clipboard or cookies saved.
            application = parse_approved_application(
                args.source, page.locator("body").inner_text(), page.url
            )
        finally:
            browser.close()
    with httpx.Client(timeout=20) as client:
        verify_approved_application(application, source.url, client)
    status = save_approved_application(
        application, ROOT / ".runtime", source.url, api_verified=True
    )
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
