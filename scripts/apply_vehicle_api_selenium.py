"""Open the vehicle API application flow with persistent Selenium state.

The dedicated Chrome profile is stored below ``.runtime`` so the portal login
session survives later runs without placing cookies in Git. The service key is
never printed or copied into browser storage; collectors read it only from the
ignored runtime env files.

The script never submits an application by itself. It opens and inspects the
official form, then waits for an explicit ``SUBMIT`` line on stdin. Login and
CAPTCHA, if requested, are completed by the user in the visible Chrome window.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import dotenv_values
from selenium import webdriver
from selenium.common.exceptions import (
    NoAlertPresentException,
    NoSuchElementException,
    UnexpectedAlertPresentException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
PROFILE = RUNTIME / "selenium-portal-profile"
STATUS_PATH = RUNTIME / "vehicle_api_application_status.json"
DETAIL_URL = "https://www.data.go.kr/data/3035912/fileData.do"
LOGIN_URL = "https://www.data.go.kr/uim/login/loginView.do"


def logged_in(driver: webdriver.Chrome) -> bool:
    try:
        return "로그아웃" in driver.find_element(By.TAG_NAME, "body").text
    except UnexpectedAlertPresentException:
        # The portal asks whether this trusted profile should retain login state.
        # Accepting it is limited to the ignored Selenium profile below .runtime.
        try:
            driver.switch_to.alert.accept()
        except NoAlertPresentException:
            pass
        time.sleep(1)
        return "로그아웃" in driver.find_element(By.TAG_NAME, "body").text


def key_storage_status() -> dict[str, bool]:
    """Return presence flags only; never expose or log the credential."""
    collector = dotenv_values(RUNTIME / "collector.env")
    local = dotenv_values(RUNTIME / "local-collector.env")
    return {
        "collector_key_saved": bool(collector.get("DATA_GO_KR_SERVICE_KEY")),
        "local_collector_key_saved": bool(
            local.get("DATA_GO_KR_SERVICE_KEY")
        ),
    }


def save_status(status: str, **details: object) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "vehicle_registrations_api",
        "portal_id": "3035912",
        "status": status,
        **key_storage_status(),
        **details,
    }
    temporary = STATUS_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(STATUS_PATH)


def field_inventory(driver: webdriver.Chrome) -> list[dict]:
    fields = []
    for element in driver.find_elements(By.CSS_SELECTOR, "input, textarea, select"):
        kind = element.tag_name.lower()
        input_type = element.get_attribute("type") or kind
        if input_type in {"hidden", "submit", "button", "password"}:
            continue
        item = {
            "tag": kind,
            "type": input_type,
            "name": element.get_attribute("name"),
            "id": element.get_attribute("id"),
            "placeholder": element.get_attribute("placeholder"),
            "required": bool(element.get_attribute("required")),
        }
        if kind == "select":
            item["options"] = [
                option.text.strip()
                for option in element.find_elements(By.TAG_NAME, "option")
            ][:20]
        fields.append(item)
    return fields


def find_action(driver: webdriver.Chrome, label: str):
    return driver.find_element(
        By.XPATH,
        "//*[self::a or self::button or @role='button']"
        f"[contains(normalize-space(.), '{label}')]",
    )


def prefill_login(driver: webdriver.Chrome) -> bool:
    """Fill credentials supplied by the DPAPI wrapper without submitting them."""
    username = os.getenv("DATA_GO_KR_PORTAL_USERNAME", "")
    password = os.getenv("DATA_GO_KR_PORTAL_PASSWORD", "")
    if not username or not password:
        return False
    driver.get(LOGIN_URL)
    username_input = WebDriverWait(driver, 20).until(
        lambda current: current.find_element(
            By.XPATH, "//input[contains(@placeholder, '아이디')]"
        )
    )
    password_input = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    username_input.clear()
    username_input.send_keys(username)
    password_input.clear()
    password_input.send_keys(password)
    # The portal always presents a CAPTCHA. Never try to bypass it or submit
    # credentials until the user has entered the challenge in the visible UI.
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--debugger-address",
        help="attach to the existing Selenium Chrome, for example 127.0.0.1:9222",
    )
    args = parser.parse_args()
    PROFILE.mkdir(parents=True, exist_ok=True)
    options = webdriver.ChromeOptions()
    if args.debugger_address:
        options.debugger_address = args.debugger_address
    else:
        options.add_argument(f"--user-data-dir={PROFILE.resolve()}")
        options.add_argument("--start-maximized")
        options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=options)
    driver.get(DETAIL_URL)
    if not logged_in(driver):
        credentials_prefilled = prefill_login(driver)
        save_status("login_required")
        if credentials_prefilled:
            print(
                "CAPTCHA_REQUIRED: 저장된 계정정보를 입력했습니다. "
                "보안문자를 직접 입력하고 로그인하세요.",
                flush=True,
            )
        else:
            print(
                "LOGIN_REQUIRED: Selenium Chrome에서 공공데이터포털에 로그인하세요.",
                flush=True,
            )
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            try:
                if logged_in(driver):
                    save_status("login_session_saved")
                    break
            except NoSuchElementException:
                pass
            time.sleep(1)
        else:
            save_status("login_timeout")
            print("LOGIN_TIMEOUT", flush=True)
            return 2

    driver.get(DETAIL_URL)
    WebDriverWait(driver, 20).until(
        lambda current: "활용신청" in current.find_element(By.TAG_NAME, "body").text
    )
    button = find_action(driver, "활용신청")
    old_url = driver.current_url
    old_handles = set(driver.window_handles)
    driver.execute_script("arguments[0].click();", button)
    WebDriverWait(driver, 20).until(
        lambda current: current.current_url != old_url
        or set(current.window_handles) != old_handles
    )
    new_handles = set(driver.window_handles) - old_handles
    if new_handles:
        driver.switch_to.window(new_handles.pop())
    save_status("application_form_open", form_url=driver.current_url)
    print(
        json.dumps(
            {
                "status": "APPLICATION_FORM_OPEN",
                "url": driver.current_url,
                "title": driver.title,
                "fields": field_inventory(driver),
                **key_storage_status(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    print(
        "WAITING_FOR_SUBMIT: 검토 후 표준입력으로 SUBMIT을 보내야 제출합니다.",
        flush=True,
    )
    command = sys.stdin.readline().strip()
    if command != "SUBMIT":
        save_status("not_submitted", form_url=driver.current_url)
        print("NOT_SUBMITTED", flush=True)
        return 3

    submit = driver.find_element(
        By.XPATH,
        "//*[self::a or self::button or @role='button']"
        "[contains(normalize-space(.), '신청') or "
        "contains(normalize-space(.), '등록')]",
    )
    driver.execute_script("arguments[0].click();", submit)
    WebDriverWait(driver, 30).until(
        lambda current: "완료" in current.find_element(By.TAG_NAME, "body").text
        or "승인" in current.find_element(By.TAG_NAME, "body").text
        or "마이페이지" in current.current_url
    )
    save_status("submitted_approval_unverified", result_url=driver.current_url)
    print(
        json.dumps(
            {
                "status": "SUBMITTED_APPROVAL_UNVERIFIED",
                "url": driver.current_url,
                "title": driver.title,
                **key_storage_status(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
