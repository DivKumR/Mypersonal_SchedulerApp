import base64
from io import StringIO

import pandas as pd
import requests

from services.schedule_service import COLUMNS, sanitize_schedule_df


REPO = "DivKumR/Mypersonal_SchedulerApp"
PATH = "schedule.csv"
API_URL = f"https://api.github.com/repos/{REPO}/contents/{PATH}"


def fetch_remote_csv_via_api(token):
    headers = {"Authorization": f"token {token}"} if token else {}
    response = requests.get(API_URL, headers=headers, timeout=30)
    if response.status_code != 200:
        return None, None

    payload = response.json()
    try:
        raw = base64.b64decode(payload.get("content", "")).decode("utf-8")
        dataframe = pd.read_csv(StringIO(raw), dtype=str)
    except Exception:
        dataframe = pd.DataFrame(columns=COLUMNS)

    return dataframe, payload.get("sha")


def load_schedule_from_github(token=None):
    if token:
        dataframe, _ = fetch_remote_csv_via_api(token)
        if dataframe is not None:
            return sanitize_schedule_df(dataframe)

    raw_url = f"https://raw.githubusercontent.com/{REPO}/main/{PATH}"
    try:
        dataframe = pd.read_csv(raw_url, dtype=str)
    except Exception:
        return pd.DataFrame(columns=COLUMNS)

    return sanitize_schedule_df(dataframe)


def get_github_sha(token):
    headers = {"Authorization": f"token {token}"}
    response = requests.get(API_URL, headers=headers, timeout=30)
    if response.status_code == 200:
        return response.json().get("sha")
    return None


def update_schedule_on_github(dataframe, token, message="Update schedule"):
    if not token:
        return False, None, "Missing token"

    upload_df = sanitize_schedule_df(dataframe)
    upload_df["Date"] = upload_df["Date"].apply(
        lambda value: "" if pd.isna(value) else str(value)
    )
    csv_content = upload_df.to_csv(index=False)
    encoded = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")

    payload = {"message": message, "content": encoded}
    sha = get_github_sha(token)
    if sha:
        payload["sha"] = sha

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    response = requests.put(
        API_URL,
        json=payload,
        headers=headers,
        timeout=30,
    )
    return (
        response.status_code in (200, 201),
        response.status_code,
        response.text,
    )