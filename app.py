import streamlit as st
import pandas as pd
import base64
import requests
import speech_recognition as sr
import dateparser
from datetime import timedelta

# --- Config
REPO = "DivKumR/Mypersonal_SchedulerApp"
PATH = "schedule.csv"
API_URL = f"https://api.github.com/repos/{REPO}/contents/{PATH}"
COLUMNS = ["Date", "Weekday", "Name", "Activity", "Time"]

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

def sanitize_remote_df(df):
    if df is None:
        return pd.DataFrame(columns=COLUMNS)

    df = df.loc[:, ~df.columns.str.lower().str.contains("^unnamed")]

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[COLUMNS].copy()

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    df["Weekday"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%A")

    return df.reset_index(drop=True)

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

def parse_event(text):
    import re
    pattern = re.search(r"add\s+(.+?)\s+(?:on\s+(.+?)\s+)?for\s+(.+?)(?:\s+at\s+(.+))?$", text, re.IGNORECASE)
    if not pattern:
        return None

    activity = pattern.group(1).strip()
    date_phrase = pattern.group(2).strip() if pattern.group(2) else "today"
    name = pattern.group(3).strip()
    time = pattern.group(4).strip() if pattern.group(4) else ""

    parsed = dateparser.parse(date_phrase)
    if not parsed:
        return None

    date = parsed.date()
    weekday = pd.to_datetime(date).strftime("%A")

    return {"Date": date, "Weekday": weekday, "Name": name, "Activity": activity, "Time": time}

def expand_recurring_events(date, name, activity, time, recurrence, repeat_count):
    rows = []
    for i in range(repeat_count):
        if recurrence == "Daily":
            new_date = date + timedelta(days=i)
        elif recurrence == "Weekly":
            new_date = date + timedelta(weeks=i)
        else:
            new_date = date
        rows.append([new_date, pd.to_datetime(new_date).strftime("%A"), name, activity, time])
    return pd.DataFrame(rows, columns=COLUMNS)

# --- UI
st.set_page_config(page_title="Daily Scheduler", layout="centered")
st.title("📅 Daily Scheduler")

token = st.secrets.get("GITHUB_TOKEN", None)
latest_df = load_schedule_from_github(token)

# Display
display_df = latest_df.copy()

st.subheader("📊 Filter and Sort")
weekday_filter = st.selectbox("Filter by Weekday", ["All"] + ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])
if weekday_filter != "All":
    display_df = display_df[display_df["Weekday"] == weekday_filter]

display_df = display_df.fillna("")
weekday_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
display_df["Weekday_cat"] = pd.Categorical(display_df["Weekday"].replace("", pd.NA), categories=weekday_order, ordered=True)

if "Time" in display_df.columns:
    display_df = display_df.sort_values(["Weekday_cat","Time"], na_position="last").drop(columns=["Weekday_cat"])
else:
    display_df = display_df.sort_values(["Weekday_cat"], na_position="last").drop(columns=["Weekday_cat"])

st.dataframe(display_df.replace({pd.NA:""}).fillna(""))

# Weekly Calendar
st.subheader("🗓️ Weekly Calendar View")
if not display_df.empty:
    pivot_df = display_df.copy()
    pivot_df["Time"] = pivot_df["Time"].astype(str)
    pivot_df["Weekday"] = pivot_df["Weekday"].astype(str)
    try:
        calendar_df = pivot_df.pivot_table(index="Time", columns="Weekday", values="Activity",
                                           aggfunc=lambda x: ", ".join(x.dropna().astype(str)))
        st.dataframe(calendar_df.fillna(""))
    except Exception:
        st.write("No events to show in calendar.")
else:
    st.write("No events to show in calendar.")

# Manual Add
st.subheader("➕ Add Event Manually")
name = st.text_input("Name")
activity = st.text_input("Activity")
time_val = st.text_input("Time")
date_val = st.date_input("Date")
recurrence = st.selectbox("Repeat", ["None","Daily","Weekly"])
repeat_count = st.number_input("Repeat how many times?", min_value=1, max_value=30, value=1)

if st.button("Add Event"):
    new_rows = expand_recurring_events(date_val, name, activity, time_val, recurrence, repeat_count)

    latest_df = load_schedule_from_github(token)
    new_rows["Date"] = pd.to_datetime(new_rows["Date"], errors="coerce").dt.date

    combined_df = pd.concat([latest_df, new_rows], ignore_index=True)

    combined_df["Date"] = pd.to_datetime(combined_df["Date"], errors="coerce").dt.date
    combined_df = combined_df.sort_values("Date").reset_index(drop=True)

    st.write("📦 Preview of CSV to be uploaded:")
    st.dataframe(combined_df.fillna("").head(200))

    if not token:
        st.error("Missing GITHUB_TOKEN in secrets.toml; cannot push to GitHub.")
    else:
        ok, code, text = update_schedule_on_github(combined_df, token, message="Add event(s) via UI")
        st.write(f"GitHub response: {code}")
        if ok:
            st.success("✅ Event(s) added!")
        else:
            st.error("❌ Failed to update GitHub")
            st.code(text)

# NLP Add
st.subheader("🧠 Smart Add via Natural Language")
nl_input = st.text_input("e.g. Add gym on Wednesday for Vinoth")

if st.button("Parse and Add"):
    parsed = parse_event(nl_input)
    if not parsed:
        st.warning("Could not parse input. Try: Add gym on Wednesday for Vinoth")
    else:
        new_row = pd.DataFrame([parsed], columns=COLUMNS)

        latest_df = load_schedule_from_github(token)
        new_row["Date"] = pd.to_datetime(new_row["Date"], errors="coerce").dt.date

        combined_df = pd.concat([latest_df, new_row], ignore_index=True)

        combined_df["Date"] = pd.to_datetime(combined_df["Date"], errors="coerce").dt.date
        combined_df = combined_df.sort_values("Date").reset_index(drop=True)

        st.write("📦 Preview of CSV to be uploaded:")
        st.dataframe(combined_df.fillna("").head(200))

        if not token:
            st.error("Missing GITHUB_TOKEN in secrets.toml; cannot push to GitHub.")
        else:
            ok, code, text = update_schedule_on_github(combined_df, token, message="Add event via NLP")
            st.write(f"GitHub response: {code}")
            if ok:
                st.success("✅ Event added from natural input!")
            else:
                st.error("❌ Failed to update GitHub")
                st.code(text)

# Delete Event
st.subheader("🗑️ Delete Event")

latest_df = load_schedule_from_github(token)
latest_df["Label"] = latest_df.apply(
    lambda row: f"{row['Date']} | {row['Weekday']} | {row['Name']} - {row['Activity']} @ {row['Time']}", axis=1
)

selected_label = st.selectbox("Select event to delete", options=latest_df["Label"].tolist())

if st.button("Delete Selected Event"):
    to_delete = latest_df[latest_df["Label"] == selected_label]
    if to_delete.empty:
        st.warning("No matching event found.")
    else:
        updated_df = latest_df[latest_df["Label"] != selected_label].drop(columns=["Label"])

        updated_df["Date"] = pd.to_datetime(updated_df["Date"], errors="coerce").dt.date
        updated_df = updated_df.sort_values("Date").reset_index(drop=True)

        st.write("📦 Updated CSV preview after deletion:")
        st.dataframe(updated_df.head(100))

        if not token:
            st.error("Missing GITHUB_TOKEN in secrets.toml; cannot push to GitHub.")
        else:
            ok, code, text = update_schedule_on_github(updated_df, token, message="Delete event")
            st.write(f"GitHub response: {code}")
            if ok:
                st.success("✅ Event deleted successfully!")
            else:
                st.error("❌ Failed to update GitHub")
                st.code(text)
