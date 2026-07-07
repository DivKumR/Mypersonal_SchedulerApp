import pandas as pd
import datetime
import requests
import os

CSV_URL = "https://raw.githubusercontent.com/DivKumR/Mypersonal_SchedulerApp/main/schedule.csv"

EMAIL_API_KEY = os.getenv("SENDGRID_API_KEY")
TO_EMAIL = os.getenv("TO_EMAIL")
FROM_EMAIL = os.getenv("FROM_EMAIL")

PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")

def send_email(subject, body):
    if not EMAIL_API_KEY:
        return

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {"Authorization": f"Bearer {EMAIL_API_KEY}", "Content-Type": "application/json"}
    data = {
        "personalizations": [{"to": [{"email": TO_EMAIL}]}],
        "from": {"email": FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}]
    }
    requests.post(url, headers=headers, json=data)

def send_push(message):
    if not PUSHOVER_TOKEN or not PUSHOVER_USER:
        return

    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER,
        "message": message
    }
    requests.post(url, data=data)

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

def check_events():
    df = pd.read_csv(CSV_URL)
    now = datetime.datetime.utcnow()  # GitHub Actions uses UTC

    for _, row in df.iterrows():
        date = row["Date"]
        time = normalize_time(row["Time"])

        if pd.isna(date):
            continue

        try:
            # If time is empty, parse date only
            if time == "":
                event_dt = pd.to_datetime(date)
            else:
                event_dt = pd.to_datetime(f"{date} {time}")
        except:
            continue

        diff = event_dt - now

        # Trigger if event is within the next 24 hours
        if datetime.timedelta(0) < diff <= datetime.timedelta(days=1):
            msg = f"Event tomorrow: {row['Activity']} for {row['Name']} at {row['Time']}"
            send_email("Reminder: Event Tomorrow", msg)
            send_push(msg)

check_events()
