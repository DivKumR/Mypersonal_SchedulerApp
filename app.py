import streamlit as st
import pandas as pd
import base64
import requests
import speech_recognition as sr
import dateparser
from datetime import timedelta
import json

# --- Config
REPO = "DivKumR/Mypersonal_SchedulerApp"
PATH = "schedule.csv"
API_URL = f"https://api.github.com/repos/{REPO}/contents/{PATH}"
COLUMNS = ["Date", "Weekday", "Name", "Activity", "Time"]

# --- Helpers
def fetch_remote_csv_via_api(token):
    """
    Use GitHub API to get the file content and sha. Return (df, sha).
    If token is None or GET fails, return (None, None).
    """
    headers = {"Authorization": f"token {token}"} if token else {}
    r = requests.get(API_URL, headers=headers)
    if r.status_code == 200:
        j = r.json()
        sha = j.get("sha")
        content_b64 = j.get("content", "")
        # content may have newlines; decode
        try:
            raw = base64.b64decode(content_b64).decode("utf-8")
            # read as strings to avoid inference of index column
            from io import StringIO
            df = pd.read_csv(StringIO(raw), dtype=str)
        except Exception:
            # fallback: empty dataframe
            df = pd.DataFrame(columns=COLUMNS)
        return df, sha
    else:
        return None, None

def load_schedule_from_github(token=None):
    """
    Preferred: use API when token available to ensure latest authoritative content.
    Fallback: try raw.githubusercontent (not ideal but keeps backward compatibility).
    """
    # Try API if token provided
    if token:
        df, sha = fetch_remote_csv_via_api(token)
        if df is not None:
            # sanitize and normalize
            df = sanitize_remote_df(df)
            return df
    # Fallback to raw URL (no token)
    raw_url = f"https://raw.githubusercontent.com/{REPO}/main/{PATH}"
    try:
        df = pd.read_csv(raw_url, dtype=str)
    except Exception:
        return pd.DataFrame(columns=COLUMNS)
    df = sanitize_remote_df(df)
    return df

def sanitize_remote_df(df):
    """
    - remove unnamed/index columns
    - ensure required columns exist and in correct order
    - normalize Date -> date
    - recompute Weekday from Date when possible
    """
    if df is None:
        return pd.DataFrame(columns=COLUMNS)
    # drop Unnamed columns introduced by index written into CSV
    df = df.loc[:, ~df.columns.str.lower().str.contains("^unnamed")]
    # ensure columns
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[COLUMNS].copy()
    # normalize Date column to date objects where possible
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    df["Weekday"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%A")
    return df.reset_index(drop=True)

def get_github_sha(token):
    headers = {"Authorization": f"token {token}"} if token else {}
    r = requests.get(API_URL, headers=headers)
    if r.status_code == 200:
        return r.json().get("sha")
    return None

def update_schedule_on_github(df, token, message="Update schedule"):
    """
    PUT the CSV content using the correct SHA. Returns (ok, status_code, response_text).
    """
    if not token:
        return False, None, "Missing token"

    # convert Date to ISO strings or empty string
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
    return r.status_code in (200,201), r.status_code, r.text

def get_voice_input():
    recognizer = sr.Recognizer()
    try:
        # Check if microphone is available (skip if running on cloud)
        try:
            import pyaudio  # runtime check only
        except ImportError:
            st.warning("🎤 Microphone not available in this environment. Try uploading audio or using text input.")
            return ""

        with sr.Microphone() as source:
            st.info("🎤 Listening...")
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=30)
        text = recognizer.recognize_google(audio)
        st.success(f"🗣️ You said: {text}")
        return text
    except sr.UnknownValueError:
        st.error("Could not understand audio.")
    except sr.RequestError:
        st.error("Speech recognition service failed.")
    except Exception as e:
        st.error(f"Microphone error: {e}")
    return ""

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

# Load token once
token = st.secrets.get("GITHUB_TOKEN", None)

# Always fetch authoritative latest copy from API when possible
latest_df = load_schedule_from_github(token)

# Display copy
display_df = latest_df.copy()

st.subheader("📊 Filter and Sort")
weekday_filter = st.selectbox("Filter by Weekday", ["All"] + ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])
if weekday_filter != "All":
    display_df = display_df[display_df["Weekday"] == weekday_filter]

# safe fill and temporary categorical sorting for display
display_df = display_df.fillna("")
weekday_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
display_df["Weekday_cat"] = pd.Categorical(display_df["Weekday"].replace("", pd.NA), categories=weekday_order, ordered=True)
if "Time" in display_df.columns:
    display_df = display_df.sort_values(["Weekday_cat","Time"], na_position="last").drop(columns=["Weekday_cat"])
else:
    display_df = display_df.sort_values(["Weekday_cat"], na_position="last").drop(columns=["Weekday_cat"])

st.dataframe(display_df.replace({pd.NA:""}).fillna(""))

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

# Manual add
st.subheader("➕ Add Event Manually")
name = st.text_input("Name")
activity = st.text_input("Activity")
time_val = st.text_input("Time")
date_val = st.date_input("Date")
recurrence = st.selectbox("Repeat", ["None","Daily","Weekly"])
repeat_count = st.number_input("Repeat how many times?", min_value=1, max_value=30, value=1)

if st.button("Add Event"):
    new_rows = expand_recurring_events(date_val, name, activity, time_val, recurrence, repeat_count)
    # -> KEY: fetch authoritative latest again BEFORE merging
    latest_df = load_schedule_from_github(token)
    # normalize types
    new_rows["Date"] = pd.to_datetime(new_rows["Date"]).dt.date
    combined_df = pd.concat([latest_df, new_rows], ignore_index=True).reset_index(drop=True)
    # show preview
    st.write("📦 Preview of CSV to be uploaded:")
    st.dataframe(combined_df.fillna("").head(200))
    if not token:
        st.error("Missing GITHUB_TOKEN in secrets.toml; cannot push to GitHub.")
    else:
        ok, code, text = update_schedule_on_github(combined_df, token, message="Add event(s) via UI")
        st.write(f"GitHub response: {code}")
        if ok:
            st.success("✅ Event(s) added!")
            latest_df = load_schedule_from_github(token)
        else:
            st.error("❌ Failed to update GitHub")
            st.code(text)

# Voice
st.subheader("🎙️ Voice Input")
voice_text = ""
if st.button("Use Voice Input"):
    voice_text = get_voice_input()
st.text_area("Voice Input Result", value=voice_text)

# NLP add
st.subheader("🧠 Smart Add via Natural Language")
nl_input = st.text_input("e.g. Add gym on Wednesday for Vinoth")
if st.button("Parse and Add"):
    parsed = parse_event(nl_input)
    if not parsed:
        st.warning("Could not parse input. Try: Add gym on Wednesday for Vinoth")
    else:
        new_row = pd.DataFrame([parsed], columns=COLUMNS)
        latest_df = load_schedule_from_github(token)
        new_row["Date"] = pd.to_datetime(new_row["Date"]).dt.date
        combined_df = pd.concat([latest_df, new_row], ignore_index=True).reset_index(drop=True)
        st.write("📦 Preview of CSV to be uploaded:")
        st.dataframe(combined_df.fillna("").head(200))
        if not token:
            st.error("Missing GITHUB_TOKEN in secrets.toml; cannot push to GitHub.")
        else:
            ok, code, text = update_schedule_on_github(combined_df, token, message="Add event via NLP")
            st.write(f"GitHub response: {code}")
            if ok:
                st.success("✅ Event added from natural input!")
                latest_df = load_schedule_from_github(token)
            else:
                st.error("❌ Failed to update GitHub")

                st.code(text)


st.subheader("🗑️ Delete Event")

# Reload latest for accurate options
latest_df = load_schedule_from_github(token)

# Build a label for each row
latest_df["Label"] = latest_df.apply(
    lambda row: f"{row['Date']} | {row['Weekday']} | {row['Name']} - {row['Activity']} @ {row['Time']}", axis=1
)

selected_label = st.selectbox("Select event to delete", options=latest_df["Label"].tolist())

if st.button("Delete Selected Event"):
    # Find the row to delete
    to_delete = latest_df[latest_df["Label"] == selected_label]
    if to_delete.empty:
        st.warning("No matching event found.")
    else:
        updated_df = latest_df[latest_df["Label"] != selected_label].drop(columns=["Label"]).reset_index(drop=True)
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
