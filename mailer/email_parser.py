"""Email parsing and tender reference extraction utilities."""

import re
from dataclasses import dataclass, field, asdict
from email.header import decode_header
from typing import Optional, List, Dict, Any

TEMPLATE_PATTERN = re.compile(
    r"Request for Tender Documents\s*[–\-]\s*([A-Za-z0-9/_\-\s]+?)\s*[–\-]",
    re.IGNORECASE,
)
HKUST_TN_PATTERN = re.compile(
    r"\b(TN[A-Z0-9]{6,12}(?:\s*PQ)?)\b",
    re.IGNORECASE,
)
HKUST_CODE_PATTERN = re.compile(
    r"\b([A-Z]{2,6}/\d{4}/\d{2,5}(?:[A-Z0-9_-]+)?)\b",
    re.IGNORECASE,
)
TENDER_REF_KEYWORD_PATTERN = re.compile(
    r"\bTender\s*(?:No\.?|Ref\.?|Reference)\s*[:：#]?\s*([A-Za-z0-9/_-]+)",
    re.IGNORECASE,
)
GENERIC_IGNORE_WORDS = {
    "documents", "document", "notice", "invitation", "enquiry", "details",
    "clarification", "submission", "schedule", "requirements", "for", "the",
}


@dataclass
class TenderReceivedEmail:
    """Represents an incoming email message identified or tagged for HKUST tenders."""
    msg_id: str
    uid: str
    subject: str
    sender: str
    date: str
    body_snippet: str
    tender_no: Optional[str] = None
    labels: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def decode_mime_words(header_value: Optional[str]) -> str:
    """Decode MIME encoded email header fields into plain Unicode text."""
    if not header_value:
        return ""
    try:
        decoded_fragments = decode_header(header_value)
        pieces = []
        for piece, charset in decoded_fragments:
            if isinstance(piece, bytes):
                encoding = charset or "utf-8"
                try:
                    pieces.append(piece.decode(encoding, errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    pieces.append(piece.decode("utf-8", errors="replace"))
            else:
                pieces.append(str(piece))
        return "".join(pieces).strip()
    except Exception:
        return str(header_value).strip()


def extract_tender_no_from_text(
    text: str,
    known_tenders: Optional[List[str]] = None,
) -> Optional[str]:
    """Identify and extract HKUST tender reference number from email subject or body."""
    if not text:
        return None

    # 1. Match against known active tender numbers if provided
    if known_tenders:
        text_lower = text.lower()
        for ref in known_tenders:
            if ref and ref.lower() in text_lower:
                return ref

    # 2. Match standard template: "Request for Tender Documents – <Tender No.> - <Description>"
    tmpl_match = TEMPLATE_PATTERN.search(text)
    if tmpl_match:
        found_tmpl = tmpl_match.group(1).strip().rstrip(".,:;")
        if len(found_tmpl) >= 4:
            return found_tmpl

    # 3. Match HKUST TN code format (e.g. TNL2600072, TNK2600074, TNA2600095 PQ)
    tn_match = HKUST_TN_PATTERN.search(text)
    if tn_match:
        found_tn = tn_match.group(1).strip().rstrip(".,:;")
        if len(found_tn) >= 4:
            return found_tn

    # 4. Match standard HKUST tender format with slashes (e.g. PU/2026/001, EO/2026/012)
    code_match = HKUST_CODE_PATTERN.search(text)
    if code_match:
        found_code = code_match.group(1).strip().rstrip(".,:;")
        if len(found_code) >= 4:
            return found_code

    # 5. Match explicit keyword indicators (e.g. Tender No.: CC-2025-001)
    kw_match = TENDER_REF_KEYWORD_PATTERN.search(text)
    if kw_match:
        found_kw = kw_match.group(1).strip().rstrip(".,:;")
        if found_kw.lower() not in GENERIC_IGNORE_WORDS and len(found_kw) >= 3:
            return found_kw

    return None


def extract_body_snippet(msg, max_len: int = 200) -> str:
    """Extract a short readable plain-text preview from email message object."""
    body_text = ""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdispo = str(part.get("Content-Disposition", ""))
                if ctype == "text/plain" and "attachment" not in cdispo:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body_text = payload.decode(charset, errors="replace")
                        except Exception:
                            body_text = payload.decode("utf-8", errors="replace")
                        break
                elif ctype == "text/html" and "attachment" not in cdispo and not body_text:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            html_text = payload.decode(charset, errors="replace")
                        except Exception:
                            html_text = payload.decode("utf-8", errors="replace")
                        body_text = re.sub(r"<[^>]+>", " ", html_text)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    body_text = payload.decode(charset, errors="replace")
                except Exception:
                    body_text = payload.decode("utf-8", errors="replace")
    except Exception:
        pass

    clean = " ".join(body_text.split())
    if len(clean) > max_len:
        return clean[:max_len] + "..."
    return clean


def parse_gmail_labels(raw_metadata: str) -> List[str]:
    """Parse Gmail labels from IMAP FETCH response metadata (X-GM-LABELS)."""
    if not raw_metadata:
        return []
    match = re.search(r"X-GM-LABELS\s*\((.*?)\)", raw_metadata, re.DOTALL | re.IGNORECASE)
    if not match:
        return []
    content = match.group(1).strip()
    if not content:
        return []
    labels = []
    for quoted, unquoted in re.findall(r'"([^"]*)"|(\S+)', content):
        val = (quoted or unquoted).strip()
        if val:
            labels.append(val)
    return labels
