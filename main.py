import logging
from datetime import datetime, date

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler

from app.database import init_db, get_db, SessionLocal
from app.models import Church, Service, Contact, ContactPreference, Phase, ContactStatus
from app import messages
from app.sender import send_sms, send_email
from app.scheduler import run_daily_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("newcomer_reminder")

app = FastAPI(title="Newcomer Reminder System")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

init_db()


# ---------------------------------------------------------------------------
# Scheduler: runs the daily reminder job automatically once a day.
# ---------------------------------------------------------------------------
def _scheduled_job():
    db = SessionLocal()
    try:
        run_daily_job(db)
        logger.info("Daily reminder job completed")
    finally:
        db.close()


scheduler = BackgroundScheduler()
scheduler.add_job(_scheduled_job, "cron", hour=9, minute=0)  # 9am server time daily
scheduler.start()


# ---------------------------------------------------------------------------
# Public signup form (digital form -> this is what the QR code points to)
# ---------------------------------------------------------------------------
@app.get("/signup/{church_id}", response_class=HTMLResponse)
def signup_form(request: Request, church_id: str, db: Session = Depends(get_db)):
    church = db.query(Church).filter(Church.id == church_id).first()
    if not church:
        raise HTTPException(404, "Church not found")
    services = [s for s in church.services if s.enabled]
    return templates.TemplateResponse("signup.html", {
        "request": request, "church": church, "services": services
    })


@app.post("/signup/{church_id}")
def signup_submit(
    church_id: str,
    request: Request,
    first_name: str = Form(...),
    contact_preference: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    service_visited_id: str = Form(""),
    wants_midweek: bool = Form(False),
    consent_given: bool = Form(False),
    db: Session = Depends(get_db),
):
    church = db.query(Church).filter(Church.id == church_id).first()
    if not church:
        raise HTTPException(404, "Church not found")

    if not consent_given:
        raise HTTPException(400, "Consent is required to sign up for reminders")

    contact = Contact(
        church_id=church.id,
        first_name=first_name.strip(),
        phone=phone.strip() or None,
        email=email.strip() or None,
        contact_preference=ContactPreference(contact_preference),
        service_visited_id=service_visited_id or None,
        wants_midweek=wants_midweek,
        consent_given=True,
        consent_timestamp=datetime.utcnow(),
        source="digital",
        first_visit_date=date.today(),
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)

    _send_signup_confirmation(contact, church)

    return RedirectResponse(url=f"/signup/{church_id}/thanks", status_code=303)


@app.get("/signup/{church_id}/thanks", response_class=HTMLResponse)
def signup_thanks(request: Request, church_id: str, db: Session = Depends(get_db)):
    church = db.query(Church).filter(Church.id == church_id).first()
    return templates.TemplateResponse("thanks.html", {"request": request, "church": church})


def _send_signup_confirmation(contact: Contact, church: Church):
    body = messages.render(
        messages.SIGNUP_CONFIRMATION,
        first_name=contact.first_name,
        church_name=church.name,
        church_signoff=church.signoff,
    )
    if contact.contact_preference == ContactPreference.sms and contact.phone:
        send_sms(contact.phone, body, from_number=church.twilio_from_number)
    elif contact.contact_preference == ContactPreference.email and contact.email:
        send_email(
            contact.email, subject=f"Welcome to {church.name}!", body=body,
            from_email=church.email_from_address, from_name=church.email_from_name or church.name,
        )


# ---------------------------------------------------------------------------
# Staff intake screen - for re-keying physical paper forms
# ---------------------------------------------------------------------------
@app.get("/staff/{church_id}/intake", response_class=HTMLResponse)
def staff_intake_form(request: Request, church_id: str, db: Session = Depends(get_db)):
    church = db.query(Church).filter(Church.id == church_id).first()
    if not church:
        raise HTTPException(404, "Church not found")
    services = [s for s in church.services if s.enabled]
    return templates.TemplateResponse("staff_intake.html", {
        "request": request, "church": church, "services": services
    })


@app.post("/staff/{church_id}/intake")
def staff_intake_submit(
    church_id: str,
    first_name: str = Form(...),
    contact_preference: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    service_visited_id: str = Form(""),
    wants_midweek: bool = Form(False),
    consent_given: bool = Form(False),
    visit_date: str = Form(""),
    db: Session = Depends(get_db),
):
    church = db.query(Church).filter(Church.id == church_id).first()
    if not church:
        raise HTTPException(404, "Church not found")
    if not consent_given:
        raise HTTPException(400, "The paper form must show the visitor checked/signed consent")

    visit = datetime.strptime(visit_date, "%Y-%m-%d").date() if visit_date else date.today()

    contact = Contact(
        church_id=church.id,
        first_name=first_name.strip(),
        phone=phone.strip() or None,
        email=email.strip() or None,
        contact_preference=ContactPreference(contact_preference),
        service_visited_id=service_visited_id or None,
        wants_midweek=wants_midweek,
        consent_given=True,
        consent_timestamp=datetime.utcnow(),  # timestamp of data entry, not of the physical signature
        source="physical",
        first_visit_date=visit,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)

    _send_signup_confirmation(contact, church)

    return RedirectResponse(url=f"/staff/{church_id}/intake?added=1", status_code=303)


# ---------------------------------------------------------------------------
# Twilio inbound webhook - handles STOP / YES replies
# ---------------------------------------------------------------------------
@app.post("/webhooks/twilio/inbound", response_class=PlainTextResponse)
def twilio_inbound(From: str = Form(...), Body: str = Form(...), db: Session = Depends(get_db)):
    text = Body.strip().lower()
    contact = db.query(Contact).filter(Contact.phone == From).order_by(Contact.created_at.desc()).first()

    if not contact:
        return PlainTextResponse("", status_code=200)

    if text in ("stop", "unsubscribe", "cancel"):
        contact.status = ContactStatus.opted_out
        db.commit()
        church = contact.church
        body = messages.render(messages.OPT_OUT_CONFIRMATION, church_name=church.name, church_signoff=church.signoff)
        send_sms(contact.phone, body, from_number=church.twilio_from_number)

    elif text in ("yes", "y") and contact.phase == Phase.ended and contact.phase2_opt_in is None:
        contact.phase2_opt_in = True
        contact.phase = Phase.phase_2
        contact.status = ContactStatus.active
        db.commit()

    return PlainTextResponse("", status_code=200)


# ---------------------------------------------------------------------------
# Internal/admin: manually trigger the daily job (useful for testing,
# and as a fallback if you'd rather drive this from an external cron
# than the built-in APScheduler above).
# ---------------------------------------------------------------------------
@app.post("/internal/run-daily-job")
def trigger_daily_job(db: Session = Depends(get_db)):
    run_daily_job(db)
    return {"status": "ok", "ran_at": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Minimal church/service setup endpoints (so onboarding a new church
# doesn't require touching the database by hand)
# ---------------------------------------------------------------------------
@app.post("/admin/churches")
def create_church(
    name: str = Form(...),
    timezone: str = Form("America/New_York"),
    leader_name: str = Form(""),
    signoff: str = Form(""),
    twilio_from_number: str = Form(""),
    email_from_address: str = Form(""),
    email_from_name: str = Form(""),
    primary_color: str = Form(""),
    primary_deep_color: str = Form(""),
    accent_color: str = Form(""),
    background_color: str = Form(""),
    badge_url: str = Form(""),
    db: Session = Depends(get_db),
):
    church = Church(
        name=name,
        timezone=timezone,
        leader_name=leader_name or None,
        signoff=signoff or f"{name} Family",
        twilio_from_number=twilio_from_number or None,
        email_from_address=email_from_address or None,
        email_from_name=email_from_name or None,
        primary_color=primary_color or None,
        primary_deep_color=primary_deep_color or None,
        accent_color=accent_color or None,
        background_color=background_color or None,
        badge_url=badge_url or None,
    )
    db.add(church)
    db.commit()
    db.refresh(church)
    return {"id": church.id, "signup_url": f"/signup/{church.id}", "staff_intake_url": f"/staff/{church.id}/intake"}


@app.post("/admin/churches/{church_id}/branding")
def update_branding(
    church_id: str,
    primary_color: str = Form(""),
    primary_deep_color: str = Form(""),
    accent_color: str = Form(""),
    background_color: str = Form(""),
    badge_url: str = Form(""),
    db: Session = Depends(get_db),
):
    church = db.query(Church).filter(Church.id == church_id).first()
    if not church:
        raise HTTPException(404, "Church not found")
    if primary_color:
        church.primary_color = primary_color
    if primary_deep_color:
        church.primary_deep_color = primary_deep_color
    if accent_color:
        church.accent_color = accent_color
    if background_color:
        church.background_color = background_color
    if badge_url:
        church.badge_url = badge_url
    db.commit()
    return {"status": "updated", "church_id": church.id}


@app.post("/admin/churches/{church_id}/services")
def add_service(
    church_id: str,
    name: str = Form(...),
    type: str = Form(...),          # "sunday" or "midweek"
    day_of_week: int = Form(...),   # 0=Monday ... 6=Sunday
    time_of_day: str = Form(...),   # "10:00"
    db: Session = Depends(get_db),
):
    church = db.query(Church).filter(Church.id == church_id).first()
    if not church:
        raise HTTPException(404, "Church not found")
    service = Service(
        church_id=church.id, name=name, type=type,
        day_of_week=day_of_week, time_of_day=time_of_day,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return {"id": service.id}


@app.get("/health")
def health():
    return {"status": "ok"}
