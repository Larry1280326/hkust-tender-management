"""Unit tests for mailbox reading, tender number parsing, and Gmail tagging."""

import unittest
from unittest.mock import MagicMock, patch
from email.message import EmailMessage

from mailer.google_account import (
    GoogleAccountMailer,
    TenderReceivedEmail,
    extract_tender_no_from_text,
    decode_mime_words,
    parse_gmail_labels,
)


class TestMailReader(unittest.TestCase):

    def test_extract_tender_no_from_text(self):
        # Case 1: Standard tender number in subject
        subject1 = "Request for Tender Documents – PU/2026/001 - Supply of IT Equipment"
        self.assertEqual(extract_tender_no_from_text(subject1), "PU/2026/001")

        # Case 2: HKUST TN code in template subject
        subject2 = "Request for Tender Documents – TNL2600072 - Supply and Installation of Slide"
        self.assertEqual(extract_tender_no_from_text(subject2), "TNL2600072")

        # Case 3: HKUST TN code with PQ
        subject3 = "Request for Tender Documents – TNA2600095 PQ - Express of Interest and Pre-Te"
        self.assertEqual(extract_tender_no_from_text(subject3), "TNA2600095 PQ")

        # Case 4: Reply with tender number
        subject4 = "Re: Tender No.: EO/2026/012 - Provision of Electrical & Renovation Works"
        self.assertEqual(extract_tender_no_from_text(subject4), "EO/2026/012")

        # Case 5: Tender ref variation
        subject5 = "Enquiry regarding Tender Ref: FO/2025/102"
        self.assertEqual(extract_tender_no_from_text(subject5), "FO/2025/102")

        # Case 6: Match against known tender list
        known = ["CUSTOM-TENDER-99", "PU/2026/001"]
        text6 = "Questions about custom-tender-99 from contractor"
        self.assertEqual(extract_tender_no_from_text(text6, known_tenders=known), "CUSTOM-TENDER-99")

        # Case 7: Irrelevant email
        subject7 = "Lunch meeting tomorrow at HKUST cafeteria"
        self.assertIsNone(extract_tender_no_from_text(subject7))

    def test_decode_mime_words(self):
        # Plain string
        self.assertEqual(decode_mime_words("Simple Subject"), "Simple Subject")
        self.assertEqual(decode_mime_words(""), "")
        self.assertEqual(decode_mime_words(None), "")

        # MIME encoded-word (UTF-8)
        encoded = "=?UTF-8?B?VEVTVCAtIFBVLzIwMjYvMDAx?="  # "TEST - PU/2026/001" in base64
        self.assertEqual(decode_mime_words(encoded), "TEST - PU/2026/001")

    def test_parse_gmail_labels(self):
        raw = '123 (UID 456 X-GM-LABELS ("\\\\Important" "HKUST-Tenders" "PU-2026-001") RFC822 {100}'
        labels = parse_gmail_labels(raw)
        self.assertIn("\\\\Important", labels)
        self.assertIn("HKUST-Tenders", labels)
        self.assertIn("PU-2026-001", labels)

        # Unquoted system label
        raw2 = "12 (UID 34 X-GM-LABELS (\\Inbox \\Sent))"
        labels2 = parse_gmail_labels(raw2)
        self.assertEqual(labels2, ["\\Inbox", "\\Sent"])

        # Empty
        raw3 = "12 (UID 34 X-GM-LABELS ())"
        self.assertEqual(parse_gmail_labels(raw3), [])

    @patch("imaplib.IMAP4_SSL")
    def test_list_mailboxes(self, mock_imap_cls):
        mock_imap = MagicMock()
        mock_imap_cls.return_value = mock_imap
        mock_imap.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "[Gmail]/Drafts"',
                b'(\\HasNoChildren) "/" "HKUST-Tenders"',
            ],
        )

        mailer = GoogleAccountMailer(username="user@test.com", app_password="password123")
        mailboxes = mailer.list_mailboxes()

        self.assertIn("INBOX", mailboxes)
        self.assertIn("[Gmail]/Drafts", mailboxes)
        self.assertIn("HKUST-Tenders", mailboxes)

    @patch("imaplib.IMAP4_SSL")
    def test_read_emails_and_tagging(self, mock_imap_cls):
        mock_imap = MagicMock()
        mock_imap_cls.return_value = mock_imap

        # Select & Search returns 1 UID
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.uid.side_effect = lambda cmd, *args: self._mock_imap_uid(cmd, *args)

        mailer = GoogleAccountMailer(username="user@test.com", app_password="password123")

        # 1. Test read_emails
        emails = mailer.read_emails(folder="INBOX", limit=5)
        self.assertEqual(len(emails), 1)
        email_item = emails[0]
        self.assertEqual(email_item.uid, "101")
        self.assertEqual(email_item.tender_no, "PU/2026/001")
        self.assertIn("pur@ust.hk", email_item.sender)

        # 2. Test tag_hkust_tender_emails
        tagged = mailer.tag_hkust_tender_emails(
            emails=[email_item],
            tag_prefix="HKUST-Tenders",
            per_tender_tag=True,
        )
        self.assertEqual(len(tagged), 1)
        self.assertEqual(tagged[0]["tender_no"], "PU/2026/001")
        # Should apply base tag and sub-tag with sanitized slash
        self.assertIn("HKUST-Tenders", tagged[0]["applied_tags"])
        self.assertIn("HKUST-Tenders/PU-2026-001", tagged[0]["applied_tags"])

    def _mock_imap_uid(self, cmd, *args):
        if cmd == "SEARCH":
            return ("OK", [b"101"])
        elif cmd == "FETCH":
            # Build sample message
            msg = EmailMessage()
            msg["Subject"] = "Re: Request for Tender Documents – PU/2026/001"
            msg["From"] = "HKUST Purchasing <pur@ust.hk>"
            msg["Date"] = "Mon, 28 Sep 2026 15:30:00 +0800"
            msg.set_content("Dear Sir, please find the documents attached.")
            meta_header = b'1 (UID 101 X-GM-LABELS ("\\\\Inbox") RFC822 {150}'
            return ("OK", [(meta_header, msg.as_bytes())])
        elif cmd == "STORE":
            return ("OK", [b"OK"])
        return ("OK", [])


if __name__ == "__main__":
    unittest.main()
