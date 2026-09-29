"""Unit tests for skipping already-processed tenders in TenderParser and CLI selection."""

import unittest
from unittest.mock import MagicMock, patch

from scraper.tender_parser import TenderParser, TenderNotice
from mailer.email_parser import normalize_tender_ref


class TestTenderParserSkip(unittest.TestCase):

    def test_extract_tenders_skips_existing(self):
        """Verify that extract_tenders detects existing tenders and skips detail navigation."""
        mock_page = MagicMock()
        mock_page.url = TenderParser.TENDER_NOTICE_URL

        # Create mock table with 2 rows: one already in Gmail, one new
        mock_table = MagicMock()
        mock_page.locator.return_value.first = mock_table

        # Cells for Row 0: TNP2600099 (Already in Gmail)
        mock_cell_0_0 = MagicMock()
        mock_cell_0_0.inner_text.return_value = "TNP2600099"
        mock_cell_0_1 = MagicMock()
        mock_cell_0_1.inner_text.return_value = "Works"
        mock_cell_0_2 = MagicMock()
        mock_cell_0_2.inner_text.return_value = "Fitting Out Works for Office"
        mock_cell_0_3 = MagicMock()
        mock_cell_0_3.inner_text.return_value = "2026-10-15"

        mock_row_0 = MagicMock()
        mock_row_0.locator.return_value.all.return_value = [
            mock_cell_0_0, mock_cell_0_1, mock_cell_0_2, mock_cell_0_3
        ]

        # Cells for Row 1: TNK2600096 (New tender)
        mock_cell_1_0 = MagicMock()
        mock_cell_1_0.inner_text.return_value = "TNK2600096"
        mock_cell_1_1 = MagicMock()
        mock_cell_1_1.inner_text.return_value = "Services"
        mock_cell_1_2 = MagicMock()
        mock_cell_1_2.inner_text.return_value = "IBM Maximo Application Suite"
        mock_cell_1_3 = MagicMock()
        mock_cell_1_3.inner_text.return_value = "2026-10-20"

        # Detail link on row 1 should be clicked
        mock_link_1 = MagicMock()
        mock_cell_1_2.locator.return_value.first = mock_link_1

        mock_row_1 = MagicMock()
        mock_row_1.locator.return_value.all.return_value = [
            mock_cell_1_0, mock_cell_1_1, mock_cell_1_2, mock_cell_1_3
        ]

        # Table rows
        mock_table.locator.return_value.all.return_value = [mock_row_0, mock_row_1]
        mock_table.locator.return_value.nth.side_effect = lambda idx: [mock_row_0, mock_row_1][idx]

        # Parser
        parser = TenderParser(mock_page)
        parser._parse_enquiry_details = MagicMock(return_value=("Mimi WONG", "pumimi@ust.hk", "Raw info"))

        progress_calls = []

        def mock_progress(curr, total, name):
            progress_calls.append(name)

        existing_in_gmail = {"TNP2600099"}
        tenders = parser.extract_tenders(
            progress_callback=mock_progress,
            existing_tenders=existing_in_gmail,
        )

        # Only new tenders should be returned (already drafted ones are skipped entirely)
        self.assertEqual(len(tenders), 1)

        # Row 0 (TNP2600099) was skipped, so its detail link was NOT clicked
        mock_cell_0_2.locator.assert_not_called()

        # Returned tender should be the new tender (TNK2600096)
        self.assertEqual(tenders[0].tender_no, "TNK2600096")
        self.assertFalse(tenders[0].already_processed)
        self.assertEqual(tenders[0].contact_person, "Mimi WONG")
        self.assertEqual(tenders[0].contact_email, "pumimi@ust.hk")
        mock_link_1.click.assert_called_once()

        # Progress callback should record the skip
        self.assertTrue(any("Already in Gmail" in msg for msg in progress_calls))

    def test_normalize_tender_ref_consistency(self):
        """Ensure normalization handles variations with slashes, hyphens, and whitespace."""
        self.assertEqual(
            normalize_tender_ref("TNP2600099"),
            normalize_tender_ref(" tnp-2600099 "),
        )
        self.assertEqual(
            normalize_tender_ref("PU/2026/001"),
            normalize_tender_ref("pu-2026-001"),
        )


if __name__ == "__main__":
    unittest.main()
