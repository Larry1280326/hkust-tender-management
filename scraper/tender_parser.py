"""Scraper for HKUST Tender Notices and Enquiry contact details."""

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable, Tuple
from playwright.sync_api import Page

import config

EMAIL_REGEX = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", re.IGNORECASE)
CONTACT_PERSON_REGEX = re.compile(r"Contact\s+Person\s*[:：]\s*([^\n\r]+)", re.IGNORECASE)
PHONE_REGEX = re.compile(r"(\+?852[-\s]?)?[2-9]\d{3}[-\s]?\d{4}")
CACHE_FILE = config.BASE_DIR / "tenders_cache.json"


@dataclass
class TenderNotice:
    """Structured data for an active HKUST Tender notice."""
    tender_no: str
    description: str
    closing_date: str
    contact_person: str
    contact_email: str
    contact_phone: Optional[str] = None
    tender_type: Optional[str] = None
    raw_enquiry: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def save_tenders_cache(tenders: List[TenderNotice], cache_path: Optional[Path] = None) -> None:
    """Save parsed tender list to a local JSON cache file."""
    path = cache_path or CACHE_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump([t.to_dict() for t in tenders], f, ensure_ascii=False, indent=2)


def load_tenders_cache(cache_path: Optional[Path] = None) -> List[TenderNotice]:
    """Load tender list from a local JSON cache file."""
    path = cache_path or CACHE_FILE
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [TenderNotice(**d) for d in data]
    except Exception:
        return []


class TenderParser:
    """Parses tender notices and extracts enquiry contact information."""

    TENDER_NOTICE_URL = "https://w5.ab.ust.hk/jstd/td_tender_notice"

    def __init__(self, page: Page):
        self.page = page

    def _parse_enquiry_details(self) -> Tuple[str, str, str]:
        """Extract contact person, email, and raw enquiry text from current detail page."""
        contact_person = "Sir/Madam"
        contact_email = ""
        raw_enquiry = ""

        info_rows = self.page.locator("table tr").all()
        for ir in info_rows:
            th = ir.locator("th, td").first.inner_text().strip()
            if "enquiry" in th.lower():
                enquiry_cell = ir.locator("td").last
                raw_enquiry = enquiry_cell.inner_text().strip()

                cp_match = CONTACT_PERSON_REGEX.search(raw_enquiry)
                if cp_match:
                    contact_person = cp_match.group(1).strip()

                em_match = EMAIL_REGEX.search(raw_enquiry)
                if em_match:
                    contact_email = em_match.group(1).strip()
                break

            elif "request for tender document" in th.lower():
                req_text = ir.locator("td").last.inner_text().strip()
                if not contact_email:
                    em_match = EMAIL_REGEX.search(req_text)
                    if em_match:
                        contact_email = em_match.group(1).strip()
                if contact_person == "Sir/Madam":
                    cp_match = re.search(
                        r"attention of\s+([A-Za-z\s]+?)\s+of",
                        req_text,
                        re.IGNORECASE,
                    )
                    if cp_match:
                        contact_person = cp_match.group(1).strip()

        return contact_person, contact_email, raw_enquiry

    def extract_tenders(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[TenderNotice]:
        """Extract all active tender notices and their enquiry contact info."""
        self.page.goto(self.TENDER_NOTICE_URL, wait_until="networkidle")

        table = self.page.locator("table").first
        rows = table.locator("tbody tr").all()
        total_rows = len(rows)

        tenders: List[TenderNotice] = []

        for idx in range(total_rows):
            # Ensure on directory page; prefer fast go_back
            if self.page.url != self.TENDER_NOTICE_URL:
                try:
                    self.page.go_back(wait_until="networkidle")
                except Exception:
                    pass
                if self.page.url != self.TENDER_NOTICE_URL:
                    self.page.goto(self.TENDER_NOTICE_URL, wait_until="networkidle")

            table = self.page.locator("table").first
            row = table.locator("tbody tr").nth(idx)
            cells = row.locator("td").all()

            if len(cells) < 4:
                continue

            tender_no = cells[0].inner_text().strip()
            tender_type = cells[1].inner_text().strip()
            description = cells[2].inner_text().strip()
            closing_date = cells[3].inner_text().strip()

            if progress_callback:
                progress_callback(idx + 1, total_rows, tender_no)

            contact_person = "Sir/Madam"
            contact_email = ""
            raw_enquiry = ""

            try:
                link = cells[2].locator("a").first
                link.click()
                self.page.wait_for_load_state("networkidle")
                contact_person, contact_email, raw_enquiry = self._parse_enquiry_details()
            except Exception:
                pass

            tenders.append(
                TenderNotice(
                    tender_no=tender_no,
                    description=description,
                    closing_date=closing_date,
                    contact_person=contact_person,
                    contact_email=contact_email,
                    tender_type=tender_type,
                    raw_enquiry=raw_enquiry,
                )
            )

        return tenders
