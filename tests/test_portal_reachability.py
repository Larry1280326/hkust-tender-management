import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright
import config


def test_portal_flow():
    print("[*] Launching headless browser to test HKUST portal flow...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"[*] Navigating to {config.HKUST_WELCOME_URL}...")
        page.goto(config.HKUST_WELCOME_URL, wait_until="networkidle")

        title = page.title()
        print(f"[+] Page Title: {title}")
        assert "HKUST" in title, f"Unexpected page title: {title}"

        # Check Terms box
        assert page.locator("#tncChkBox").count() > 0, "Terms checkbox #tncChkBox not found"
        tnc_box = page.locator("#tncChkBox")
        tnc_box.check()
        assert tnc_box.is_checked(), "Failed to check terms checkbox"

        # Submit Terms
        print("[*] Clicking Accept button (#submitBtn)...")
        page.click("#submitBtn")
        page.wait_for_load_state("networkidle")

        # Verify navigation to logon page
        print(f"[*] Current URL after accept: {page.url}")
        assert "/td_login" in page.url or page.locator("#vendorId").count() > 0, (
            "Did not reach logon page after accepting terms"
        )

        vendor_input = page.locator("#vendorId")
        password_input = page.locator("#password")
        assert vendor_input.is_visible(), "Vendor ID input not visible"
        assert password_input.is_visible(), "Password input not visible"

        print("[+] [OK] Verified HKUST portal navigation & login form readiness!")
        browser.close()


if __name__ == "__main__":
    test_portal_flow()
