"""Webmail and local EML file generation helper."""

import urllib.parse
from pathlib import Path
from mailer.template import TenderEmailDraft
from mailer.mime import build_mime_message


def generate_gmail_compose_url(draft_info: TenderEmailDraft) -> str:
    """Generate a direct Gmail web compose URL with pre-filled To, Subject, and Body."""
    base_url = "https://mail.google.com/mail/u/0/"
    params = {
        "view": "cm",
        "fs": "1",
        "to": draft_info.recipient_email,
        "su": draft_info.subject,
        "body": draft_info.body,
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def export_eml_file(draft_info: TenderEmailDraft, output_dir: Path) -> Path:
    """Export the draft as a standard .eml file that opens directly in desktop email clients."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_tender = "".join(
        c for c in draft_info.tender_no if c.isalnum() or c in ("-", "_")
    )
    file_path = output_dir / f"draft_{safe_tender}.eml"

    msg = build_mime_message(draft_info)

    with open(file_path, "wb") as f:
        f.write(msg.as_bytes())

    return file_path
