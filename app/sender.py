"""
Sending layer. Reads system-wide credentials from env vars, but a Church
row can override the "from" number/email so each org sends as itself.
"""

import os
import logging

from twilio.rest import Client as TwilioClient
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logger = logging.getLogger("newcomer_reminder.sender")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_DEFAULT_FROM = os.getenv("TWILIO_FROM_NUMBER")

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_DEFAULT_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")
SENDGRID_DEFAULT_FROM_NAME = os.getenv("SENDGRID_FROM_NAME", "Church Team")


def send_sms(to_number: str, body: str, from_number: str | None = None) -> tuple[bool, str | None]:
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return False, "Twilio credentials not configured"
    try:
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            to=to_number,
            from_=from_number or TWILIO_DEFAULT_FROM,
            body=body,
        )
        return True, None
    except Exception as e:
        logger.exception("Twilio send failed")
        return False, str(e)


def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str | None = None,
    from_name: str | None = None,
) -> tuple[bool, str | None]:
    if not SENDGRID_API_KEY:
        return False, "SendGrid API key not configured"
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        message = Mail(
            from_email=(from_email or SENDGRID_DEFAULT_FROM_EMAIL, from_name or SENDGRID_DEFAULT_FROM_NAME),
            to_emails=to_email,
            subject=subject,
            plain_text_content=body,
        )
        sg.send(message)
        return True, None
    except Exception as e:
        logger.exception("SendGrid send failed")
        return False, str(e)
