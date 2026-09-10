import streamlit as st
import pandas as pd
import base64
import requests
import speech_recognition as sr
import dateparser
from datetime import timedelta

# --- Helpers
def fetch_remote_csv_via_api(token):
    headers = {"Authorization": f"token {token}"} if token else {}
    r = requests.get(API_URL, headers=headers)
    if r.status_code == 200:
        j = r.json()
        content_b64 = j.get("content", "")
        try:
            raw = base64.b64decode(content_b64).decode("utf-8")
            from io import StringIO
            df = pd.read_csv(StringIO(raw), dtype=str)
        except Exception:
            df = pd.DataFrame(columns=COLUMNS)
        return df, j.get("sha")
    return None, None

def load_schedule_from_github(token=None):
    if token:
        df, sha = fetch_remote_csv_via_api(token)
        if df is not None:
            return sanitize_remote_df(df)

    raw_url = f"https://raw.githubusercontent.com/{REPO}/main/{PATH}"
    try:
        df = pd.read_csv(raw_url, dtype=str)
    except Exception:
        return pd.DataFrame(columns=COLUMNS)

    return sanitize_remote_df(df)

def get_github_sha(token):
    headers = {"Authorization": f"token {token}"} if token else {}
    r = requests.get(API_URL, headers=headers)
    if r.status_code == 200:
        return r.json().get("sha")
    return None

def update_schedule_on_github(df, token, message="Update schedule"):
    if not token:
        return False, None, "Missing token"

    upload_df = df.copy()
    upload_df["Date"] = upload_df["Date"].apply(lambda d: "" if pd.isna(d) else str(d))

    csv_content = upload_df.to_csv(index=False)
    encoded = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")

    sha = get_github_sha(token)
    payload = {"message": message, "content": encoded}
    if sha:
        payload["sha"] = sha

    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    r = requests.put(API_URL, json=payload, headers=headers)
    return r.status_code in (200, 201), r.status_code, r.text
