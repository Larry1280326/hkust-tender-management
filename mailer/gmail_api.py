"""Gmail API integration for drafting emails with attachments."""

import base64
import mimetypes
from pathlib import Path
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from typing import Optional, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from mailer.template import TenderEmailDraft

# OAuth Scopes: gmail.compose allows creating and modifying drafts without full mailbox access
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


class GmailService:
    """Manages Gmail API authentication and draft creation."""

    def __init__(
        self,
        credentials_path: Optional[Path] = None,
        token_path: Optional[Path] = None,
    ):
        self.credentials_path = credentials_path or config.GMAIL_CREDENTIALS_PATH
        self.token_path = token_path or config.GMAIL_TOKEN_PATH
        self.service = None

    def authenticate(self) -> Any:
        """Authenticate with Google OAuth 2.0 and build the Gmail service."""
        creds = None

        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(self.token_path), SCOPES
                )
            except Exception as e:
                print(f"[!] Existing token is invalid ({e}), requesting new login.")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"[!] Token refresh failed: {e}. Re-authenticating...")
                    creds = None

            if not creds:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Google OAuth client credentials file not found at: {self.credentials_path}\n\n"
                        "To use the Gmail API:\n"
                        "1. Go to https://console.cloud.google.com/\n"
                        "2. Create a project and enable the 'Gmail API'\n"
                        "3. Go to 'APIs & Services' > 'Credentials' > 'Create Credentials' > 'OAuth client ID'\n"
                        "4. Select Application Type: 'Desktop app'\n"
                        "5. Download the JSON file and save it as 'credentials.json' in this project folder."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save the credentials for subsequent runs
            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)
        return self.service

    def create_draft(self, draft_info: TenderEmailDraft) -> Dict[str, Any]:
        """Create an email draft in Gmail with recipient, subject, body, and attachment."""
        if not self.service:
            self.authenticate()

        # Build MIME Message
        message = MIMEMultipart()
        message["to"] = draft_info.recipient_email
        message["subject"] = draft_info.subject

        # Email Body
        text_part = MIMEText(draft_info.body, "plain", "utf-8")
        message.attach(text_part)

        # Attachment (BR Certificate)
        if draft_info.attachment_path:
            attach_file = Path(draft_info.attachment_path)
            if attach_file.exists():
                content_type, encoding = mimetypes.guess_type(str(attach_file))
                if content_type is None or encoding is not None:
                    content_type = "application/octet-stream"
                main_type, sub_type = content_type.split("/", 1)

                with open(attach_file, "rb") as f:
                    part = MIMEBase(main_type, sub_type)
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{attach_file.name}"',
                    )
                    message.attach(part)
            else:
                print(f"[!] Warning: Attachment file not found: {attach_file}")

        # Encode raw RFC 2822 message to URL-safe base64 string
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        try:
            created_draft = (
                self.service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw_message}})
                .execute()
            )
            return created_draft
        except HttpError as error:
            print(f"[!] An error occurred while creating Gmail draft: {error}")
            raise
