"""Main CLI application for HKUST Vendor Automation & Gmail Drafting."""

import argparse
import sys
import webbrowser
from typing import List, Optional

# Ensure standard UTF-8 console output for Windows cmd/PowerShell
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import questionary

import config
from scraper.auth import HKUSTAuthManager
from scraper.tender_parser import (
    TenderParser,
    TenderNotice,
    load_tenders_cache,
    save_tenders_cache,
)
from mailer.template import generate_tender_email, TenderEmailDraft
from mailer.gmail_api import GmailService
from mailer.google_account import GoogleAccountMailer, TenderReceivedEmail
from mailer.webmail_helper import generate_gmail_compose_url, export_eml_file
from cli_views import (
    console,
    display_welcome_banner,
    display_tender_table,
    display_received_emails_table,
    display_draft_preview,
    display_email_detail,
)


def run_scrape_workflow(headless: bool = True) -> List[TenderNotice]:
    """Launch browser, log in to HKUST portal, and extract active tenders."""
    auth_mgr = HKUSTAuthManager(headless=headless)

    with sync_playwright() as p:
        console.print("[*] Launching Chromium browser...", style="cyan")
        browser = p.chromium.launch(headless=headless)
        context = auth_mgr.get_context(browser)
        page = context.new_page()

        try:
            if config.HKUST_VENDOR_ID and config.HKUST_PASSWORD:
                console.print(f"[*] Logging in as Vendor ID: {config.HKUST_VENDOR_ID}...", style="cyan")
                auth_mgr.perform_login(page)
            else:
                console.print("[yellow]No login credentials in .env, accessing public directory...[/yellow]")

            parser = TenderParser(page)
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console,
            ) as progress:
                task = progress.add_task("[cyan]Scraping tenders...", total=100)

                def update_progress(curr, total, name):
                    pct = int(curr / total * 100) if total else 0
                    progress.update(task, completed=pct, description=f"[cyan]Parsing: {name}")

                tenders = parser.extract_tenders(progress_callback=update_progress)

            if tenders:
                save_tenders_cache(tenders)
                console.print(f"[bold green][OK] Saved {len(tenders)} tenders to cache.[/bold green]")

            return tenders
        except Exception as e:
            console.print(f"[bold red]Scraper Error:[/bold red] {e}")
            return []
        finally:
            browser.close()


def select_suitable_tenders(
    tenders: List[TenderNotice],
    preselected_refs: Optional[set] = None,
) -> List[TenderNotice]:
    """Interactive checklist or keyword filtering for tender selection."""
    if not tenders:
        return []

    mode = questionary.select(
        "How would you like to select suitable tenders?",
        choices=[
            "1. Interactive Checklist (pick individual tenders)",
            "2. Select All tenders",
            "3. Keyword Filter (match keywords in title/description)",
            "4. Cancel / Exit",
        ],
    ).ask()

    if not mode or mode.startswith("4"):
        return []

    if mode.startswith("1"):
        choices = [
            questionary.Choice(
                title=f"{t.tender_no} - {t.description[:55]}... ({t.contact_person} <{t.contact_email}>)",
                value=t,
                checked=(t.tender_no in preselected_refs) if preselected_refs else False,
            )
            for t in tenders
        ]
        console.print("[dim]Tip: Space to toggle, 'a' to select all, Enter to confirm.[/dim]")
        selected = questionary.checkbox("Select tenders to draft emails for:", choices=choices).ask()
        return selected or []

    if mode.startswith("2"):
        return tenders

    if mode.startswith("3"):
        kw_input = questionary.text(
            "Enter keywords to match (comma separated, e.g. IT, software, renovation):"
        ).ask()
        if not kw_input:
            return []
        keywords = [k.strip().lower() for k in kw_input.split(",") if k.strip()]
        matched = [
            t for t in tenders
            if any(k in t.description.lower() or k in t.tender_no.lower() for k in keywords)
        ]
        console.print(f"[+] Found [bold green]{len(matched)}[/bold green] matching tenders.")
        return matched

    return []


def handle_tender_selection_and_drafting(tenders: List[TenderNotice]) -> None:
    """Loop between selection, preview, and drafting with back-navigation."""
    if not tenders:
        return

    current_selected = []
    while True:
        preselected_refs = {t.tender_no for t in current_selected} if current_selected else None
        current_selected = select_suitable_tenders(tenders, preselected_refs=preselected_refs)

        if not current_selected:
            console.print("[yellow]No tenders selected.[/yellow]")
            return

        drafts: List[TenderEmailDraft] = [
            generate_tender_email(
                tender_no=t.tender_no,
                description=t.description,
                recipient_name=t.contact_person,
                recipient_email=t.contact_email,
            )
            for t in current_selected
        ]

        # Display preview card of sample draft
        console.print("\n[bold yellow]Draft Preview (Sample):[/bold yellow]")
        display_draft_preview(drafts[0], count=len(drafts))

        action = questionary.select(
            f"Ready to create drafts for {len(drafts)} selected tenders?",
            choices=[
                f"1. Yes, Create {len(drafts)} Drafts in Gmail",
                "2. Back to Selection (Modify which tenders are selected)",
                "3. Cancel / Exit",
            ],
        ).ask()

        if not action or action.startswith("3"):
            console.print("[yellow]Cancelled draft creation.[/yellow]")
            return

        if action.startswith("2"):
            console.print("[cyan]Returning to tender selection...[/cyan]")
            continue

        draft_emails_for_tenders(drafts)
        break


def draft_emails_for_tenders(drafts: List[TenderEmailDraft]) -> None:
    """Execute draft creation via App Password (IMAP), OAuth (Gmail API), or EML fallback."""
    drafted_successfully = False

    # Priority 1: Google Account App Password (IMAP)
    if config.GMAIL_APP_PASSWORD:
        console.print("[*] Connecting to Gmail via App Password (IMAP)...", style="cyan")
        account_mailer = GoogleAccountMailer()
        try:
            for d in drafts:
                if not d.recipient_email:
                    console.print(f"[yellow]Skipping {d.tender_no}: No recipient email.[/yellow]")
                    continue
                account_mailer.save_draft(d)
                console.print(
                    f"  [green][OK][/green] Saved to Gmail 'Drafts' for [bold]{d.tender_no}[/bold] (To: {d.recipient_email})"
                )
            drafted_successfully = True
        except Exception as e:
            console.print(f"[!] Note on App Password drafting: {e}", style="yellow")

    # Priority 2: Google Cloud OAuth (Gmail API)
    if not drafted_successfully and config.GMAIL_CREDENTIALS_PATH.exists():
        gmail_svc = GmailService()
        try:
            console.print("[*] Connecting to Gmail API...", style="cyan")
            gmail_svc.authenticate()
            for d in drafts:
                if not d.recipient_email:
                    console.print(f"[yellow]Skipping {d.tender_no}: No recipient email.[/yellow]")
                    continue
                res = gmail_svc.create_draft(d)
                console.print(
                    f"  [green][OK][/green] Draft created for [bold]{d.tender_no}[/bold] (ID: {res.get('id')})"
                )
            drafted_successfully = True
        except Exception as e:
            console.print(f"[!] Note on Gmail API: {e}", style="yellow")

    # Priority 3: Offline .EML files + 1-Click Direct Gmail Compose Web Links
    if not drafted_successfully:
        console.print("[*] Generating fallback offline .EML files and direct Gmail web links...", style="cyan")
        output_dir = config.BASE_DIR / "output_drafts"
        output_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[*] Exporting .eml files to: [bold]{output_dir}[/bold]")

        for d in drafts:
            if not d.recipient_email:
                continue
            eml_path = export_eml_file(d, output_dir)
            web_link = generate_gmail_compose_url(d)
            console.print(f"\n[bold cyan]Tender {d.tender_no}:[/bold cyan]")
            console.print(f"  * EML file: {eml_path.name}")
            console.print(f"  * Direct Gmail Compose URL:\n    {web_link}")

        console.print("\n[green]Done! EML files exported to output_drafts directory.[/green]")
    else:
        console.print("\n[bold green]Success! All drafts saved directly to your Gmail 'Drafts' folder.[/bold green]")
        drafts_url = config.GMAIL_DRAFTS_URL
        console.print(f"[*] Opening Gmail Drafts: [bold underline cyan]{drafts_url}[/bold underline cyan]")
        try:
            webbrowser.open(drafts_url)
        except Exception as e:
            console.print(f"[!] Could not launch browser: {e}", style="yellow")


def handle_read_and_tag_mailbox(auto_tag: bool = False, limit: int = 50) -> None:
    """Fetch emails from mailbox, display summary table, and apply tags in Gmail."""
    if not config.GMAIL_APP_PASSWORD:
        console.print(
            "[bold red][!] GMAIL_APP_PASSWORD is not configured in .env![/bold red]\n"
            "Please generate an App Password at https://myaccount.google.com/apppasswords"
        )
        return

    mailer = GoogleAccountMailer()
    known_tenders = [t.tender_no for t in load_tenders_cache()]
    target_folder = mailer.find_tender_tag_folder() or "INBOX"

    console.print(
        f"[*] Connecting to IMAP for [cyan]{mailer.username}[/cyan] (Scanning: [bold yellow]{target_folder}[/bold yellow])...",
        style="cyan",
    )
    try:
        with console.status(f"[cyan]Scanning {target_folder}...", spinner="dots"):
            emails = mailer.fetch_hkust_tender_emails(
                folder=target_folder, limit=limit, known_tenders=known_tenders
            )
    except Exception as e:
        console.print(f"[bold red]Failed to read mailbox:[/bold red] {e}")
        return

    if not emails:
        console.print(f"[yellow]No emails found in folder '{target_folder}'.[/yellow]")
        return

    display_received_emails_table(emails)

    tag_prefix = config.HKUST_MAIL_TAG

    if auto_tag:
        console.print(f"\n[*] Automatically tagging HKUST tender emails under '[bold]{tag_prefix}[/bold]'...", style="cyan")
        summary = mailer.tag_hkust_tender_emails(
            emails=emails,
            tag_prefix=tag_prefix,
            folder=target_folder,
            per_tender_tag=True,
            known_tenders=known_tenders,
        )
        console.print(f"[bold green][OK] Processed {len(summary)} emails in Gmail successfully![/bold green]")
        for item in summary:
            console.print(
                f"  * [bold]{item['tender_no'] or 'General HKUST'}[/bold]: Applied tags {item['applied_tags']} "
                f"to '{item['subject'][:45]}...'"
            )
        return

    # Interactive action loop
    while True:
        action = questionary.select(
            "What would you like to do with these emails?",
            choices=[
                "1. Apply Gmail tags to detected tenders (e.g. 'HKUST Tenders/<tender_no>')",
                "2. View snippet / details of an email",
                f"3. Switch folder (currently: '{target_folder}')",
                "4. Back to Main Menu / Exit",
            ],
        ).ask()

        if not action or action.startswith("4"):
            break

        if action.startswith("1"):
            console.print(f"\n[*] Applying Gmail tags under '[bold]{tag_prefix}[/bold]'...", style="cyan")
            with console.status("[cyan]Applying Gmail labels via IMAP...", spinner="dots"):
                summary = mailer.tag_hkust_tender_emails(
                    emails=emails,
                    tag_prefix=tag_prefix,
                    folder=target_folder,
                    per_tender_tag=True,
                    known_tenders=known_tenders,
                )
            console.print(f"[bold green][OK] Successfully tagged {len(summary)} emails in Gmail![/bold green]")
            for item in summary:
                console.print(
                    f"  * [bold]{item['tender_no'] or 'General HKUST'}[/bold]: {item['applied_tags']} "
                    f"-> '{item['subject'][:40]}...'"
                )
            break

        if action.startswith("2"):
            choices = [
                questionary.Choice(
                    title=f"#{idx} [{em.tender_no or 'No Ref'}] {em.subject[:50]}... (From: {em.sender[:20]})",
                    value=em,
                )
                for idx, em in enumerate(emails, 1)
            ]
            selected_em = questionary.select("Select email to view:", choices=choices).ask()
            if selected_em:
                display_email_detail(selected_em)

        elif action.startswith("3"):
            new_folder = questionary.select(
                "Select folder to scan:",
                choices=[
                    "HKUST Tenders (Tag Folder - Ultra Fast)",
                    "INBOX (General Inbox)",
                ],
            ).ask()
            if new_folder:
                target_folder = "HKUST Tenders" if "HKUST" in new_folder else "INBOX"
                with console.status(f"[cyan]Scanning {target_folder}...", spinner="dots"):
                    emails = mailer.fetch_hkust_tender_emails(
                        folder=target_folder, limit=limit, known_tenders=known_tenders
                    )
                display_received_emails_table(emails)


def interactive_menu():
    """Display main CLI menu and route user choices."""
    choice = questionary.select(
        "HKUST Workflow - Select an option:",
        choices=[
            "1. Scrape HKUST Tenders & Draft Emails",
            "2. Read Mailbox & Track HKUST Replies / Apply Tags",
            "3. Use Cached Tenders (Offline Draft Mode)",
            "4. Test Google Account Connection",
            "5. Exit",
        ],
    ).ask()

    if not choice or choice.startswith("5"):
        console.print("[yellow]Exiting.[/yellow]")
        return

    if choice.startswith("1"):
        console.print("[*] Directly fetching all active tenders (headless)...", style="cyan")
        tenders = run_scrape_workflow(headless=True)
        if tenders:
            display_tender_table(tenders)
            handle_tender_selection_and_drafting(tenders)
        else:
            console.print("[bold red]No active tenders found or failed to fetch.[/bold red]")

    elif choice.startswith("2"):
        handle_read_and_tag_mailbox(auto_tag=False)

    elif choice.startswith("3"):
        cached = load_tenders_cache()
        if cached:
            console.print(f"[*] Loaded {len(cached)} cached tenders.", style="cyan")
            display_tender_table(cached)
            handle_tender_selection_and_drafting(cached)
        else:
            console.print("[yellow]No cached tenders found. Run live scrape first.[/yellow]")

    elif choice.startswith("4"):
        console.print(f"[*] Testing Google App Password connection for {config.GMAIL_USER}...", style="cyan")
        mailer = GoogleAccountMailer()
        success, msg = mailer.test_connection()
        if success:
            console.print(f"[bold green][OK] {msg}[/bold green]")
        else:
            console.print(f"[bold red][!] {msg}[/bold red]")


def parse_cli_args():
    """Configure and parse command-line flags."""
    parser = argparse.ArgumentParser(
        description="HKUST e-Tendering Portal Automation & Gmail Drafter",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--test", action="store_true", help="Test Google IMAP / App Password connection")
    parser.add_argument("--read-mail", action="store_true", help="Read mailbox and inspect HKUST tender emails")
    parser.add_argument("--tag-tenders", action="store_true", help="Scan mailbox and automatically tag tender emails")
    parser.add_argument("--cached", action="store_true", help="Load cached tenders in offline draft mode")
    parser.add_argument("--visible", action="store_true", help="Run scraper with visible Chromium browser")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of emails to scan")
    return parser.parse_args()


def main():
    display_welcome_banner()
    args = parse_cli_args()

    if args.test:
        if config.GMAIL_APP_PASSWORD:
            console.print(f"[*] Testing Google App Password connection for {config.GMAIL_USER}...", style="cyan")
            mailer = GoogleAccountMailer()
            success, msg = mailer.test_connection()
            status_style = "bold green" if success else "bold red"
            prefix = "[OK]" if success else "[!]"
            console.print(f"[{status_style}]{prefix} {msg}[/{status_style}]")
        return

    if args.read_mail:
        handle_read_and_tag_mailbox(auto_tag=False, limit=args.limit)
        return

    if args.tag_tenders:
        handle_read_and_tag_mailbox(auto_tag=True, limit=args.limit)
        return

    if args.cached:
        cached = load_tenders_cache()
        if cached:
            console.print(f"[*] Loaded {len(cached)} cached tenders.", style="cyan")
            display_tender_table(cached)
            handle_tender_selection_and_drafting(cached)
        else:
            console.print("[yellow]No cache found, fetching live...[/yellow]")
        return

    if args.visible:
        console.print("[*] Directly fetching all active tenders (visible browser)...", style="cyan")
        tenders = run_scrape_workflow(headless=False)
        if tenders:
            display_tender_table(tenders)
            handle_tender_selection_and_drafting(tenders)
        return

    interactive_menu()


if __name__ == "__main__":
    main()
