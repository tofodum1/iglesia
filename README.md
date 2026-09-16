# Newcomer Reminder System

Multi-tenant SMS/email follow-up system for church newcomers. Sends a
3-Sunday welcome reminder sequence, then offers an ongoing "stay connected"
phase for anyone who opts in.

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in your Twilio + Resend credentials.
3. Run locally: `uvicorn app.main:app --reload`
4. Visit `http://localhost:8000/docs` for the interactive API.

## Onboarding a church

POST to `/admin/churches` with the church's name, signoff line, timezone,
and optional per-church Twilio/Resend overrides. That returns a `signup_url`
(put this behind a QR code for the digital form) and a `staff_intake_url`
(bookmark this on a staff tablet/laptop for re-keying paper forms).

Then POST to `/admin/churches/{church_id}/services` once per service
(Sunday, midweek, etc.) with its name, type, day_of_week (0=Monday..6=Sunday),
and time_of_day.

## How reminders go out

A background job runs daily (9am server time, configurable in `main.py`)
and checks every active contact against their church's service schedule.
Reminders go out the day before each service. The exact wording lives in
`app/messages.py` and mirrors the approved spec doc.

## Twilio webhook

Point your Twilio number's inbound webhook at `/webhooks/twilio/inbound`
so STOP/YES replies are handled automatically.

## Deploying

Same pattern as Maître: push to Render, set the env vars from `.env.example`
in the Render dashboard, and set `DATABASE_URL` to a Postgres instance once
you outgrow SQLite (fine for a single church; recommended once you're running
several).
