"""
Daily reminder job.

Run once a day (e.g. via APScheduler in main.py, or an external cron hitting
/internal/run-daily-job). For each active contact, it figures out whether a
reminder for one of their church's services is due tomorrow, and if so sends
the right template for their current phase.

Design choice: reminders go out the day BEFORE the service, so people have
time to plan. Change REMINDER_LEAD_DAYS if you want same-day instead.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import messages
from app.models import Contact, Service, Church, ContactStatus, Phase, ServiceType, MessageLog
from app.sender import send_sms, send_email

logger = logging.getLogger("newcomer_reminder.scheduler")

REMINDER_LEAD_DAYS = 1  # send reminder this many days before the service


def _service_falls_tomorrow(service: Service, today: datetime) -> bool:
    target_date = today + timedelta(days=REMINDER_LEAD_DAYS)
    return target_date.weekday() == service.day_of_week


def _log(db: Session, contact: Contact, channel: str, template_name: str, body: str, success: bool, error: str | None):
    db.add(MessageLog(
        contact_id=contact.id,
        channel=channel,
        template_used=template_name,
        body=body,
        success=success,
        error=error,
    ))


def _deliver(db: Session, contact: Contact, church: Church, body: str, template_name: str):
    if contact.contact_preference.value == "sms" and contact.phone:
        ok, err = send_sms(contact.phone, body, from_number=church.twilio_from_number)
        _log(db, contact, "sms", template_name, body, ok, err)
    elif contact.contact_preference.value == "email" and contact.email:
        ok, err = send_email(
            contact.email,
            subject=f"{church.name} — Service Reminder",
            body=body,
            from_email=church.sendgrid_from_email,
            from_name=church.sendgrid_from_name or church.name,
        )
        _log(db, contact, "email", template_name, body, ok, err)
    else:
        logger.warning(f"Contact {contact.id} has no usable {contact.contact_preference} destination")
        return

    contact.last_reminder_sent_at = datetime.utcnow()


def _render_for(contact: Contact, church: Church, service: Service, template: str) -> str:
    return messages.render(
        template,
        first_name=contact.first_name,
        church_name=church.name,
        service_name=service.name,
        service_day=service.day_of_week_label if hasattr(service, "day_of_week_label") else _weekday_name(service.day_of_week),
        service_time=service.time_of_day,
        church_signoff=church.signoff,
    )


def _weekday_name(day_of_week: int) -> str:
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return names[day_of_week]


def run_daily_job(db: Session, now: datetime | None = None):
    """
    Main entry point. Call this once a day per church (or once globally -
    it iterates every active church anyway).
    """
    now = now or datetime.utcnow()
    churches = db.query(Church).filter(Church.active == True).all()  # noqa: E712

    for church in churches:
        services = [s for s in church.services if s.enabled]
        sunday_services = [s for s in services if s.type == ServiceType.sunday]
        midweek_services = [s for s in services if s.type == ServiceType.midweek]

        contacts = db.query(Contact).filter(
            Contact.church_id == church.id,
            Contact.status == ContactStatus.active,
        ).all()

        for contact in contacts:
            _process_contact(db, church, contact, sunday_services, midweek_services, now)

    db.commit()


def _process_contact(db, church, contact: Contact, sunday_services, midweek_services, now):
    # Midweek reminders can go out regardless of phase, as long as the contact wants them
    if contact.wants_midweek:
        for service in midweek_services:
            if _service_falls_tomorrow(service, now):
                body = _render_for(contact, church, service, messages.MIDWEEK_REMINDER)
                _deliver(db, contact, church, body, "midweek_reminder")

    if contact.phase == Phase.phase_1:
        for service in sunday_services:
            if _service_falls_tomorrow(service, now) and contact.sundays_sent < 3:
                template = messages.PHASE1_SEQUENCE[contact.sundays_sent]
                body = _render_for(contact, church, service, template)
                _deliver(db, contact, church, body, f"phase1_reminder_{contact.sundays_sent + 1}")
                contact.sundays_sent += 1

                if contact.sundays_sent == 3:
                    # Immediately queue the phase 2 opt-in ask (sent same day as 3rd reminder's follow-up window closes).
                    # In practice you may want to delay this a few days after their 3rd Sunday - see NOTE below.
                    ask_body = messages.render(
                        messages.PHASE2_OPT_IN_ASK,
                        first_name=contact.first_name,
                        church_name=church.name,
                        church_signoff=church.signoff,
                    )
                    _deliver(db, contact, church, ask_body, "phase2_opt_in_ask")
                    contact.phase = Phase.ended  # waiting on their reply to flip to phase_2

    elif contact.phase == Phase.phase_2:
        for service in sunday_services:
            if _service_falls_tomorrow(service, now):
                template = messages.next_phase2_variant()
                body = _render_for(contact, church, service, template)
                _deliver(db, contact, church, body, "phase2_ongoing")

# NOTE: the opt-in ask currently fires the same day as reminder #3 is sent.
# If you'd rather wait a few days after their 3rd Sunday actually happens
# (so it reads as "how was it" rather than "one more thing"), track a
# `phase1_completed_date` on the contact and add a separate check here.
