import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import requests

from services.schedule_service import format_time_12h

CSV_URL = "https://raw.githubusercontent.com/DivKumR/Mypersonal_SchedulerApp/main/schedule.csv"

EMAIL_API_KEY = os.getenv("SENDGRID_API_KEY")
TO_EMAIL = os.getenv("TO_EMAIL")
FROM_EMAIL = os.getenv("FROM_EMAIL")

PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "UTC")
REMINDER_MINUTES = int(os.getenv("REMINDER_MINUTES", "15"))


def send_email(subject, body):
    if not EMAIL_API_KEY or not TO_EMAIL or not FROM_EMAIL:
        return

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {"Authorization": f"Bearer {EMAIL_API_KEY}", "Content-Type": "application/json"}
    data = {
        "personalizations": [{"to": [{"email": TO_EMAIL}]}],
        "from": {"email": FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}]
    }
    response = requests.post(url, headers=headers, json=data, timeout=30)
    response.raise_for_status()


def send_push(message):
    if not PUSHOVER_TOKEN or not PUSHOVER_USER:
        return

    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER,
        "message": message
    }
    response = requests.post(url, data=data, timeout=30)
    response.raise_for_status()


def normalize_time(time_str):
    """Convert various time formats into something pandas can parse."""
    if pd.isna(time_str):
        return ""

    t = str(time_str).strip().lower()

    # Handle special cases
    if t in ["", "now"]:
        return ""

    # Convert "10 am" → "10:00 AM"
    if "am" in t or "pm" in t:
        return t.replace(" ", "")

    # Convert "2.15 to 3.45" → ignore time, treat as all-day event
    if "to" in t:
        return ""

    return t


def get_scheduler_timezone():
    try:
        return ZoneInfo(SCHEDULER_TIMEZONE)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Unknown SCHEDULER_TIMEZONE: {SCHEDULER_TIMEZONE}"
        ) from exc


def check_events():
    df = pd.read_csv(CSV_URL)
    scheduler_timezone = get_scheduler_timezone()
    now = datetime.now(scheduler_timezone)

    for _, row in df.iterrows():
        event_date = row["Date"]
        start_time = normalize_time(row["StartTime"])

        if pd.isna(event_date) or not start_time:
            continue

        try:
            parsed_date = pd.to_datetime(event_date).date()
            parsed_time = pd.to_datetime(start_time).time()
            event_dt = datetime.combine(
                parsed_date,
                parsed_time,
                tzinfo=scheduler_timezone,
            )
        except (TypeError, ValueError):
            continue

        diff = event_dt - now

        if timedelta(0) <= diff < timedelta(minutes=REMINDER_MINUTES):
            minutes_until = max(1, int(diff.total_seconds() // 60) + 1)
            msg = (
                f"{row['Activity']} for {row['Name']} starts in "
                f"{minutes_until} minute(s) at "
                f"{format_time_12h(row['StartTime'])}."
            )
            send_email(f"Reminder: {row['Activity']}", msg)
            send_push(msg)


if __name__ == "__main__":
    check_events()
