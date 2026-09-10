# This is a real agent entry point, but it does not give the model direct access to the GitHub token or 
# permission to write the CSV. app.py remains responsible for validating, previewing, and persisting the proposed operation.

import json
import os
from datetime import date
from typing import Any

import dateparser
from ollama import Client

from agent.schemas import (
    AgentAction,
    AgentResponse,
    EventDetails,
)


SYSTEM_PROMPT = """
You are a personal scheduling agent.

Return only JSON matching the supplied schema.

Supported actions:
1. create_event
2. get_events
3. unknown

For create_event, extract:
- date
- name
- activity
- start_time
- end_time

Rules:
- Use ISO dates: YYYY-MM-DD.
- Use 24-hour times: HH:MM:SS.
- Never invent missing values.
- If end_time is missing but start_time exists, set end_time to exactly
one hour after start_time.
- Set requires_confirmation=true only when all create-event fields exist.
- Put missing required field names in missing_fields.
- For read-only listing requests, use get_events and
requires_confirmation=false.
"""


def _safe_json_loads(content: str) -> dict[str, Any]:
    cleaned = content.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]

    if cleaned.startswith("```"):
        cleaned = cleaned[3:]

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    return json.loads(cleaned.strip())


class SchedulerAgent:
    def __init__(self, model: str = "llama3.1:8b"):
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model
        self.client = Client(host=host)

    def invoke(self, user_input: str) -> AgentResponse:
        if not user_input or not user_input.strip():
            return AgentResponse(
                action=AgentAction.UNKNOWN,
                message="Enter a scheduling request.",
                missing_fields=["request"],
            )

        prompt = (
            f"Today is {date.today().isoformat()}.\n"
            f"User request: {user_input.strip()}"
        )

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                format=AgentResponse.model_json_schema(),
                options={"temperature": 0},
            )

            content = response["message"]["content"]
            payload = _safe_json_loads(content)
            return AgentResponse.model_validate(payload)

        except Exception as exc:
            return AgentResponse(
                action=AgentAction.UNKNOWN,
                message=f"Agent could not process the request: {exc}",
            )


scheduler_agent = SchedulerAgent()