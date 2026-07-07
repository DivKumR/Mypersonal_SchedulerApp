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

def check_events():
    df = pd.read_csv(CSV_URL)
    now = datetime.datetime.now()

    for _, row in df.iterrows():
        date = row["Date"]
        time = row["Time"]

        if pd.isna(date):
            continue

        try:
            event_dt = pd.to_datetime(f"{date} {time}") if time else pd.to_datetime(date)
        except:
            continue

        diff = event_dt - now

        # 1 day reminder ONLY
        if datetime.timedelta(seconds=1) < diff <= datetime.timedelta(days=1):
            msg = f"Event tomorrow: {row['Activity']} for {row['Name']} at {row['Time']}"
            send_email("Reminder: Event Tomorrow", msg)
            send_push(msg)

check_events()
