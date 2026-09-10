# Personal Scheduler

A mobile-friendly Streamlit scheduler that stores events in `schedule.csv` on GitHub. It supports conflict detection, quick entry, today's schedule, deletion, and `.ics` calendar export.

## Use the hosted app

1. Open the Streamlit app URL in a phone or desktop browser.
2. Use **Today** to see today's events.
3. Use **Add** to create an event manually or enter a shortcut such as `Gym tomorrow 6pm to 7pm`.
4. Use **Calendar** to browse events and download `schedule.ics` for Apple Calendar, Google Calendar, or Outlook.
5. Use **Manage** to delete an event.

On iPhone or Android, use the browser's **Add to Home Screen** command for app-like access.

## Download and run locally

### 1. Get the project

Clone with Git:

```powershell
git clone https://github.com/DivKumR/Mypersonal_SchedulerApp.git
cd Mypersonal_SchedulerApp
```

Alternatively, download the repository ZIP from GitHub, extract it, and open the extracted folder in a terminal.

### 2. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux, activate it with:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure GitHub access

Create `.streamlit/secrets.toml`:

```toml
GITHUB_TOKEN = "your-github-token"
```

Use a fine-grained GitHub personal access token with **Contents: Read and write** access to this repository. The secrets file is ignored by Git and must never be committed.

### 5. Start the app

```powershell
streamlit run app.py
```

Open the local URL displayed by Streamlit, usually `http://localhost:8501`.

## Deploy to Streamlit Community Cloud

1. Fork or push this repository to your GitHub account.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create an app using this repository, branch, and `app.py` as the entry point.
4. In the app's **Secrets** settings, add:

```toml
GITHUB_TOKEN = "your-github-token"
```

5. Deploy and open the generated `https://...streamlit.app` URL.

The token needs write access because adding and deleting events updates `schedule.csv` through the GitHub API.

## Quick entry format

Supported examples:

```text
Gym tomorrow 6pm to 7pm
Doctor Friday 10am
Meeting next Monday 2pm to 3pm
```

When no end time is supplied, the event lasts one hour. Overlapping events are rejected.

## CSV format

The application expects this header:

```csv
EventId,Date,Weekday,Name,Activity,StartTime,EndTime
```

Do not rename these columns. Existing rows without an ID or end time are normalized when loaded.

## Validate changes

```powershell
python -m py_compile app.py reminder.py services\schedule_service.py services\github_schedule_repository.py
```

The Ollama scheduler agent is not loaded by the Streamlit app, keeping cloud and mobile deployment lightweight.