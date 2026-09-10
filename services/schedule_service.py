# Existing rows get stable sequential IDs.
# The former Time value becomes StartTime.
# Existing events without an end time default to one hour.
# Back-to-back events are allowed.
# Overlapping events are rejected.


from datetime import date, datetime, time
from typing import Optional

import pandas as pd


COLUMNS = [
"EventId",
"Date",
"Weekday",
"Name",
"Activity",
"StartTime",
"EndTime",
]


def _normalize_date(value) -> Optional[date]:
	if value is None or pd.isna(value):
		return None

	parsed = pd.to_datetime(value, errors="coerce")

	if pd.isna(parsed):
		return None

	return parsed.date()


def _normalize_time(value) -> Optional[time]:
	if value is None or pd.isna(value) or str(value).strip() == "":
		return None

	if isinstance(value, time):
		return value

	parsed = pd.to_datetime(str(value), errors="coerce")

	if pd.isna(parsed):
		return None

	return parsed.time().replace(second=0, microsecond=0)


def format_time(value) -> str:
	normalized = _normalize_time(value)
	return normalized.strftime("%H:%M") if normalized else ""


def _parse_event_id(value) -> Optional[int]:
	if value is None or pd.isna(value):
		return None

	text = str(value).strip()
	if not text:
		return None

	try:
		numeric_value = float(text)
	except ValueError:
		return None

	if not numeric_value.is_integer() or numeric_value <= 0:
		return None

	return int(numeric_value)


def _normalize_event_ids(values: pd.Series) -> pd.Series:
	parsed_ids = []
	reserved_ids = set()

	for value in values:
		parsed_id = _parse_event_id(value)
		if parsed_id is None or parsed_id in reserved_ids:
			parsed_ids.append(None)
		else:
			parsed_ids.append(parsed_id)
			reserved_ids.add(parsed_id)

	next_id = max(reserved_ids, default=0) + 1
	for index, parsed_id in enumerate(parsed_ids):
		if parsed_id is not None:
			continue

		while next_id in reserved_ids:
			next_id += 1
		parsed_ids[index] = next_id
		reserved_ids.add(next_id)
		next_id += 1

	return pd.Series(
		[str(event_id) for event_id in parsed_ids],
		index=values.index,
		dtype="object",
	)


def sanitize_schedule_df(df: Optional[pd.DataFrame]) -> pd.DataFrame:
	if df is None:
		return pd.DataFrame(columns=COLUMNS)

	result = df.copy()

	result = result.loc[
		:, ~result.columns.astype(str).str.lower().str.contains("^unnamed")
	]

	# Migrate the old Time column into StartTime.
	if "StartTime" not in result.columns and "Time" in result.columns:
		result["StartTime"] = result["Time"]

	# Give old events a default one-hour duration.
	if "EndTime" not in result.columns:
		result["EndTime"] = ""

	for column in COLUMNS:
		if column not in result.columns:
			result[column] = ""

	result = result[COLUMNS].copy()

	result["Date"] = result["Date"].apply(_normalize_date)
	result["Weekday"] = result["Date"].apply(
		lambda value: value.strftime("%A") if value else ""
	)

	result["StartTime"] = result["StartTime"].apply(format_time)

	def calculate_end_time(row):
		existing_end = format_time(row["EndTime"])
		if existing_end:
			return existing_end

		start = _normalize_time(row["StartTime"])
		if start is None:
			return ""

		start_datetime = datetime.combine(date.today(), start)
		return (start_datetime + pd.Timedelta(hours=1)).strftime("%H:%M")

	result["EndTime"] = result.apply(calculate_end_time, axis=1)

	result["EventId"] = _normalize_event_ids(result["EventId"])

	return result.reset_index(drop=True)


def get_events(
df: pd.DataFrame,
event_date: Optional[date] = None,
name: Optional[str] = None,
) -> pd.DataFrame:
	result = sanitize_schedule_df(df)

	if event_date is not None:
		result = result[result["Date"] == event_date]

	if name:
		result = result[
			result["Name"].astype(str).str.contains(
				name,
				case=False,
				na=False,
				regex=False,
			)
		]

	return result.sort_values(
		by=["Date", "StartTime"],
		na_position="last",
	).reset_index(drop=True)


def check_conflicts(
df: pd.DataFrame,
event_date: date,
start_time: time,
end_time: time,
exclude_event_id: Optional[str] = None,
) -> pd.DataFrame:
	if end_time <= start_time:
		raise ValueError("EndTime must be later than StartTime.")

	events = get_events(df, event_date=event_date)

	if exclude_event_id:
		events = events[events["EventId"] != exclude_event_id]

	requested_start = datetime.combine(event_date, start_time)
	requested_end = datetime.combine(event_date, end_time)

	conflicting_indexes = []

	for index, row in events.iterrows():
		existing_start_time = _normalize_time(row["StartTime"])
		existing_end_time = _normalize_time(row["EndTime"])

		if existing_start_time is None or existing_end_time is None:
			continue

		existing_start = datetime.combine(event_date, existing_start_time)
		existing_end = datetime.combine(event_date, existing_end_time)

		# Two intervals conflict when each starts before the other ends.
		if requested_start < existing_end and requested_end > existing_start:
			conflicting_indexes.append(index)

	return events.loc[conflicting_indexes].reset_index(drop=True)


def create_event(
df: pd.DataFrame,
event_date: date,
name: str,
activity: str,
start_time: time,
end_time: time,
) -> tuple[pd.DataFrame, dict]:
	if not name.strip():
		raise ValueError("Name is required.")

	if not activity.strip():
		raise ValueError("Activity is required.")

	if end_time <= start_time:
		raise ValueError("EndTime must be later than StartTime.")

	current = sanitize_schedule_df(df)

	conflicts = check_conflicts(
		current,
		event_date=event_date,
		start_time=start_time,
		end_time=end_time,
	)

	if not conflicts.empty:
		conflict_names = ", ".join(
			conflicts["Activity"].astype(str).tolist()
		)
		raise ValueError(f"Schedule conflict with: {conflict_names}")

	numeric_ids = current["EventId"].apply(_parse_event_id).dropna()
	next_event_id = int(numeric_ids.max()) + 1 if not numeric_ids.empty else 1

	event = {
		"EventId": str(next_event_id),
		"Date": event_date,
		"Weekday": event_date.strftime("%A"),
		"Name": name.strip(),
		"Activity": activity.strip(),
		"StartTime": start_time.strftime("%H:%M"),
		"EndTime": end_time.strftime("%H:%M"),
	}

	updated = pd.concat([current, pd.DataFrame([event])], ignore_index=True)
	return sanitize_schedule_df(updated), event