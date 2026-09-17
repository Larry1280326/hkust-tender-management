"""Authentication and session management for HKUST e-Tendering portal."""

import time
from typing import Optional
from playwright.sync_api import Browser, BrowserContext, Page

import config


class HKUSTAuthManager:
    """Manages login, Terms acceptance, and session persistence for HKUST portal."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.session_file = config.SESSION_STATE_PATH

    def get_context(self, browser: Browser) -> BrowserContext:
        """Create fresh browser context."""
        return browser.new_context(viewport={"width": 1400, "height": 900})

    def perform_login(
        self,
        page: Page,
        vendor_id: Optional[str] = None,
        password: Optional[str] = None,
    ) -> bool:
        """Navigate to HKUST portal, accept Terms if required, and log in."""
        v_id = vendor_id or config.HKUST_VENDOR_ID
        v_pwd = password or config.HKUST_PASSWORD

        if not v_id or not v_pwd:
            raise ValueError(
                "HKUST Vendor ID or Password is missing!\n"
                "Please configure HKUST_VENDOR_ID and HKUST_PASSWORD in your .env file."
            )

        print(f"[*] Navigating directly to HKUST login page: {config.HKUST_LOGIN_URL}")
        page.goto(config.HKUST_LOGIN_URL, wait_until="networkidle")

        # If redirected to td_welcome (in case terms agreement is required)
        if "/td_welcome" in page.url or page.locator("#tncChkBox").count() > 0:
            print("[*] Terms agreement required. Accepting Terms & Conditions...")
            page.evaluate("""() => {
                const el = document.getElementById('tncChkBox');
                if (el) {
                    el.checked = true;
                    if (typeof $ !== 'undefined') $(el).prop('checked', true).trigger('change');
                }
            }""")
            page.locator("#submitBtn").click()
            try:
                page.wait_for_url("**/td_login*", timeout=8000)
            except Exception:
                page.goto(config.HKUST_LOGIN_URL, wait_until="networkidle")

        # Fill credentials on login page
        print("[*] Waiting for login form...")
        page.wait_for_selector("#vendorId:visible", timeout=15000)

        print(f"[*] Entering Vendor ID: {v_id}")
        page.locator("#vendorId:visible").fill(v_id)
        page.locator("#password:visible").fill(v_pwd)

        print("[*] Submitting login credentials...")
        page.locator("#submitBtn").click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Check for login errors
        warning_modal = page.locator("#warningModal")
        if warning_modal.is_visible():
            err_text = page.locator("#warningMsg").inner_text().strip()
            raise RuntimeError(f"HKUST Login Failed: {err_text}")

        alert_box = page.locator("#alertBox")
        if alert_box.is_visible() and alert_box.inner_text().strip():
            print(f"[!] Portal alert: {alert_box.inner_text().strip()}")

        print(f"[+] Login successful. Current URL: {page.url}")
        return True
