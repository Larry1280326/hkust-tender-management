"""Google App Password integration using IMAP (for Drafts & Inbox) and SMTP (for Sending).

Requires zero Google Cloud Console setup!
Only needs:
1. Google 2-Step Verification enabled.
2. A 16-character App Password from https://myaccount.google.com/apppasswords
"""

import imaplib
import smtplib
import time
from contextlib import contextmanager
from email import message_from_bytes
import re
from typing import Optional, Tuple, List, Dict, Any, Generator

import config
from mailer.template import TenderEmailDraft
from mailer.mime import build_mime_message
from mailer.email_parser import (
    TenderReceivedEmail,
    decode_mime_words,
    extract_tender_no_from_text,
    extract_body_snippet,
    parse_gmail_labels,
    TEMPLATE_PATTERN,
    HKUST_TN_PATTERN,
    HKUST_CODE_PATTERN,
    TENDER_REF_KEYWORD_PATTERN,
    GENERIC_IGNORE_WORDS,
)

# Re-export for backward compatibility
__all__ = [
    "GoogleAccountMailer",
    "TenderReceivedEmail",
    "decode_mime_words",
    "extract_tender_no_from_text",
    "extract_body_snippet",
    "parse_gmail_labels",
    "TEMPLATE_PATTERN",
    "HKUST_TN_PATTERN",
    "HKUST_CODE_PATTERN",
    "TENDER_REF_KEYWORD_PATTERN",
    "GENERIC_IGNORE_WORDS",
]


class GoogleAccountMailer:
    """Handles Gmail drafts, sending, mailbox reading, and tender tagging via IMAP & SMTP."""

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
            or config.GMAIL_APP_PASSWORD
        ).replace(" ", "")

    def is_configured(self) -> bool:
        """Check if username and app password are present."""
        return bool(self.username and self.app_password)

    @contextmanager
    def imap_session(
        self,
        folder: Optional[str] = None,
        readonly: bool = False,
    ) -> Generator[imaplib.IMAP4_SSL, None, None]:
        """Context manager for IMAP connection, login, optional folder selection, and clean logout."""
        if not self.is_configured():
            raise ValueError(
                "Gmail App Password not configured in .env!\n"
                "Please add GMAIL_APP_PASSWORD to your .env file."
            )

        mail = imaplib.IMAP4_SSL(self.IMAP_HOST, self.IMAP_PORT)
        try:
            mail.login(self.username, self.app_password)
            if folder:
                status, _ = mail.select(f'"{folder}"', readonly=readonly)
                if status != "OK":
                    status, _ = mail.select(folder, readonly=readonly)
                    if status != "OK":
                        raise RuntimeError(f"Could not open mailbox folder: {folder}")
            yield mail
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def _find_drafts_folder(self, mail: imaplib.IMAP4_SSL) -> str:
        """Auto-detect the Gmail Drafts mailbox across all account languages."""
        typ, mailboxes = mail.list()
        if typ == "OK" and mailboxes:
            for mb in mailboxes:
                mb_str = mb.decode("utf-8", errors="ignore")
                if "\\Drafts" in mb_str:
                    parts = mb_str.split(' "/" ')
                    if len(parts) > 1:
                        return parts[-1].strip().strip('"')

        return "[Gmail]/Drafts"

    def save_draft(self, draft_info: TenderEmailDraft) -> bool:
        """Append message directly into Gmail's Drafts folder using IMAP."""
        msg = build_mime_message(draft_info, from_email=self.username)
        raw_bytes = msg.as_bytes()

        with self.imap_session() as mail:
            drafts_folder = self._find_drafts_folder(mail)
            res, data = mail.append(
                drafts_folder,
                "(\\Draft)",
                imaplib.Time2Internaldate(time.time()),
                raw_bytes,
            )
            if res == "OK":
                return True
            raise RuntimeError(f"Failed to append draft to {drafts_folder}: {data}")

    def send_email(self, draft_info: TenderEmailDraft) -> bool:
        """Send email directly using Gmail SMTP."""
        if not self.is_configured():
            raise ValueError("Gmail App Password not configured in .env!")

        msg = build_mime_message(draft_info, from_email=self.username)
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
            with self.imap_session() as mail:
                drafts_folder = self._find_drafts_folder(mail)
                return True, f"Connected successfully! Detected Drafts mailbox: '{drafts_folder}'"
        except Exception as e:
            return False, f"Connection failed: {e}"

    def list_mailboxes(self) -> List[str]:
        """List all available mailbox folder / label names in the Gmail account."""
        with self.imap_session() as mail:
            typ, mailboxes = mail.list()
            names = []
            if typ == "OK" and mailboxes:
                for mb in mailboxes:
                    mb_str = mb.decode("utf-8", errors="ignore")
                    parts = mb_str.split(' "/" ')
                    if len(parts) > 1:
                        names.append(parts[-1].strip().strip('"'))
            return names

    def find_tender_tag_folder(self) -> Optional[str]:
        """Find the HKUST Tenders tag folder if it exists in Gmail."""
        try:
            mailboxes = self.list_mailboxes()
            target = config.HKUST_MAIL_TAG
            for mb in mailboxes:
                if mb.lower() == target.lower():
                    return mb
            for mb in mailboxes:
                if mb.lower() in ("hkust tenders", "hkust-tenders", "hkust_tenders"):
                    return mb
        except Exception:
            pass
        return None

    def read_emails(
        self,
        folder: str = "INBOX",
        search_criteria: str = "ALL",
        limit: int = 40,
        known_tenders: Optional[List[str]] = None,
    ) -> List[TenderReceivedEmail]:
        """Read and parse emails quickly using batch header & label fetching."""
        with self.imap_session(folder=folder, readonly=True) as mail:
            typ, data = mail.uid("SEARCH", None, search_criteria)
            if typ != "OK" or not data or not data[0]:
                return []

            uids = data[0].split()
            if not uids:
                return []

            # Newest emails first
            recent_uids = uids[-limit:]
            recent_uids.reverse()

            uid_batch = b",".join(recent_uids)
            fetch_status, fetch_data = mail.uid(
                "FETCH",
                uid_batch,
                "(X-GM-LABELS BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)])",
            )

            if fetch_status != "OK" or not fetch_data:
                return []

            results: List[TenderReceivedEmail] = []
            for item in fetch_data:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue

                meta_str = (
                    item[0].decode("utf-8", errors="ignore")
                    if isinstance(item[0], bytes)
                    else str(item[0])
                )
                uid_match = re.search(r"UID\s+(\d+)", meta_str)
                uid_str = uid_match.group(1) if uid_match else "unknown"

                labels = parse_gmail_labels(meta_str)
                hdr_msg = message_from_bytes(item[1])

                subject = decode_mime_words(hdr_msg.get("Subject", ""))
                sender = decode_mime_words(hdr_msg.get("From", ""))
                date_str = decode_mime_words(hdr_msg.get("Date", ""))

                tender_no = extract_tender_no_from_text(subject, known_tenders=known_tenders)

                results.append(
                    TenderReceivedEmail(
                        msg_id=uid_str,
                        uid=uid_str,
                        subject=subject,
                        sender=sender,
                        date=date_str,
                        body_snippet=subject,
                        tender_no=tender_no,
                        labels=labels,
                    )
                )

            return results

    def fetch_hkust_tender_emails(
        self,
        folder: Optional[str] = None,
        limit: int = 50,
        known_tenders: Optional[List[str]] = None,
    ) -> List[TenderReceivedEmail]:
        """Fetch emails related to HKUST or tenders."""
        target_folder = folder
        if not target_folder:
            tag_folder = self.find_tender_tag_folder()
            target_folder = tag_folder if tag_folder else "INBOX"

        if target_folder != "INBOX":
            return self.read_emails(
                folder=target_folder,
                search_criteria="ALL",
                limit=limit,
                known_tenders=known_tenders,
            )

        emails: List[TenderReceivedEmail] = []
        try:
            emails = self.read_emails(
                folder="INBOX",
                search_criteria='X-GM-RAW "from:ust.hk OR subject:tender OR tender"',
                limit=limit,
                known_tenders=known_tenders,
            )
        except Exception:
            emails = self.read_emails(
                folder="INBOX",
                search_criteria="ALL",
                limit=limit,
                known_tenders=known_tenders,
            )

        filtered: List[TenderReceivedEmail] = []
        for e in emails:
            is_ust = "ust.hk" in e.sender.lower()
            has_tender = "tender" in e.subject.lower() or bool(e.tender_no)
            if is_ust or has_tender:
                filtered.append(e)

        return filtered

    def add_gmail_label(
        self,
        uid: str,
        label_name: str,
        folder: str = "INBOX",
        client: Optional[imaplib.IMAP4_SSL] = None,
    ) -> bool:
        """Add a Gmail label/tag to a specific email by UID."""
        clean_label = label_name.strip()
        if not clean_label:
            return False

        def _apply_store(mail_client: imaplib.IMAP4_SSL) -> bool:
            try:
                mail_client.create(f'"{clean_label}"')
            except Exception:
                pass
            status, _ = mail_client.select(f'"{folder}"')
            if status != "OK":
                mail_client.select(folder)
            res, _ = mail_client.uid("STORE", uid, "+X-GM-LABELS", f'("{clean_label}")')
            return res == "OK"

        if client:
            return _apply_store(client)

        with self.imap_session() as mail:
            return _apply_store(mail)

    def tag_hkust_tender_emails(
        self,
        emails: Optional[List[TenderReceivedEmail]] = None,
        tag_prefix: Optional[str] = None,
        folder: str = "INBOX",
        per_tender_tag: bool = True,
        known_tenders: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Tag HKUST tender emails in Gmail by checking the email title/subject."""
        prefix = tag_prefix or config.HKUST_MAIL_TAG

        if emails is None:
            emails = self.fetch_hkust_tender_emails(
                folder=folder, known_tenders=known_tenders
            )

        if not emails:
            return []

        tagged_summary: List[Dict[str, Any]] = []

        with self.imap_session(folder=folder) as mail:
            created_labels = set()

            for e in emails:
                tags_to_apply = [prefix]
                if per_tender_tag and e.tender_no:
                    safe_no = e.tender_no.replace("/", "-")
                    tender_tag = f"{prefix}/{safe_no}"
                    tags_to_apply.append(tender_tag)

                applied: List[str] = []
                for tag in tags_to_apply:
                    if tag in e.labels:
                        applied.append(tag)
                        continue

                    if tag not in created_labels:
                        try:
                            mail.create(f'"{tag}"')
                        except Exception:
                            pass
                        created_labels.add(tag)

                    res, _ = mail.uid("STORE", e.uid, "+X-GM-LABELS", f'("{tag}")')
                    if res == "OK":
                        applied.append(tag)
                        if tag not in e.labels:
                            e.labels.append(tag)

                tagged_summary.append({
                    "uid": e.uid,
                    "subject": e.subject,
                    "sender": e.sender,
                    "tender_no": e.tender_no,
                    "applied_tags": applied,
                })

            return tagged_summary
