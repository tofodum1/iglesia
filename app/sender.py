"""
Sending layer. Reads system-wide credentials from env vars, but a Church
row can override the "from" number/email so each org sends as itself.
"""

import os
import logging

from twilio.rest import Client as TwilioClient
import resend

logger = logging.getLogger("newcomer_reminder.sender")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_DEFAULT_FROM = os.getenv("TWILIO_FROM_NUMBER")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_DEFAULT_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL")  # must be on a domain verified in Resend
RESEND_DEFAULT_FROM_NAME = os.getenv("RESEND_FROM_NAME", "Church Team")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


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
    if not RESEND_API_KEY:
        return False, "Resend API key not configured"
    try:
        sender_email = from_email or RESEND_DEFAULT_FROM_EMAIL
        sender_name = from_name or RESEND_DEFAULT_FROM_NAME
        resend.Emails.send({
            "from": f"{sender_name} <{sender_email}>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        })
        return True, None
    except Exception as e:
        logger.exception("Resend send failed")
        return False, str(e)
