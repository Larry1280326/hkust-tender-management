"""Configuration module for HKUST Vendor Automation."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables from .env
load_dotenv(BASE_DIR / ".env")

# HKUST Portal Config
HKUST_WELCOME_URL = os.getenv(
    "HKUST_WELCOME_URL", "https://w5.ab.ust.hk/jstd/td_welcome?page=td_login"
)
HKUST_LOGIN_URL = os.getenv("HKUST_LOGIN_URL", "https://w5.ab.ust.hk/jstd/td_login")
HKUST_VENDOR_ID = os.getenv("HKUST_VENDOR_ID", "")
HKUST_PASSWORD = os.getenv("HKUST_PASSWORD", "")

# Playwright session state file (to cache cookies/session)
SESSION_STATE_PATH = BASE_DIR / "session_state.json"

# Company Information (Configured solely via .env)
COMPANY_NAME = os.getenv("COMPANY_NAME", "")
CONTACT_PERSON_NAME = os.getenv("CONTACT_PERSON_NAME", "")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")
CONTACT_PHONE = os.getenv("CONTACT_PHONE", "")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "")


def _build_default_sign_off() -> str:
    lines = ["Best regards,"]
    if CONTACT_PERSON_NAME:
        lines.append(CONTACT_PERSON_NAME)
    if COMPANY_NAME:
        lines.append(COMPANY_NAME)
    return "\n".join(lines)


SIGN_OFF = os.getenv("SIGN_OFF", "") or _build_default_sign_off()

# Business Registration (BR) Certificate Path
BR_CERTIFICATE_PATH = Path(
    os.getenv("BR_CERTIFICATE_PATH", str(ASSETS_DIR / "br_certificate.pdf"))
)

# Google Account Credentials (App Password / IMAP & SMTP)
GMAIL_USER = os.getenv("GMAIL_USER", os.getenv("CONTACT_EMAIL", ""))
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
GMAIL_DRAFTS_URL = os.getenv("GMAIL_DRAFTS_URL", "https://mail.google.com/mail/#drafts")
HKUST_MAIL_TAG = os.getenv("HKUST_MAIL_TAG", "HKUST Tenders")

# Google API Credentials (Fallback / OAuth)
GMAIL_CREDENTIALS_PATH = Path(
    os.getenv("GMAIL_CREDENTIALS_PATH", str(BASE_DIR / "credentials.json"))
)
GMAIL_TOKEN_PATH = Path(os.getenv("GMAIL_TOKEN_PATH", str(BASE_DIR / "token.json")))

# Email Template
EMAIL_SUBJECT_TEMPLATE = "Request for Tender Documents – {tender_no} - {description}"

EMAIL_BODY_TEMPLATE = """Dear {recipient_name},

I am writing to express our interest in Tender No.: {tender_no}- {description}.

In accordance with your requirements, here are our company details for your records:
Company Name: {company_name}
Name of Contact Person: {contact_person}
Email Address: {contact_email}
Phone Number: {contact_phone}
Company Address: {company_address}

Please find attached a copy of our Business Registration Certificate (BR) for your verification.

Kindly confirm receipt and advise of any further steps or requirements. Thank you.

{sign_off}
"""
