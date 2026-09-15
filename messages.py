"""
Message templates for the newcomer reminder sequence.
Mirrors church-newcomer-reminder-system-spec.md - edit both together if you change wording.
"""

import random

SIGNUP_CONFIRMATION = (
    "Hi {first_name}! So glad you visited {church_name} \U0001F49B "
    "You'll get a friendly reminder before our next few services so it's "
    "easier to make it back. Reply STOP anytime to opt out. — {church_signoff}"
)

PHASE1_REMINDER_1 = (
    "Hey {first_name}! Just a heads up — {service_name} is this {service_day} "
    "at {service_time}. We'd love to see you there again. — {church_signoff}"
)

PHASE1_REMINDER_2 = (
    "{first_name}, {service_name} is coming up this {service_day} at "
    "{service_time}. Hope you can join us — it's always better with you there. "
    "— {church_signoff}"
)

PHASE1_REMINDER_3 = (
    "Hi {first_name}, this {service_day} at {service_time} is our next "
    "{service_name}. We've genuinely loved having you. — {church_signoff}"
)

MIDWEEK_REMINDER = (
    "Hey {first_name}, don't forget {service_name} this {service_day} at "
    "{service_time}. A great midweek reset. — {church_signoff}"
)

PHASE2_OPT_IN_ASK = (
    "{first_name}, it's been great having you these past few weeks! Want to "
    "keep getting reminders and encouragement from {church_name} going "
    "forward? Reply YES to stay in the loop, or no worries if not. "
    "— {church_signoff}"
)

PHASE2_ONGOING_VARIANTS = [
    (
        "{first_name}, {service_name} is this {service_day} at {service_time}. "
        "Hope to see your face this week \U0001F64C — {church_signoff}"
    ),
    (
        "Just a reminder, {first_name} — {service_name} is {service_day} at "
        "{service_time}. You're always welcome. — {church_signoff}"
    ),
]

OPT_OUT_CONFIRMATION = (
    "You've been unsubscribed from {church_name} reminders. You're always "
    "welcome back — just let us know. — {church_signoff}"
)

# Ordered so sundays_sent (0,1,2) indexes directly into this list
PHASE1_SEQUENCE = [PHASE1_REMINDER_1, PHASE1_REMINDER_2, PHASE1_REMINDER_3]


def render(template: str, **kwargs) -> str:
    return template.format(**kwargs)


def next_phase2_variant() -> str:
    return random.choice(PHASE2_ONGOING_VARIANTS)
