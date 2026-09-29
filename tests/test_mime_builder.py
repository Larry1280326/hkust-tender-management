"""Unit tests for the unified MIME message builder and IMAP session manager."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from mailer.mime import build_mime_message
from mailer.template import TenderEmailDraft
from mailer.google_account import GoogleAccountMailer


class TestMimeBuilderAndSession(unittest.TestCase):

    def test_build_mime_message_basic(self):
        draft = TenderEmailDraft(
            tender_no="TEST-MIME-01",
            description="Supply of Office Laptops",
            recipient_name="Mr. Smith",
            recipient_email="smith@ust.hk",
            subject="Request for Tender Documents – TEST-MIME-01",
            body="Dear Mr. Smith,\n\nPlease send tender documents.",
        )

        msg = build_mime_message(draft, from_email="sender@example.com")
        self.assertEqual(msg["From"], "sender@example.com")
        self.assertEqual(msg["To"], "smith@ust.hk")
        self.assertEqual(msg["Subject"], "Request for Tender Documents – TEST-MIME-01")
        self.assertIn("Please send tender documents.", msg.get_content())

    def test_build_mime_message_with_attachment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_pdf = Path(tmpdir) / "sample_br.pdf"
            sample_pdf.write_bytes(b"%PDF-1.4 test attachment content")

            draft = TenderEmailDraft(
                tender_no="TEST-MIME-02",
                description="Testing attachment",
                recipient_name="Ms. Wong",
                recipient_email="wong@ust.hk",
                subject="Request for Tender Documents – TEST-MIME-02",
                body="Here is the BR certificate.",
                attachment_path=str(sample_pdf),
            )

            msg = build_mime_message(draft)
            attachments = list(msg.iter_attachments())
            self.assertEqual(len(attachments), 1)
            att = attachments[0]
            self.assertEqual(att.get_filename(), "sample_br.pdf")
            self.assertEqual(att.get_content_type(), "application/pdf")
            self.assertEqual(att.get_content(), b"%PDF-1.4 test attachment content")

    def test_build_mime_message_missing_attachment_graceful(self):
        draft = TenderEmailDraft(
            tender_no="TEST-MIME-03",
            description="Testing missing attachment",
            recipient_name="Ms. Wong",
            recipient_email="wong@ust.hk",
            subject="Subject",
            body="Body",
            attachment_path="non_existent_file.pdf",
        )
        msg = build_mime_message(draft)
        attachments = list(msg.iter_attachments())
        self.assertEqual(len(attachments), 0)

    @patch("imaplib.IMAP4_SSL")
    def test_imap_session_context_manager(self, mock_imap_cls):
        mock_imap = MagicMock()
        mock_imap_cls.return_value = mock_imap
        mock_imap.select.return_value = ("OK", [b"10"])

        mailer = GoogleAccountMailer(username="user@test.com", app_password="password123")

        with mailer.imap_session(folder="INBOX", readonly=True) as mail:
            self.assertEqual(mail, mock_imap)
            mock_imap.login.assert_called_once_with("user@test.com", "password123")
            mock_imap.select.assert_called_once_with('"INBOX"', readonly=True)

        mock_imap.logout.assert_called_once()

    @patch("imaplib.IMAP4_SSL")
    def test_imap_session_exception_still_logs_out(self, mock_imap_cls):
        mock_imap = MagicMock()
        mock_imap_cls.return_value = mock_imap

        mailer = GoogleAccountMailer(username="user@test.com", app_password="password123")

        with self.assertRaises(RuntimeError):
            with mailer.imap_session() as mail:
                raise RuntimeError("Unexpected failure during IMAP operation")

        mock_imap.logout.assert_called_once()

    @patch("imaplib.IMAP4_SSL")
    def test_save_draft_with_automatic_tagging(self, mock_imap_cls):
        mock_imap = MagicMock()
        mock_imap_cls.return_value = mock_imap

        # Mock list() to return standard drafts folder
        mock_imap.list.return_value = ("OK", [b'(\\Drafts) "/" "[Gmail]/Drafts"'])
        # Mock append() returning RFC 4315 APPENDUID response
        mock_imap.append.return_value = ("OK", [b"[APPENDUID 12345 777] (Success)"])
        mock_imap.uid.return_value = ("OK", [b"OK"])

        mailer = GoogleAccountMailer(username="user@test.com", app_password="password123")

        # Verify draft creation applies base HKUST Tenders tag
        draft = TenderEmailDraft(
            tender_no="TNA2600090",
            description="Automated Laboratory Liquid Handling and Sampling System",
            recipient_name="Officer",
            recipient_email="tender@ust.hk",
            subject="Request for Tender Documents – TNA2600090 - Automated Laboratory Liquid Handling and Sampling System",
            body="Draft body here",
        )

        success, applied_tags = mailer.save_draft(draft, apply_tags=True, tag_prefix="HKUST Tenders")
        self.assertTrue(success)
        self.assertEqual(applied_tags, ["HKUST Tenders"])

        # Verify IMAP append was called
        mock_imap.append.assert_called_once()
        # Verify STORE was called to attach label to uid 777
        calls = [c[0] for c in mock_imap.uid.call_args_list]
        self.assertTrue(any(c[0] == "STORE" and c[1] == "777" for c in calls))


if __name__ == "__main__":
    unittest.main()
