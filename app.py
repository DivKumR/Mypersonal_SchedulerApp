import base64
from datetime import date, time
from io import StringIO

import pandas as pd
import requests
import streamlit as st

from agent.schemas import AgentAction
from agent.scheduler_agent import scheduler_agent
from services.schedule_service import (
    COLUMNS,
    check_conflicts,
    create_event,
    format_time,
    get_events,
    sanitize_schedule_df,
)


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


st.set_page_config(page_title="Daily Scheduler", layout="centered")
st.title("Daily Scheduler")

token = st.secrets.get("GITHUB_TOKEN", None)
latest_df = load_schedule_from_github(token)

st.subheader("Schedule")
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
    na_position="last",
).reset_index(drop=True)
st.dataframe(display_df.fillna(""), use_container_width=True, hide_index=True)


st.subheader("Add Event Manually")
manual_name = st.text_input("Name", key="manual_name")
manual_activity = st.text_input("Activity", key="manual_activity")
manual_date = st.date_input("Date", key="manual_date")
manual_start_time = st.time_input("Start time", key="manual_start_time")
manual_end_time = st.time_input("End time", key="manual_end_time")

if st.button("Add Event", key="add_manual_event"):
    if not token:
        st.error("GITHUB_TOKEN is required to save the event.")
    else:
        try:
            current_df = load_schedule_from_github(token)
            updated_df, created_event = create_event(
                current_df,
                event_date=manual_date,
                name=manual_name,
                activity=manual_activity,
                start_time=manual_start_time,
                end_time=manual_end_time,
            )
            st.write("Preview of the schedule to be uploaded:")
            st.dataframe(
                updated_df.fillna(""),
                use_container_width=True,
                hide_index=True,
            )

            ok, status_code, response_text = update_schedule_on_github(
                updated_df,
                token,
                message=f"Create event: {created_event['EventId']}",
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


st.subheader("Scheduling Agent")
agent_request = st.text_input(
    "Scheduling request",
    placeholder="Schedule a project review tomorrow from 10:00 to 11:00",
)

if st.button("Ask Scheduler Agent", key="ask_scheduler_agent"):
    agent_response = scheduler_agent.invoke(agent_request)
    st.info(agent_response.message)

    if agent_response.action == AgentAction.GET_EVENTS:
        event_date = agent_response.event.date if agent_response.event else None
        event_name = agent_response.event.name if agent_response.event else None
        matching_events = get_events(
            latest_df,
            event_date=event_date,
            name=event_name,
        )
        st.dataframe(
            matching_events.fillna(""),
            use_container_width=True,
            hide_index=True,
        )
    elif (
        agent_response.action == AgentAction.CREATE_EVENT
        and agent_response.requires_confirmation
        and agent_response.event is not None
    ):
        event = agent_response.event
        st.session_state["pending_agent_event"] = {
            "date": event.date.isoformat(),
            "name": event.name,
            "activity": event.activity,
            "start_time": event.start_time.isoformat(),
            "end_time": event.end_time.isoformat(),
        }
    elif agent_response.missing_fields:
        st.warning("Missing: " + ", ".join(agent_response.missing_fields))


pending_agent_event = st.session_state.get("pending_agent_event")
if pending_agent_event:
    st.write("Proposed event:")
    st.json(pending_agent_event)
    confirm_column, cancel_column = st.columns(2)

    with confirm_column:
        if st.button("Confirm Agent Event", key="confirm_agent_event"):
            if not token:
                st.error("GITHUB_TOKEN is required to save the event.")
            else:
                try:
                    pending_date = date.fromisoformat(
                        pending_agent_event["date"]
                    )
                    pending_start_time = time.fromisoformat(
                        pending_agent_event["start_time"]
                    )
                    pending_end_time = time.fromisoformat(
                        pending_agent_event["end_time"]
                    )
                    current_df = load_schedule_from_github(token)
                    conflicts = check_conflicts(
                        current_df,
                        event_date=pending_date,
                        start_time=pending_start_time,
                        end_time=pending_end_time,
                    )

                    if not conflicts.empty:
                        st.error(
                            "The schedule changed and this time now "
                            "conflicts with another event."
                        )
                        st.dataframe(
                            conflicts.fillna(""),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        updated_df, created_event = create_event(
                            current_df,
                            event_date=pending_date,
                            name=pending_agent_event["name"],
                            activity=pending_agent_event["activity"],
                            start_time=pending_start_time,
                            end_time=pending_end_time,
                        )
                        ok, status_code, response_text = (
                            update_schedule_on_github(
                                updated_df,
                                token,
                                message=(
                                    "Create event via scheduler agent: "
                                    f"{created_event['EventId']}"
                                ),
                            )
                        )

                        if ok:
                            del st.session_state["pending_agent_event"]
                            st.success("Agent event created successfully.")
                            st.rerun()
                        else:
                            show_github_error(status_code, response_text)
                except (ValueError, TypeError, KeyError) as exc:
                    st.error(f"Invalid pending agent event: {exc}")
                except requests.RequestException as exc:
                    st.error(f"GitHub request failed: {exc}")
                except Exception as exc:
                    st.error(f"Unable to create the agent event: {exc}")

    with cancel_column:
        if st.button("Cancel Agent Event", key="cancel_agent_event"):
            del st.session_state["pending_agent_event"]
            st.info("Proposed event canceled.")
            st.rerun()


st.subheader("Delete Event")
delete_df = load_schedule_from_github(token)

if delete_df.empty:
    st.info("No events are available to delete.")
else:
    delete_options = {}
    for _, event_row in delete_df.iterrows():
        event_label = format_event_label(event_row)
        delete_options[event_label] = event_row["EventId"]

    selected_delete_label = st.selectbox(
        "Select event to delete",
        options=list(delete_options.keys()),
        key="delete_event_selection",
    )

    if st.button("Delete Selected Event", key="delete_selected_event"):
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
                    st.write("Preview of the schedule after deletion:")
                    st.dataframe(
                        updated_delete_df.fillna(""),
                        use_container_width=True,
                        hide_index=True,
                    )
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