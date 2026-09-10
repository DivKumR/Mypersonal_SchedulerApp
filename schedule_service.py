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
