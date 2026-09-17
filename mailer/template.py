"""Email template rendering module."""

from dataclasses import dataclass
from typing import Optional
import config


@dataclass
class TenderEmailDraft:
    tender_no: str
    description: str
    recipient_name: str
    recipient_email: str
    subject: str
    body: str
    attachment_path: Optional[str] = None


def generate_tender_email(
    tender_no: str,
    description: str,
    recipient_name: str,
    recipient_email: str,
    attachment_path: Optional[str] = None,
) -> TenderEmailDraft:
    """Format the tender enquiry request email according to HKUST vendor template."""

    cleaned_recipient_name = recipient_name.strip() if recipient_name else "Sir/Madam"
    cleaned_tender_no = tender_no.strip()
    cleaned_description = description.strip()

    subject = config.EMAIL_SUBJECT_TEMPLATE.format(
        tender_no=cleaned_tender_no,
        description=cleaned_description,
    )

    body = config.EMAIL_BODY_TEMPLATE.format(
        recipient_name=cleaned_recipient_name,
        tender_no=cleaned_tender_no,
        description=cleaned_description,
        company_name=config.COMPANY_NAME,
        contact_person=config.CONTACT_PERSON_NAME,
        contact_email=config.CONTACT_EMAIL,
        contact_phone=config.CONTACT_PHONE,
        company_address=config.COMPANY_ADDRESS,
        sign_off=config.SIGN_OFF,
    )

    attach_path = attachment_path or (
        str(config.BR_CERTIFICATE_PATH)
        if config.BR_CERTIFICATE_PATH.exists()
        else None
    )

    return TenderEmailDraft(
        tender_no=cleaned_tender_no,
        description=cleaned_description,
        recipient_name=cleaned_recipient_name,
        recipient_email=recipient_email.strip(),
        subject=subject,
        body=body,
        attachment_path=attach_path,
    )
