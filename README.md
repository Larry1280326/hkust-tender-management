# HKUST e-Tendering Automation & Gmail Drafter

Automated workflow to:
1. Log in to the HKUST e-Tendering Portal (`https://w5.ab.ust.hk/jstd/td_welcome?page=td_login`) and accept the Terms & Conditions.
2. Scrape all active Tender Notices and parse the enquiry section (Contact Person name, email, phone).
3. Allow interactive selection of suitable tenders (or keyword filtering).
4. Automatically draft personalized enquiry emails directly in **Gmail** (with your company details and Business Registration certificate attached).

---

## Quick Start

### 1. First-Time Setup (Environment & Browsers)

If setting up for the first time, synchronize project dependencies and install the Chromium browser for Playwright:

```bash
# 1. Sync dependencies and create the .venv environment
uv sync

# 2. Install Playwright browser binary (Chromium)
uv run playwright install chromium
```

> **Tip:** While `uv run` will automatically install Python packages on first execution, running `uv sync` ensures your editor/IDE recognizes `.venv` immediately for autocomplete and linting. Installing Chromium is required for portal scraping.

---

### 2. Configure Credentials

Copy `.env.example` to `.env` (or edit existing `.env`):

```ini
# HKUST Vendor Portal Credentials
HKUST_VENDOR_ID=your_vendor_id_here
HKUST_PASSWORD=your_password_here

# Path to your Business Registration (BR) Certificate file (PDF or image)
BR_CERTIFICATE_PATH=assets/br_certificate.pdf

# Company Info (Loaded from .env)
COMPANY_NAME=Your Company Name
CONTACT_PERSON_NAME=Contact Person, Title
CONTACT_EMAIL=contact@example.com
CONTACT_PHONE=12345678
COMPANY_ADDRESS=Your Company Address
```

Place your official Business Registration certificate in `assets/br_certificate.pdf` (a placeholder has been provided for testing).

---

### 3. Gmail Integration Setup (One-time)

To create drafts directly inside your Gmail account:
1. Visit the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g. `HKUST-Tender-Automation`).
3. Enable the **Gmail API** under **APIs & Services > Library**.
4. Go to **APIs & Services > Credentials** > **Create Credentials** > **OAuth client ID**.
5. Choose Application type: **Desktop app**.
6. Download the OAuth credentials JSON and save it in this project folder as:
   ```
   credentials.json
   ```
7. On first run, a browser window will open asking you to sign in with your Google account. A `token.json` file will then be saved automatically for future runs.

*(Note: Even if `credentials.json` is not yet configured, the script will automatically export standard `.eml` files and generate one-click direct Gmail Web compose links!)*

---

### 4. Run the Automation

Run with `uv`:

```bash
uv run python app.py
```

You will see an interactive menu:
- **1. Scrape HKUST Tenders & Draft Emails**: Headless scraping + interactive tender checklist + Gmail draft creation.
- **2. Read Mailbox & Track HKUST Replies / Apply Tags**: Reads your Gmail INBOX via IMAP, finds HKUST enquiry threads and tender numbers from the subject line, displays a clean summary table, and applies Gmail tags.
- **3. Use Cached Tenders (Offline Draft Mode)**: Use tenders from local cache without connecting to HKUST portal.
- **4. Test Google Account Connection**: Verifies Google App Password and IMAP connection.
- **5. Exit**

#### Direct Command Line Flags:

```bash
# Read mailbox and display HKUST tender emails / interactive tagging
uv run python app.py --read-mail

# Scan mailbox and automatically tag all HKUST tender emails in Gmail
uv run python app.py --tag-tenders

# Test Google IMAP / App Password connection
uv run python app.py --test

# Run portal scraper with visible Chromium browser
uv run python app.py --visible

# Display help and all available CLI arguments
uv run python app.py --help

# Custom scan limit when reading mailbox (e.g. latest 20 emails)
uv run python app.py --read-mail --limit 20
```

---

## Gmail Tagging & Tender Tracking

When reading the mailbox, the tool checks each email's sender and title/subject for HKUST tender numbers (e.g. `PU/2026/001` or `EO/2026/012`).

It can automatically apply:
1. **Base Tag**: `HKUST-Tenders` (configurable via `HKUST_MAIL_TAG` in `.env`).
2. **Per-Tender Nested Tag**: `HKUST-Tenders/PU-2026-001` (organizes all correspondence for each specific tender into its own clean label in Gmail!).

---

## Email Template Generated

- **Subject**:
  `Request for Tender Documents – <Tender No.> - <Description>`

- **Body**:
  ```
  Dear <receipant name>,

  I am writing to express our interest in Tender No.: <Tender No.>- <Description>.

  In accordance with your requirements, here are our company details for your records:
  Company Name: <COMPANY_NAME from .env>
  Name of Contact Person: <CONTACT_PERSON_NAME from .env>
  Email Address: <CONTACT_EMAIL from .env>
  Phone Number: <CONTACT_PHONE from .env>
  Company Address: <COMPANY_ADDRESS from .env>

  Please find attached a copy of our Business Registration Certificate (BR) for your verification.

  Kindly confirm receipt and advise of any further steps or requirements. Thank you.

  <SIGN_OFF from .env>
  ```

- **Attachment**:
  Attached Business Registration Certificate (`assets/br_certificate.pdf`).

---

## Running Unit Tests

To run the automated verification suite:

```bash
uv run python -m unittest discover tests
```
