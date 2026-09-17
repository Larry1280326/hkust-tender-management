"""Google App Password integration using IMAP (for Drafts) and SMTP (for Sending).

Requires zero Google Cloud Console setup!
Only needs:
1. Google 2-Step Verification enabled.
2. A 16-character App Password from https://myaccount.google.com/apppasswords
"""

import imaplib
import smtplib
import time
import mimetypes
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from typing import Optional, Tuple

import config
from mailer.template import TenderEmailDraft


class GoogleAccountMailer:
    """Handles creating Gmail drafts via IMAP and sending emails via SMTP using an App Password."""

    IMAP_HOST = "imap.gmail.com"
    IMAP_PORT = 993
    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 587

    def __init__(
        self,
        username: Optional[str] = None,
        app_password: Optional[str] = None,
    ):
        self.username = username or config.CONTACT_EMAIL
        self.app_password = (
            app_password
            or getattr(config, "GMAIL_APP_PASSWORD", None)
            or ""
        ).replace(" ", "")

    def is_configured(self) -> bool:
        return bool(self.username and self.app_password)

    def _build_mime_message(self, draft_info: TenderEmailDraft) -> MIMEMultipart:
        """Construct standard MIME multipart message with attachment."""
        msg = MIMEMultipart()
        msg["From"] = self.username
        msg["To"] = draft_info.recipient_email
        msg["Subject"] = draft_info.subject
        msg["Date"] = imaplib.Time2Internaldate(time.time())

        # Body
        msg.attach(MIMEText(draft_info.body, "plain", "utf-8"))

        # Attachment
        if draft_info.attachment_path:
            attach_file = Path(draft_info.attachment_path)
            if attach_file.exists():
                ctype, encoding = mimetypes.guess_type(str(attach_file))
                if ctype is None or encoding is not None:
                    ctype = "application/octet-stream"
                maintype, subtype = ctype.split("/", 1)

                with open(attach_file, "rb") as fp:
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(fp.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{attach_file.name}"',
                    )
                    msg.attach(part)
            else:
                print(f"[!] Warning: Attachment file not found: {attach_file}")

        return msg

    def _find_drafts_folder(self, mail: imaplib.IMAP4_SSL) -> str:
        """Auto-detect the Gmail Drafts mailbox across all account languages."""
        typ, mailboxes = mail.list()
        if typ == "OK" and mailboxes:
            for mb in mailboxes:
                mb_str = mb.decode("utf-8", errors="ignore")
                if "\\Drafts" in mb_str:
                    # Extract folder name: usually "[Gmail]/Drafts" or similar
                    parts = mb_str.split(' "/" ')
                    if len(parts) > 1:
                        folder_name = parts[-1].strip().strip('"')
                        return folder_name

        # Fallback to standard Gmail folder names
        return "[Gmail]/Drafts"

    def save_draft(self, draft_info: TenderEmailDraft) -> bool:
        """Append message directly into Gmail's Drafts folder using IMAP."""
        if not self.is_configured():
            raise ValueError(
                "Gmail App Password not configured!\n"
                "Please add GMAIL_APP_PASSWORD to your .env file."
            )

        msg = self._build_mime_message(draft_info)
        raw_bytes = msg.as_bytes()

        # Connect to Gmail IMAP with SSL
        mail = imaplib.IMAP4_SSL(self.IMAP_HOST, self.IMAP_PORT)
        try:
            mail.login(self.username, self.app_password)
            drafts_folder = self._find_drafts_folder(mail)

            # Append with \Draft flag so it appears as a draft
            res, data = mail.append(
                drafts_folder,
                "(\\Draft)",
                imaplib.Time2Internaldate(time.time()),
                raw_bytes,
            )

            if res == "OK":
                return True
            else:
                raise RuntimeError(f"Failed to append draft to {drafts_folder}: {data}")
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def send_email(self, draft_info: TenderEmailDraft) -> bool:
        """Send email directly using Gmail SMTP (Optional)."""
        if not self.is_configured():
            raise ValueError(
                "Gmail App Password not configured!\n"
                "Please add GMAIL_APP_PASSWORD to your .env file."
            )

        msg = self._build_mime_message(draft_info)

        with smtplib.SMTP(self.SMTP_HOST, self.SMTP_PORT) as server:
            server.starttls()
            server.login(self.username, self.app_password)
            server.send_message(msg)
        return True

    def test_connection(self) -> Tuple[bool, str]:
        """Verify IMAP login and locate Drafts folder."""
        if not self.is_configured():
            return False, "Missing GMAIL_USER or GMAIL_APP_PASSWORD in .env"

        try:
            mail = imaplib.IMAP4_SSL(self.IMAP_HOST, self.IMAP_PORT)
            mail.login(self.username, self.app_password)
            drafts_folder = self._find_drafts_folder(mail)
            mail.logout()
            return True, f"Connected successfully! Detected Drafts mailbox: '{drafts_folder}'"
        except Exception as e:
            return False, f"Connection failed: {e}"
