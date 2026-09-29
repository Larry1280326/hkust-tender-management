"""Gmail API integration for drafting emails with attachments."""

import base64
from pathlib import Path
from typing import Optional, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from mailer.template import TenderEmailDraft
from mailer.mime import build_mime_message

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

        # Build standardized MIME message
        message = build_mime_message(draft_info)

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
