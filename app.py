import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser
import pandas as pd
import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from services.github_schedule_repository import (
    load_schedule_from_github,
    update_schedule_on_github,
)
from services.schedule_service import (
    create_event,
    format_time,
)


def show_github_error(status_code, response_text):
    st.error(f"GitHub update failed with status {status_code}.")
    if response_text:
        st.code(response_text)


def format_event_label(event_row):
    return (
        f"{event_row['Date']} | {event_row['Name']} | "
        f"{event_row['Activity']} | "
        f"{format_time(event_row['StartTime'])}-"
        f"{format_time(event_row['EndTime'])}"
    )


def parse_quick_entry(value):
    pattern = re.compile(
        r"^(?P<activity>.+?)\s+"
        r"(?P<date>today|tomorrow|(?:next\s+)?(?:monday|tuesday|"
        r"wednesday|thursday|friday|saturday|sunday)|\d{4}-\d{1,2}-\d{1,2})"
        r"\s+(?:at\s+)?"
        r"(?P<start>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
        r"(?:\s*(?:to|-)\s*"
        r"(?P<end>\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?$",
        re.IGNORECASE,
    )
    match = pattern.match(value.strip())
    if not match:
        raise ValueError(
            "Use a format like 'Gym tomorrow 6pm to 7pm'."
        )

    settings = {
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": datetime.now(),
    }
    date_text = match.group("date")
    if date_text.lower().startswith("next "):
        date_text = date_text[5:]

    parsed_date = dateparser.parse(date_text, settings=settings)
    parsed_start = dateparser.parse(match.group("start"), settings=settings)
    parsed_end = (
        dateparser.parse(match.group("end"), settings=settings)
        if match.group("end")
        else parsed_start + timedelta(hours=1)
    )

    if parsed_date is None or parsed_start is None or parsed_end is None:
        raise ValueError("The date or time could not be understood.")

    return {
        "activity": match.group("activity").strip(),
        "date": parsed_date.date(),
        "start_time": parsed_start.time().replace(second=0, microsecond=0),
        "end_time": parsed_end.time().replace(second=0, microsecond=0),
    }


def build_ics(dataframe):
    def escape(value):
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
        )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Personal Scheduler//EN",
        "CALSCALE:GREGORIAN",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for _, event_row in dataframe.iterrows():
        event_date = event_row["Date"]
        start = format_time(event_row["StartTime"])
        end = format_time(event_row["EndTime"])
        if not event_date or not start or not end:
            continue

        date_value = pd.Timestamp(event_date).strftime("%Y%m%d")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{escape(event_row['EventId'])}@personal-scheduler",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{date_value}T{start.replace(':', '')}00",
                f"DTEND:{date_value}T{end.replace(':', '')}00",
                f"SUMMARY:{escape(event_row['Activity'])}",
                f"DESCRIPTION:For {escape(event_row['Name'])}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def save_event(token, event_date, name, activity, start_time, end_time):
    current_df = load_schedule_from_github(token)
    updated_df, created_event = create_event(
        current_df,
        event_date=event_date,
        name=name,
        activity=activity,
        start_time=start_time,
        end_time=end_time,
    )
    ok, status_code, response_text = update_schedule_on_github(
        updated_df,
        token,
        message=f"Create event: {created_event['EventId']}",
    )
    return ok, status_code, response_text


def get_setting(name, default=None):
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except StreamlitSecretNotFoundError:
        return os.getenv(name, default)


def get_next_event(dataframe, current_time):
    upcoming_events = []

    for _, event_row in dataframe.iterrows():
        start = format_time(event_row["StartTime"])
        if not event_row["Date"] or not start:
            continue

        event_start = datetime.combine(
            event_row["Date"],
            datetime.strptime(start, "%H:%M").time(),
            tzinfo=current_time.tzinfo,
        )
        if event_start >= current_time:
            upcoming_events.append((event_start, event_row))

    if not upcoming_events:
        return None

    return min(upcoming_events, key=lambda item: item[0])


@st.fragment(run_every="30s")
def render_next_event_timer(dataframe, app_timezone):
    current_time = datetime.now(app_timezone)
    next_event = get_next_event(dataframe, current_time)

    if next_event is None:
        st.info("No upcoming events.")
        return

    event_start, event_row = next_event
    remaining_seconds = max(0, int((event_start - current_time).total_seconds()))
    days, remainder = divmod(remaining_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    if days:
        countdown = f"{days}d {hours}h {minutes}m"
    elif hours:
        countdown = f"{hours}h {minutes}m {seconds}s"
    else:
        countdown = f"{minutes}m {seconds}s"

    st.metric("Next event", event_row["Activity"], countdown)
    st.caption(
        f"{event_start.strftime('%a, %d %b %Y at %H:%M')} · "
        f"{event_row['Name']}"
    )


st.set_page_config(page_title="Daily Scheduler", layout="centered")
st.title("Daily Scheduler")

token = get_setting("GITHUB_TOKEN")
timezone_name = get_setting("SCHEDULER_TIMEZONE", "UTC")
try:
    app_timezone = ZoneInfo(timezone_name)
except ZoneInfoNotFoundError:
    st.warning(f"Unknown timezone '{timezone_name}'; using UTC.")
    app_timezone = timezone.utc

latest_df = load_schedule_from_github(token)

today_tab, add_tab, calendar_tab, manage_tab = st.tabs(
    ["Today", "Add", "Calendar", "Manage"]
)

with today_tab:
    render_next_event_timer(latest_df, app_timezone)
    st.divider()

    local_today = datetime.now(app_timezone).date()
    today_df = latest_df[latest_df["Date"] == local_today].sort_values(
        by="StartTime"
    )
    if today_df.empty:
        st.info("No events scheduled today.")
    else:
        st.dataframe(
            today_df.fillna(""),
            use_container_width=True,
            hide_index=True,
        )

with add_tab:
    selected_name = st.text_input(
        "Name",
        key="event_name",
    )

    sports_column, school_column, personal_column = st.columns(3)
    if sports_column.button("Sports", use_container_width=True):
        st.session_state["manual_activity"] = "Sports"
    if school_column.button("School", use_container_width=True):
        st.session_state["manual_activity"] = "School"
    if personal_column.button("Personal", use_container_width=True):
        st.session_state["manual_activity"] = "Personal"

    quick_entry = st.text_input(
        "Quick Add",
        placeholder="Gym tomorrow 6pm to 7pm",
    )
    if st.button("Add Quick Entry", use_container_width=True):
        if not token:
            st.error("GITHUB_TOKEN is required to save the event.")
        else:
            try:
                quick_event = parse_quick_entry(quick_entry)
                ok, status_code, response_text = save_event(
                    token,
                    event_date=quick_event["date"],
                    name=selected_name,
                    activity=quick_event["activity"],
                    start_time=quick_event["start_time"],
                    end_time=quick_event["end_time"],
                )
                if ok:
                    st.success("Event created successfully.")
                    st.rerun()
                else:
                    show_github_error(status_code, response_text)
            except requests.RequestException as exc:
                st.error(f"GitHub request failed: {exc}")
            except (ValueError, TypeError) as exc:
                st.error(f"Unable to create event: {exc}")

    st.divider()
    manual_activity = st.text_input("Activity", key="manual_activity")
    manual_date = st.date_input("Date", key="manual_date")
    manual_start_time = st.time_input("Start time", key="manual_start_time")
    manual_end_time = st.time_input("End time", key="manual_end_time")

    if st.button("Add Event", key="add_manual_event", use_container_width=True):
        if not token:
            st.error("GITHUB_TOKEN is required to save the event.")
        else:
            try:
                ok, status_code, response_text = save_event(
                    token,
                    event_date=manual_date,
                    name=selected_name,
                    activity=manual_activity,
                    start_time=manual_start_time,
                    end_time=manual_end_time,
                )
                if ok:
                    st.success("Event created successfully.")
                    st.rerun()
                else:
                    show_github_error(status_code, response_text)
            except requests.RequestException as exc:
                st.error(f"GitHub request failed: {exc}")
            except (ValueError, TypeError) as exc:
                st.error(f"Unable to create event: {exc}")

with calendar_tab:
    sort_order = st.radio(
        "Sort order",
        ["Upcoming first", "Latest first"],
        horizontal=True,
    )
    weekday_filter = st.selectbox(
        "Filter by Weekday",
        [
            "All",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ],
    )
    display_df = latest_df.copy()
    if weekday_filter != "All":
        display_df = display_df[display_df["Weekday"] == weekday_filter]

    display_df = display_df.sort_values(
        by=["Date", "StartTime"],
        ascending=sort_order == "Upcoming first",
        na_position="last",
    ).reset_index(drop=True)
    st.dataframe(
        display_df.fillna(""),
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Download Calendar",
        data=build_ics(display_df),
        file_name="schedule.ics",
        mime="text/calendar",
        use_container_width=True,
    )

with manage_tab:
    delete_df = latest_df
    if delete_df.empty:
        st.info("No events are available to delete.")
    else:
        delete_options = {
            format_event_label(event_row): event_row["EventId"]
            for _, event_row in delete_df.iterrows()
        }
        selected_delete_label = st.selectbox(
            "Select event to delete",
            options=list(delete_options.keys()),
            key="delete_event_selection",
        )

        if st.button(
            "Delete Selected Event",
            key="delete_selected_event",
            use_container_width=True,
        ):
            if not token:
                st.error("GITHUB_TOKEN is required to delete the event.")
            else:
                try:
                    selected_event_id = delete_options[selected_delete_label]
                    current_delete_df = load_schedule_from_github(token)
                    updated_delete_df = current_delete_df[
                        current_delete_df["EventId"] != selected_event_id
                    ].reset_index(drop=True)

                    if len(updated_delete_df) == len(current_delete_df):
                        st.warning("The selected event no longer exists.")
                    else:
                        ok, status_code, response_text = (
                            update_schedule_on_github(
                                updated_delete_df,
                                token,
                                message=f"Delete event: {selected_event_id}",
                            )
                        )
                        if ok:
                            st.success("Event deleted successfully.")
                            st.rerun()
                        else:
                            show_github_error(status_code, response_text)
                except requests.RequestException as exc:
                    st.error(f"GitHub request failed: {exc}")
                except Exception as exc:
                    st.error(f"Unable to delete the event: {exc}")