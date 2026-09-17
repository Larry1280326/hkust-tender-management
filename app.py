"""Main CLI application for HKUST Vendor Automation & Gmail Drafting."""

import sys
import json
import webbrowser
from typing import List, Optional

# Ensure standard UTF-8 console output for Windows cmd/PowerShell
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import questionary

import config
from scraper.auth import HKUSTAuthManager
from scraper.tender_parser import TenderParser, TenderNotice
from mailer.template import generate_tender_email, TenderEmailDraft
from mailer.gmail_api import GmailService
from mailer.google_account import GoogleAccountMailer
from mailer.webmail_helper import generate_gmail_compose_url, export_eml_file

console = Console()
CACHE_FILE = config.BASE_DIR / "tenders_cache.json"


def save_tenders_cache(tenders: List[TenderNotice]):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump([t.to_dict() for t in tenders], f, ensure_ascii=False, indent=2)


def load_tenders_cache() -> List[TenderNotice]:
    if not CACHE_FILE.exists():
        return []
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [TenderNotice(**d) for d in data]
    except Exception:
        return []


def display_welcome_banner():
    banner_text = (
        "[bold cyan]HKUST e-Tendering Portal Automation & Gmail Drafter[/bold cyan]\n"
        f"[green]Company:[/green] {config.COMPANY_NAME} | [green]Contact:[/green] {config.CONTACT_PERSON_NAME}\n"
        f"[green]Email:[/green] {config.CONTACT_EMAIL} | [green]Phone:[/green] {config.CONTACT_PHONE}\n"
        f"[dim]Portal URL: {config.HKUST_WELCOME_URL}[/dim]"
    )
    console.print(Panel(banner_text, expand=False, border_style="cyan"))


def display_tender_table(tenders: List[TenderNotice]):
    table = Table(
        title=f"[bold yellow]Available HKUST Tender Notices ({len(tenders)} Total)[/bold yellow]",
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Tender No.", style="bold cyan", width=16)
    table.add_column("Description / Subject", style="white", min_width=30)
    table.add_column("Closing Date", style="green", width=19)
    table.add_column("Contact Person", style="yellow", width=22)
    table.add_column("Contact Email", style="blue", width=24)

    for idx, t in enumerate(tenders, start=1):
        table.add_row(
            str(idx),
            t.tender_no,
            t.description,
            t.closing_date or "N/A",
            t.contact_person or "Sir/Madam",
            t.contact_email or "[red]Missing Email[/red]",
        )

    console.print(table)


def run_scrape_workflow(headless: bool = True) -> List[TenderNotice]:
    """Launch browser, log in to HKUST portal, and extract all tenders & enquiries."""
    auth_mgr = HKUSTAuthManager(headless=headless)

    with sync_playwright() as p:
        console.print("[*] Launching Chromium browser...", style="cyan")
        browser = p.chromium.launch(headless=headless)
        context = auth_mgr.get_context(browser)
        page = context.new_page()

        try:
            # Step 1: Login if credentials configured
            if config.HKUST_VENDOR_ID and config.HKUST_PASSWORD:
                console.print(f"[*] Logging in as Vendor ID: {config.HKUST_VENDOR_ID}...", style="cyan")
                auth_mgr.perform_login(page)
            else:
                console.print("[yellow]No login credentials provided in .env, proceeding to public tender directory...[/yellow]")

            # Step 2: Scrape tenders with progress bar
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
                    progress.update(task, completed=int(curr / total * 100), description=f"[cyan]Parsing: {name}")

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
    """Allow the user to select tenders interactively or via filter."""
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
        console.print("[dim]Tip: Press Space to select/deselect, 'a' to toggle all, Enter to confirm.[/dim]")
        selected = questionary.checkbox(
            "Select tenders to draft emails for:",
            choices=choices,
        ).ask()
        return selected or []

    elif mode.startswith("2"):
        return tenders

    elif mode.startswith("3"):
        kw_input = questionary.text(
            "Enter keywords to match (separated by comma, e.g. IT, software, renovation, imaging):"
        ).ask()
        if not kw_input:
            return []
        keywords = [k.strip().lower() for k in kw_input.split(",") if k.strip()]
        matched = [
            t
            for t in tenders
            if any(k in t.description.lower() or k in t.tender_no.lower() for k in keywords)
        ]
        console.print(f"[+] Found [bold green]{len(matched)}[/bold green] matching tenders.")
        return matched

    return []


def handle_tender_selection_and_drafting(tenders: List[TenderNotice]):
    """Loop between selection, preview, and drafting with full Back navigation."""
    if not tenders:
        return

    current_selected = []
    
    while True:
        preselected_refs = {t.tender_no for t in current_selected} if current_selected else None
        current_selected = select_suitable_tenders(tenders, preselected_refs=preselected_refs)

        if not current_selected:
            console.print("[yellow]No tenders selected.[/yellow]")
            return

        # Prepare drafts
        drafts: List[TenderEmailDraft] = [
            generate_tender_email(
                tender_no=t.tender_no,
                description=t.description,
                recipient_name=t.contact_person,
                recipient_email=t.contact_email,
            )
            for t in current_selected
        ]

        # Preview first draft
        console.print("\n[bold yellow]Draft Preview (Sample):[/bold yellow]")
        sample = drafts[0]
        preview_box = (
            f"[bold]To:[/bold] {sample.recipient_email}\n"
            f"[bold]Subject:[/bold] {sample.subject}\n"
            f"[bold]Attachment:[/bold] {sample.attachment_path or '[yellow]None[/yellow]'}\n\n"
            f"[dim]{sample.body}[/dim]"
        )
        console.print(Panel(preview_box, title=f"Sample Email Preview (1 of {len(drafts)} selected)", border_style="yellow"))

        # Ask action with Back option
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

        # If Yes (Option 1), execute drafting
        draft_emails_for_tenders(drafts)
        break


def draft_emails_for_tenders(drafts: List[TenderEmailDraft]):
    """Execute draft creation in Gmail via App Password, OAuth, or fallback."""

    # 1. First priority: Google Account App Password (IMAP/SMTP - zero Google Cloud setup)
    drafted_successfully = False

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

    # 2. Second priority: Google Cloud OAuth (Gmail API)
    if not drafted_successfully and config.GMAIL_CREDENTIALS_PATH.exists():
        gmail_svc = GmailService()
        try:
            console.print("[*] Connecting to Gmail API...", style="cyan")
            gmail_svc.authenticate()
            for idx, d in enumerate(drafts, 1):
                if not d.recipient_email:
                    console.print(f"[yellow]Skipping {d.tender_no}: No recipient email.[/yellow]")
                    continue
                res = gmail_svc.create_draft(d)
                console.print(
                    f"  [green][OK][/green] Draft created in Gmail for [bold]{d.tender_no}[/bold] (Draft ID: {res.get('id')})"
                )
            drafted_successfully = True
        except Exception as e:
            console.print(f"[!] Note on Gmail API: {e}", style="yellow")

    # 3. Third priority: Offline .EML files + 1-Click Direct Gmail Compose Web Links
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

        console.print("\n[green]Done! You can double-click any .eml file to open it in Outlook/Windows Mail, or click the Gmail link above.[/green]")
    else:
        console.print("\n[bold green]Success! All drafts have been saved directly to your Gmail 'Drafts' folder.[/bold green]")
        console.print("You can review them and click Send!")
        drafts_url = getattr(config, "GMAIL_DRAFTS_URL", "https://mail.google.com/mail/u/2/#drafts")
        console.print(f"[*] Popping up browser to Gmail Drafts: [bold underline cyan]{drafts_url}[/bold underline cyan]")
        try:
            webbrowser.open(drafts_url)
        except Exception as e:
            console.print(f"[!] Could not launch browser automatically: {e}", style="yellow")


def main():
    display_welcome_banner()

    # Direct headless workflow by default (flags supported: --cached, --visible, --test)
    if "--test" in sys.argv:
        if config.GMAIL_APP_PASSWORD:
            console.print(f"[*] Testing Google App Password connection for {config.GMAIL_USER}...", style="cyan")
            mailer = GoogleAccountMailer()
            success, msg = mailer.test_connection()
            if success:
                console.print(f"[bold green][OK] {msg}[/bold green]")
            else:
                console.print(f"[bold red][!] {msg}[/bold red]")
        return

    if "--cached" in sys.argv:
        cached = load_tenders_cache()
        if cached:
            console.print(f"[*] Loaded {len(cached)} cached tenders.", style="cyan")
            display_tender_table(cached)
            handle_tender_selection_and_drafting(cached)
            return
        else:
            console.print("[yellow]No cache found, fetching live...[/yellow]")

    headless = "--visible" not in sys.argv
    console.print(f"[*] Directly fetching all active tenders ({'headless' if headless else 'visible'})...", style="cyan")
    tenders = run_scrape_workflow(headless=headless)
    if tenders:
        display_tender_table(tenders)
        handle_tender_selection_and_drafting(tenders)
    else:
        console.print("[bold red]No active tenders found or failed to fetch.[/bold red]")


if __name__ == "__main__":
    main()
