# HKUST e-Tendering Automation & Gmail Drafter

Automated workflow to:
1. Log in to the HKUST e-Tendering Portal (`https://w5.ab.ust.hk/jstd/td_welcome?page=td_login`) and accept the Terms & Conditions.
2. Scrape all active Tender Notices and parse the enquiry section (Contact Person name, email, phone).
3. Allow interactive selection of suitable tenders (or keyword filtering).
4. Automatically draft personalized enquiry emails directly in **Gmail** (with Chun King Limited company details and Business Registration certificate attached).

---

## Quick Start

### 1. Configure Credentials

Copy `.env.example` to `.env` (or edit existing `.env`):

```ini
# HKUST Vendor Portal Credentials
HKUST_VENDOR_ID=your_vendor_id_here
HKUST_PASSWORD=your_password_here

# Path to your Business Registration (BR) Certificate file (PDF or image)
BR_CERTIFICATE_PATH=assets/br_certificate.pdf

# Company Info (Pre-configured for Chun King Limited)
COMPANY_NAME=Chun King Limited
CONTACT_PERSON_NAME=Kong Ming Foon, Director
CONTACT_EMAIL=account@chunking.com.hk
CONTACT_PHONE=92300940
COMPANY_ADDRESS=Room A1008, 10/F, Union Hing Yip Factory Building, 20 Hing Yip Street, Kwun Tong, Kowloon
```

Place your official Business Registration certificate in `assets/br_certificate.pdf` (a placeholder has been provided for testing).

---

### 2. Gmail Integration Setup (One-time)

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

### 3. Run the Automation

Run with `uv`:

```bash
uv run python app.py
```

You will see an interactive menu:
- **1. Run HKUST Tender Scraper & Draft Emails**: Headless scraping + interactive tender checklist + Gmail draft creation.
- **2. Run Scraper in Headed Browser**: Shows the browser window in real-time (useful for verifying login visually).
- **3. Test Gmail Authentication**: Verifies Google Cloud OAuth connection.
- **4. Load Sample / Mock Tenders**: Test draft generation and email preview immediately without needing HKUST portal credentials.
- **5. Exit**

---

## Email Template Generated

- **Subject**:
  `Request for Tender Documents – <Tender No.> - <Description>`

- **Body**:
  ```
  Dear <receipant name>,

  I am writing to express our interest in Tender No.: <Tender No.>- <Description>.

  In accordance with your requirements, here are our company details for your records:
  Company Name: Chun King Limited
  Name of Contact Person: Kong Ming Foon, Director
  Email Address: account@chunking.com.hk
  Phone Number: 92300940
  Company Address: Room A1008, 10/F, Union Hing Yip Factory Building, 20 Hing Yip Street, Kwun Tong, Kowloon

  Please find attached a copy of our Business Registration Certificate (BR) for your verification.

  Kindly confirm receipt and advise of any further steps or requirements. Thank you.

  Best regards,
  Kong Ming Foon
  Director
  Chun King Limited
  ```

- **Attachment**:
  Attached Business Registration Certificate (`assets/br_certificate.pdf`).

---

## Running Unit Tests

To run the automated verification suite:

```bash
uv run python -m unittest discover tests
```
