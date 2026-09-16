"""
Database models for the Newcomer Reminder System.

Multi-tenant by design: every Church has its own services + signoff,
and every Contact belongs to exactly one church. Onboarding a new
church means creating one Church row + its Service rows - nothing
else in the codebase changes.
"""

import enum
import uuid
from datetime import datetime, date

from sqlalchemy import (
    Column, String, Boolean, Integer, DateTime, Date, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def gen_id():
    return str(uuid.uuid4())


class ContactPreference(str, enum.Enum):
    sms = "sms"
    email = "email"


class Phase(str, enum.Enum):
    phase_1 = "phase_1"       # first 3 Sundays welcome sequence
    phase_2 = "phase_2"       # ongoing, opted-in
    ended = "ended"           # sequence finished, no phase 2 opt-in (yet)


class ContactStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    opted_out = "opted_out"


class ServiceType(str, enum.Enum):
    sunday = "sunday"
    midweek = "midweek"


class Church(Base):
    __tablename__ = "churches"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    timezone = Column(String, nullable=False, default="America/New_York")
    leader_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    signoff = Column(String, nullable=False)  # e.g. "Winners Chapel Family"

    # Twilio / Resend credentials, per-church so each org can use its own
    # sending numbers/identities. Falls back to system-wide env vars if blank.
    twilio_from_number = Column(String, nullable=True)
    email_from_address = Column(String, nullable=True)
    email_from_name = Column(String, nullable=True)

    # Branding for the signup/intake forms. All optional - falls back to the
    # default berry/gold look if a church doesn't set its own.
    primary_color = Column(String, nullable=True)    # e.g. "#6E1F35" - main accent (buttons, headings)
    primary_deep_color = Column(String, nullable=True)  # darker shade of primary, for hover/emphasis
    accent_color = Column(String, nullable=True)     # e.g. "#C79A3E" - secondary accent (focus rings, badges)
    background_color = Column(String, nullable=True)  # e.g. "#FAF6EF" - page background
    badge_url = Column(String, nullable=True)        # URL to the church's logo image; falls back to a plain circle

    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    services = relationship("Service", back_populates="church", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="church", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(String, primary_key=True, default=gen_id)
    church_id = Column(String, ForeignKey("churches.id"), nullable=False)
    name = Column(String, nullable=False)              # "Sunday Worship Service"
    type = Column(Enum(ServiceType), nullable=False)
    day_of_week = Column(Integer, nullable=False)       # 0=Monday ... 6=Sunday (Python convention)
    time_of_day = Column(String, nullable=False)        # "10:00" 24hr HH:MM in church's local tz
    enabled = Column(Boolean, default=True)

    church = relationship("Church", back_populates="services")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String, primary_key=True, default=gen_id)
    church_id = Column(String, ForeignKey("churches.id"), nullable=False)

    first_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    contact_preference = Column(Enum(ContactPreference), nullable=False)

    service_visited_id = Column(String, ForeignKey("services.id"), nullable=True)
    first_visit_date = Column(Date, default=date.today)

    wants_midweek = Column(Boolean, default=False)

    consent_given = Column(Boolean, default=False)
    consent_timestamp = Column(DateTime, nullable=True)
    source = Column(String, default="digital")  # "digital" or "physical"

    phase = Column(Enum(Phase), default=Phase.phase_1)
    sundays_sent = Column(Integer, default=0)
    phase2_opt_in = Column(Boolean, nullable=True)  # null = not yet asked
    status = Column(Enum(ContactStatus), default=ContactStatus.active)

    last_reminder_sent_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    church = relationship("Church", back_populates="contacts")
    service_visited = relationship("Service")


class MessageLog(Base):
    """Every send gets logged - useful for debugging and for proving consent/opt-out compliance."""
    __tablename__ = "message_log"

    id = Column(String, primary_key=True, default=gen_id)
    contact_id = Column(String, ForeignKey("contacts.id"), nullable=False)
    channel = Column(String, nullable=False)  # "sms" or "email"
    template_used = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    error = Column(Text, nullable=True)
