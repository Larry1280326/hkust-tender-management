"""Integration test for HKUST portal reachability and login flow."""

import os
import unittest
from playwright.sync_api import sync_playwright
import config


class TestPortalReachability(unittest.TestCase):
    """Verifies HKUST portal terms acceptance and login form readiness."""

    @unittest.skipUnless(
        os.getenv("RUN_LIVE_PORTAL_TEST") == "1",
        "Live portal test skipped by default. Set RUN_LIVE_PORTAL_TEST=1 to run.",
    )
    def test_portal_flow(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(config.HKUST_WELCOME_URL, wait_until="networkidle")
            title = page.title()
            self.assertIn("HKUST", title, f"Unexpected page title: {title}")

            # Check Terms box
            self.assertGreater(page.locator("#tncChkBox").count(), 0, "Terms checkbox #tncChkBox not found")
            tnc_box = page.locator("#tncChkBox")
            tnc_box.check()
            self.assertTrue(tnc_box.is_checked(), "Failed to check terms checkbox")

            # Submit Terms
            page.click("#submitBtn")
            page.wait_for_load_state("networkidle")

            # Verify navigation to logon page
            is_login_page = "/td_login" in page.url or page.locator("#vendorId").count() > 0
            self.assertTrue(is_login_page, "Did not reach logon page after accepting terms")

            vendor_input = page.locator("#vendorId")
            password_input = page.locator("#password")
            self.assertTrue(vendor_input.is_visible(), "Vendor ID input not visible")
            self.assertTrue(password_input.is_visible(), "Password input not visible")

            browser.close()


if __name__ == "__main__":
    # If run directly from command line, enable live test
    os.environ["RUN_LIVE_PORTAL_TEST"] = "1"
    unittest.main()
